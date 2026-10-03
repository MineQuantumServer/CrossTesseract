package dev.crosstesseract.backend;

import dev.crosstesseract.core.Resource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;

/** MySQL advisory migration lock belongs to one connection and is never a resource/quota lock. */
public final class Migrations {
    public static void apply(Sql db) throws SQLException, IOException {
        var migrations=new java.util.ArrayList<byte[]>();
        for(String name:java.util.List.of("V001__authority.sql","V002__thermal_and_ae.sql","V003__bounded_history.sql","V004__stock_requests.sql"))try(var in=Migrations.class.getResourceAsStream("/db/migration/"+name)){if(in==null)throw new IOException("missing migration");migrations.add(in.readAllBytes());}
        db.connection(c->{
            var lock=Sql.one(c,"SELECT GET_LOCK('cross_tesseract_schema_v1', 20) AS acquired");
            if(Sql.num(lock,"acquired")!=1) throw new SQLException("migration lock unavailable");
            try {
                Sql.update(c,"CREATE TABLE IF NOT EXISTS ct_schema_history (version INT PRIMARY KEY, checksum CHAR(64) CHARACTER SET ascii NOT NULL, state VARCHAR(16) NOT NULL, applied_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6)) ENGINE=InnoDB");
                var latest=Sql.one(c,"SELECT COALESCE(MAX(version),0) AS n FROM ct_schema_history");
                if(Sql.num(latest,"n")>migrations.size())throw new SQLException("database schema newer than this mod; upgrade required");
                for(int index=0;index<migrations.size();index++){
                    int version=index+1;byte[] bytes=migrations.get(index);String checksum=Resource.hash(bytes),sql=new String(bytes,StandardCharsets.UTF_8);
                    var history=Sql.one(c,"SELECT * FROM ct_schema_history WHERE version=?",version);
                    if(history!=null){if(!checksum.equals(Sql.str(history,"checksum")) || !"COMPLETE".equals(Sql.str(history,"state")))throw new SQLException("migration checksum mismatch or interrupted DDL; operator repair required");continue;}
                    Sql.update(c,"INSERT INTO ct_schema_history(version,checksum,state) VALUES(?,?,'APPLYING')",version,checksum);
                    for(String statement:sql.split(version==3?"(?m)^-- @statement\\s*$":";"))if(!statement.isBlank())Sql.update(c,statement);
                    Sql.update(c,"UPDATE ct_schema_history SET state='COMPLETE' WHERE version=?",version);
                }
            } finally { Sql.one(c,"SELECT RELEASE_LOCK('cross_tesseract_schema_v1') AS released"); }
            return null;
        });
    }
    private Migrations() {}
}
