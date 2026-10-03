package dev.crosstesseract.core;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

/** Time-bearing immutable UUIDv7 keys permit bounded terminal history without old replay. */
public final class BusinessIds {
    public static final int RETENTION_DAYS=30;
    public static UUID next(){long now=System.currentTimeMillis();var random=ThreadLocalRandom.current();return new UUID((now<<16)|0x7000L|random.nextLong(4096),(random.nextLong()&0x3fffffffffffffffL)|0x8000000000000000L);}
    public static void fresh(UUID id){
        long now=System.currentTimeMillis(),created=id.getMostSignificantBits()>>>16;
        DomainException.require(id.version()==7 && id.variant()==2 && created<=now+60_000 && created>=now-Duration.ofDays(RETENTION_DAYS).toMillis(),"operation_expired");
    }
    private BusinessIds(){}
}
