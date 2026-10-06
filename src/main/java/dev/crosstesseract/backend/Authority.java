package dev.crosstesseract.backend;

import dev.crosstesseract.core.*;
import dev.crosstesseract.core.Models.*;
import java.io.IOException;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import static dev.crosstesseract.backend.Sql.*;
import static dev.crosstesseract.core.DomainException.require;

/** All methods are blocking and belong exclusively on bounded backend workers. */
public final class Authority implements AutoCloseable {
    public static final int LEASE_SECONDS=12;
    private final BackendConfig config;
    private final Sql db;
    private volatile Session session;
    public Authority(BackendConfig config) { this.config=config; db=new Sql(config); }
    public Sql database() { return db; }
    public Session session() { return Objects.requireNonNull(session,"not joined"); }
    private String cluster() { return config.cluster(); }

    public Session join(UUID world,UUID boot,Set<String> capabilities) throws SQLException,IOException {
        Migrations.apply(db);
        session=db.transaction(c->{
            update(c,"INSERT IGNORE INTO ct_clusters(cluster_id,quota_limit,max_channels,max_endpoints) VALUES(?,?,?,?)",cluster(),config.quota(),config.maxChannels(),config.maxEndpoints());
            var policy=one(c,"SELECT * FROM ct_clusters WHERE cluster_id=? FOR UPDATE",cluster());
            require(num(policy,"quota_limit")==config.quota() && num(policy,"max_channels")==config.maxChannels() && num(policy,"max_endpoints")==config.maxEndpoints(),"policy_mismatch");
            var previous=one(c,"SELECT *,lease_until>CURRENT_TIMESTAMP(6) AS live FROM ct_servers WHERE cluster_id=? AND server_id=? FOR UPDATE",cluster(),config.server());
            long epoch=1;
            boolean recovery=false;
            if(previous!=null) {
                require(num(previous,"live")==0,"duplicate_server_id");
                require(world.equals(uuid(previous,"world_id")),"world_id_mismatch");
                epoch=Math.addExact(num(previous,"fencing_epoch"),1);
                recovery=!Boolean.TRUE.equals(previous.get("clean_stop")) && !"STOPPED".equals(str(previous,"status"));
            }
            String caps=String.join(",",new TreeSet<>(capabilities));
            require(caps.length()<=2048,"capabilities_too_large");
            update(c,"INSERT INTO ct_servers(cluster_id,server_id,world_id,session_id,fencing_epoch,lease_until,protocol_version,format_version,capabilities,status,clean_stop) VALUES(?,?,?,?,?,TIMESTAMPADD(SECOND,12,CURRENT_TIMESTAMP(6)),?,?,?,'ONLINE',FALSE) ON DUPLICATE KEY UPDATE session_id=VALUES(session_id),fencing_epoch=VALUES(fencing_epoch),lease_until=VALUES(lease_until),protocol_version=VALUES(protocol_version),format_version=VALUES(format_version),capabilities=VALUES(capabilities),status='ONLINE',clean_stop=FALSE",cluster(),config.server(),world,boot,epoch,Protocol.VERSION,Protocol.FORMAT,caps);
            if(recovery) {
                update(c,"UPDATE ct_endpoints SET state='QUARANTINED',pause_reason='unclean_external_io' WHERE cluster_id=? AND server_id=? AND state='ACTIVE'",cluster(),config.server());
                update(c,"UPDATE ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id SET g.state='PAUSED',g.reason='unclean_external_io' WHERE g.cluster_id=? AND e.server_id=? AND g.desired=TRUE",cluster(),config.server());
                audit(c,null,"UNCLEAN_BOOT",null,"External inventories and world saves are not atomic; endpoints quarantined");
            }
            return new Session(cluster(),config.server(),world,boot,epoch,num(policy,"recovery_generation"),recovery);
        });
        return session;
    }
    private void fenced(Connection c) throws SQLException {
        Session s=session();
        var row=one(c,"SELECT fencing_epoch,session_id,lease_until>CURRENT_TIMESTAMP(6) AS live FROM ct_servers WHERE cluster_id=? AND server_id=? FOR SHARE",cluster(),s.server());
        require(row!=null && num(row,"live")==1 && num(row,"fencing_epoch")==s.epoch() && s.boot().equals(uuid(row,"session_id")),"session_fenced");
        var policy=one(c,"SELECT recovery_generation FROM ct_clusters WHERE cluster_id=? FOR SHARE",cluster());
        require(num(policy,"recovery_generation")==s.generation(),"backup_generation_conflict");
    }
    public void heartbeat() throws SQLException {
        db.transaction(c->{heartbeat(c);return null;});
    }
    private void heartbeat(Connection c) throws SQLException {
            // An expired session cannot renew itself; it must rejoin with a new fenced epoch.
            fenced(c);
            update(c,"UPDATE ct_servers SET lease_until=TIMESTAMPADD(SECOND,12,CURRENT_TIMESTAMP(6)) WHERE cluster_id=? AND server_id=? AND fencing_epoch=? AND session_id=?",cluster(),session().server(),session().epoch(),session().boot());
            update(c,"UPDATE ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id SET g.runtime_until=TIMESTAMPADD(SECOND,10,CURRENT_TIMESTAMP(6)) WHERE g.cluster_id=? AND e.server_id=? AND g.runtime_session=? AND g.runtime_epoch=? AND g.desired=TRUE AND g.state='ACTIVE' AND e.state='ACTIVE'",cluster(),session().server(),session().boot(),session().epoch());
    }
    public record MaintenanceState(List<Grant> grants,int quota){public MaintenanceState{grants=List.copyOf(grants);}}
    /** One bounded control transaction; permission scans and history are separate lanes. */
    public MaintenanceState maintainState() throws SQLException {
        return db.transaction(c->{heartbeat(c);
            var grants=query(c,"SELECT g.*,e.server_id,e.world_id,e.device_owner,e.channel_id,e.dimension_id,e.pos_x,e.pos_y,e.pos_z,e.version,e.checkpoint,e.pause_reason,e.state AS endpoint_state FROM ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id WHERE g.cluster_id=? AND e.server_id=? AND e.world_id=? ORDER BY g.created_at LIMIT 4096",cluster(),session().server(),session().world()).stream().map(r->grant(r,endpointMap(r))).toList();
            int quota=(int)num(one(c,"SELECT quota_limit FROM ct_clusters WHERE cluster_id=?",cluster()),"quota_limit");
            return new MaintenanceState(grants,quota);
        });
    }
    public void stopClean() throws SQLException {
        db.transaction(c->{
            fenced(c);
            update(c,"UPDATE ct_servers SET status='STOPPED',clean_stop=TRUE,lease_until=CURRENT_TIMESTAMP(6) WHERE cluster_id=? AND server_id=? AND fencing_epoch=?",cluster(),session().server(),session().epoch());
            return null;
        });
    }
    private Map<String,Object> channelRow(Connection c,UUID channel,UUID actor,int permission,boolean allowFrozen) throws SQLException {
        var row=one(c,"SELECT * FROM ct_channels WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),channel);
        require(row!=null && !"DELETED".equals(str(row,"status")),"channel_not_found");
        require(allowFrozen || "ACTIVE".equals(str(row,"status")),"channel_frozen");
        int mask=Protocol.OWNER;
        if(!actor.equals(uuid(row,"owner_uuid"))) {
            var member=one(c,"SELECT permissions FROM ct_members WHERE cluster_id=? AND channel_id=? AND player_uuid=?",cluster(),channel,actor);
            mask=member==null?0:(int)num(member,"permissions");
        }
        require(Protocol.permits(mask,permission),"forbidden");
        row.put("permissions",mask); return row;
    }
    private static void version(Map<String,Object> row,long expected) { require(num(row,"version")==expected,"stale_version"); }
    private void changed(Connection c,UUID channel) throws SQLException {
        update(c,"UPDATE ct_channels SET version=version+1,updated_at=CURRENT_TIMESTAMP(6) WHERE cluster_id=? AND channel_id=?",cluster(),channel);
        event(c,"CHANNEL_CHANGED",channel,null);
    }
    private void guard(Connection c,UUID player) throws SQLException {
        update(c,"INSERT IGNORE INTO ct_player_guards(cluster_id,player_uuid) VALUES(?,?)",cluster(),player);
        one(c,"SELECT player_uuid FROM ct_player_guards WHERE cluster_id=? AND player_uuid=? FOR UPDATE",cluster(),player);
    }
    public UUID createChannel(UUID player,String name,UUID request) throws SQLException {
        require(name!=null && !name.isBlank() && name.length()<=64 && name.codePoints().noneMatch(Character::isISOControl),"invalid_name");
        return db.transaction(c->{
            fenced(c); guard(c,player);
            var op=one(c,"SELECT * FROM ct_operations WHERE cluster_id=? AND operation_id=?",cluster(),request);
            if(op!=null) { require(player.equals(uuid(op,"actor_uuid")) && "CREATE_CHANNEL".equals(str(op,"kind")),"idempotency_conflict"); return uuid(op,"subject_id"); }
            BusinessIds.fresh(request);
            long count=num(one(c,"SELECT COUNT(*) AS n FROM ct_channels WHERE cluster_id=? AND owner_uuid=? AND status<>'DELETED'",cluster(),player),"n");
            long limit=num(one(c,"SELECT max_channels FROM ct_clusters WHERE cluster_id=?",cluster()),"max_channels");
            require(count<limit,"channel_limit");
            UUID id=UUID.randomUUID();
            update(c,"INSERT INTO ct_channels(cluster_id,channel_id,owner_uuid,name) VALUES(?,?,?,?)",cluster(),id,player,name);
            operation(c,request,player,"CREATE_CHANNEL",id,"OK"); event(c,"CHANNEL_CHANGED",id,null); audit(c,player,"CREATE_CHANNEL",id,name); return id;
        });
    }
    public List<Channel> channels(UUID player) throws SQLException {
        return db.transaction(c->{ fenced(c); return query(c,"SELECT c.*,IF(c.owner_uuid=?,31,m.permissions) AS permissions FROM ct_channels c LEFT JOIN ct_members m ON m.cluster_id=c.cluster_id AND m.channel_id=c.channel_id AND m.player_uuid=? WHERE c.cluster_id=? AND c.status<>'DELETED' AND (c.owner_uuid=? OR m.player_uuid IS NOT NULL) ORDER BY c.created_at LIMIT 256",player,player,cluster(),player).stream().map(Authority::channel).toList(); });
    }
    public Channel authorize(UUID actor,UUID channel,int permission) throws SQLException {
        return db.transaction(c->{fenced(c); return channel(channelRow(c,channel,actor,permission,false));});
    }
    public void rename(UUID actor,UUID channel,long expected,String name) throws SQLException {
        require(name!=null && !name.isBlank() && name.length()<=64 && name.codePoints().noneMatch(Character::isISOControl),"invalid_name");
        db.transaction(c->{fenced(c); version(channelRow(c,channel,actor,Protocol.SETTINGS,false),expected); update(c,"UPDATE ct_channels SET name=? WHERE cluster_id=? AND channel_id=?",name,cluster(),channel); changed(c,channel); audit(c,actor,"RENAME",channel,name); return null;});
    }
    public UUID invite(UUID actor,UUID channel,long expected,UUID target,boolean transfer,UUID request) throws SQLException {
        return db.transaction(c->{
            fenced(c); var row=channelRow(c,channel,actor,Protocol.MEMBERS,false); version(row,expected);
            if(transfer) require(actor.equals(uuid(row,"owner_uuid")),"owner_required");
            require(!target.equals(uuid(row,"owner_uuid")),"already_owner");
            if(transfer) require(one(c,"SELECT player_uuid FROM ct_members WHERE cluster_id=? AND channel_id=? AND player_uuid=?",cluster(),channel,target)!=null,"target_not_member");
            var old=one(c,"SELECT * FROM ct_invites WHERE cluster_id=? AND invite_id=?",cluster(),request);
            if(old!=null) { require(target.equals(uuid(old,"target_uuid")) && channel.equals(uuid(old,"channel_id")) && actor.equals(uuid(old,"issued_by")),"idempotency_conflict"); return request; }
            BusinessIds.fresh(request);
            long pending=num(one(c,"SELECT COUNT(*) AS n FROM ct_invites WHERE cluster_id=? AND channel_id=? AND state='PENDING' AND expires_at>CURRENT_TIMESTAMP(6)",cluster(),channel),"n");
            require(pending<256,"invite_limit");
            update(c,"INSERT INTO ct_invites(cluster_id,invite_id,channel_id,target_uuid,issued_by,kind,channel_version,expires_at) VALUES(?,?,?,?,?,?,?,TIMESTAMPADD(DAY,7,CURRENT_TIMESTAMP(6)))",cluster(),request,channel,target,actor,transfer?"TRANSFER":"JOIN",expected);
            event(c,"INVITE_CHANGED",request,null); audit(c,actor,transfer?"OFFER_TRANSFER":"INVITE",channel,target.toString()); return request;
        });
    }
    public List<Invitation> invitations(UUID target) throws SQLException {
        return db.transaction(c->{fenced(c); update(c,"UPDATE ct_invites SET state='EXPIRED' WHERE cluster_id=? AND (target_uuid=? OR issued_by=?) AND state='PENDING' AND expires_at<=CURRENT_TIMESTAMP(6)",cluster(),target,target); return query(c,"SELECT * FROM ct_invites WHERE cluster_id=? AND (target_uuid=? OR issued_by=?) AND state='PENDING' ORDER BY created_at LIMIT 64",cluster(),target,target).stream().map(r->new Invitation(uuid(r,"invite_id"),uuid(r,"channel_id"),uuid(r,"target_uuid"),str(r,"kind"),str(r,"state"),((Timestamp)r.get("expires_at")).toInstant())).toList(); });
    }
    public void answerInvitation(UUID player,UUID invitation,boolean accept) throws SQLException {
        db.transaction(c->{
            fenced(c);
            // Lock channel before invitation to use the same order as invite/revoke.
            var lookup=one(c,"SELECT channel_id FROM ct_invites WHERE cluster_id=? AND invite_id=?",cluster(),invitation); require(lookup!=null,"invite_not_found");
            UUID id=uuid(lookup,"channel_id");
            var channel=one(c,"SELECT * FROM ct_channels WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),id);
            var inv=one(c,"SELECT *,expires_at>CURRENT_TIMESTAMP(6) AS valid FROM ct_invites WHERE cluster_id=? AND invite_id=? FOR UPDATE",cluster(),invitation);
            require(player.equals(uuid(inv,"target_uuid")),"forbidden");
            if("ACCEPTED".equals(str(inv,"state")) && accept || "DECLINED".equals(str(inv,"state")) && !accept) return null;
            require("PENDING".equals(str(inv,"state")) && num(inv,"valid")==1,"invite_expired");
            require("ACTIVE".equals(str(channel,"status")),"channel_frozen");
            require(uuid(inv,"issued_by").equals(uuid(channel,"owner_uuid")),"invite_revoked");
            if(accept) {
                if("TRANSFER".equals(str(inv,"kind"))) {
                    version(channel,num(inv,"channel_version"));
                    require(one(c,"SELECT player_uuid FROM ct_members WHERE cluster_id=? AND channel_id=? AND player_uuid=?",cluster(),id,player)!=null,"target_not_member");
                    UUID former=uuid(channel,"owner_uuid");
                    update(c,"INSERT INTO ct_members(cluster_id,channel_id,player_uuid,permissions) VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE permissions=VALUES(permissions)",cluster(),id,former,Protocol.MEMBER);
                    update(c,"DELETE FROM ct_members WHERE cluster_id=? AND channel_id=? AND player_uuid=?",cluster(),id,player);
                    update(c,"UPDATE ct_channels SET owner_uuid=? WHERE cluster_id=? AND channel_id=?",player,cluster(),id);
                    update(c,"UPDATE ct_invites SET state='REVOKED' WHERE cluster_id=? AND channel_id=? AND state='PENDING' AND invite_id<>?",cluster(),id,invitation);
                } else update(c,"INSERT IGNORE INTO ct_members(cluster_id,channel_id,player_uuid,permissions) VALUES(?,?,?,?)",cluster(),id,player,Protocol.MEMBER);
                changed(c,id);
            }
            update(c,"UPDATE ct_invites SET state=? WHERE cluster_id=? AND invite_id=?",accept?"ACCEPTED":"DECLINED",cluster(),invitation);
            audit(c,player,accept?"ACCEPT_INVITE":"DECLINE_INVITE",id,invitation.toString()); return null;
        });
    }
    public void revokeInvitation(UUID actor,UUID invitation) throws SQLException {
        db.transaction(c->{fenced(c); var inv=one(c,"SELECT * FROM ct_invites WHERE cluster_id=? AND invite_id=?",cluster(),invitation); require(inv!=null,"invite_not_found"); UUID id=uuid(inv,"channel_id"); channelRow(c,id,actor,Protocol.MEMBERS,false); update(c,"UPDATE ct_invites SET state='REVOKED' WHERE cluster_id=? AND invite_id=? AND state='PENDING'",cluster(),invitation); audit(c,actor,"REVOKE_INVITE",id,invitation.toString()); return null;});
    }
    public List<UUID> members(UUID actor,UUID channel) throws SQLException {
        return db.transaction(c->{fenced(c); channelRow(c,channel,actor,Protocol.VIEW,true); return query(c,"SELECT player_uuid FROM ct_members WHERE cluster_id=? AND channel_id=? ORDER BY joined_at LIMIT 512",cluster(),channel).stream().map(r->uuid(r,"player_uuid")).toList();});
    }
    public void removeMember(UUID actor,UUID channel,long expected,UUID target) throws SQLException {
        db.transaction(c->{
            fenced(c); var row=channelRow(c,channel,actor,actor.equals(target)?Protocol.VIEW:Protocol.MEMBERS,false); version(row,expected);
            require(!uuid(row,"owner_uuid").equals(target),"owner_cannot_leave");
            update(c,"DELETE FROM ct_members WHERE cluster_id=? AND channel_id=? AND player_uuid=?",cluster(),channel,target);
            update(c,"UPDATE ct_invites SET state='REVOKED' WHERE cluster_id=? AND channel_id=? AND target_uuid=? AND state='PENDING'",cluster(),channel,target);
            update(c,"DELETE d FROM ct_demands d JOIN ct_endpoints e ON e.cluster_id=d.cluster_id AND e.endpoint_id=d.endpoint_id WHERE e.cluster_id=? AND e.channel_id=? AND e.device_owner=?",cluster(),channel,target);
            changed(c,channel); audit(c,actor,"REMOVE_MEMBER",channel,target.toString()); return null;
        });
    }
    public void permissions(UUID actor,UUID channel,long expected,UUID target,int mask) throws SQLException {
        require(mask>=0 && mask<=Protocol.MEMBER,"invalid_permissions");
        db.transaction(c->{fenced(c); var row=channelRow(c,channel,actor,Protocol.MEMBERS,false); version(row,expected); require(actor.equals(uuid(row,"owner_uuid")),"owner_required"); require(!target.equals(actor),"already_owner"); require(update(c,"UPDATE ct_members SET permissions=? WHERE cluster_id=? AND channel_id=? AND player_uuid=?",mask,cluster(),channel,target)==1,"member_not_found"); changed(c,channel); audit(c,actor,"PERMISSIONS",channel,target+":"+mask); return null;});
    }
    public void freeze(UUID actor,UUID channel,long expected) throws SQLException {
        db.transaction(c->{fenced(c); var row=channelRow(c,channel,actor,Protocol.SETTINGS,true); version(row,expected); require(actor.equals(uuid(row,"owner_uuid")),"owner_required"); update(c,"UPDATE ct_channels SET status='FROZEN' WHERE cluster_id=? AND channel_id=?",cluster(),channel); update(c,"DELETE FROM ct_demands WHERE cluster_id=? AND channel_id=?",cluster(),channel); changed(c,channel); audit(c,actor,"FREEZE_CHANNEL",channel,""); return null;});
    }
    public void deleteChannel(UUID actor,UUID channel,long expected) throws SQLException {
        db.transaction(c->{
            fenced(c); var row=channelRow(c,channel,actor,Protocol.SETTINGS,true); version(row,expected); require(actor.equals(uuid(row,"owner_uuid")),"owner_required"); require("FROZEN".equals(str(row,"status")),"freeze_first");
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=? AND amount>0",cluster(),channel),"n")==0,"channel_not_empty");
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND channel_id=? AND kind='ALLOCATE' AND remaining>0",cluster(),channel),"n")==0,"channel_not_empty");
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_endpoints WHERE cluster_id=? AND channel_id=?",cluster(),channel),"n")==0,"endpoints_bound");
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=? AND microjoules>0",cluster(),channel),"n")==0,"channel_not_empty");
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_heat_exchanges WHERE cluster_id=? AND channel_id=? AND state='PREPARED'",cluster(),channel),"n")==0,"channel_not_empty");
            update(c,"UPDATE ct_channels SET status='DELETED' WHERE cluster_id=? AND channel_id=?",cluster(),channel); update(c,"UPDATE ct_invites SET state='REVOKED' WHERE cluster_id=? AND channel_id=? AND state='PENDING'",cluster(),channel); changed(c,channel); audit(c,actor,"DELETE_CHANNEL",channel,"tombstone retained"); return null;
        });
    }
    public Endpoint registerEndpoint(Endpoint endpoint,long savedCheckpoint) throws SQLException {
        require(endpoint.server().equals(config.server()) && endpoint.world().equals(session().world()),"world_id_mismatch");
        require(endpoint.dimension().matches("[a-z0-9_]+:[a-z0-9_/.-]+") && endpoint.dimension().length()<=128,"invalid_dimension");
        return db.transaction(c->{
            fenced(c);
            var old=one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint.id());
            if(old==null) {
                require(one(c,"SELECT endpoint_id FROM ct_endpoints WHERE cluster_id=? AND server_id=? AND world_id=? AND dimension_id=? AND pos_x=? AND pos_y=? AND pos_z=? AND state<>'RETIRED' FOR UPDATE",cluster(),endpoint.server(),endpoint.world(),endpoint.dimension(),endpoint.x(),endpoint.y(),endpoint.z())==null,"location_sealed");
                update(c,"INSERT INTO ct_endpoints(cluster_id,endpoint_id,server_id,world_id,device_owner,dimension_id,pos_x,pos_y,pos_z,recovery_generation,last_epoch) VALUES(?,?,?,?,?,?,?,?,?,?,?)",cluster(),endpoint.id(),endpoint.server(),endpoint.world(),endpoint.owner(),endpoint.dimension(),endpoint.x(),endpoint.y(),endpoint.z(),session().generation(),session().epoch());
            } else {
                require(endpoint.server().equals(str(old,"server_id")) && endpoint.world().equals(uuid(old,"world_id")) && endpoint.owner().equals(uuid(old,"device_owner")) && endpoint.dimension().equals(str(old,"dimension_id")) && endpoint.x()==num(old,"pos_x") && endpoint.y()==num(old,"pos_y") && endpoint.z()==num(old,"pos_z"),"cloned_endpoint");
                require(num(old,"recovery_generation")==session().generation(),"backup_generation_conflict");
                if(savedCheckpoint<num(old,"checkpoint")) {
                    update(c,"UPDATE ct_endpoints SET state='QUARANTINED',pause_reason='world_checkpoint_behind' WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint.id());
                    quarantine(c,endpoint.id(),null,"world_checkpoint_behind","Saved chunk checkpoint is older than committed endpoint checkpoint");
                }
                update(c,"UPDATE ct_endpoints SET last_epoch=?,last_seen=CURRENT_TIMESTAMP(6) WHERE cluster_id=? AND endpoint_id=?",session().epoch(),cluster(),endpoint.id());
            }
            return endpoint(one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint.id()));
        });
    }
    public Endpoint endpoint(UUID id) throws SQLException { return db.transaction(c->{fenced(c); var r=one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),id); require(r!=null,"endpoint_not_found"); return endpoint(r);}); }
    public List<Endpoint> endpoints(UUID actor,UUID channel) throws SQLException {
        return db.transaction(c->{fenced(c); channelRow(c,channel,actor,Protocol.VIEW,true); return query(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND channel_id=? ORDER BY server_id,dimension_id,pos_x,pos_z LIMIT 256",cluster(),channel).stream().map(Authority::endpoint).toList();});
    }
    private Map<String,Object> localEndpoint(Connection c,UUID id,boolean active) throws SQLException {
        var e=one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),id);
        require(e!=null,"endpoint_not_found");
        require(session().server().equals(str(e,"server_id")) && session().world().equals(uuid(e,"world_id")) && session().epoch()==num(e,"last_epoch"),"endpoint_fenced");
        require(session().generation()==num(e,"recovery_generation"),"backup_generation_conflict");
        if(active) require("ACTIVE".equals(str(e,"state")),"endpoint_paused"); return e;
    }
    public Endpoint bind(UUID actor,UUID id,long expected,UUID channel) throws SQLException {
        return db.transaction(c->{
            fenced(c); if(channel!=null) channelRow(c,channel,actor,Protocol.VIEW,false);
            var e=localEndpoint(c,id,true); require(actor.equals(uuid(e,"device_owner")),"device_owner_required"); version(e,expected);
            if(Objects.equals(channel,uuid(e,"channel_id"))) return endpoint(e);
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='ALLOCATE' AND remaining>0",cluster(),id),"n")==0,"endpoint_not_empty");
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_heat_exchanges WHERE cluster_id=? AND endpoint_id=? AND state='PREPARED'",cluster(),id),"n")==0,"heat_exchange_pending");
            if(channel!=null) {
                long limit=num(one(c,"SELECT max_endpoints FROM ct_clusters WHERE cluster_id=?",cluster()),"max_endpoints");
                require(num(one(c,"SELECT COUNT(*) AS n FROM ct_endpoints WHERE cluster_id=? AND channel_id=?",cluster(),channel),"n")<limit,"endpoint_limit");
            }
            update(c,"DELETE FROM ct_demands WHERE cluster_id=? AND endpoint_id=?",cluster(),id);
            update(c,"UPDATE ct_stock_requests SET state='CANCELLED' WHERE cluster_id=? AND endpoint_id=? AND state IN ('PENDING','PARTIAL')",cluster(),id);
            update(c,"UPDATE ct_endpoints SET channel_id=?,version=version+1 WHERE cluster_id=? AND endpoint_id=?",channel,cluster(),id); event(c,"ENDPOINT_CHANGED",id,session().server()); audit(c,actor,"BIND_ENDPOINT",id,Objects.toString(channel,"unbound")); return endpoint(one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),id));
        });
    }
    public void sealEndpoint(UUID id,String reason) throws SQLException {
        db.transaction(c->{fenced(c); localEndpoint(c,id,false); update(c,"UPDATE ct_endpoints SET state='SEALED',pause_reason=?,version=version+1 WHERE cluster_id=? AND endpoint_id=?",reason,cluster(),id); update(c,"UPDATE ct_chunk_grants SET state='REVOKING',desired=FALSE,reason=? WHERE cluster_id=? AND endpoint_id=?",reason,cluster(),id); update(c,"DELETE FROM ct_demands WHERE cluster_id=? AND endpoint_id=?",cluster(),id); audit(c,null,"SEAL_ENDPOINT",id,reason); return null;});
    }
    public Grant reserveChunk(UUID actor,UUID endpoint,UUID request,boolean admin) throws SQLException {
        return db.transaction(c->{
            fenced(c); var e=localEndpoint(c,endpoint,true); UUID owner=uuid(e,"device_owner"); require(admin || actor.equals(owner),"device_owner_required");
            var policy=one(c,"SELECT * FROM ct_clusters WHERE cluster_id=? FOR SHARE",cluster()); guard(c,owner);
            var previous=one(c,"SELECT * FROM ct_operations WHERE cluster_id=? AND operation_id=?",cluster(),request);
            if(previous!=null) { require(owner.equals(uuid(previous,"actor_uuid")) && endpoint.equals(uuid(previous,"subject_id")) && "CHUNK_ON".equals(str(previous,"kind")),"idempotency_conflict"); }
            var existing=one(c,"SELECT * FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint);
            if(existing!=null) { require(!"REVOKING".equals(str(existing,"state")),"revocation_pending"); return grant(existing,e); }
            require(previous==null,"operation_completed");
            int max=(int)num(policy,"quota_limit");
            BusinessIds.fresh(request);
            Set<Integer> slots=new HashSet<>(); query(c,"SELECT slot_no FROM ct_chunk_grants WHERE cluster_id=? AND player_uuid=? FOR UPDATE",cluster(),owner).forEach(r->slots.add((int)num(r,"slot_no")));
            int slot=0; while(slot<max && slots.contains(slot)) slot++; require(slot<max,"quota_exhausted");
            update(c,"INSERT INTO ct_chunk_grants(cluster_id,player_uuid,slot_no,endpoint_id,request_id,state,policy_version) VALUES(?,?,?,?,?,'RESERVING',?)",cluster(),owner,slot,endpoint,request,num(policy,"policy_version"));
            operation(c,request,owner,"CHUNK_ON",endpoint,"RESERVED"); audit(c,actor,"CHUNK_RESERVED",endpoint,"owner="+owner+",slot="+slot); return grant(one(c,"SELECT * FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint),e);
        });
    }
    public void confirmChunk(UUID endpoint,boolean installed) throws SQLException {
        db.transaction(c->{fenced(c); var e=localEndpoint(c,endpoint,false); guard(c,uuid(e,"device_owner")); var g=one(c,"SELECT * FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint); require(g!=null,"grant_not_found"); require(Boolean.TRUE.equals(g.get("desired")) && !"REVOKING".equals(str(g,"state")),"revocation_pending"); if(installed) update(c,"UPDATE ct_chunk_grants SET state='ACTIVE',runtime_session=?,runtime_epoch=?,runtime_until=TIMESTAMPADD(SECOND,10,CURRENT_TIMESTAMP(6)),reason='' WHERE cluster_id=? AND endpoint_id=?",session().boot(),session().epoch(),cluster(),endpoint); else { update(c,"DELETE FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint); audit(c,null,"CHUNK_INSTALL_FAILED",endpoint,"no ticket installed; reservation compensated"); } return null;});
    }
    public void requestChunkOff(UUID actor,UUID endpoint,boolean admin) throws SQLException {
        db.transaction(c->{fenced(c); var e=one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint); require(e!=null,"endpoint_not_found"); UUID owner=uuid(e,"device_owner"); require(admin || actor.equals(owner),"device_owner_required"); guard(c,owner); update(c,"UPDATE ct_chunk_grants SET state='REVOKING',desired=FALSE,reason='owner_disabled' WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint); event(c,"CHUNK_REVOKE",endpoint,str(e,"server_id")); audit(c,actor,"CHUNK_OFF_REQUESTED",endpoint,""); return null;});
    }
    public void confirmChunkOff(UUID endpoint) throws SQLException {
        db.transaction(c->{fenced(c); var e=one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint); require(e!=null && session().server().equals(str(e,"server_id")) && session().world().equals(uuid(e,"world_id")),"foreign_endpoint"); guard(c,uuid(e,"device_owner")); var g=one(c,"SELECT * FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint); if(g==null) return null; require(!Boolean.TRUE.equals(g.get("desired")),"grant_still_enabled"); update(c,"DELETE FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint); audit(c,null,"CHUNK_OFF_CONFIRMED",endpoint,"ticket removed on current fenced session"); return null;});
    }
    public List<Grant> grants(UUID player) throws SQLException {
        return db.transaction(c->{fenced(c); return query(c,"SELECT g.*,e.server_id,e.world_id,e.device_owner,e.channel_id,e.dimension_id,e.pos_x,e.pos_y,e.pos_z,e.version,e.checkpoint,e.pause_reason,e.state AS endpoint_state FROM ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id WHERE g.cluster_id=? AND g.player_uuid=? ORDER BY g.slot_no",cluster(),player).stream().map(r->grant(r,endpointMap(r))).toList();});
    }
    public List<Grant> localGrants() throws SQLException {
        return db.transaction(c->{fenced(c); return query(c,"SELECT g.*,e.server_id,e.world_id,e.device_owner,e.channel_id,e.dimension_id,e.pos_x,e.pos_y,e.pos_z,e.version,e.checkpoint,e.pause_reason,e.state AS endpoint_state FROM ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id WHERE g.cluster_id=? AND e.server_id=? AND e.world_id=? ORDER BY g.created_at LIMIT 4096",cluster(),session().server(),session().world()).stream().map(r->grant(r,endpointMap(r))).toList();});
    }
    public void lowerQuota(UUID admin,int newLimit,long expectedPolicy) throws SQLException {
        require(newLimit>=0 && newLimit<=64,"invalid_config");
        db.transaction(c->{fenced(c); var p=one(c,"SELECT * FROM ct_clusters WHERE cluster_id=? FOR UPDATE",cluster()); require(num(p,"policy_version")==expectedPolicy,"stale_version"); update(c,"UPDATE ct_clusters SET quota_limit=?,policy_version=policy_version+1 WHERE cluster_id=?",newLimit,cluster()); update(c,"UPDATE ct_chunk_grants SET state='REVOKING',desired=FALSE,reason='policy_reduced' WHERE cluster_id=? AND slot_no>=?",cluster(),newLimit); event(c,"POLICY_CHANGED",UUID.randomUUID(),null); audit(c,admin,"QUOTA_POLICY",null,"deterministic slot>= "+newLimit+" revocation; slots remain occupied until confirmed"); return null;});
    }
    private UUID resource(Connection c,Resource payload) throws SQLException {
        UUID candidate=UUID.randomUUID();
        update(c,"INSERT IGNORE INTO ct_resources(cluster_id,resource_id,kind,format_version,payload_hash,payload) VALUES(?,?,?,?,?,?)",cluster(),candidate,payload.kind(),Protocol.FORMAT,payload.hash(),payload.bytes());
        var row=one(c,"SELECT resource_id,payload,format_version FROM ct_resources WHERE cluster_id=? AND kind=? AND payload_hash=?",cluster(),payload.kind(),payload.hash());
        require(num(row,"format_version")==Protocol.FORMAT && Arrays.equals((byte[])row.get("payload"),payload.bytes()),"payload_hash_collision");
        return uuid(row,"resource_id");
    }
    /** Cache scope is exactly this fenced, channel-locked SQL transaction. */
    private static final class BatchContext {
        final UUID channel;final Map<String,Object> row;
        final Map<UUID,Map<String,Object>> endpoints=new HashMap<>();
        final Map<UUID,Integer> permissions=new HashMap<>();
        final Map<Resource,UUID> resources=new HashMap<>();
        final Set<String> capabilities;boolean balanceChanged;
        BatchContext(UUID channel,Map<String,Object> row,Set<String> capabilities){this.channel=channel;this.row=row;this.capabilities=capabilities;}
    }
    private Map<String,Object> batchOwner(Connection c,UUID endpoint,BatchContext context) throws SQLException {
        return context==null?one(c,"SELECT device_owner FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint):batchEndpoint(c,endpoint,false,context);
    }
    private Map<String,Object> batchEndpoint(Connection c,UUID endpoint,boolean active,BatchContext context) throws SQLException {
        if(context==null)return localEndpoint(c,endpoint,active);
        var row=context.endpoints.get(endpoint);require(row!=null,"endpoint_not_found");
        if(active)require("ACTIVE".equals(str(row,"state")),"endpoint_paused");return row;
    }
    private void authorizeBatch(Connection c,UUID channel,UUID owner,int permission,BatchContext context) throws SQLException {
        if(context==null){channelRow(c,channel,owner,permission,false);return;}
        require(channel.equals(context.channel),"binding_changed");
        require("ACTIVE".equals(str(context.row,"status")),"channel_frozen");
        Integer mask=context.permissions.get(owner);
        if(mask==null){if(owner.equals(uuid(context.row,"owner_uuid")))mask=Protocol.OWNER;
            else{var member=one(c,"SELECT permissions FROM ct_members WHERE cluster_id=? AND channel_id=? AND player_uuid=?",cluster(),channel,owner);mask=member==null?0:(int)num(member,"permissions");}
            context.permissions.put(owner,mask);
        }
        require(Protocol.permits(mask,permission),"forbidden");
    }
    private UUID batchResource(Connection c,Resource payload,BatchContext context) throws SQLException {
        if(context==null)return resource(c,payload);UUID id=context.resources.get(payload);
        if(id==null){id=resource(c,payload);context.resources.put(payload,id);}return id;
    }
    private BatchContext batchContext(Connection c,UUID channel) throws SQLException {
        fenced(c);var row=one(c,"SELECT * FROM ct_channels WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),channel);
        require(row!=null && !"DELETED".equals(str(row,"status")),"channel_not_found");
        var capabilities=one(c,"SELECT capabilities FROM ct_servers WHERE cluster_id=? AND server_id=?",cluster(),session().server());
        return new BatchContext(channel,row,Set.of(str(capabilities,"capabilities").split(",")));
    }
    private void captureEndpoint(Connection c,BatchContext context,UUID id,UUID channel,long expected) throws SQLException {
        var endpoint=localEndpoint(c,id,false);
        require(num(endpoint,"recovery_generation")==session().generation(),"backup_generation_conflict");
        require(channel.equals(uuid(endpoint,"channel_id")),"binding_changed");version(endpoint,expected);context.endpoints.put(id,endpoint);
    }
    /** One bounded channel transaction: checkpoint, deposits, demand, outstanding reads, fair allocation.
     * WAL and Redis are deliberately outside this transaction. Domain failure rolls back one endpoint;
     * connection/deadlock failure retries the whole phase with the SAME captured business IDs. */
    public List<TransferWork.Result> channelBatch(UUID channel,List<TransferWork.Request> requests) throws SQLException {
        require(!requests.isEmpty() && requests.size()<=16 && requests.stream().map(TransferWork.Request::endpoint).distinct().count()==requests.size(),"invalid_limit");
        return db.transaction(c->{
            var context=batchContext(c,channel);var results=new LinkedHashMap<UUID,TransferWork.Result>();
            var valid=new ArrayList<TransferWork.Request>();
            for(var request:requests.stream().sorted(Comparator.comparing(TransferWork.Request::endpoint)).toList()){
                require(channel.equals(request.channel()) && request.snapshot().world().equals(session().world()) && request.snapshot().generation()==session().generation(),"journal_generation_conflict");
                try(var scope=Sql.savepoint(c)){
                var savepoint=scope.point();boolean changedBefore=context.balanceChanged;
                try{
                    captureEndpoint(c,context,request.endpoint(),channel,request.endpointVersion());
                    var committed=new HashSet<UUID>();var consumed=new HashSet<UUID>();var remaining=new HashMap<UUID,Long>();
                    for(var credit:request.snapshot().credits()){remaining.put(credit.transaction(),credit.remaining());if(credit.remaining()==0)consumed.add(credit.transaction());}
                    if(request.checkpoint())checkpoint(request.endpoint(),request.snapshot().revision(),remaining,c,context);
                    for(var deposit:request.snapshot().deposits().stream().filter(d->request.sending().contains(d.resource().kind())).limit(request.depositLimit()).toList()){
                        deposit(deposit.transaction(),request.endpoint(),deposit.channel(),deposit.resource(),deposit.amount(),c,context);committed.add(deposit.transaction());
                    }
                    for(var demand:request.demands())demand(request.endpoint(),channel,demand.kind(),demand.room(),demand.profile(),demand.quantum(),c,context);
                    valid.add(request);results.put(request.endpoint(),new TransferWork.Result(request.endpoint(),committed,consumed,List.of(),null));
                }catch(DomainException error){c.rollback(savepoint);context.resources.clear();context.balanceChanged=changedBefore;context.endpoints.remove(request.endpoint());results.put(request.endpoint(),TransferWork.Result.failed(request.endpoint(),error.code()));}
                }
            }
            var knownCredits=new HashSet<UUID>();for(var request:valid)for(var credit:request.snapshot().credits())knownCredits.add(credit.transaction());
            var outstanding=allocationRows(c,valid.stream().map(TransferWork.Request::endpoint).toList(),knownCredits,true);
            // Order here does not define priority: allocate() ranks ALL eligible local and remote
            // demands by the same SQL last_grant sequence while this channel is locked.
            for(var request:valid){
                var prior=results.get(request.endpoint());var received=new ArrayList<LocalSnapshot.Credit>();
                var known=new HashSet<UUID>();for(var credit:request.snapshot().credits())known.add(credit.transaction());
                for(var allocation:outstanding.getOrDefault(request.endpoint(),List.of()))if(!known.contains(allocation.id()) && !"QUARANTINED".equals(allocation.state()))received.add(new LocalSnapshot.Credit(allocation.id(),allocation.channel(),allocation.payload(),allocation.amount(),allocation.remaining()));
                String failure=null;
                for(var demand:request.demands())if(received.stream().noneMatch(credit->credit.resource().kind().equals(demand.kind()))){
                    try(var scope=Sql.savepoint(c)){
                    var savepoint=scope.point();
                    try{var allocated=allocate(demand.transaction(),request.endpoint(),channel,demand.kind(),demand.room(),c,context);
                        if(allocated.isPresent()){var allocation=allocated.orElseThrow();received.add(new LocalSnapshot.Credit(allocation.id(),allocation.channel(),allocation.payload(),allocation.amount(),allocation.remaining()));}
                    }catch(DomainException error){c.rollback(savepoint);failure=error.code();update(c,"UPDATE ct_demands SET room=0,expires_at=CURRENT_TIMESTAMP(6) WHERE cluster_id=? AND endpoint_id=? AND kind=?",cluster(),request.endpoint(),demand.kind());}
                    }
                }
                results.put(request.endpoint(),new TransferWork.Result(request.endpoint(),prior.committed(),prior.consumed(),received,failure));
            }
            if(context.balanceChanged)event(c,"BALANCE_CHANGED",channel,null);
            return List.copyOf(results.values());
        });
    }
    /** Destination checkpoint was fsynced before this phase. Never publish an unfenced LOCAL credit. */
    public Map<UUID,String> publishBatch(UUID channel,List<TransferWork.Publication> publications) throws SQLException {
        require(!publications.isEmpty() && publications.size()<=16,"invalid_limit");
        return db.transaction(c->{var context=batchContext(c,channel);var errors=new HashMap<UUID,String>();
            for(var publication:publications.stream().sorted(Comparator.comparing(p->p.snapshot().endpoint())).toList()){
                var snapshot=publication.snapshot();try(var scope=Sql.savepoint(c)){var savepoint=scope.point();
                try{
                    captureEndpoint(c,context,snapshot.endpoint(),channel,publication.endpointVersion());
                    if(!publication.received().isEmpty()){
                        var endpoint=batchEndpoint(c,snapshot.endpoint(),true,context);authorizeBatch(c,channel,uuid(endpoint,"device_owner"),Protocol.RECEIVE,context);
                        for(var credit:publication.received())require(update(c,"UPDATE ct_transfers SET state='LOCAL' WHERE cluster_id=? AND transfer_id=? AND endpoint_id=? AND kind='ALLOCATE' AND state IN ('RESERVED','LOCAL')",cluster(),credit.transaction(),snapshot.endpoint())==1,"allocation_not_found");
                    }
                    for(var quarantine:publication.quarantined().entrySet()){update(c,"UPDATE ct_transfers SET state='QUARANTINED' WHERE cluster_id=? AND endpoint_id=? AND transfer_id=? AND kind='ALLOCATE'",cluster(),snapshot.endpoint(),quarantine.getKey());quarantine(c,snapshot.endpoint(),quarantine.getKey(),quarantine.getValue(),"exclusive allocation; no automatic refund");}
                    var remaining=new HashMap<UUID,Long>();for(var credit:snapshot.credits())remaining.put(credit.transaction(),credit.remaining());
                    checkpoint(snapshot.endpoint(),snapshot.revision(),remaining,c,context);
                }catch(DomainException error){c.rollback(savepoint);errors.put(snapshot.endpoint(),error.code());}
                }
            }
            return Map.copyOf(errors);
        });
    }
    /** Deposit belongs to exactly one captured channel, never the endpoint's binding at callback time. */
    public void deposit(UUID transaction,UUID endpoint,UUID capturedChannel,Resource payload,long amount) throws SQLException {
        require(amount>0,"invalid_amount");
        db.transaction(c->deposit(transaction,endpoint,capturedChannel,payload,amount,c,null));
    }
    private Void deposit(UUID transaction,UUID endpoint,UUID capturedChannel,Resource payload,long amount,Connection c,BatchContext context) throws SQLException {

            if(context==null)fenced(c);
            var old=one(c,"SELECT * FROM ct_transfers WHERE cluster_id=? AND transfer_id=?",cluster(),transaction);
            if(old!=null) {
                require("DEPOSIT".equals(str(old,"kind")) && endpoint.equals(uuid(old,"endpoint_id")) && capturedChannel.equals(uuid(old,"channel_id")) && amount==num(old,"amount"),"idempotency_conflict");
                var original=one(c,"SELECT kind,payload FROM ct_resources WHERE cluster_id=? AND resource_id=?",cluster(),uuid(old,"resource_id"));
                require(payload.equals(new Resource(str(original,"kind"),(byte[])original.get("payload"))),"idempotency_conflict"); return null;
            }
            var location=batchOwner(c,endpoint,context); require(location!=null,"endpoint_not_found");
            BusinessIds.fresh(transaction);
            authorizeBatch(c,capturedChannel,uuid(location,"device_owner"),Protocol.SEND,context);
            var e=batchEndpoint(c,endpoint,true,context); require(capturedChannel.equals(uuid(e,"channel_id")),"binding_changed");
            UUID res=batchResource(c,payload,context);
            update(c,"INSERT IGNORE INTO ct_balances(cluster_id,channel_id,resource_id,amount) VALUES(?,?,?,0)",cluster(),capturedChannel,res);
            long before=num(one(c,"SELECT amount FROM ct_balances WHERE cluster_id=? AND channel_id=? AND resource_id=? FOR UPDATE",cluster(),capturedChannel,res),"amount");
            long after;
            try { after=Math.addExact(before,amount); } catch(ArithmeticException ex) { throw new DomainException("quantity_overflow"); }
            update(c,"UPDATE ct_balances SET amount=? WHERE cluster_id=? AND channel_id=? AND resource_id=?",after,cluster(),capturedChannel,res);
            reserveHistory(c);
            update(c,"INSERT INTO ct_transfers(cluster_id,transfer_id,endpoint_id,channel_id,resource_id,amount,kind,state,epoch,remaining) VALUES(?,?,?,?,?,?,'DEPOSIT','COMMITTED',?,0)",cluster(),transaction,endpoint,capturedChannel,res,amount,session().epoch());
            if(context==null)event(c,"BALANCE_CHANGED",capturedChannel,null);else context.balanceChanged=true; return null;
    }
    public void demand(UUID endpoint,UUID capturedChannel,String kind,long room) throws SQLException {
        demand(endpoint,capturedChannel,kind,room,null,1);
    }
    public void demand(UUID endpoint,UUID capturedChannel,String kind,long room,String profile,long quantum) throws SQLException {
        require(room>=0 && room<=1_000_000_000_000L,"invalid_amount");
        require(quantum>=1 && quantum<=1_000_000_000_000L && (profile==null || profile.matches("[a-f0-9]{64}")),"invalid_resource");
        db.transaction(c->demand(endpoint,capturedChannel,kind,room,profile,quantum,c,null));
    }
    private Void demand(UUID endpoint,UUID capturedChannel,String kind,long room,String profile,long quantum,Connection c,BatchContext context) throws SQLException {
            require(room>=0 && room<=1_000_000_000_000L,"invalid_amount");
            require(quantum>=1 && quantum<=1_000_000_000_000L && (profile==null || profile.matches("[a-f0-9]{64}")),"invalid_resource");
            if(context==null)fenced(c); var owner=batchOwner(c,endpoint,context); require(owner!=null,"endpoint_not_found");
            authorizeBatch(c,capturedChannel,uuid(owner,"device_owner"),Protocol.RECEIVE,context);
            var e=batchEndpoint(c,endpoint,true,context); require(capturedChannel.equals(uuid(e,"channel_id")),"binding_changed");
            require(context==null?Set.of(str(one(c,"SELECT capabilities FROM ct_servers WHERE cluster_id=? AND server_id=?",cluster(),session().server()),"capabilities").split(",")).contains(kind):context.capabilities.contains(kind),"resource_unsupported");
            Map<String,Object> directed=null;if(kind.equals(Protocol.ITEM)||kind.equals(Protocol.FLUID)){expireStock(c,endpoint);
                directed=one(c,"SELECT q.remaining,r.payload_hash FROM ct_stock_requests q JOIN ct_resources r ON r.cluster_id=q.cluster_id AND r.resource_id=q.resource_id WHERE q.cluster_id=? AND q.endpoint_id=? AND q.channel_id=? AND q.state IN ('PENDING','PARTIAL') AND r.kind=? ORDER BY q.created_at,q.request_id LIMIT 1",cluster(),endpoint,capturedChannel,kind);}
            long actualRoom=directed==null?room:Math.min(room,num(directed,"remaining"));String actualProfile=directed==null?profile:str(directed,"payload_hash");
            update(c,"INSERT INTO ct_demands(cluster_id,channel_id,endpoint_id,kind,room,expires_at,profile_hash,quantum) VALUES(?,?,?,?,?,TIMESTAMPADD(SECOND,6,CURRENT_TIMESTAMP(6)),?,?) ON DUPLICATE KEY UPDATE room=VALUES(room),expires_at=VALUES(expires_at),profile_hash=VALUES(profile_hash),quantum=VALUES(quantum)",cluster(),capturedChannel,endpoint,kind,actualRoom,actualProfile,quantum); return null;
    }
    /** Global oldest eligible demand is served once. N receivers contend on a channel, not N squared links. */
    public Optional<Allocation> allocate(UUID transaction,UUID endpoint,UUID capturedChannel,String kind,long maxAmount) throws SQLException {
        require(maxAmount>0,"invalid_amount");
        return db.transaction(c->allocate(transaction,endpoint,capturedChannel,kind,maxAmount,c,null));
    }
    private Optional<Allocation> allocate(UUID transaction,UUID endpoint,UUID capturedChannel,String kind,long maxAmount,Connection c,BatchContext context) throws SQLException {

            if(context==null)fenced(c);
            var old=one(c,"SELECT * FROM ct_transfers WHERE cluster_id=? AND transfer_id=?",cluster(),transaction);
            if(old!=null) { require("ALLOCATE".equals(str(old,"kind")) && endpoint.equals(uuid(old,"endpoint_id")) && capturedChannel.equals(uuid(old,"channel_id")),"idempotency_conflict"); return Optional.of(allocation(c,old)); }
            BusinessIds.fresh(transaction);
            var owner=batchOwner(c,endpoint,context); require(owner!=null,"endpoint_not_found");
            authorizeBatch(c,capturedChannel,uuid(owner,"device_owner"),Protocol.RECEIVE,context);
            var e=batchEndpoint(c,endpoint,true,context); require(capturedChannel.equals(uuid(e,"channel_id")),"binding_changed");
            var candidate=one(c,"SELECT d.endpoint_id,d.room,d.profile_hash,d.quantum FROM ct_demands d JOIN ct_endpoints e ON e.cluster_id=d.cluster_id AND e.endpoint_id=d.endpoint_id JOIN ct_servers s ON s.cluster_id=e.cluster_id AND s.server_id=e.server_id JOIN ct_channels ch ON ch.cluster_id=d.cluster_id AND ch.channel_id=d.channel_id LEFT JOIN ct_members m ON m.cluster_id=e.cluster_id AND m.channel_id=e.channel_id AND m.player_uuid=e.device_owner WHERE d.cluster_id=? AND d.channel_id=? AND d.kind=? AND d.room>=d.quantum AND d.expires_at>CURRENT_TIMESTAMP(6) AND e.channel_id=d.channel_id AND e.world_id=s.world_id AND e.last_epoch=s.fencing_epoch AND e.recovery_generation=(SELECT recovery_generation FROM ct_clusters WHERE cluster_id=d.cluster_id) AND e.state='ACTIVE' AND s.lease_until>CURRENT_TIMESTAMP(6) AND s.protocol_version=1 AND s.format_version=1 AND FIND_IN_SET(d.kind,s.capabilities)>0 AND (ch.owner_uuid=e.device_owner OR (m.permissions & 4)=4) AND (SELECT COUNT(*) FROM ct_transfers t WHERE t.cluster_id=d.cluster_id AND t.endpoint_id=d.endpoint_id AND t.kind='ALLOCATE' AND t.remaining>0)<64 AND (SELECT COUNT(*) FROM ct_transfers t JOIN ct_resources tr ON tr.cluster_id=t.cluster_id AND tr.resource_id=t.resource_id WHERE t.cluster_id=d.cluster_id AND t.endpoint_id=d.endpoint_id AND t.kind='ALLOCATE' AND t.remaining>0 AND tr.kind=d.kind)<CASE WHEN d.kind IN ('cross_tesseract:fe','cross_tesseract:gt_eu') THEN 32 WHEN d.kind='cross_tesseract:item' THEN 9 ELSE 4 END AND COALESCE((SELECT used FROM ct_history_buckets hb WHERE hb.cluster_id=e.cluster_id AND hb.server_id=e.server_id),0)<(SELECT history_limit FROM ct_clusters WHERE cluster_id=d.cluster_id) AND EXISTS(SELECT 1 FROM ct_balances b JOIN ct_resources r ON r.cluster_id=b.cluster_id AND r.resource_id=b.resource_id WHERE b.cluster_id=d.cluster_id AND b.channel_id=d.channel_id AND r.kind=d.kind AND r.format_version=1 AND b.amount>=d.quantum AND (d.profile_hash IS NULL OR d.profile_hash=r.payload_hash)) ORDER BY d.last_grant,d.endpoint_id LIMIT 1",cluster(),capturedChannel,kind);
            if(candidate==null || !endpoint.equals(uuid(candidate,"endpoint_id"))) return Optional.empty();
            long outstanding=num(one(c,"SELECT COUNT(*) AS n FROM ct_transfers t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE t.cluster_id=? AND t.endpoint_id=? AND t.kind='ALLOCATE' AND r.kind=? AND t.remaining>0",cluster(),endpoint,kind),"n");
            if(outstanding>=LocalBuffer.creditLimit(kind)) return Optional.empty();
            String profile=str(candidate,"profile_hash");long quantum=num(candidate,"quantum");
            var balance=one(c,"SELECT b.resource_id,b.amount,r.kind,r.format_version,r.payload_hash,r.payload FROM ct_balances b JOIN ct_resources r ON r.cluster_id=b.cluster_id AND r.resource_id=b.resource_id WHERE b.cluster_id=? AND b.channel_id=? AND r.kind=? AND r.format_version=1 AND b.amount>=? AND (? IS NULL OR r.payload_hash=?) ORDER BY b.resource_id LIMIT 1",cluster(),capturedChannel,kind,quantum,profile,profile);
            if(balance==null) return Optional.empty();
            long qty=Math.min(Math.min(maxAmount,num(candidate,"room")),num(balance,"amount"));
            qty=(qty/quantum)*quantum;if(qty==0)return Optional.empty();
            update(c,"UPDATE ct_balances SET amount=amount-? WHERE cluster_id=? AND channel_id=? AND resource_id=?",qty,cluster(),capturedChannel,uuid(balance,"resource_id"));
            reserveHistory(c);
            update(c,"INSERT INTO ct_transfers(cluster_id,transfer_id,endpoint_id,channel_id,resource_id,amount,kind,state,epoch,remaining) VALUES(?,?,?,?,?,?,'ALLOCATE','RESERVED',?,?)",cluster(),transaction,endpoint,capturedChannel,uuid(balance,"resource_id"),qty,session().epoch(),qty);
            long sequence=num(one(c,"SELECT COALESCE(MAX(last_grant),0) AS n FROM ct_demands WHERE cluster_id=? AND channel_id=? AND kind=?",cluster(),capturedChannel,kind),"n");
            update(c,"UPDATE ct_demands SET room=room-?,last_grant=? WHERE cluster_id=? AND channel_id=? AND endpoint_id=? AND kind=?",qty,Math.addExact(sequence,1),cluster(),capturedChannel,endpoint,kind);
            var directed=kind.equals(Protocol.ITEM)||kind.equals(Protocol.FLUID)?one(c,"SELECT request_id,remaining FROM ct_stock_requests WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND resource_id=? AND state IN ('PENDING','PARTIAL') AND expires_at>CURRENT_TIMESTAMP(6) ORDER BY created_at,request_id LIMIT 1 FOR UPDATE",cluster(),endpoint,capturedChannel,uuid(balance,"resource_id")):null;
            if(directed!=null){long left=Math.max(0,num(directed,"remaining")-qty);update(c,"UPDATE ct_stock_requests SET remaining=?,state=? WHERE cluster_id=? AND request_id=?",left,left==0?"FULFILLED":"PARTIAL",cluster(),uuid(directed,"request_id"));}
            event(c,"ALLOCATION_READY",transaction,session().server());
            return Optional.of(new Allocation(transaction,endpoint,capturedChannel,uuid(balance,"resource_id"),decodeResource(balance),qty,qty,"RESERVED"));
    }
    private Allocation allocation(Connection c,Map<String,Object> r) throws SQLException {
        var payload=one(c,"SELECT * FROM ct_resources WHERE cluster_id=? AND resource_id=?",cluster(),uuid(r,"resource_id"));
        require(num(payload,"format_version")==Protocol.FORMAT,"resource_unsupported");
        var resource=new Resource(str(payload,"kind"),(byte[])payload.get("payload")); require(resource.hash().equals(str(payload,"payload_hash")),"payload_corrupt");
        return new Allocation(uuid(r,"transfer_id"),uuid(r,"endpoint_id"),uuid(r,"channel_id"),uuid(r,"resource_id"),resource,num(r,"amount"),num(r,"remaining"),str(r,"state"));
    }
    public List<Allocation> allocations(UUID endpoint) throws SQLException {
        return db.transaction(c->{fenced(c);localEndpoint(c,endpoint,false);return allocationRows(c,List.of(endpoint)).getOrDefault(endpoint,List.of());});
    }
    private Map<UUID,List<Allocation>> allocationRows(Connection c,List<UUID> endpoints) throws SQLException {return allocationRows(c,endpoints,Set.of(),false);}
    private Map<UUID,List<Allocation>> allocationRows(Connection c,List<UUID> endpoints,Set<UUID> known,boolean activeOnly) throws SQLException {
        if(endpoints.isEmpty())return Map.of();
        var args=new ArrayList<Object>();args.add(cluster());args.addAll(endpoints);args.addAll(known);
        String unseen=known.isEmpty()?"":" AND transfer_id NOT IN ("+String.join(",",Collections.nCopies(known.size(),"?"))+")";
        // MySQL 8 window bound applies PER endpoint. Recovery cannot let one legacy endpoint
        // monopolize the entire result, and ordinary discovery returns at most eight unseen rows.
        var rows=query(c,"SELECT t.*,r.kind AS payload_kind,r.format_version,r.payload_hash,r.payload FROM (SELECT owned.*,ROW_NUMBER() OVER(PARTITION BY endpoint_id ORDER BY created_at,transfer_id) AS rn FROM ct_transfers owned WHERE cluster_id=? AND endpoint_id IN ("+String.join(",",Collections.nCopies(endpoints.size(),"?"))+") AND kind='ALLOCATE' AND remaining>0"+(activeOnly?" AND state<>'QUARANTINED'":"")+unseen+") t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE t.rn<="+(activeOnly?8:64)+" ORDER BY t.endpoint_id,t.rn",args.toArray());
        var result=new HashMap<UUID,List<Allocation>>();var payloads=new HashMap<UUID,Resource>();
        for(var row:rows){UUID resourceId=uuid(row,"resource_id");Resource resource=payloads.get(resourceId);
            try{if(resource==null){var payload=new HashMap<>(row);payload.put("kind",str(row,"payload_kind"));resource=decodeResource(payload);payloads.put(resourceId,resource);}}
            catch(DomainException invalid){update(c,"UPDATE ct_transfers SET state='QUARANTINED' WHERE cluster_id=? AND transfer_id=? AND kind='ALLOCATE'",cluster(),uuid(row,"transfer_id"));quarantine(c,uuid(row,"endpoint_id"),uuid(row,"transfer_id"),invalid.code(),"unreadable payload; exclusive SQL ownership retained");continue;}
            var allocation=new Allocation(uuid(row,"transfer_id"),uuid(row,"endpoint_id"),uuid(row,"channel_id"),resourceId,resource,num(row,"amount"),num(row,"remaining"),str(row,"state"));
            result.computeIfAbsent(allocation.endpoint(),x->new ArrayList<>()).add(allocation);
        }
        return result;
    }
    public void markLocal(UUID endpoint,UUID transfer) throws SQLException {
        db.transaction(c->{fenced(c);var owner=one(c,"SELECT device_owner,channel_id FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint);require(owner!=null,"endpoint_not_found");channelRow(c,uuid(owner,"channel_id"),uuid(owner,"device_owner"),Protocol.RECEIVE,false);var e=localEndpoint(c,endpoint,true);require(uuid(owner,"channel_id").equals(uuid(e,"channel_id")),"binding_changed");require(update(c,"UPDATE ct_transfers SET state='LOCAL' WHERE cluster_id=? AND transfer_id=? AND endpoint_id=? AND channel_id=? AND kind='ALLOCATE' AND state IN ('RESERVED','LOCAL')",cluster(),transfer,endpoint,uuid(e,"channel_id"))==1,"allocation_not_found");return null;});
    }
    /** Bounded paged advisory view. Payloads stay server-side; only native local credits are spendable. */
    public StockPage stock(UUID actor,UUID endpoint,UUID channel,UUID after) throws SQLException {
        return db.transaction(c->{fenced(c);channelRow(c,channel,actor,Protocol.VIEW,true);var e=localEndpoint(c,endpoint,false);
            require(actor.equals(uuid(e,"device_owner")),"device_owner_required");require(channel.equals(uuid(e,"channel_id")),"binding_changed");expireStock(c,endpoint);
            String cursor=after==null?"":after.toString();
            var ids=query(c,"SELECT resource_id FROM (SELECT resource_id FROM ct_balances WHERE cluster_id=? AND channel_id=? AND amount>0 AND resource_id>? UNION SELECT resource_id FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND kind='ALLOCATE' AND state IN ('RESERVED','LOCAL','QUARANTINED') AND remaining>0 AND resource_id>?) visible JOIN ct_resources r USING(resource_id) WHERE r.cluster_id=? AND r.kind IN (?,?) ORDER BY resource_id LIMIT 9",cluster(),channel,cursor,cluster(),endpoint,channel,cursor,cluster(),Protocol.ITEM,Protocol.FLUID);
            var rows=new ArrayList<StockRow>();for(var id:ids.stream().limit(8).toList()){
                UUID resource=uuid(id,"resource_id");var r=one(c,"SELECT * FROM ct_resources WHERE cluster_id=? AND resource_id=?",cluster(),resource);var payload=decodeResource(r);
                var b=one(c,"SELECT amount FROM ct_balances WHERE cluster_id=? AND channel_id=? AND resource_id=?",cluster(),channel,resource);
                var quantities=one(c,"SELECT COALESCE(SUM(IF(state='RESERVED',remaining,0)),0) AS reserved,COALESCE(SUM(IF(state='LOCAL',remaining,0)),0) AS local_amount,COALESCE(SUM(IF(state='QUARANTINED',remaining,0)),0) AS quarantined FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND resource_id=? AND kind='ALLOCATE' AND state IN ('RESERVED','LOCAL','QUARANTINED')",cluster(),endpoint,channel,resource);
                rows.add(new StockRow(resource,payload,b==null?0:num(b,"amount"),num(quantities,"reserved"),num(quantities,"local_amount"),num(quantities,"quarantined")));
            }
            var requests=query(c,"SELECT * FROM ct_stock_requests WHERE cluster_id=? AND endpoint_id=? AND channel_id=? ORDER BY state IN ('PENDING','PARTIAL') DESC,created_at DESC LIMIT 8",cluster(),endpoint,channel).stream().map(Authority::stockRequest).toList();
            return new StockPage(List.copyOf(rows),ids.size()>8?rows.getLast().resource():null,requests);
        });
    }
    public Resource stockResource(UUID actor,UUID endpoint,UUID channel,UUID resource) throws SQLException {
        return db.transaction(c->{fenced(c);channelRow(c,channel,actor,Protocol.VIEW,true);var e=localEndpoint(c,endpoint,false);require(actor.equals(uuid(e,"device_owner")),"device_owner_required");require(channel.equals(uuid(e,"channel_id")),"binding_changed");require(one(c,"SELECT resource_id FROM ct_balances WHERE cluster_id=? AND channel_id=? AND resource_id=?",cluster(),channel,resource)!=null || one(c,"SELECT resource_id FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND resource_id=? LIMIT 1",cluster(),endpoint,channel,resource)!=null,"forbidden");var r=one(c,"SELECT * FROM ct_resources WHERE cluster_id=? AND resource_id=?",cluster(),resource);require(r!=null,"resource_unsupported");return decodeResource(r);});
    }
    /** Intent only. The existing fair allocator is the only operation that debits balances. */
    public StockRequest requestStock(UUID actor,UUID request,UUID endpoint,UUID channel,long expected,Resource payload,long amount,boolean coalesce) throws SQLException {
        require(Set.of(Protocol.ITEM,Protocol.FLUID).contains(payload.kind()),"resource_unsupported");require(amount>0 && amount<=LocalBuffer.slots(payload.kind())*LocalBuffer.slotCapacity(payload.kind()),"invalid_amount");
        return db.transaction(c->{fenced(c);channelRow(c,channel,actor,Protocol.RECEIVE,false);var e=localEndpoint(c,endpoint,true);require(actor.equals(uuid(e,"device_owner")),"device_owner_required");require(channel.equals(uuid(e,"channel_id")),"binding_changed");version(e,expected);
            require(Arrays.asList(str(one(c,"SELECT capabilities FROM ct_servers WHERE cluster_id=? AND server_id=?",cluster(),session().server()),"capabilities").split(",")).contains(payload.kind()),"resource_unsupported");
            var old=one(c,"SELECT * FROM ct_stock_requests WHERE cluster_id=? AND request_id=?",cluster(),request);
            if(old!=null){require(actor.equals(uuid(old,"actor_uuid")) && endpoint.equals(uuid(old,"endpoint_id")) && channel.equals(uuid(old,"channel_id")) && amount==num(old,"amount"),"idempotency_conflict");var original=decodeResource(one(c,"SELECT * FROM ct_resources WHERE cluster_id=? AND resource_id=?",cluster(),uuid(old,"resource_id")));require(payload.equals(original),"idempotency_conflict");return stockRequest(old);}
            BusinessIds.fresh(request);expireStock(c,endpoint);UUID res=resource(c,payload);
            if(coalesce){var pending=one(c,"SELECT * FROM ct_stock_requests WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND resource_id=? AND state IN ('PENDING','PARTIAL') ORDER BY created_at,request_id LIMIT 1",cluster(),endpoint,channel,res);if(pending!=null)return stockRequest(pending);}
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_stock_requests WHERE cluster_id=? AND endpoint_id=? AND state IN ('PENDING','PARTIAL')",cluster(),endpoint),"n")<8,"stock_request_limit");reserveHistory(c);
            update(c,"INSERT INTO ct_stock_requests(cluster_id,request_id,endpoint_id,channel_id,resource_id,actor_uuid,amount,remaining,expires_at) VALUES(?,?,?,?,?,?,?,?,TIMESTAMPADD(SECOND,60,CURRENT_TIMESTAMP(6)))",cluster(),request,endpoint,channel,res,actor,amount,amount);
            event(c,"STOCK_REQUESTED",request,session().server());return stockRequest(one(c,"SELECT * FROM ct_stock_requests WHERE cluster_id=? AND request_id=?",cluster(),request));
        });
    }
    public void cancelStock(UUID actor,UUID endpoint,UUID channel,UUID request) throws SQLException {
        db.transaction(c->{fenced(c);channelRow(c,channel,actor,Protocol.VIEW,true);var e=localEndpoint(c,endpoint,false);require(actor.equals(uuid(e,"device_owner")),"device_owner_required");require(channel.equals(uuid(e,"channel_id")),"binding_changed");var r=one(c,"SELECT * FROM ct_stock_requests WHERE cluster_id=? AND request_id=? FOR UPDATE",cluster(),request);require(r!=null && endpoint.equals(uuid(r,"endpoint_id")) && channel.equals(uuid(r,"channel_id")) && actor.equals(uuid(r,"actor_uuid")),"forbidden");update(c,"UPDATE ct_stock_requests SET state='CANCELLED' WHERE cluster_id=? AND request_id=? AND state IN ('PENDING','PARTIAL')",cluster(),request);audit(c,actor,"CANCEL_STOCK",request,"unallocated intent only; existing allocations remain owned");return null;});
    }
    private void expireStock(Connection c,UUID endpoint) throws SQLException {update(c,"UPDATE ct_stock_requests SET state='EXPIRED' WHERE cluster_id=? AND endpoint_id=? AND state IN ('PENDING','PARTIAL') AND expires_at<=CURRENT_TIMESTAMP(6)",cluster(),endpoint);}
    private static StockRequest stockRequest(Map<String,Object> r){return new StockRequest(uuid(r,"request_id"),uuid(r,"resource_id"),num(r,"amount"),num(r,"remaining"),str(r,"state"),((Timestamp)r.get("expires_at")).toInstant());}
    private static Resource decodeResource(Map<String,Object> r){require(r!=null && num(r,"format_version")==Protocol.FORMAT,"resource_unsupported");var payload=new Resource(str(r,"kind"),(byte[])r.get("payload"));require(payload.hash().equals(str(r,"payload_hash")),"payload_corrupt");return payload;}
    /** WAL presence alone cannot reactivate a SQL-quarantined allocation. */
    public LocalSnapshot restoreSnapshot(LocalSnapshot snapshot) throws SQLException {
        require(snapshot.credits().size()<=64,"invalid_checkpoint");
        require(snapshot.world().equals(session().world()) && snapshot.generation()==session().generation(),"journal_generation_conflict");
        return db.transaction(c->{fenced(c);
            // Match the asset lock order: channel(s), endpoint, transfers. WAL may contain
            // RESERVED receipts from an interrupted publication, which are not yet local assets.
            var channels=new TreeSet<UUID>();for(var credit:snapshot.credits())channels.add(credit.channel());
            for(UUID channel:channels)one(c,"SELECT channel_id FROM ct_channels WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),channel);
            var endpoint=localEndpoint(c,snapshot.endpoint(),false);var credits=new ArrayList<LocalSnapshot.Credit>();
            for(var credit:snapshot.credits()){
                var row=one(c,"SELECT * FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND transfer_id=? AND kind='ALLOCATE' FOR UPDATE",cluster(),snapshot.endpoint(),credit.transaction());require(row!=null,"allocation_not_found");
                var allocation=allocation(c,row);require(allocation.channel().equals(credit.channel()) && allocation.payload().equals(credit.resource()) && allocation.amount()==credit.original() && credit.remaining()<=allocation.remaining(),"invalid_checkpoint");
                if(allocation.state().equals("RESERVED")){
                    // An unclean boot leaves the endpoint quarantined. Keep these assets
                    // exclusively in SQL, not in the usable buffer; recovery may later fetch them.
                    if(!"ACTIVE".equals(str(endpoint,"state")))continue;
                    require("ACTIVE".equals(str(endpoint,"state")) && credit.channel().equals(uuid(endpoint,"channel_id")),"endpoint_paused");
                    channelRow(c,credit.channel(),uuid(endpoint,"device_owner"),Protocol.RECEIVE,false);
                    update(c,"UPDATE ct_transfers SET state='LOCAL' WHERE cluster_id=? AND transfer_id=?",cluster(),credit.transaction());
                }
                if(!allocation.state().equals("QUARANTINED"))credits.add(credit);
            }
            return new LocalSnapshot(snapshot.endpoint(),snapshot.world(),snapshot.generation(),snapshot.revision(),snapshot.deposits(),credits,snapshot.thermal());
        });
    }
    /** Absolute monotone remaining values from an fsynced local checkpoint. No timeout refunds. */
    public void checkpoint(UUID endpoint,long sequence,Map<UUID,Long> remaining) throws SQLException {
        require(sequence>=0 && remaining.size()<=64,"invalid_checkpoint");
        db.transaction(c->checkpoint(endpoint,sequence,remaining,c,null));
    }
    private Void checkpoint(UUID endpoint,long sequence,Map<UUID,Long> remaining,Connection c,BatchContext context) throws SQLException {

            if(context==null)fenced(c); var e=batchEndpoint(c,endpoint,false,context);
            require(sequence>=num(e,"checkpoint"),"stale_checkpoint");
            for(var entry:new TreeMap<>(remaining).entrySet()) {
                var transfer=one(c,"SELECT remaining,kind,state FROM ct_transfers WHERE cluster_id=? AND transfer_id=? AND endpoint_id=? FOR UPDATE",cluster(),entry.getKey(),endpoint);
                require(transfer!=null && "ALLOCATE".equals(str(transfer,"kind")) && entry.getValue()>=0 && entry.getValue()<=num(transfer,"remaining"),"invalid_checkpoint");
                if("QUARANTINED".equals(str(transfer,"state"))){require(entry.getValue()==num(transfer,"remaining"),"quarantined_allocation");continue;}
                require(!"RESERVED".equals(str(transfer,"state")),"allocation_not_local");
                update(c,"UPDATE ct_transfers SET remaining=?,state=? WHERE cluster_id=? AND transfer_id=?",entry.getValue(),entry.getValue()==0?"CONSUMED":"LOCAL",cluster(),entry.getKey());
            }
            update(c,"UPDATE ct_endpoints SET checkpoint=? WHERE cluster_id=? AND endpoint_id=?",sequence,cluster(),endpoint); return null;
    }
    public void quarantineAllocation(UUID endpoint,UUID transfer,String reason) throws SQLException {
        db.transaction(c->{fenced(c); localEndpoint(c,endpoint,false); update(c,"UPDATE ct_transfers SET state='QUARANTINED' WHERE cluster_id=? AND endpoint_id=? AND transfer_id=? AND kind='ALLOCATE'",cluster(),endpoint,transfer); quarantine(c,endpoint,transfer,reason,"Allocation remains exclusively owned; no automatic refund or replay"); return null;});
    }
    public List<Event> unpublished(int limit) throws SQLException {
        require(limit>0 && limit<=256,"invalid_limit");
        return db.transaction(c->{fenced(c); return query(c,"SELECT * FROM ct_outbox WHERE cluster_id=? AND published_at IS NULL ORDER BY id LIMIT ?",cluster(),limit).stream().map(r->new Event(num(r,"id"),uuid(r,"event_id"),str(r,"event_type"),uuid(r,"subject_id"),str(r,"target_server"))).toList();});
    }
    public void published(long id) throws SQLException { published(List.of(id)); }
    public void published(List<Long> ids) throws SQLException {
        require(ids.size()<=256,"invalid_limit");if(ids.isEmpty())return;
        db.transaction(c->{fenced(c);var args=new ArrayList<Object>();args.add(cluster());args.addAll(ids);
            update(c,"UPDATE ct_outbox SET published_at=CURRENT_TIMESTAMP(6) WHERE cluster_id=? AND id IN ("+String.join(",",Collections.nCopies(ids.size(),"?"))+")",args.toArray());return null;});
    }
    public boolean receiveEvent(UUID event) throws SQLException { return db.transaction(c->{fenced(c); return update(c,"INSERT IGNORE INTO ct_inbox(cluster_id,server_id,event_id) VALUES(?,?,?)",cluster(),session().server(),event)==1;}); }
    /** Inbox is one transaction per bounded delivery batch. Redis-provided type/subject are
     * never trusted: wake targets are reconstructed from the current SQL outbox and binding. */
    public List<RedisTransport.Hint> receiveEvents(List<UUID> events) throws SQLException {
        require(events.size()<=256,"invalid_limit");if(events.isEmpty())return List.of();
        var unique=events.stream().distinct().toList();
        return db.transaction(c->{fenced(c);var values=new ArrayList<Object>();for(UUID event:unique){values.add(cluster());values.add(session().server());values.add(event);}
            update(c,"INSERT IGNORE INTO ct_inbox(cluster_id,server_id,event_id) VALUES "+String.join(",",Collections.nCopies(unique.size(),"(?,?,?)")),values.toArray());
            var args=new ArrayList<Object>();args.add(session().server());args.add(session().world());args.add(session().epoch());args.add(session().generation());args.add(cluster());args.add(session().server());args.addAll(unique);
            var rows=query(c,"SELECT o.event_type,o.subject_id,t.endpoint_id AS transfer_endpoint,t.channel_id AS transfer_channel,q.endpoint_id AS stock_endpoint,q.channel_id AS stock_channel,e.endpoint_id AS current_endpoint,e.channel_id AS current_channel FROM ct_outbox o LEFT JOIN ct_transfers t ON t.cluster_id=o.cluster_id AND t.transfer_id=o.subject_id AND o.event_type='ALLOCATION_READY' LEFT JOIN ct_stock_requests q ON q.cluster_id=o.cluster_id AND q.request_id=o.subject_id AND o.event_type='STOCK_REQUESTED' LEFT JOIN ct_endpoints e ON e.cluster_id=o.cluster_id AND e.endpoint_id=COALESCE(t.endpoint_id,q.endpoint_id,CASE WHEN o.event_type='ENDPOINT_CHANGED' THEN o.subject_id END) AND e.server_id=? AND e.world_id=? AND e.last_epoch=? AND e.recovery_generation=? WHERE o.cluster_id=? AND (o.target_server IS NULL OR o.target_server=?) AND o.event_id IN ("+String.join(",",Collections.nCopies(unique.size(),"?"))+")",args.toArray());
            var result=new ArrayList<RedisTransport.Hint>();
            for(var row:rows){String type=str(row,"event_type");UUID channel=null,endpoint=null;
                if(Set.of("BALANCE_CHANGED","CHANNEL_CHANGED","HEAT_CHANGED").contains(type))channel=uuid(row,"subject_id");
                else if(type.equals("ALLOCATION_READY")){channel=uuid(row,"transfer_channel");endpoint=uuid(row,"transfer_endpoint");}
                else if(type.equals("STOCK_REQUESTED")){channel=uuid(row,"stock_channel");endpoint=uuid(row,"stock_endpoint");}
                else if(type.equals("ENDPOINT_CHANGED"))endpoint=uuid(row,"subject_id");
                if(endpoint!=null){if(!endpoint.equals(uuid(row,"current_endpoint")) || channel!=null && !channel.equals(uuid(row,"current_channel")))continue;channel=uuid(row,"current_channel");}
                if(channel!=null)result.add(new RedisTransport.Hint(type,channel,endpoint));
            }
            return List.copyOf(result);
        });
    }
    public Map<String,Long> health() throws SQLException {
        return db.transaction(c->{
            fenced(c); Map<String,Long> result=new LinkedHashMap<>();
            for(String table:List.of("ct_channels","ct_endpoints","ct_chunk_grants","ct_transfers","ct_quarantine")) result.put(table,num(one(c,"SELECT COUNT(*) AS n FROM "+table+" WHERE cluster_id=?",cluster()),"n"));
            result.put("outbox_pending",num(one(c,"SELECT COUNT(*) AS n FROM ct_outbox WHERE cluster_id=? AND published_at IS NULL",cluster()),"n"));
            result.put("quota_limit",num(one(c,"SELECT quota_limit FROM ct_clusters WHERE cluster_id=?",cluster()),"quota_limit")); return Collections.unmodifiableMap(result);
        });
    }
    public List<PermissionSnapshot> refreshPermissions(List<UUID> ids) throws SQLException {
        require(ids.size()<=256,"invalid_limit");if(ids.isEmpty())return List.of();
        String placeholders=String.join(",",Collections.nCopies(ids.size(),"?"));
        List<Object> parameters=new ArrayList<>();parameters.add(cluster());parameters.add(session().server());parameters.add(session().world());parameters.addAll(ids);
        return db.transaction(c->{
            fenced(c);
            return query(c,"SELECT e.endpoint_id,e.channel_id,e.version AS endpoint_version,e.state,e.pause_reason,c.owner_uuid,c.version AS channel_version,IF(c.status='ACTIVE',IF(c.owner_uuid=e.device_owner,31,COALESCE(m.permissions,0)),0) AS permissions FROM ct_endpoints e LEFT JOIN ct_channels c ON c.cluster_id=e.cluster_id AND c.channel_id=e.channel_id LEFT JOIN ct_members m ON m.cluster_id=e.cluster_id AND m.channel_id=e.channel_id AND m.player_uuid=e.device_owner WHERE e.cluster_id=? AND e.server_id=? AND e.world_id=? AND e.endpoint_id IN ("+placeholders+")",parameters.toArray()).stream().map(r->new PermissionSnapshot(uuid(r,"endpoint_id"),uuid(r,"channel_id"),uuid(r,"owner_uuid"),r.get("channel_version")==null?0:num(r,"channel_version"),num(r,"endpoint_version"),(int)num(r,"permissions"),str(r,"state"),str(r,"pause_reason"))).toList();
        });
    }
    public void thaw(UUID actor,UUID channel,long expected) throws SQLException {
        db.transaction(c->{fenced(c);var row=channelRow(c,channel,actor,Protocol.SETTINGS,true);version(row,expected);require(actor.equals(uuid(row,"owner_uuid")),"owner_required");update(c,"UPDATE ct_channels SET status='ACTIVE' WHERE cluster_id=? AND channel_id=?",cluster(),channel);changed(c,channel);audit(c,actor,"THAW_CHANNEL",channel,"");return null;});
    }
    public Optional<ThermalBuffer.Pending> prepareHeat(UUID exchange,UUID endpoint,UUID capturedChannel,long localEnergy,double localCapacity,double inverseConduction,boolean sending,boolean receiving) throws SQLException {
        require(localEnergy>=0 && Double.isFinite(localCapacity)&&localCapacity>=1&&localCapacity<=1e12 && Double.isFinite(inverseConduction)&&inverseConduction>=1,"invalid_heat");
        return db.transaction(c->{
            fenced(c);var owner=one(c,"SELECT device_owner FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint);require(owner!=null,"endpoint_not_found");var ch=channelRow(c,capturedChannel,uuid(owner,"device_owner"),Protocol.VIEW,false);var e=localEndpoint(c,endpoint,true);require(capturedChannel.equals(uuid(e,"channel_id")),"binding_changed");
            var old=one(c,"SELECT * FROM ct_heat_exchanges WHERE cluster_id=? AND exchange_id=?",cluster(),exchange);
            if(old!=null){require(endpoint.equals(uuid(old,"endpoint_id"))&&capturedChannel.equals(uuid(old,"channel_id")),"idempotency_conflict");return Optional.of(heat(old));}
            BusinessIds.fresh(exchange);
            require(num(one(c,"SELECT COUNT(*) AS n FROM ct_heat_exchanges WHERE cluster_id=? AND endpoint_id=? AND state='PREPARED'",cluster(),endpoint),"n")==0,"heat_exchange_pending");
            update(c,"INSERT IGNORE INTO ct_thermal_pools(cluster_id,channel_id) VALUES(?,?)",cluster(),capturedChannel);
            var pool=one(c,"SELECT * FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),capturedChannel);
            long energy=num(pool,"microjoules");double capacity=((Number)pool.get("capacity")).doubleValue();
            long pending=num(one(c,"SELECT COALESCE(SUM(signed_microjoules),0) AS n FROM ct_heat_exchanges WHERE cluster_id=? AND channel_id=? AND state='PREPARED' AND signed_microjoules>0",cluster(),capturedChannel),"n");
            long preview;try{preview=Math.addExact(energy,pending);}catch(ArithmeticException ex){throw new DomainException("quantity_overflow");}
            double localTemp=localEnergy/1_000_000.0/localCapacity,poolTemp=energy/1_000_000.0/capacity;
            long signed=0,poolAfter=energy;
            if(sending && Protocol.permits((int)num(ch,"permissions"),Protocol.SEND) && localTemp>preview/1_000_000.0/capacity){
                long max=Math.min(1_000_000_000_000L,Math.min(localEnergy,Long.MAX_VALUE-preview));
                signed=HeatModel.exchange(localTemp,localCapacity,preview/1_000_000.0/capacity,capacity,inverseConduction,0.2,0,max).microjoules();
            }else if(receiving && Protocol.permits((int)num(ch,"permissions"),Protocol.RECEIVE) && poolTemp>localTemp){
                long max=Math.min(1_000_000_000_000L,Math.min(energy,Long.MAX_VALUE-localEnergy));
                long amount=HeatModel.exchange(poolTemp,capacity,localTemp,localCapacity,inverseConduction,0.2,0,max).microjoules();signed=-amount;poolAfter=energy-amount;
                if(amount>0)update(c,"UPDATE ct_thermal_pools SET microjoules=? WHERE cluster_id=? AND channel_id=?",poolAfter,cluster(),capturedChannel);
            }
            if(signed==0)return Optional.empty();
            reserveHistory(c);
            update(c,"INSERT INTO ct_heat_exchanges(cluster_id,exchange_id,endpoint_id,channel_id,signed_microjoules,local_before,local_capacity,pool_before,pool_after,epoch) VALUES(?,?,?,?,?,?,?,?,?,?)",cluster(),exchange,endpoint,capturedChannel,signed,localEnergy,localCapacity,energy,poolAfter,session().epoch());
            return Optional.of(new ThermalBuffer.Pending(exchange,capturedChannel,signed,localEnergy,localCapacity,energy,poolAfter));
        });
    }
    private static ThermalBuffer.Pending heat(Map<String,Object> row){return new ThermalBuffer.Pending(uuid(row,"exchange_id"),uuid(row,"channel_id"),num(row,"signed_microjoules"),num(row,"local_before"),((Number)row.get("local_capacity")).doubleValue(),num(row,"pool_before"),num(row,"pool_after"));}
    public void completeHeat(UUID endpoint,ThermalBuffer.Pending pending) throws SQLException {
        db.transaction(c->{
            fenced(c);UUID channel=pending.channel();var owner=one(c,"SELECT device_owner FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint);require(owner!=null,"endpoint_not_found");channelRow(c,channel,uuid(owner,"device_owner"),pending.signedMicrojoules()>0?Protocol.SEND:Protocol.RECEIVE,false);var e=localEndpoint(c,endpoint,false);
            var row=one(c,"SELECT * FROM ct_heat_exchanges WHERE cluster_id=? AND exchange_id=? AND endpoint_id=? FOR UPDATE",cluster(),pending.id(),endpoint);require(row!=null && heat(row).equals(pending),"idempotency_conflict");
            if("COMMITTED".equals(str(row,"state")))return null;require("PREPARED".equals(str(row,"state")),"heat_state_changed");
            require("ACTIVE".equals(str(e,"state")),"endpoint_paused");
            require(channel.equals(uuid(e,"channel_id")),"binding_changed");
            if(pending.signedMicrojoules()>0){var pool=one(c,"SELECT * FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),channel);long next;try{next=Math.addExact(num(pool,"microjoules"),pending.signedMicrojoules());}catch(ArithmeticException ex){throw new DomainException("quantity_overflow");}update(c,"UPDATE ct_thermal_pools SET microjoules=? WHERE cluster_id=? AND channel_id=?",next,cluster(),channel);}
            update(c,"UPDATE ct_heat_exchanges SET state='COMMITTED' WHERE cluster_id=? AND exchange_id=?",cluster(),pending.id());
            event(c,"HEAT_CHANGED",channel,null);return null;
        });
    }
    /** Only a definitive local rejection before application may cancel. Never run this on a timeout. */
    public void cancelHeatBeforeApplication(UUID endpoint,UUID exchange) throws SQLException {
        db.transaction(c->{fenced(c);var hint=one(c,"SELECT channel_id FROM ct_heat_exchanges WHERE cluster_id=? AND exchange_id=? AND endpoint_id=?",cluster(),exchange,endpoint);require(hint!=null,"transfer_not_found");one(c,"SELECT channel_id FROM ct_channels WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),uuid(hint,"channel_id"));localEndpoint(c,endpoint,false);var row=one(c,"SELECT * FROM ct_heat_exchanges WHERE cluster_id=? AND exchange_id=? AND endpoint_id=? FOR UPDATE",cluster(),exchange,endpoint);require(row!=null,"transfer_not_found");if("CANCELLED".equals(str(row,"state")))return null;require("PREPARED".equals(str(row,"state")),"heat_state_changed");var p=heat(row);if(p.signedMicrojoules()<0){var pool=one(c,"SELECT microjoules FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),p.channel());long energy;try{energy=Math.subtractExact(num(pool,"microjoules"),p.signedMicrojoules());}catch(ArithmeticException ex){throw new DomainException("quantity_overflow");}update(c,"UPDATE ct_thermal_pools SET microjoules=? WHERE cluster_id=? AND channel_id=?",energy,cluster(),p.channel());}update(c,"UPDATE ct_heat_exchanges SET state='CANCELLED' WHERE cluster_id=? AND exchange_id=?",cluster(),exchange);audit(c,null,"HEAT_LOCAL_REJECTION",exchange,"definitively rejected before local energy changed; not a timeout refund");return null;});
    }
    public boolean retireEmptySealed(UUID id) throws SQLException {
        return db.transaction(c->{fenced(c);var e=localEndpoint(c,id,false);require("SEALED".equals(str(e,"state")),"endpoint_not_sealed");
            if(one(c,"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",cluster(),id)!=null || one(c,"SELECT transfer_id FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND remaining>0 LIMIT 1",cluster(),id)!=null || one(c,"SELECT exchange_id FROM ct_heat_exchanges WHERE cluster_id=? AND endpoint_id=? AND state='PREPARED' LIMIT 1",cluster(),id)!=null)return false;
            update(c,"UPDATE ct_endpoints SET state='RETIRED',channel_id=NULL,version=version+1,pause_reason='empty_removed' WHERE cluster_id=? AND endpoint_id=?",cluster(),id);audit(c,null,"RETIRE_EMPTY",id,"no local resources, live allocation, heat operation or chunk authorization");return true;
        });
    }
    public Map<String,Long> policy() throws SQLException {return db.transaction(c->{fenced(c);var p=one(c,"SELECT quota_limit,policy_version,history_limit,max_channels,max_endpoints FROM ct_clusters WHERE cluster_id=?",cluster());var result=new LinkedHashMap<String,Long>();for(String key:List.of("quota_limit","policy_version","history_limit","max_channels","max_endpoints"))result.put(key,num(p,key));return Collections.unmodifiableMap(result);});}
    public List<Grant> quotaReductionPlan(int newLimit) throws SQLException {require(newLimit>=0 && newLimit<=64,"invalid_config");return db.transaction(c->{fenced(c);return query(c,"SELECT g.*,e.server_id,e.world_id,e.device_owner,e.channel_id,e.dimension_id,e.pos_x,e.pos_y,e.pos_z,e.version,e.checkpoint,e.pause_reason,e.state AS endpoint_state FROM ct_chunk_grants g JOIN ct_endpoints e ON e.cluster_id=g.cluster_id AND e.endpoint_id=g.endpoint_id WHERE g.cluster_id=? AND g.slot_no>=? ORDER BY g.player_uuid,g.slot_no LIMIT 4096",cluster(),newLimit).stream().map(r->grant(r,endpointMap(r))).toList();});}
    public void historyPolicy(UUID actor,int limit,long expected) throws SQLException {require(limit>=1000 && limit<=10_000_000,"invalid_config");db.transaction(c->{fenced(c);var row=one(c,"SELECT policy_version FROM ct_clusters WHERE cluster_id=? FOR UPDATE",cluster());require(num(row,"policy_version")==expected,"stale_version");update(c,"UPDATE ct_clusters SET history_limit=?,policy_version=policy_version+1 WHERE cluster_id=?",limit,cluster());audit(c,actor,"HISTORY_POLICY",null,"bounded rows per server="+limit);return null;});}
    /** Explicit operator recovery after reviewing external save uncertainty; never timeout-driven. */
    public long reclaimSealed(UUID admin,LocalSnapshot checkpoint,long expected,String confirmation) throws SQLException {
        require("ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY".equals(confirmation),"recovery_confirmation_required");
        require(checkpoint.world().equals(session().world()) && checkpoint.generation()==session().generation(),"journal_generation_conflict");
        require(checkpoint.thermal().microjoules()==0 && checkpoint.thermal().pending()==null && checkpoint.thermal().residual()==0,"sealed_heat_requires_review");
        return db.transaction(c->{fenced(c);
            // Sealing disables deposits and allocation. Read the immutable set of owned
            // channels, lock them in UUID order BEFORE endpoint/transfer rows, then revalidate.
            var channels=new TreeSet<UUID>();for(var deposit:checkpoint.deposits())channels.add(deposit.channel());
            for(var credit:checkpoint.credits())channels.add(credit.channel());
            for(var transfer:query(c,"SELECT channel_id FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='ALLOCATE' AND remaining>0",cluster(),checkpoint.endpoint()))channels.add(uuid(transfer,"channel_id"));
            for(UUID channel:channels){var row=one(c,"SELECT status FROM ct_channels WHERE cluster_id=? AND channel_id=? FOR UPDATE",cluster(),channel);require(row!=null && !"DELETED".equals(str(row,"status")),"channel_not_found");}
            var e=localEndpoint(c,checkpoint.endpoint(),false);version(e,expected);
            require("SEALED".equals(str(e,"state")),"endpoint_not_sealed");require(checkpoint.revision()>=num(e,"checkpoint"),"stale_checkpoint");
            require(one(c,"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",cluster(),checkpoint.endpoint())==null,"revocation_pending");
            require(one(c,"SELECT exchange_id FROM ct_heat_exchanges WHERE cluster_id=? AND endpoint_id=? AND state='PREPARED' LIMIT 1",cluster(),checkpoint.endpoint())==null,"heat_exchange_pending");
            // Reconcile durable LOCAL consumption inside this recovery transaction. A WAL
            // receipt is not permission to promote RESERVED ownership to a spendable credit.
            // The endpoint is already SEALED, and the operator has explicitly accepted the
            // external-save uncertainty. No normal timeout or lease expiry calls this path.
            require(checkpoint.credits().size()<=64,"invalid_checkpoint");
            var seenCredits=new HashSet<UUID>();
            for(var credit:checkpoint.credits()){
                require(seenCredits.add(credit.transaction()),"invalid_checkpoint");
                var row=one(c,"SELECT * FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND transfer_id=? AND kind='ALLOCATE' FOR UPDATE",cluster(),checkpoint.endpoint(),credit.transaction());
                require(row!=null && channels.contains(uuid(row,"channel_id")),"invalid_checkpoint");
                var owned=allocation(c,row);
                require(owned.channel().equals(credit.channel()) && owned.payload().equals(credit.resource()) && owned.amount()==credit.original() && credit.remaining()<=owned.remaining(),"invalid_checkpoint");
                if(Set.of("RESERVED","QUARANTINED").contains(owned.state())){
                    require(credit.remaining()==owned.remaining(),"allocation_not_local");
                }else{
                    require(Set.of("LOCAL","CONSUMED").contains(owned.state()),"invalid_checkpoint");
                    update(c,"UPDATE ct_transfers SET remaining=?,state=? WHERE cluster_id=? AND transfer_id=?",credit.remaining(),credit.remaining()==0?"CONSUMED":"LOCAL",cluster(),credit.transaction());
                }
            }
            update(c,"UPDATE ct_endpoints SET checkpoint=? WHERE cluster_id=? AND endpoint_id=?",checkpoint.revision(),cluster(),checkpoint.endpoint());
            var allocated=query(c,"SELECT * FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='ALLOCATE' AND remaining>0 FOR UPDATE",cluster(),checkpoint.endpoint());
            for(var transfer:allocated){require(channels.contains(uuid(transfer,"channel_id")),"binding_changed");allocation(c,transfer);}
            long reclaimed=0;
            for(var d:checkpoint.deposits()){
                var old=one(c,"SELECT * FROM ct_transfers WHERE cluster_id=? AND transfer_id=?",cluster(),d.transaction());
                if(old!=null){require(checkpoint.endpoint().equals(uuid(old,"endpoint_id")) && d.channel().equals(uuid(old,"channel_id")) && "DEPOSIT".equals(str(old,"kind")) && d.amount()==num(old,"amount"),"idempotency_conflict");
                    var payload=one(c,"SELECT kind,payload FROM ct_resources WHERE cluster_id=? AND resource_id=?",cluster(),uuid(old,"resource_id"));require(d.resource().equals(new Resource(str(payload,"kind"),(byte[])payload.get("payload"))),"idempotency_conflict");continue;}
                UUID resource=resource(c,d.resource());addRecoveredBalance(c,d.channel(),resource,d.amount());reserveHistory(c);
                update(c,"INSERT INTO ct_transfers(cluster_id,transfer_id,endpoint_id,channel_id,resource_id,amount,kind,state,epoch,remaining) VALUES(?,?,?,?,?,?,'DEPOSIT','COMMITTED',?,0)",cluster(),d.transaction(),checkpoint.endpoint(),d.channel(),resource,d.amount(),session().epoch());reclaimed=Math.addExact(reclaimed,d.amount());
            }
            for(var t:allocated){long amount=num(t,"remaining");addRecoveredBalance(c,uuid(t,"channel_id"),uuid(t,"resource_id"),amount);reclaimed=Math.addExact(reclaimed,amount);
                update(c,"UPDATE ct_transfers SET remaining=0,state='CONSUMED' WHERE cluster_id=? AND transfer_id=?",cluster(),uuid(t,"transfer_id"));}
            update(c,"UPDATE ct_endpoints SET state='RETIRED',channel_id=NULL,version=version+1,pause_reason='reclaimed_by_operator' WHERE cluster_id=? AND endpoint_id=?",cluster(),checkpoint.endpoint());
            update(c,"UPDATE ct_quarantine SET state='RESOLVED' WHERE cluster_id=? AND endpoint_id=? AND state='OPEN'",cluster(),checkpoint.endpoint());
            audit(c,admin,"RECLAIM_SEALED",checkpoint.endpoint(),confirmation+"; original channels; quantitative sum="+reclaimed+" (mixed units)");return reclaimed;
        });
    }
    private void addRecoveredBalance(Connection c,UUID channel,UUID resource,long amount) throws SQLException {
        update(c,"INSERT IGNORE INTO ct_balances(cluster_id,channel_id,resource_id,amount) VALUES(?,?,?,0)",cluster(),channel,resource);
        long before=num(one(c,"SELECT amount FROM ct_balances WHERE cluster_id=? AND channel_id=? AND resource_id=? FOR UPDATE",cluster(),channel,resource),"amount");
        long after;try{after=Math.addExact(before,amount);}catch(ArithmeticException ex){throw new DomainException("quantity_overflow");}
        update(c,"UPDATE ct_balances SET amount=? WHERE cluster_id=? AND channel_id=? AND resource_id=?",after,cluster(),channel,resource);event(c,"BALANCE_CHANGED",channel,null);
    }
    public void quarantineEndpoint(UUID id,String reason) throws SQLException {
        db.transaction(c->{fenced(c);localEndpoint(c,id,false);update(c,"UPDATE ct_endpoints SET state='QUARANTINED',pause_reason=? WHERE cluster_id=? AND endpoint_id=?",reason,cluster(),id);update(c,"UPDATE ct_chunk_grants SET state='PAUSED',reason=? WHERE cluster_id=? AND endpoint_id=?",reason,cluster(),id);quarantine(c,id,null,reason,"Local journal must be reviewed before reopening the endpoint");return null;});
    }
    /** Experimental AE service advertisement; no IGrid or IGridNode crosses a process boundary. */
    public List<AeNetwork> advertiseAe(UUID endpoint,UUID capturedChannel,UUID network,int used,boolean active,String controller) throws SQLException {
        require(used>=0 && used<=4096 && Set.of("NO_CONTROLLER","CONTROLLER_ONLINE","CONTROLLER_CONFLICT").contains(controller),"invalid_ae_network");
        return db.transaction(c->{
            fenced(c);var owner=one(c,"SELECT device_owner FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint);require(owner!=null,"endpoint_not_found");channelRow(c,capturedChannel,uuid(owner,"device_owner"),Protocol.VIEW,false);var e=localEndpoint(c,endpoint,true);require(capturedChannel.equals(uuid(e,"channel_id")),"binding_changed");
            require(Arrays.asList(str(one(c,"SELECT capabilities FROM ct_servers WHERE cluster_id=? AND server_id=?",cluster(),session().server()),"capabilities").split(",")).contains("cross_tesseract:ae_proxy_v1"),"resource_unsupported");
            update(c,"INSERT INTO ct_ae_networks(cluster_id,endpoint_id,channel_id,server_id,network_id,epoch,used_channels,active,controller_state,lease_until) VALUES(?,?,?,?,?,?,?,?,?,TIMESTAMPADD(SECOND,6,CURRENT_TIMESTAMP(6))) ON DUPLICATE KEY UPDATE channel_id=VALUES(channel_id),network_id=VALUES(network_id),epoch=VALUES(epoch),used_channels=VALUES(used_channels),active=VALUES(active),controller_state=VALUES(controller_state),lease_until=VALUES(lease_until)",cluster(),endpoint,capturedChannel,session().server(),network,session().epoch(),used,active,controller);
            // Duplicate bridges on one native grid advertise the same identity. One row per grid is returned.
            var rows=query(c,"SELECT a.server_id,a.network_id,MAX(a.used_channels) AS used_channels,MIN(a.active) AS active,MAX(a.controller_state) AS controller_state FROM ct_ae_networks a JOIN ct_servers s ON s.cluster_id=a.cluster_id AND s.server_id=a.server_id JOIN ct_endpoints e ON e.cluster_id=a.cluster_id AND e.endpoint_id=a.endpoint_id JOIN ct_channels ch ON ch.cluster_id=a.cluster_id AND ch.channel_id=a.channel_id LEFT JOIN ct_members m ON m.cluster_id=a.cluster_id AND m.channel_id=a.channel_id AND m.player_uuid=e.device_owner WHERE a.cluster_id=? AND a.channel_id=? AND a.lease_until>CURRENT_TIMESTAMP(6) AND s.lease_until>CURRENT_TIMESTAMP(6) AND FIND_IN_SET('cross_tesseract:ae_proxy_v1',s.capabilities)>0 AND a.epoch=s.fencing_epoch AND e.state='ACTIVE' AND e.channel_id=a.channel_id AND ch.status='ACTIVE' AND (ch.owner_uuid=e.device_owner OR (m.permissions & 1)=1) GROUP BY a.server_id,a.network_id ORDER BY a.server_id,a.network_id LIMIT 65",cluster(),capturedChannel);
            require(rows.size()<=64,"ae_peer_limit");return rows.stream().map(r->new AeNetwork(str(r,"server_id"),uuid(r,"network_id"),(int)num(r,"used_channels"),num(r,"active")==1,str(r,"controller_state"))).toList();
        });
    }
    public List<Map<String,Object>> trace(UUID admin,UUID id,String entity) throws SQLException {
        String table=switch(entity) { case "channel" -> "ct_channels"; case "endpoint" -> "ct_endpoints"; case "transfer" -> "ct_transfers"; case "quarantine" -> "ct_quarantine"; default -> throw new DomainException("invalid_entity"); };
        String column=switch(entity) { case "channel" -> "channel_id"; case "endpoint" -> "endpoint_id"; case "transfer" -> "transfer_id"; default -> "record_id"; };
        return db.transaction(c->{fenced(c); audit(c,admin,"DIAGNOSTIC_QUERY",id,entity); return query(c,"SELECT * FROM "+table+" WHERE cluster_id=? AND "+column+"=? LIMIT 16",cluster(),id);});
    }
    public void releaseOfflineRevocation(UUID admin,UUID endpoint) throws SQLException {
        db.transaction(c->{
            fenced(c); var e=one(c,"SELECT * FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint); require(e!=null,"endpoint_not_found"); guard(c,uuid(e,"device_owner"));
            var g=one(c,"SELECT *,runtime_until IS NULL OR runtime_until<TIMESTAMPADD(SECOND,-20,CURRENT_TIMESTAMP(6)) AS expired FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=? FOR UPDATE",cluster(),endpoint);
            require(g!=null && !Boolean.TRUE.equals(g.get("desired")),"revocation_pending");
            var s=one(c,"SELECT lease_until<TIMESTAMPADD(SECOND,-20,CURRENT_TIMESTAMP(6)) AS expired FROM ct_servers WHERE cluster_id=? AND server_id=? FOR UPDATE",cluster(),str(e,"server_id"));
            require(num(g,"expired")==1 && num(s,"expired")==1,"old_lease_unconfirmed");
            update(c,"DELETE FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint); audit(c,admin,"OFFLINE_REVOCATION_RELEASE",endpoint,"server and runtime leases expired with 20-second safety margin"); return null;
        });
    }
    public void recoverEndpoint(UUID admin,UUID endpoint,long expected,String confirmation) throws SQLException {
        require("ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY".equals(confirmation),"recovery_confirmation_required");
        db.transaction(c->{fenced(c); var e=localEndpoint(c,endpoint,false); version(e,expected); require("QUARANTINED".equals(str(e,"state")),"not_quarantined"); update(c,"UPDATE ct_endpoints SET state='ACTIVE',pause_reason='',version=version+1 WHERE cluster_id=? AND endpoint_id=?",cluster(),endpoint); update(c,"UPDATE ct_chunk_grants SET state='PAUSED',reason='awaiting_ticket_restore' WHERE cluster_id=? AND endpoint_id=? AND desired=TRUE",cluster(),endpoint); audit(c,admin,"RECOVER_ENDPOINT",endpoint,confirmation+"; operator reviewed external world save and ledger"); event(c,"ENDPOINT_CHANGED",endpoint,session().server()); return null;});
    }
    private Map<String,Object> endpointMap(Map<String,Object> row) { var copy=new HashMap<>(row); copy.put("state",row.get("endpoint_state")); return copy; }
    private static Grant grant(Map<String,Object> g,Map<String,Object> e) { return new Grant(uuid(g,"endpoint_id"),uuid(g,"player_uuid"),(int)num(g,"slot_no"),str(g,"state"),Boolean.TRUE.equals(g.get("desired")),num(g,"policy_version"),str(g,"reason"),endpoint(e)); }
    private static Channel channel(Map<String,Object> r) { return new Channel(uuid(r,"channel_id"),uuid(r,"owner_uuid"),str(r,"name"),num(r,"version"),str(r,"status"),(int)num(r,"permissions")); }
    private static Endpoint endpoint(Map<String,Object> r) { return new Endpoint(uuid(r,"endpoint_id"),str(r,"server_id"),uuid(r,"world_id"),uuid(r,"device_owner"),uuid(r,"channel_id"),str(r,"dimension_id"),(int)num(r,"pos_x"),(int)num(r,"pos_y"),(int)num(r,"pos_z"),num(r,"version"),str(r,"state"),num(r,"checkpoint"),str(r,"pause_reason")); }
    private void operation(Connection c,UUID request,UUID actor,String kind,UUID subject,String result) throws SQLException { update(c,"INSERT INTO ct_operations(cluster_id,operation_id,actor_uuid,kind,subject_id,result_code) VALUES(?,?,?,?,?,?)",cluster(),request,actor,kind,subject,result); }
    private void audit(Connection c,UUID actor,String action,UUID subject,String details) throws SQLException { update(c,"INSERT INTO ct_audit(cluster_id,actor_uuid,action,subject_id,details) VALUES(?,?,?,?,?)",cluster(),actor,action,subject,details); }
    private void quarantine(Connection c,UUID endpoint,UUID transfer,String reason,String details) throws SQLException {
        if(one(c,"SELECT record_id FROM ct_quarantine WHERE cluster_id=? AND endpoint_id=? AND transfer_id<=>? AND reason=? AND state='OPEN' LIMIT 1",cluster(),endpoint,transfer,reason)!=null)return;
        update(c,"INSERT INTO ct_quarantine(cluster_id,record_id,endpoint_id,transfer_id,reason,details) VALUES(?,?,?,?,?,?)",cluster(),UUID.randomUUID(),endpoint,transfer,reason,details);
    }
    /** Bounded periodic cleanup. Live ownership and unresolved quarantine are NEVER expired. UUIDv4
     * legacy transactions remain until an explicit coordinated archive; new keys reject old replay. */
    private void reserveHistory(Connection c) throws SQLException {
        // An ignored duplicate acquires an S lock; concurrent channel batches then
        // deadlock upgrading that same row to X. Acquire X on first access instead.
        update(c,"INSERT INTO ct_history_buckets(cluster_id,server_id,used) VALUES(?,?,0) ON DUPLICATE KEY UPDATE used=used",cluster(),session().server());
        long maximum=num(one(c,"SELECT history_limit FROM ct_clusters WHERE cluster_id=?",cluster()),"history_limit");
        require(update(c,"UPDATE ct_history_buckets SET used=used+1 WHERE cluster_id=? AND server_id=? AND used<?",cluster(),session().server(),maximum)==1,"history_limit");
    }
    public void sweepHistory() throws SQLException {
        db.transaction(c->{fenced(c);
            int removed=update(c,"DELETE FROM ct_transfers WHERE cluster_id=? AND endpoint_id IN (SELECT endpoint_id FROM ct_endpoints WHERE cluster_id=? AND server_id=?) AND remaining=0 AND state IN ('COMMITTED','CONSUMED') AND SUBSTRING(transfer_id,15,1)='7' AND created_at<TIMESTAMPADD(DAY,-30,CURRENT_TIMESTAMP(6)) ORDER BY created_at LIMIT 512",cluster(),cluster(),session().server());
            removed+=update(c,"DELETE FROM ct_heat_exchanges WHERE cluster_id=? AND endpoint_id IN (SELECT endpoint_id FROM ct_endpoints WHERE cluster_id=? AND server_id=?) AND state IN ('COMMITTED','CANCELLED') AND SUBSTRING(exchange_id,15,1)='7' AND created_at<TIMESTAMPADD(DAY,-30,CURRENT_TIMESTAMP(6)) ORDER BY created_at LIMIT 512",cluster(),cluster(),session().server());
            removed+=update(c,"DELETE FROM ct_stock_requests WHERE cluster_id=? AND endpoint_id IN (SELECT endpoint_id FROM ct_endpoints WHERE cluster_id=? AND server_id=?) AND expires_at<TIMESTAMPADD(DAY,-30,CURRENT_TIMESTAMP(6)) AND SUBSTRING(request_id,15,1)='7' ORDER BY created_at LIMIT 512",cluster(),cluster(),session().server());
            if(removed>0)update(c,"UPDATE ct_history_buckets SET used=GREATEST(0,used-?) WHERE cluster_id=? AND server_id=?",removed,cluster(),session().server());
            update(c,"DELETE FROM ct_outbox WHERE cluster_id=? AND published_at IS NOT NULL AND created_at<TIMESTAMPADD(DAY,-7,CURRENT_TIMESTAMP(6)) ORDER BY id LIMIT 512",cluster());
            update(c,"DELETE FROM ct_inbox WHERE cluster_id=? AND received_at<TIMESTAMPADD(DAY,-7,CURRENT_TIMESTAMP(6)) ORDER BY received_at LIMIT 512",cluster());
            update(c,"DELETE FROM ct_operations WHERE cluster_id=? AND SUBSTRING(operation_id,15,1)='7' AND created_at<TIMESTAMPADD(DAY,-30,CURRENT_TIMESTAMP(6)) ORDER BY created_at LIMIT 512",cluster());
            update(c,"DELETE FROM ct_invites WHERE cluster_id=? AND expires_at<TIMESTAMPADD(DAY,-30,CURRENT_TIMESTAMP(6)) ORDER BY expires_at LIMIT 512",cluster());
            update(c,"DELETE FROM ct_audit WHERE cluster_id=? AND created_at<TIMESTAMPADD(DAY,-180,CURRENT_TIMESTAMP(6)) ORDER BY id LIMIT 512",cluster());
            update(c,"DELETE FROM ct_quarantine WHERE cluster_id=? AND state<>'OPEN' AND created_at<TIMESTAMPADD(DAY,-180,CURRENT_TIMESTAMP(6)) ORDER BY created_at LIMIT 512",cluster());return null;
        });
    }
    private void event(Connection c,String type,UUID subject,String target) throws SQLException { update(c,"INSERT INTO ct_outbox(cluster_id,event_id,event_type,subject_id,target_server) VALUES(?,?,?,?,?)",cluster(),UUID.randomUUID(),type,subject,target); }
    @Override public void close() { db.close(); }
}
