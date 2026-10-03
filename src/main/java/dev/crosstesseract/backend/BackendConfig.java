package dev.crosstesseract.backend;

import dev.crosstesseract.core.DomainException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public record BackendConfig(boolean enabled, String cluster, String server, String jdbcUrl, String mysqlUser,
                            String mysqlPassword, String redisUri, int quota, int poolSize, int batchMillis,
                            int queueSize, int maxChannels, int maxEndpoints) {
    public static BackendConfig load(Path path) throws IOException {
        Properties p = new Properties();
        if (Files.exists(path)) try (var in=Files.newInputStream(path)) { p.load(in); }
        boolean enabled=Boolean.parseBoolean(p.getProperty("backend.enabled","false"));
        String cluster=p.getProperty("cluster.id","development"), server=p.getProperty("server.id", "UNCONFIGURED");
        DomainException.require(cluster.matches("[A-Za-z0-9_-]{1,64}") && server.matches("[A-Za-z0-9_-]{1,64}"), "invalid_identity");
        if (enabled) DomainException.require(!server.equals("UNCONFIGURED"), "server_id_required");
        return new BackendConfig(enabled,cluster,server,
                secret(p,"mysql.url","CT_MYSQL_URL","jdbc:mysql://127.0.0.1:3306/cross_tesseract?sslMode=VERIFY_IDENTITY&connectTimeout=1500&socketTimeout=3000"),
                secret(p,"mysql.user","CT_MYSQL_USER","cross_tesseract"),
                secret(p,"mysql.password","CT_MYSQL_PASSWORD",""),
                secret(p,"redis.uri","CT_REDIS_URI","redis://127.0.0.1:6379"),
                number(p,"chunkLoading.maxPerPlayer",2,0,64),number(p,"backend.poolSize",4,1,16),
                number(p,"transfer.batchMillis",200,100,2000),number(p,"backend.queueSize",128,16,4096),
                number(p,"limits.maxChannelsPerPlayer",32,1,1024), number(p,"limits.maxEndpointsPerChannel",256,1,65536));
    }
    private static String secret(Properties p,String key,String env,String fallback) { return System.getenv().getOrDefault(env,p.getProperty(key,fallback)); }
    private static int number(Properties p,String key,int fallback,int min,int max) {
        int n=Integer.parseInt(p.getProperty(key,Integer.toString(fallback)));
        DomainException.require(n>=min && n<=max,"invalid_config"); return n;
    }
    // Do not generate a record toString containing backend credentials.
    @Override public String toString() { return "BackendConfig["+cluster+"/"+server+",enabled="+enabled+"]"; }
}
