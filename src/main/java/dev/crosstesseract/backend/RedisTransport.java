package dev.crosstesseract.backend;

import dev.crosstesseract.core.Models.Event;
import java.net.URI;
import java.util.*;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;
import redis.clients.jedis.*;
import redis.clients.jedis.params.*;

/** Redis holds hints only. Each destination gets its own stream; MySQL polling recovers trimmed/lost hints. */
public final class RedisTransport implements AutoCloseable {
    private final JedisPool pool;
    private final String prefix;
    public RedisTransport(BackendConfig config) {
        GenericObjectPoolConfig<Jedis> pc=new GenericObjectPoolConfig<>();
        pc.setMaxTotal(3); pc.setMaxIdle(2); pc.setMinIdle(0); pc.setMaxWait(java.time.Duration.ofMillis(1000));
        var tls=new javax.net.ssl.SSLParameters();tls.setEndpointIdentificationAlgorithm("HTTPS");
        pool=new JedisPool(pc,URI.create(config.redisUri()),1500,1500,(javax.net.ssl.SSLSocketFactory)javax.net.ssl.SSLSocketFactory.getDefault(),tls,javax.net.ssl.HttpsURLConnection.getDefaultHostnameVerifier());
        prefix="ct:"+config.cluster()+":";
    }
    public boolean healthy() { try(var j=pool.getResource()) { return "PONG".equals(j.ping()); } }
    public void online(String server,UUID session,long epoch) {
        try(var j=pool.getResource()) { j.setex(prefix+"online:"+server,12,session+":"+epoch); }
    }
    public void dispatch(Authority authority,int limit) throws java.sql.SQLException {
        var events=authority.unpublished(limit);if(events.isEmpty())return;
        try(var j=pool.getResource();var pipeline=j.pipelined()) {
            var results=new ArrayList<Response<StreamEntryID>>();
            for(Event event:events){String key=prefix+"events:"+Objects.toString(event.target(),"cluster");
                results.add(pipeline.xadd(key,XAddParams.xAddParams().maxLen(4096).approximateTrimming(),Map.of("event",event.event().toString(),"type",event.type(),"subject",event.subject().toString())));}
            pipeline.sync();for(var result:results)result.get();
        }
        // Crash here repeats hints. One SQL transaction marks the successfully published batch.
        authority.published(events.stream().map(Event::id).toList());
    }
    public int drain(Authority authority,String server) throws java.sql.SQLException {
        int received=0;
        try(var j=pool.getResource()) {
            String key=prefix+"events:"+server, group="server-"+server, consumer=authority.session().boot().toString();
            try { j.xgroupCreate(key,group,new StreamEntryID("0-0"),true); }
            catch(redis.clients.jedis.exceptions.JedisDataException e) { if(!e.getMessage().contains("BUSYGROUP")) throw e; }
            // Recover pending messages abandoned by a dead consumer. Duplicates are durable inbox entries.
            var recovered=j.xautoclaim(key,group,consumer,15_000,new StreamEntryID("0-0"),XAutoClaimParams.xAutoClaimParams().count(64));
            for(var entry:recovered.getValue()) { authority.receiveEvent(UUID.fromString(entry.getFields().get("event"))); j.xack(key,group,entry.getID()); received++; }
            var messages=j.xreadGroup(group,consumer,XReadGroupParams.xReadGroupParams().count(64),Map.of(key,StreamEntryID.UNRECEIVED_ENTRY));
            if(messages!=null) for(var stream:messages) for(var entry:stream.getValue()) {
                authority.receiveEvent(UUID.fromString(entry.getFields().get("event"))); j.xack(key,group,entry.getID()); received++;
            }
            // ACK above means a hint was recorded. It NEVER acknowledges a world inventory delivery.
            // Cluster stream is a lossy invalidation hint; authoritative refresh also runs every 2 seconds.
            int removed=0;
            for(var old:j.xinfoConsumers(key,group))if(!old.getName().equals(consumer) && old.getIdle()>60_000 && old.getPending()==0 && removed++<16)j.xgroupDelConsumer(key,group,old.getName());
        }
        return received;
    }
    @Override public void close() { pool.close(); }
}
