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
    public record Hint(String type,UUID channel,UUID endpoint){}
    public record DrainResult(int directed,List<Hint> hints){public DrainResult{hints=List.copyOf(hints);}}
    private final Set<String> groups=new HashSet<>();
    private final Map<String,StreamEntryID> clusterCursors=new HashMap<>();
    private final Map<String,Long> claimAt=new HashMap<>();
    public int drain(Authority authority,String server) throws java.sql.SQLException {return drainHints(authority,server).directed();}
    public synchronized DrainResult drainHints(Authority authority,String server) throws java.sql.SQLException {
        try(var j=pool.getResource()){
            String key=prefix+"events:"+server,group="server-"+server,consumer=authority.session().boot().toString();
            if(groups.add(group))try{j.xgroupCreate(key,group,new StreamEntryID("0-0"),true);}catch(redis.clients.jedis.exceptions.JedisDataException error){if(!error.getMessage().contains("BUSYGROUP")){groups.remove(group);throw error;}}
            var directed=new ArrayList<redis.clients.jedis.resps.StreamEntry>();long now=System.nanoTime();
            if(now>=claimAt.getOrDefault(server,0L)){claimAt.put(server,now+java.util.concurrent.TimeUnit.SECONDS.toNanos(5));
                var recovered=j.xautoclaim(key,group,consumer,15_000,new StreamEntryID("0-0"),XAutoClaimParams.xAutoClaimParams().count(64));directed.addAll(recovered.getValue());
                int removed=0;for(var old:j.xinfoConsumers(key,group))if(!old.getName().equals(consumer)&&old.getIdle()>60_000&&old.getPending()==0&&removed++<16)j.xgroupDelConsumer(key,group,old.getName());
            }
            var messages=j.xreadGroup(group,consumer,XReadGroupParams.xReadGroupParams().count(64),Map.of(key,StreamEntryID.UNRECEIVED_ENTRY));
            if(messages!=null)for(var stream:messages)directed.addAll(stream.getValue());
            String clusterKey=prefix+"events:cluster";StreamEntryID cursor=clusterCursors.get(server);
            if(cursor==null){var last=j.xrevrange(clusterKey,StreamEntryID.MAXIMUM_ID,StreamEntryID.MINIMUM_ID,1);cursor=last.isEmpty()?new StreamEntryID("0-0"):last.getFirst().getID();clusterCursors.put(server,cursor);}
            var broadcast=new ArrayList<redis.clients.jedis.resps.StreamEntry>();
            var clusterMessages=j.xread(XReadParams.xReadParams().count(64),Map.of(clusterKey,cursor));
            if(clusterMessages!=null)for(var stream:clusterMessages)broadcast.addAll(stream.getValue());
            var events=new ArrayList<UUID>();for(var entry:directed)parseEvent(entry).ifPresent(events::add);for(var entry:broadcast)parseEvent(entry).ifPresent(events::add);
            var hints=authority.receiveEvents(events);
            // Durable inbox ACK acknowledges ONLY hints; it says nothing about world delivery.
            if(!directed.isEmpty())j.xack(key,group,directed.stream().map(redis.clients.jedis.resps.StreamEntry::getID).toArray(StreamEntryID[]::new));
            if(!broadcast.isEmpty())clusterCursors.put(server,broadcast.getLast().getID());
            return new DrainResult(directed.size(),hints);
        }catch(redis.clients.jedis.exceptions.JedisDataException error){if(error.getMessage()!=null&&error.getMessage().contains("NOGROUP"))groups.remove("server-"+server);throw error;}
    }
    private static Optional<UUID> parseEvent(redis.clients.jedis.resps.StreamEntry entry){String event=entry.getFields().get("event");if(event==null||event.length()!=36)return Optional.empty();try{return Optional.of(UUID.fromString(event));}catch(IllegalArgumentException error){return Optional.empty();}}
    @Override public void close() { pool.close(); }
}
