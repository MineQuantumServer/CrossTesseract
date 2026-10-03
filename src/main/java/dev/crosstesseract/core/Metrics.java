package dev.crosstesseract.core;

import java.util.*;
import java.util.concurrent.atomic.*;

public final class Metrics {
    private final long[] tickSamples=new long[2048], deliverySamples=new long[2048], sqlSamples=new long[2048];
    private long ticks,deliveries,sqlCalls;
    public final LongAdder transactions=new LongAdder(), retries=new LongAdder(), errors=new LongAdder(), rejected=new LongAdder(), duplicate=new LongAdder(), quarantined=new LongAdder();
    public synchronized void tick(long nanos) { tickSamples[(int)(ticks++%tickSamples.length)]=Math.max(0,nanos); }
    public synchronized void delivered(long nanos) { deliverySamples[(int)(deliveries++%deliverySamples.length)]=Math.max(0,nanos); }
    public synchronized void sql(long nanos) { sqlSamples[(int)(sqlCalls++%sqlSamples.length)]=Math.max(0,nanos); }
    public synchronized void resetWindow(){ticks=deliveries=sqlCalls=0;Arrays.fill(tickSamples,0);Arrays.fill(deliverySamples,0);Arrays.fill(sqlSamples,0);}
    public synchronized Map<String,Number> snapshot(int endpoints,int active,int queue,int tickets) {
        var map=new LinkedHashMap<String,Number>();
        map.put("registered_loaded_endpoints",endpoints);map.put("active_endpoints",active);map.put("worker_queue",queue);map.put("actual_tickets",tickets);
        map.put("transactions",transactions.sum());map.put("errors",errors.sum());map.put("queue_rejected",rejected.sum());map.put("quarantined",quarantined.sum());
        quantiles(map,"tick_ms",tickSamples,ticks);quantiles(map,"delivery_ms",deliverySamples,deliveries);quantiles(map,"sql_ms",sqlSamples,sqlCalls);
        return Collections.unmodifiableMap(map);
    }
    public static void quantiles(Map<String,Number> map,String prefix,long[] samples,long count) {
        long[] sorted=Arrays.copyOf(samples,(int)Math.min(count,samples.length));Arrays.sort(sorted);
        for(int p:new int[]{50,95,99}) map.put(prefix+"_p"+p,sorted.length==0?0:sorted[Math.min(sorted.length-1,(int)Math.ceil(sorted.length*p/100.0)-1)]/1_000_000.0);
        map.put(prefix+"_samples",Math.min(count,samples.length));
    }
}
