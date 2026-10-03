package dev.crosstesseract;

import dev.crosstesseract.backend.*;
import dev.crosstesseract.core.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class MigrationConcurrencyTest {
    @Test void threeConcurrentFreshMigrationsAndInterruptedDdlFailClosed() throws Exception {
        assumeTrue(Boolean.getBoolean("ct.integration"),"isolated real MySQL required");
        String database="ct_schema_"+BusinessIds.next().toString().replace("-","");
        root("CREATE DATABASE "+database+"; GRANT ALL ON "+database+".* TO 'ct_dev'@'%';");
        var servers=new ArrayList<Authority>();var executor=Executors.newFixedThreadPool(3);
        try{
            var futures=new ArrayList<Future<?>>();
            for(int i=0;i<3;i++) {var cfg=new BackendConfig(true,"test_fresh","schema-"+i,"jdbc:mysql://127.0.0.1:13306/"+database+"?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectTimeout=1000&socketTimeout=3000","ct_dev","ct_dev_only","redis://127.0.0.1:16379",2,4,200,128,32,256);var a=new Authority(cfg);servers.add(a);futures.add(executor.submit(()->{try{return a.join(BusinessIds.next(),BusinessIds.next(),Protocol.BASE);}catch(Exception e){throw new RuntimeException(e);}}));}
            for(var f:futures)f.get(30,TimeUnit.SECONDS);var a=servers.getFirst();UUID channel=a.createChannel(BusinessIds.next(),"DDL retained asset metadata",BusinessIds.next());
            a.database().transaction(c->{assertEquals(4,Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_schema_history WHERE state='COMPLETE'"),"n"));Sql.update(c,"UPDATE ct_schema_history SET state='APPLYING' WHERE version=4");return null;});
            assertTrue(assertThrows(java.sql.SQLException.class,()->Migrations.apply(a.database())).getMessage().contains("interrupted DDL"));
            assertFalse(a.trace(BusinessIds.next(),channel,"channel").isEmpty(),"an interrupted migration must not rebuild/drop data");
        }finally{executor.shutdownNow();servers.forEach(Authority::close);root("DROP DATABASE "+database+";");}
    }
    private static void root(String sql) throws Exception {
        var builder=new ProcessBuilder("docker","--host=unix:///var/run/docker.sock","exec","-i","-e","MYSQL_PWD=ct_dev_root_only","ct-dev-mysql","mysql","-u","root","--batch","--skip-column-names");for(String name:List.of("DOCKER_HOST","DOCKER_CONTEXT","DOCKER_TLS","DOCKER_TLS_VERIFY","DOCKER_CERT_PATH"))builder.environment().remove(name);
        var process=builder.start();try(var out=process.getOutputStream()){out.write(sql.getBytes(java.nio.charset.StandardCharsets.UTF_8));}assertTrue(process.waitFor(20,TimeUnit.SECONDS));assertEquals(0,process.exitValue(),new String(process.getErrorStream().readAllBytes()));
    }
}
