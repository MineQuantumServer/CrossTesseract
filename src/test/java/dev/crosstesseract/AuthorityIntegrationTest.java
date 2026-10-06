package dev.crosstesseract;

import dev.crosstesseract.backend.*;
import dev.crosstesseract.core.*;
import dev.crosstesseract.core.Models.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class AuthorityIntegrationTest {
    private final List<Authority> servers=new ArrayList<>();
    private final List<BackendConfig> configs=new ArrayList<>();
    private final UUID owner=BusinessIds.next(), member=BusinessIds.next(), outsider=BusinessIds.next();
    private UUID channel;
    private final String cluster="test_"+BusinessIds.next().toString().replace("-","");
    @BeforeAll void start() throws Exception {
        assumeTrue(Boolean.getBoolean("ct.integration"),"requires real isolated MySQL and Redis; run -Dct.integration=true");
        var executor=Executors.newFixedThreadPool(3);
        try {
            List<Future<?>> jobs=new ArrayList<>();
            for(int i=0;i<3;i++) {
                var cfg=new BackendConfig(true,cluster,"test-"+i,"jdbc:mysql://127.0.0.1:13306/cross_tesseract?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectTimeout=1000&socketTimeout=3000","ct_dev","ct_dev_only","redis://127.0.0.1:16379",2,4,200,128,32,256);
                configs.add(cfg); var a=new Authority(cfg); servers.add(a);
                jobs.add(executor.submit(()->{ try { a.join(BusinessIds.next(),BusinessIds.next(),Protocol.BASE); } catch(Exception e) { throw new RuntimeException(e); } }));
            }
            for(var job:jobs) job.get(30,TimeUnit.SECONDS);
        } finally { executor.shutdownNow(); }
        channel=servers.getFirst().createChannel(owner,"三服集成",BusinessIds.next());
    }
    @BeforeEach void renew() throws Exception { for(var server:servers) server.heartbeat(); }
    @AfterAll void finish() { for(var server:servers) { try { server.stopClean(); } catch(Exception ignored) {} server.close(); } }
    private Endpoint device(int server,UUID player,int x,int z) throws Exception {
        var a=servers.get(server); var s=a.session(); UUID id=BusinessIds.next();
        return a.registerEndpoint(new Endpoint(id,s.server(),s.world(),player,null,"minecraft:overworld",x,64,z,1,"ACTIVE",0,""),0);
    }
    private Endpoint bound(int server,UUID player,int x) throws Exception {
        var e=device(server,player,x,server*16); return servers.get(server).bind(player,e.id(),e.version(),channel);
    }
    private static void rejected(String code,org.junit.jupiter.api.function.Executable action) { assertEquals(code,assertThrows(DomainException.class,action).code()); }
    @Test void invitationsArePrivateConcurrentIdempotentAndTransfersHaveOneOwner() throws Exception {
        var a=servers.get(0); var b=servers.get(1); var c=servers.get(2);
        UUID id=a.createChannel(owner,"invitations",BusinessIds.next());
        rejected("forbidden",()->c.authorize(outsider,id,Protocol.VIEW));
        long version=a.authorize(owner,id,Protocol.VIEW).version();
        UUID invite=b.invite(owner,id,version,member,false,BusinessIds.next());
        rejected("forbidden",()->c.answerInvitation(outsider,invite,true));
        var executor=Executors.newFixedThreadPool(2);
        try {
            var first=executor.submit(()->{c.answerInvitation(member,invite,true);return 0;});
            var second=executor.submit(()->{b.answerInvitation(member,invite,true);return 0;});
            first.get();second.get();
        } finally {executor.shutdownNow();}
        assertEquals(List.of(member),a.members(owner,id));
        version=a.authorize(owner,id,Protocol.VIEW).version();
        UUID transfer=a.invite(owner,id,version,member,true,BusinessIds.next());
        c.answerInvitation(member,transfer,true);
        c.answerInvitation(member,transfer,true);
        assertEquals(member,b.authorize(member,id,Protocol.VIEW).owner());
        rejected("owner_cannot_leave",()->b.removeMember(member,id,b.authorize(member,id,Protocol.VIEW).version(),member));
        c.removeMember(member,id,c.authorize(member,id,Protocol.VIEW).version(),owner);
        rejected("forbidden",()->a.authorize(owner,id,Protocol.SEND));
    }
    @Test void threeServersRaceForTwoPersistentSlots() throws Exception {
        UUID player=BusinessIds.next(); List<Endpoint> endpoints=new ArrayList<>(); for(int i=0;i<3;i++) endpoints.add(device(i,player,10+i,20));
        var executor=Executors.newFixedThreadPool(3); List<Future<String>> futures=new ArrayList<>();
        try {
            var barrier=new CyclicBarrier(3);
            for(int i=0;i<3;i++) { final int n=i; futures.add(executor.submit(()->{barrier.await();try {servers.get(n).reserveChunk(player,endpoints.get(n).id(),BusinessIds.next(),false);return "OK";}catch(DomainException e){return e.code();}})); }
            List<String> outcomes=new ArrayList<>(); for(var f:futures)outcomes.add(f.get(10,TimeUnit.SECONDS));
            assertEquals(2,Collections.frequency(outcomes,"OK")); assertEquals(1,Collections.frequency(outcomes,"quota_exhausted"));
            assertEquals(2,servers.get(2).grants(player).size());
            for(var grant:servers.get(0).grants(player)) {
                int index=Integer.parseInt(grant.location().server().substring(5)); var server=servers.get(index);
                // Different request still returns the existing endpoint slot, rather than allocating another slot.
                assertEquals(grant.slot(),server.reserveChunk(player,grant.endpoint(),BusinessIds.next(),false).slot());
                server.confirmChunk(grant.endpoint(),true);
                servers.get(2).requestChunkOff(player,grant.endpoint(),false);
                assertEquals(2,server.grants(player).size());
                rejected("device_owner_required",()->servers.get(2).requestChunkOff(outsider,grant.endpoint(),false));
                server.confirmChunkOff(grant.endpoint());
                break;
            }
            assertEquals(1,servers.get(0).grants(player).size());
        } finally {executor.shutdownNow();}
    }
    @Test void sameChunkCountsTwiceAndInstallFailureCompensates() throws Exception {
        UUID player=BusinessIds.next(); var a=servers.get(0); var e1=device(0,player,100,100); var e2=device(0,player,101,101);
        UUID request=BusinessIds.next(); a.reserveChunk(player,e1.id(),request,false); a.reserveChunk(player,e1.id(),request,false); a.reserveChunk(player,e2.id(),BusinessIds.next(),false);
        assertEquals(2,a.grants(player).size()); a.confirmChunk(e2.id(),false); assertEquals(1,a.grants(player).size());
        a.confirmChunk(e1.id(),true); a.requestChunkOff(player,e1.id(),false); assertEquals(1,a.grants(player).size()); a.confirmChunkOff(e1.id()); assertTrue(a.grants(player).isEmpty());
    }
    @Test void integerBalancesPartialDeliveryAndDuplicatesConserveAcrossThreeServers() throws Exception {
        var a=servers.get(0); var b=servers.get(1); var c=servers.get(2);
        var sender=bound(0,owner,200); var rxB=bound(1,owner,201); var rxC=bound(2,owner,202);
        var resource=new Resource(Protocol.FE,new byte[0]); UUID tx=BusinessIds.next(); long huge=(1L<<53)+123;
        a.deposit(tx,sender.id(),channel,resource,huge); a.deposit(tx,sender.id(),channel,resource,huge);
        b.demand(rxB.id(),channel,Protocol.FE,600); c.demand(rxC.id(),channel,Protocol.FE,600);
        long received=0; var allocations=new ArrayList<Allocation>();
        for(int i=0;i<10;i++) {
            for(var pair:List.of(Map.entry(b,rxB),Map.entry(c,rxC))) {
                var result=pair.getKey().allocate(BusinessIds.next(),pair.getValue().id(),channel,Protocol.FE,100);
                if(result.isPresent()) { var grant=result.orElseThrow(); allocations.add(grant); received+=grant.amount(); pair.getKey().markLocal(grant.endpoint(),grant.id()); }
            }
        }
        assertTrue(allocations.stream().anyMatch(x->x.endpoint().equals(rxB.id()))); assertTrue(allocations.stream().anyMatch(x->x.endpoint().equals(rxC.id())));
        var allocation=allocations.getFirst(); var server=allocation.endpoint().equals(rxB.id())?b:c;
        assertEquals(allocation.id(),server.allocate(allocation.id(),allocation.endpoint(),channel,Protocol.FE,100).orElseThrow().id());
        long balance=a.database().transaction(conn->Sql.num(Sql.one(conn,"SELECT SUM(amount) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",cluster,channel),"n"));
        assertEquals(huge,Math.addExact(balance,received));
        server.checkpoint(allocation.endpoint(),1,Map.of(allocation.id(),allocation.amount()-3));
        server.checkpoint(allocation.endpoint(),1,Map.of(allocation.id(),allocation.amount()-3));
        rejected("invalid_checkpoint",()->server.checkpoint(allocation.endpoint(),2,Map.of(allocation.id(),allocation.amount())));
        rejected("quantity_overflow",()->a.deposit(BusinessIds.next(),sender.id(),channel,resource,Long.MAX_VALUE));
        long unchanged=a.database().transaction(conn->Sql.num(Sql.one(conn,"SELECT SUM(amount) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",cluster,channel),"n"));
        assertEquals(balance,unchanged);
    }
    @Test void directedStockIntentIsPrivateIdempotentAndUsesExclusiveFairAllocations() throws Exception {
        var a=servers.get(0);var b=servers.get(1);UUID isolated=a.createChannel(owner,"directed-stock",BusinessIds.next());
        var sender=bound(0,owner,880001);sender=a.bind(owner,sender.id(),sender.version(),isolated);var rx=bound(1,owner,880002);rx=b.bind(owner,rx.id(),rx.version(),isolated);
        var wanted=new Resource(Protocol.ITEM,new byte[]{11});var other=new Resource(Protocol.ITEM,new byte[]{22});a.deposit(BusinessIds.next(),sender.id(),isolated,wanted,10);a.deposit(BusinessIds.next(),sender.id(),isolated,other,20);
        UUID endpoint=rx.id();long version=rx.version();UUID request=BusinessIds.next();var intent=b.requestStock(owner,request,endpoint,isolated,version,wanted,5,false);
        assertEquals(intent,b.requestStock(owner,request,endpoint,isolated,version,wanted,5,false));assertEquals(intent.id(),b.requestStock(owner,BusinessIds.next(),endpoint,isolated,version,wanted,2,true).id());
        rejected("forbidden",()->b.stock(outsider,endpoint,isolated,null));rejected("stale_version",()->b.requestStock(owner,BusinessIds.next(),endpoint,isolated,version-1,wanted,1,false));rejected("idempotency_conflict",()->b.requestStock(owner,request,endpoint,isolated,version,other,5,false));
        var view=b.stock(owner,endpoint,isolated,null);assertEquals(30,view.rows().stream().mapToLong(Models.StockRow::remoteAvailable).sum());assertEquals(0,view.rows().stream().mapToLong(Models.StockRow::reserved).sum());
        b.demand(endpoint,isolated,Protocol.ITEM,64);UUID tx=BusinessIds.next();var grant=b.allocate(tx,endpoint,isolated,Protocol.ITEM,2).orElseThrow();assertEquals(wanted,grant.payload());assertEquals(2,grant.amount());assertEquals(grant,b.allocate(tx,endpoint,isolated,Protocol.ITEM,2).orElseThrow());
        view=b.stock(owner,endpoint,isolated,null);assertEquals(28,view.rows().stream().mapToLong(Models.StockRow::remoteAvailable).sum());assertEquals(2,view.rows().stream().mapToLong(Models.StockRow::reserved).sum());assertEquals(3,view.requests().getFirst().remaining());assertEquals("PARTIAL",view.requests().getFirst().state());
        b.cancelStock(owner,endpoint,isolated,request);b.cancelStock(owner,endpoint,isolated,request);assertEquals(2,b.stock(owner,endpoint,isolated,null).rows().stream().mapToLong(Models.StockRow::reserved).sum(),"cancel does not refund an already owned allocation");
        b.markLocal(endpoint,tx);assertEquals(2,b.stock(owner,endpoint,isolated,null).rows().stream().mapToLong(Models.StockRow::ledgerLocal).sum());
        UUID empty=a.createChannel(owner,"private-resource-metadata",BusinessIds.next());var stranger=device(0,owner,880003,0);stranger=a.bind(owner,stranger.id(),stranger.version(),empty);UUID otherEndpoint=stranger.id(),resource=view.rows().getFirst().resource();rejected("forbidden",()->a.stockResource(owner,otherEndpoint,empty,resource));
    }
    @Test void stockPagingPendingCapExpirationAndBindingCancelAreBounded() throws Exception {
        var a=servers.get(0);UUID isolated=a.createChannel(owner,"stock-bounds",BusinessIds.next());var sender=bound(0,owner,880011);sender=a.bind(owner,sender.id(),sender.version(),isolated);var rx=bound(0,owner,880012);rx=a.bind(owner,rx.id(),rx.version(),isolated);UUID endpoint=rx.id();long version=rx.version();
        for(int i=0;i<10;i++)a.deposit(BusinessIds.next(),sender.id(),isolated,new Resource(Protocol.ITEM,new byte[]{(byte)(100+i)}),1);
        var first=a.stock(owner,endpoint,isolated,null);assertEquals(8,first.rows().size());assertNotNull(first.next());var second=a.stock(owner,endpoint,isolated,first.next());assertEquals(2,second.rows().size());assertNull(second.next());var keys=new HashSet<UUID>();first.rows().forEach(r->keys.add(r.resource()));second.rows().forEach(r->keys.add(r.resource()));assertEquals(10,keys.size());
        var payload=first.rows().getFirst().payload();for(int i=0;i<8;i++)a.requestStock(owner,BusinessIds.next(),endpoint,isolated,version,payload,1,false);rejected("stock_request_limit",()->a.requestStock(owner,BusinessIds.next(),endpoint,isolated,version,payload,1,false));
        a.database().transaction(c->{Sql.update(c,"UPDATE ct_stock_requests SET expires_at=TIMESTAMPADD(SECOND,-1,CURRENT_TIMESTAMP(6)) WHERE cluster_id=? AND endpoint_id=?",cluster,endpoint);return null;});assertTrue(a.stock(owner,endpoint,isolated,null).requests().stream().allMatch(r->r.state().equals("EXPIRED")));
        var current=a.requestStock(owner,BusinessIds.next(),endpoint,isolated,version,payload,1,false);a.bind(owner,endpoint,version,null);assertEquals("CANCELLED",a.database().transaction(c->Sql.str(Sql.one(c,"SELECT state FROM ct_stock_requests WHERE cluster_id=? AND request_id=?",cluster,current.id()),"state")));
    }
    @Test void outboxSurvivesUnpublishedCommitAndRedisIsNeverAssetAuthority() throws Exception {
        var a=servers.get(0);var b=servers.get(1);
        UUID isolated=a.createChannel(owner,"outbox",BusinessIds.next());
        assertTrue(a.unpublished(256).stream().anyMatch(e->isolated.equals(e.subject())));
        try(var redis=new RedisTransport(configs.get(0))) { assertTrue(redis.healthy()); redis.dispatch(a,256); redis.dispatch(b,256); redis.drain(a,a.session().server()); redis.drain(a,a.session().server()); }
        assertTrue(a.unpublished(256).isEmpty());
        UUID event=BusinessIds.next(); assertTrue(a.receiveEvent(event));assertFalse(a.receiveEvent(event));assertTrue(b.receiveEvent(event));
    }
    @Test void duplicateServerIdIsRejectedAndCloneCannotClaimAnotherLocation() throws Exception {
        var a=servers.get(0);
        try(var impostor=new Authority(configs.get(0))) { rejected("duplicate_server_id",()->impostor.join(a.session().world(),BusinessIds.next(),Protocol.BASE)); }
        var e=device(0,owner,300,300); var bad=new Endpoint(e.id(),e.server(),e.world(),e.owner(),null,e.dimension(),301,e.y(),e.z(),1,"ACTIVE",0,"");
        rejected("cloned_endpoint",()->a.registerEndpoint(bad,0));
    }
    @Test void quarantinedAllocationsCannotBeReactivatedByCheckpointOrWalRestore() throws Exception {
        var a=servers.get(0);var tx=bound(0,owner,970101);var rx=bound(0,owner,970102);var resource=new Resource(Protocol.FE,new byte[0]);
        UUID isolated=a.createChannel(owner,"quarantined-credit",BusinessIds.next());tx=a.bind(owner,tx.id(),tx.version(),isolated);rx=a.bind(owner,rx.id(),rx.version(),isolated);
        a.deposit(BusinessIds.next(),tx.id(),isolated,resource,99);a.demand(rx.id(),isolated,Protocol.FE,99);var allocation=a.allocate(BusinessIds.next(),rx.id(),isolated,Protocol.FE,99).orElseThrow();a.quarantineAllocation(rx.id(),allocation.id(),"test_invalid_registry");
        var credit=new dev.crosstesseract.core.LocalSnapshot.Credit(allocation.id(),isolated,resource,99,99);var snapshot=new LocalSnapshot(rx.id(),a.session().world(),a.session().generation(),1,List.of(),List.of(credit));
        assertTrue(a.restoreSnapshot(snapshot).credits().isEmpty());a.checkpoint(rx.id(),1,Map.of(credit.transaction(),99L));assertEquals("QUARANTINED",a.allocations(rx.id()).getFirst().state());
        UUID id=rx.id();rejected("quarantined_allocation",()->a.checkpoint(id,2,Map.of(credit.transaction(),98L)));
    }
    @Test void redisPendingConsumersDuplicateAndReorderedHintsAreRoutedAndIdempotent() throws Exception {
        var a=servers.get(0);var b=servers.get(1);String key="ct:"+cluster+":events:"+a.session().server(),other="ct:"+cluster+":events:"+b.session().server(),group="server-"+a.session().server();
        UUID first=BusinessIds.next(),second=BusinessIds.next(),remote=BusinessIds.next();
        try(var j=new redis.clients.jedis.Jedis("127.0.0.1",16379);var transport=new RedisTransport(configs.get(0))){
            try{j.xgroupCreate(key,group,new redis.clients.jedis.StreamEntryID("0-0"),true);}catch(redis.clients.jedis.exceptions.JedisDataException e){if(!e.getMessage().contains("BUSYGROUP"))throw e;}
            var ids=new ArrayList<redis.clients.jedis.StreamEntryID>();
            for(UUID id:List.of(second,first,first))ids.add(j.xadd(key,redis.clients.jedis.params.XAddParams.xAddParams(),Map.of("event",id.toString())));
            j.xadd(other,redis.clients.jedis.params.XAddParams.xAddParams(),Map.of("event",remote.toString()));
            j.xreadGroup(group,"crashed-consumer",redis.clients.jedis.params.XReadGroupParams.xReadGroupParams().count(64),Map.of(key,redis.clients.jedis.StreamEntryID.UNRECEIVED_ENTRY));
            j.xclaim(key,group,"crashed-consumer",0,redis.clients.jedis.params.XClaimParams.xClaimParams().idle(16_000),ids.toArray(redis.clients.jedis.StreamEntryID[]::new));
            assertEquals(3,transport.drain(a,a.session().server()));assertEquals(0,transport.drain(a,a.session().server()));
            long inbox=a.database().connection(c->Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_inbox WHERE cluster_id=? AND server_id=? AND event_id IN (?,?)",cluster,a.session().server(),first,second),"n"));assertEquals(2,inbox);
            assertTrue(b.receiveEvent(remote),"A cannot record or acknowledge B's targeted stream");assertEquals(1,transport.drain(b,b.session().server()));
            assertEquals(0,j.xpending(key,group).getTotal());
            j.xtrim(key,0,false);assertEquals(0,transport.drain(a,a.session().server()));
            assertNotNull(a.authorize(owner,channel,Protocol.VIEW),"a lost hint cannot delete committed authority");
        }
    }
    @Test void passiveHeatUsesExclusivePreparedOwnershipAndNeverRefundsTimeouts() throws Exception {
        var a=servers.get(0);var b=servers.get(1);var tx=bound(0,owner,450);var rx=bound(1,owner,451);
        long source=1_000_000_000_000L;UUID first=BusinessIds.next();
        var send=a.prepareHeat(first,tx.id(),channel,source,10_000,1,true,false).orElseThrow();
        assertTrue(send.signedMicrojoules()>0 && send.signedMicrojoules()<source);
        assertEquals(send,a.prepareHeat(first,tx.id(),channel,source,10_000,1,true,false).orElseThrow());
        assertTrue(b.prepareHeat(BusinessIds.next(),rx.id(),channel,0,10_000,1,false,true).isEmpty(),"prepared outgoing heat is not spendable before the WAL handoff");
        a.completeHeat(tx.id(),send);a.completeHeat(tx.id(),send);
        long pool=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT microjoules FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=?",cluster,channel),"microjoules"));
        assertEquals(send.signedMicrojoules(),pool);
        var take=b.prepareHeat(BusinessIds.next(),rx.id(),channel,0,10_000,1,false,true).orElseThrow();assertTrue(take.signedMicrojoules()<0);
        long reserved=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT microjoules FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=?",cluster,channel),"microjoules"));
        assertEquals(source,Math.addExact(Math.addExact(source-send.signedMicrojoules(),reserved),-take.signedMicrojoules()));
        rejected("heat_exchange_pending",()->b.prepareHeat(BusinessIds.next(),rx.id(),channel,0,10_000,1,false,true));
        b.cancelHeatBeforeApplication(rx.id(),take.id());b.cancelHeatBeforeApplication(rx.id(),take.id());
        assertEquals(pool,a.database().transaction(c->Sql.num(Sql.one(c,"SELECT microjoules FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=?",cluster,channel),"microjoules")).longValue());
        rejected("heat_state_changed",()->b.completeHeat(rx.id(),take));
        var take2=b.prepareHeat(BusinessIds.next(),rx.id(),channel,0,10_000,1,false,true).orElseThrow();
        var local=new ThermalBuffer();local.apply(take2);assertTrue(local.frozen());b.completeHeat(rx.id(),take2);b.completeHeat(rx.id(),take2);local.committed(take2.id());
        pool=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT microjoules FROM ct_thermal_pools WHERE cluster_id=? AND channel_id=?",cluster,channel),"microjoules"));
        assertEquals(source,source-send.signedMicrojoules()+pool+local.energy());
    }
    @Test void profileAndPacketQuantumAvoidWrongVoltageAndFractionalAmps() throws Exception {
        // Exercise actual SQL matching, using FE kind to keep the three base sessions' negotiated capabilities.
        var a=servers.get(0);var b=servers.get(1);var c=servers.get(2);UUID ch=a.createChannel(owner,"packet_profile",BusinessIds.next());
        var tx=device(0,owner,470,0);tx=a.bind(owner,tx.id(),tx.version(),ch);
        var first=device(1,owner,471,0);first=b.bind(owner,first.id(),first.version(),ch);
        var second=device(2,owner,472,0);second=c.bind(owner,second.id(),second.version(),ch);
        var voltage32=new Resource(Protocol.FE,new byte[]{32});var voltage128=new Resource(Protocol.FE,new byte[]{(byte)128});
        a.deposit(BusinessIds.next(),tx.id(),ch,voltage32,320);a.deposit(BusinessIds.next(),tx.id(),ch,voltage128,256);
        b.demand(first.id(),ch,Protocol.FE,1000,voltage128.hash(),128);c.demand(second.id(),ch,Protocol.FE,1000,voltage32.hash(),32);
        Optional<Allocation> one=Optional.empty(),two=Optional.empty();for(int i=0;i<3;i++){
            if(one.isEmpty())one=b.allocate(BusinessIds.next(),first.id(),ch,Protocol.FE,200);
            if(two.isEmpty())two=c.allocate(BusinessIds.next(),second.id(),ch,Protocol.FE,90);
        }
        assertEquals(128,one.orElseThrow().amount());assertEquals(voltage128,one.orElseThrow().payload());
        assertEquals(64,two.orElseThrow().amount());assertEquals(voltage32,two.orElseThrow().payload());
    }
    @Test void sealedRecoveryUsesOriginalOwnershipAndCannotRepeatReclaimedAssets() throws Exception {
        var a=servers.getFirst();UUID ch=a.createChannel(owner,"sealed_recovery",BusinessIds.next());var initial=device(0,owner,900,0);var e=a.bind(owner,initial.id(),initial.version(),ch);var r=new Resource(Protocol.FE,new byte[0]);UUID deposited=BusinessIds.next(),pending=BusinessIds.next();
        a.deposit(deposited,e.id(),ch,r,50);a.demand(e.id(),ch,Protocol.FE,10);var allocated=a.allocate(BusinessIds.next(),e.id(),ch,Protocol.FE,10).orElseThrow();a.markLocal(e.id(),allocated.id());a.checkpoint(e.id(),1,Map.of(allocated.id(),6L));a.sealEndpoint(e.id(),"removed");
        var snapshot=new LocalSnapshot(e.id(),a.session().world(),a.session().generation(),2,List.of(new LocalSnapshot.Deposit(deposited,ch,r,50),new LocalSnapshot.Deposit(pending,ch,r,20)),List.of(new LocalSnapshot.Credit(allocated.id(),ch,r,10,3)));
        long version=a.endpoint(e.id()).version();rejected("recovery_confirmation_required",()->a.reclaimSealed(owner,snapshot,version,""));
        assertEquals(23,a.reclaimSealed(owner,snapshot,version,"ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY"));assertEquals("RETIRED",a.endpoint(e.id()).state());
        rejected("stale_version",()->a.reclaimSealed(owner,snapshot,version,"ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY"));
        long balance=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT SUM(amount) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",cluster,ch),"n"));assertEquals(63,balance,"70 accepted - 7 externally extracted, including late WAL consumption; committed deposit not replayed");
        var replacement=device(0,owner,900,0);assertNotEquals(e.id(),replacement.id());
    }
    @Test void sealedReservedReceiptIsNeverPromotedByCheckpointOrReclaimedWithUnprovenConsumption() throws Exception {
        var a=servers.getFirst();UUID ch=a.createChannel(owner,"sealed_reserved",BusinessIds.next());var initial=device(0,owner,901,0);var e=a.bind(owner,initial.id(),initial.version(),ch);var r=new Resource(Protocol.FE,new byte[0]);
        a.deposit(BusinessIds.next(),e.id(),ch,r,50);a.demand(e.id(),ch,Protocol.FE,10);var allocation=a.allocate(BusinessIds.next(),e.id(),ch,Protocol.FE,10).orElseThrow();
        rejected("allocation_not_local",()->a.checkpoint(e.id(),1,Map.of(allocation.id(),10L)));
        a.sealEndpoint(e.id(),"removed");long version=a.endpoint(e.id()).version();
        var impossible=new LocalSnapshot(e.id(),a.session().world(),a.session().generation(),1,List.of(),List.of(new LocalSnapshot.Credit(allocation.id(),ch,r,10,9)));
        rejected("allocation_not_local",()->a.reclaimSealed(owner,impossible,version,"ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY"));
        assertEquals("RESERVED",a.allocations(e.id()).getFirst().state());assertEquals(10,a.allocations(e.id()).getFirst().remaining());
        var valid=new LocalSnapshot(e.id(),a.session().world(),a.session().generation(),1,List.of(),List.of(new LocalSnapshot.Credit(allocation.id(),ch,r,10,10)));
        assertEquals(10,a.reclaimSealed(owner,valid,version,"ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY"));
        assertEquals("RETIRED",a.endpoint(e.id()).state());
        long balance=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT SUM(amount) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",cluster,ch),"n"));assertEquals(50,balance);
    }
    @Test void quotaReductionIsDeterministicAndRetainsSlotsUntilRevocationAck() throws Exception {
        var a=servers.getFirst();UUID player=BusinessIds.next();var first=device(0,player,910,0);var second=device(1,player,911,0);a.reserveChunk(player,first.id(),BusinessIds.next(),false);servers.get(1).reserveChunk(player,second.id(),BusinessIds.next(),false);long version=a.policy().get("policy_version");
        try{assertTrue(a.quotaReductionPlan(1).stream().anyMatch(g->g.endpoint().equals(second.id())));a.lowerQuota(owner,1,version);var grants=a.grants(player);assertEquals(2,grants.size());assertTrue(grants.stream().anyMatch(g->g.slot()==1 && !g.desired() && g.state().equals("REVOKING")));servers.get(1).confirmChunkOff(second.id());assertEquals(1,a.grants(player).size());}
        finally{a.lowerQuota(owner,2,a.policy().get("policy_version"));}
    }
    @Test void historyAdmissionIsAtomicRollsBackAndOldPrunedKeysCannotReplay() throws Exception {
        var a=servers.get(0);UUID isolated=a.createChannel(owner,"history",BusinessIds.next());var initial=device(0,owner,800,0);var e=a.bind(owner,initial.id(),initial.version(),isolated);var r=new Resource(Protocol.FE,new byte[0]);UUID first=BusinessIds.next(),second=BusinessIds.next();
        long original=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT history_limit FROM ct_clusters WHERE cluster_id=?",cluster),"history_limit"));
        long used=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT COALESCE((SELECT used FROM ct_history_buckets WHERE cluster_id=? AND server_id=?),0) AS n",cluster,a.session().server()),"n"));
        try{
            a.database().transaction(c->{Sql.update(c,"UPDATE ct_clusters SET history_limit=? WHERE cluster_id=?",used+1,cluster);return null;});
            a.deposit(first,e.id(),isolated,r,10);a.deposit(first,e.id(),isolated,r,10);
            rejected("history_limit",()->a.deposit(second,e.id(),isolated,r,20));
            assertTrue(a.trace(owner,second,"transfer").isEmpty());
            long old=System.currentTimeMillis()-java.time.Duration.ofDays(31).toMillis();UUID expired=new UUID((old<<16)|0x7000L,0x8000000000000001L);
            rejected("operation_expired",()->a.deposit(expired,e.id(),isolated,r,20));
            a.database().transaction(c->{Sql.update(c,"UPDATE ct_transfers SET transfer_id=?,created_at=TIMESTAMPADD(DAY,-31,CURRENT_TIMESTAMP(6)) WHERE cluster_id=? AND transfer_id=?",expired,cluster,first);return null;});
            assertFalse(a.trace(owner,expired,"transfer").isEmpty());a.sweepHistory();assertTrue(a.trace(owner,expired,"transfer").isEmpty());
            rejected("operation_expired",()->a.deposit(expired,e.id(),isolated,r,10));
            long after=a.database().transaction(c->Sql.num(Sql.one(c,"SELECT used FROM ct_history_buckets WHERE cluster_id=? AND server_id=?",cluster,a.session().server()),"used"));assertEquals(used,after);
        }finally{a.database().transaction(c->{Sql.update(c,"UPDATE ct_clusters SET history_limit=? WHERE cluster_id=?",original,cluster);return null;});}
    }
    @Test void mysqlDeadlocksAreRetriedWithoutRepeatingCommittedMutations() throws Exception {
        var a=servers.get(0);var b=servers.get(1);UUID one=BusinessIds.next(),two=BusinessIds.next();
        a.database().transaction(c->{Sql.update(c,"INSERT INTO ct_player_guards(cluster_id,player_uuid) VALUES(?,?),(?,?)",cluster,one,cluster,two);return null;});
        var barrier=new CyclicBarrier(2);var firstAttempts=new java.util.concurrent.atomic.AtomicInteger();var secondAttempts=new java.util.concurrent.atomic.AtomicInteger();var pool=Executors.newFixedThreadPool(2);
        try{
            var f=pool.submit(()->a.database().transaction(c->{Sql.one(c,"SELECT player_uuid FROM ct_player_guards WHERE cluster_id=? AND player_uuid=? FOR UPDATE",cluster,one);if(firstAttempts.getAndIncrement()==0)await(barrier);Sql.one(c,"SELECT player_uuid FROM ct_player_guards WHERE cluster_id=? AND player_uuid=? FOR UPDATE",cluster,two);return 1;}));
            var g=pool.submit(()->b.database().transaction(c->{Sql.one(c,"SELECT player_uuid FROM ct_player_guards WHERE cluster_id=? AND player_uuid=? FOR UPDATE",cluster,two);if(secondAttempts.getAndIncrement()==0)await(barrier);Sql.one(c,"SELECT player_uuid FROM ct_player_guards WHERE cluster_id=? AND player_uuid=? FOR UPDATE",cluster,one);return 1;}));
            assertEquals(1,f.get(15,TimeUnit.SECONDS));assertEquals(1,g.get(15,TimeUnit.SECONDS));assertTrue(firstAttempts.get()+secondAttempts.get()>=3,"at least one actual InnoDB deadlock was retried");
        }finally{pool.shutdownNow();}
    }
    private static void await(CyclicBarrier barrier) throws java.sql.SQLException {try{barrier.await(5,TimeUnit.SECONDS);}catch(Exception e){throw new java.sql.SQLException(e);}}
    @Test void staleSessionIsFencedAndQuotaDoesNotExpireWithLease() throws Exception {
        var cfg=new BackendConfig(true,cluster,"stale-fixture","jdbc:mysql://127.0.0.1:13306/cross_tesseract?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectTimeout=1000&socketTimeout=3000","ct_dev","ct_dev_only","redis://127.0.0.1:16379",2,4,200,128,32,256);
        try(var stale=new Authority(cfg);var replacement=new Authority(cfg)){
            UUID world=BusinessIds.next();stale.join(world,BusinessIds.next(),Protocol.BASE);
            UUID id=BusinessIds.next();var e=new Endpoint(id,cfg.server(),world,owner,null,"minecraft:overworld",600,64,0,1,"ACTIVE",0,"");stale.registerEndpoint(e,0);stale.reserveChunk(owner,id,BusinessIds.next(),false);
            stale.database().transaction(c->{Sql.update(c,"UPDATE ct_servers SET lease_until=TIMESTAMPADD(SECOND,-1,CURRENT_TIMESTAMP(6)) WHERE cluster_id=? AND server_id=?",cluster,cfg.server());return null;});
            replacement.join(world,BusinessIds.next(),Protocol.BASE);
            rejected("session_fenced",stale::heartbeat);
            assertEquals(1,replacement.grants(owner).stream().filter(g->g.endpoint().equals(id)).count());
            assertEquals("QUARANTINED",replacement.endpoint(id).state());replacement.stopClean();
        }
    }
}
