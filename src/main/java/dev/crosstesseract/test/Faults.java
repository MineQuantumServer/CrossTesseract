package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.DomainException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Opt-in isolated console fault injection. No production or player packet entrypoint. */
public final class Faults {
    private record Point(String phase,UUID endpoint){}
    private static final AtomicReference<Point> armed=new AtomicReference<>();
    private static final Set<String> phases=Set.of("after_send_wal","after_deposit","after_allocation","after_receive_wal","after_local_sql");
    private static final int MAX_HOLDS=16;
    private static final long HOLD_NANOS=TimeUnit.SECONDS.toNanos(5);
    private static final Object admission=new Object();
    private static final ConcurrentHashMap<UUID,Hold> holds=new ConcurrentHashMap<>();
    private static boolean isolated(String cluster){return cluster!=null && (cluster.startsWith("dev_")||cluster.startsWith("test_"));}
    public static void arm(String cluster,String phase,UUID endpoint){DomainException.require(Boolean.getBoolean("cross_tesseract.testHarness") && isolated(cluster) && phases.contains(phase) && endpoint!=null,"forbidden");armed.set(new Point(phase,endpoint));}
    /** One pending hold per endpoint and at most sixteen endpoints across this JVM. */
    public static Hold hold(String cluster,String phase,UUID endpoint){
        DomainException.require((Boolean.getBoolean("cross_tesseract.testHarness")||Boolean.getBoolean("cross_tesseract.compatTests")) && isolated(cluster) && phases.contains(phase) && endpoint!=null,"forbidden");
        synchronized(admission){
            for(var hold:holds.values())hold.expireIfNeeded();
            DomainException.require(!holds.containsKey(endpoint),"test_hold_pending");
            DomainException.require(holds.size()<MAX_HOLDS,"test_hold_limit");
            var hold=new Hold(phase,endpoint);holds.put(endpoint,hold);return hold;
        }
    }
    public static int activeHolds(){synchronized(admission){for(var hold:holds.values())hold.expireIfNeeded();return holds.size();}}
    /** Called by backend workers only. With no armed dev fault this performs no wait or IO. */
    public static void hit(String phase,UUID endpoint){
        var point=armed.get();if(point!=null && point.phase().equals(phase) && point.endpoint().equals(endpoint) && armed.compareAndSet(point,null)){CrossTesseract.LOG.error("CT_FAULT {} endpoint={} halt=97",phase,endpoint);Runtime.getRuntime().halt(97);}
        var hold=holds.get(endpoint);if(hold!=null && hold.phase.equals(phase))hold.awaitRelease();
    }
    public static final class Hold implements AutoCloseable {
        private final String phase;
        private final UUID endpoint;
        private final long deadline=System.nanoTime()+HOLD_NANOS;
        private final CountDownLatch resume=new CountDownLatch(1);
        // 0 armed, 1 reached, 2 released, 3 timed out. Only the worker waits.
        private final AtomicInteger state=new AtomicInteger();
        private volatile boolean reached;
        private Hold(String phase,UUID endpoint){this.phase=phase;this.endpoint=endpoint;}
        public boolean reached(){expireIfNeeded();return reached;}
        public boolean timedOut(){expireIfNeeded();return state.get()==3;}
        public void release(){
            expireIfNeeded();
            for(int current=state.get();current<2;current=state.get())if(state.compareAndSet(current,2))break;
            resume.countDown();remove();
        }
        @Override public void close(){release();}
        private void remove(){synchronized(admission){holds.remove(endpoint,this);}}
        private void expireIfNeeded(){if(System.nanoTime()-deadline>=0)timeout();}
        private void timeout(){
            for(int current=state.get();current<2;current=state.get())if(state.compareAndSet(current,3)){resume.countDown();remove();break;}
        }
        private void awaitRelease(){
            expireIfNeeded();if(!state.compareAndSet(0,1))return;reached=true;
            try{if(!resume.await(Math.max(0,deadline-System.nanoTime()),TimeUnit.NANOSECONDS))timeout();}
            catch(InterruptedException interrupted){Thread.currentThread().interrupt();}
            finally{release();}
        }
    }
    private Faults(){}
}
