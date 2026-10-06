package dev.crosstesseract.backend;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.*;
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;

public final class Sql implements AutoCloseable {
    @FunctionalInterface public interface Work<T> { T run(Connection connection) throws SQLException; }
    /** try-with-resources retains the original deadlock if MySQL already invalidated
     * this savepoint by rolling back the whole transaction. */
    public static final class SavepointScope implements AutoCloseable {
        private final Connection connection;private final Savepoint point;
        private SavepointScope(Connection connection) throws SQLException {this.connection=connection;point=connection.setSavepoint();}
        public Savepoint point(){return point;}
        @Override public void close() throws SQLException {connection.releaseSavepoint(point);}
    }
    public static SavepointScope savepoint(Connection connection) throws SQLException {return new SavepointScope(connection);}
    private final HikariDataSource pool;
    private final java.util.concurrent.Semaphore background;
    private final Map<Connection,Boolean> gated=Collections.synchronizedMap(new IdentityHashMap<>());
    private final long[] samples=new long[2048];
    private long sampleCount;
    private final long[] waits=new long[2048];private long waitCount;
    private static final Map<Connection,Sql> OWNERS=Collections.synchronizedMap(new IdentityHashMap<>());
    private final java.util.concurrent.atomic.LongAdder statements=new java.util.concurrent.atomic.LongAdder(),attempts=new java.util.concurrent.atomic.LongAdder();
    private final java.util.concurrent.atomic.LongAdder retries=new java.util.concurrent.atomic.LongAdder(),transactions=new java.util.concurrent.atomic.LongAdder();
    public Sql(BackendConfig config) {
        HikariConfig c = new HikariConfig();
        c.setJdbcUrl(config.jdbcUrl()); c.setUsername(config.mysqlUser()); c.setPassword(config.mysqlPassword());
        c.setMaximumPoolSize(config.poolSize()); c.setMinimumIdle(0); c.setConnectionTimeout(2000);
        c.setValidationTimeout(1000); c.setInitializationFailTimeout(-1); c.setPoolName("cross-tesseract");
        c.setTransactionIsolation("TRANSACTION_READ_COMMITTED");
        pool=new HikariDataSource(c);
        background=new java.util.concurrent.Semaphore(Math.max(1,config.poolSize()-1),true);
    }
    public <T> T transaction(Work<T> work) throws SQLException {
        long started=System.nanoTime();try{
        for (int attempt=0;;attempt++) {
            attempts.increment();
            try (Connection c=acquire()) {
                try { c.setAutoCommit(false);T result=work.run(c); c.commit(); transactions.increment();return result; }
                catch (SQLException | RuntimeException e) { try{c.rollback();}catch(SQLException cleanup){e.addSuppressed(cleanup);}throw e; }
                finally { release(c); }
            } catch (SQLException e) {
                if (attempt>=3 || !(e.getErrorCode()==1213 || e.getErrorCode()==1205 || "40001".equals(e.getSQLState()))) throw e;
                retries.increment();
                // Only called on backend workers, never a Minecraft thread.
                try { Thread.sleep(ThreadLocalRandom.current().nextLong(10L << attempt, 30L << attempt)); }
                catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new SQLException("interrupted retry",interrupted); }
            }
        }
        }finally{record(System.nanoTime()-started);}
    }
    private synchronized void record(long nanos){samples[(int)(sampleCount++%samples.length)]=Math.max(0,nanos);}
    private Connection acquire() throws SQLException {
        long start=System.nanoTime();boolean permit=false,registered=false;
        try{
            // The one control lane retains a pool slot for fencing/heartbeat. Waiting is
            // bounded and happens exclusively on IO/test workers, never on Minecraft's thread.
            if(!Thread.currentThread().getName().startsWith("ct-control-")){
                try{permit=background.tryAcquire(1000,java.util.concurrent.TimeUnit.MILLISECONDS);}catch(InterruptedException error){Thread.currentThread().interrupt();throw new SQLException("interrupted connection admission",error);}
                if(!permit)throw new SQLException("background connection admission exhausted","HYT00");
            }
            Connection c=pool.getConnection();OWNERS.put(c,this);gated.put(c,permit);registered=true;return c;
        }finally{if(permit&&!registered)background.release();synchronized(this){waits[(int)(waitCount++%waits.length)]=System.nanoTime()-start;}}
    }
    private void release(Connection c){OWNERS.remove(c);if(Boolean.TRUE.equals(gated.remove(c)))background.release();}
    public synchronized Map<String,Number> stats(){var result=new LinkedHashMap<String,Number>();dev.crosstesseract.core.Metrics.quantiles(result,"db_transaction_ms",samples,sampleCount);dev.crosstesseract.core.Metrics.quantiles(result,"db_connection_wait_ms",waits,waitCount);result.put("db_transactions",transactions.sum());result.put("db_transaction_attempts",attempts.sum());result.put("db_statements",statements.sum());result.put("db_deadlock_retries",retries.sum());result.put("db_active_connections",pool.getHikariPoolMXBean().getActiveConnections());return result;}
    public <T> T connection(Work<T> work) throws SQLException { try (Connection c=acquire()) {try{return work.run(c);}finally{release(c);} } }
    private static void statement(Connection c){Sql owner=OWNERS.get(c);if(owner!=null)owner.statements.increment();}
    public static int update(Connection c,String sql,Object... args) throws SQLException {
        statement(c);
        try (PreparedStatement p=c.prepareStatement(sql)) { bind(p,args); return p.executeUpdate(); }
    }
    public static List<Map<String,Object>> query(Connection c,String sql,Object... args) throws SQLException {
        statement(c);
        try (PreparedStatement p=c.prepareStatement(sql)) {
            bind(p,args);
            try (ResultSet r=p.executeQuery()) {
                List<Map<String,Object>> rows=new ArrayList<>();
                while(r.next()) { Map<String,Object> row=new HashMap<>(); for(int i=1;i<=r.getMetaData().getColumnCount();i++) row.put(r.getMetaData().getColumnLabel(i),r.getObject(i)); rows.add(row); }
                return rows;
            }
        }
    }
    public static Map<String,Object> one(Connection c,String sql,Object... args) throws SQLException {
        var rows=query(c,sql,args); return rows.isEmpty()?null:rows.getFirst();
    }
    private static void bind(PreparedStatement p,Object[] args) throws SQLException {
        p.setQueryTimeout(3);
        for(int i=0;i<args.length;i++) { Object a=args[i]; p.setObject(i+1,a instanceof UUID?a.toString():a); }
    }
    public static String str(Map<String,Object> r,String key) { Object o=r.get(key); return o==null?null:o.toString(); }
    public static UUID uuid(Map<String,Object> r,String key) { String s=str(r,key); return s==null?null:UUID.fromString(s); }
    public static long num(Map<String,Object> r,String key) {
        Object raw=r.get(key);if(raw instanceof Boolean value)return value?1:0;
        dev.crosstesseract.core.DomainException.require(raw instanceof Number,"invalid_database_value");Number value=(Number)raw;
        try {
            if(value instanceof java.math.BigDecimal decimal)return decimal.longValueExact();
            if(value instanceof java.math.BigInteger integer)return integer.longValueExact();
            return value.longValue();
        } catch(ArithmeticException e){throw new dev.crosstesseract.core.DomainException("quantity_overflow");}
    }
    @Override public void close() { pool.close(); }
}
