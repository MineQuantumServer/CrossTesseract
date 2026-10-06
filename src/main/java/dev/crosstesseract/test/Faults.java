package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.DomainException;
import java.sql.SQLException;
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
    private static final String REGISTRATION_PHASE="after_restore_wal";
    private static final String UNHYDRATED_SEAL_PHASE="before_unhydrated_seal";
    private static final String BEFORE_REGISTER_SQL="before_register_sql",AFTER_REGISTER_SQL="after_register_sql";
    private static final Set<String> phases=Set.of("after_send_wal","after_deposit","after_allocation","after_receive_wal","after_local_sql",REGISTRATION_PHASE,UNHYDRATED_SEAL_PHASE,BEFORE_REGISTER_SQL,AFTER_REGISTER_SQL);
    private static final int MAX_HOLDS=16;
    private static final long HOLD_NANOS=TimeUnit.SECONDS.toNanos(5);
    private static final Object admission=new Object();
    private static final ConcurrentHashMap<UUID,Hold> holds=new ConcurrentHashMap<>();
    private static boolean isolated(String cluster){return cluster!=null && (cluster.startsWith("dev_")||cluster.startsWith("test_"));}
    public static void arm(String cluster,String phase,UUID endpoint){DomainException.require(Boolean.getBoolean("cross_tesseract.testHarness") && isolated(cluster) && phases.contains(phase) && endpoint!=null,"forbidden");armed.set(new Point(phase,endpoint));}
    /** One pending hold per endpoint and at most sixteen endpoints across this JVM. */
    public static Hold hold(String cluster,String phase,UUID endpoint){
        return hold(cluster,phase,endpoint,false);
    }
    /** Inject failure to obtain a checkpoint SQL acknowledgement after the restored WAL is durable.
     * This is an explicit test SQLException, not an actual database outage or an asset refund. */
    public static Hold holdLostRegistrationConfirmation(String cluster,UUID endpoint){
        return hold(cluster,REGISTRATION_PHASE,endpoint,true);
    }
    /** One checked failure before the unhydrated SQL seal attempt; the database stays running. */
    public static Hold holdFailUnhydratedSealOnce(String cluster,UUID endpoint){
        return hold(cluster,UNHYDRATED_SEAL_PHASE,endpoint,true);
    }
    /** New endpoint: fail before registerEndpoint starts; no SQL registration was committed. */
    public static Hold holdFailedBeforeSqlRegistration(String cluster,UUID endpoint){return hold(cluster,BEFORE_REGISTER_SQL,endpoint,true);}
    /** Fail to return registration after its real SQL commit; this is not a network COMMIT ACK fault. */
    public static Hold holdLostAfterSqlRegistration(String cluster,UUID endpoint){return hold(cluster,AFTER_REGISTER_SQL,endpoint,true);}
    private static Hold hold(String cluster,String phase,UUID endpoint,boolean failSqlOnRelease){
        DomainException.require((Boolean.getBoolean("cross_tesseract.testHarness")||Boolean.getBoolean("cross_tesseract.compatTests")) && isolated(cluster) && phases.contains(phase) && endpoint!=null,"forbidden");
        synchronized(admission){
            for(var hold:holds.values())hold.expireIfNeeded();
            DomainException.require(!holds.containsKey(endpoint),"test_hold_pending");
            DomainException.require(holds.size()<MAX_HOLDS,"test_hold_limit");
            var hold=new Hold(phase,endpoint,failSqlOnRelease);holds.put(endpoint,hold);return hold;
        }
    }
    public static int activeHolds(){synchronized(admission){for(var hold:holds.values())hold.expireIfNeeded();return holds.size();}}
    /** Called by backend workers only. With no armed dev fault this performs no wait or IO. */
    public static void hit(String phase,UUID endpoint){
        crash(phase,endpoint);
        var hold=holds.get(endpoint);if(hold!=null && hold.phase.equals(phase))hold.awaitRelease();
    }
    /** Registration worker only; retains the checked SQLException path of a failed SQL confirmation. */
    public static void registrationHit(UUID endpoint) throws SQLException {
        crash(REGISTRATION_PHASE,endpoint);
        var hold=holds.get(endpoint);
        if(hold!=null && hold.phase.equals(REGISTRATION_PHASE) && hold.awaitRelease() && hold.claimSqlFailure()){
            CrossTesseract.LOG.warn("CT_TEST_FAULT after_restore_wal endpoint={} injected=SQL_confirmation_failure actual_database_outage=false",endpoint);
            throw new SQLException("CT_TEST_CHECKPOINT_CONFIRMATION_LOST after_restore_wal","08006");
        }
    }
    /** Closing worker only. This tests retained SQL intent, not a real database outage. */
    public static void unhydratedSealHit(UUID endpoint) throws SQLException {
        crash(UNHYDRATED_SEAL_PHASE,endpoint);
        var hold=holds.get(endpoint);
        if(hold!=null && hold.phase.equals(UNHYDRATED_SEAL_PHASE) && hold.awaitRelease() && hold.claimSqlFailure()){
            CrossTesseract.LOG.warn("CT_TEST_FAULT before_unhydrated_seal endpoint={} injected=SQL_seal_attempt_failure actual_database_outage=false",endpoint);
            throw new SQLException("CT_TEST_SQL_SEAL_ATTEMPT_FAILED before_unhydrated_seal","08006");
        }
    }
    public static void registrationBeforeSqlHit(UUID endpoint) throws SQLException {registrationBoundaryHit(endpoint,BEFORE_REGISTER_SQL,false);}
    public static void registrationAfterSqlHit(UUID endpoint) throws SQLException {registrationBoundaryHit(endpoint,AFTER_REGISTER_SQL,true);}
    private static void registrationBoundaryHit(UUID endpoint,String phase,boolean committed) throws SQLException {
        crash(phase,endpoint);var hold=holds.get(endpoint);
        if(hold!=null && hold.phase.equals(phase) && hold.awaitRelease() && hold.claimSqlFailure()){
            CrossTesseract.LOG.warn("CT_TEST_FAULT {} endpoint={} injected=SQL_registration_boundary_failure register_sql_committed={} actual_database_outage=false",phase,endpoint,committed);
            throw new SQLException("CT_TEST_REGISTRATION_BOUNDARY_FAILURE "+phase,"08006");
        }
    }
    private static void crash(String phase,UUID endpoint){
        var point=armed.get();if(point!=null && point.phase().equals(phase) && point.endpoint().equals(endpoint) && armed.compareAndSet(point,null)){CrossTesseract.LOG.error("CT_FAULT {} endpoint={} halt=97",phase,endpoint);Runtime.getRuntime().halt(97);}
    }
    public static final class Hold implements AutoCloseable {
        private final String phase;
        private final UUID endpoint;
        private final boolean failSqlOnRelease;
        private final long deadline=System.nanoTime()+HOLD_NANOS;
        private final CountDownLatch resume=new CountDownLatch(1);
        // 0 armed, 1 reached, 2 released, 3 timed out. Only the worker waits.
        private final AtomicInteger state=new AtomicInteger();
        private final AtomicInteger sqlFailure=new AtomicInteger(); // 0 absent, 1 explicit release, 2 injected.
        private volatile boolean reached;
        private Hold(String phase,UUID endpoint,boolean failSqlOnRelease){this.phase=phase;this.endpoint=endpoint;this.failSqlOnRelease=failSqlOnRelease;}
        public boolean reached(){expireIfNeeded();return reached;}
        public boolean timedOut(){expireIfNeeded();return state.get()==3;}
        public boolean failureInjected(){return sqlFailure.get()==2;}
        public void release(){release(true);}
        private void release(boolean explicit){
            expireIfNeeded();
            for(int current=state.get();current<2;current=state.get())if(state.compareAndSet(current,2)){
                if(explicit && current==1 && failSqlOnRelease)sqlFailure.compareAndSet(0,1);
                break;
            }
            resume.countDown();remove();
        }
        @Override public void close(){release();}
        private void remove(){synchronized(admission){holds.remove(endpoint,this);}}
        private void expireIfNeeded(){if(System.nanoTime()-deadline>=0)timeout();}
        private void timeout(){
            for(int current=state.get();current<2;current=state.get())if(state.compareAndSet(current,3)){resume.countDown();remove();break;}
        }
        private boolean claimSqlFailure(){return state.get()==2 && sqlFailure.compareAndSet(1,2);}
        private boolean awaitRelease(){
            expireIfNeeded();if(!state.compareAndSet(0,1))return false;reached=true;
            try{if(!resume.await(Math.max(0,deadline-System.nanoTime()),TimeUnit.NANOSECONDS))timeout();}
            catch(InterruptedException interrupted){Thread.currentThread().interrupt();}
            finally{release(false);}
            return true;
        }
    }
    private Faults(){}
}
