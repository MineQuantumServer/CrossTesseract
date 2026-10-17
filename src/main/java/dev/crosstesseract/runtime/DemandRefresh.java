package dev.crosstesseract.runtime;

import java.util.*;

/** Main-thread scheduling metadata, never an authorization or spendable balance. */
public final class DemandRefresh {
    private record Known(long room,String profile,long quantum,long renewed){}
    private final Map<String,Known> known=new HashMap<>();
    // SQL demands expire in six seconds. Renew from capture time, well before expiry.
    public static final long RENEW_NANOS=java.util.concurrent.TimeUnit.SECONDS.toNanos(2);
    public boolean announce(String kind,long room,String profile,long quantum,long capacity,long now){
        var old=known.get(kind);
        return old==null || now-old.renewed()>=RENEW_NANOS || !Objects.equals(profile,old.profile())
            || quantum!=old.quantum() || room<old.room()
            || room-old.room()>=Math.max(quantum,capacity/2) || old.room()<quantum && room>=quantum;
    }
    public void confirmed(String kind,long room,String profile,long quantum,long capturedAt){known.put(kind,new Known(room,profile,quantum,capturedAt));}
    public void allocated(String kind,long quantity){var old=known.get(kind);if(old!=null)known.put(kind,new Known(Math.max(0,old.room()-quantity),old.profile(),old.quantum(),old.renewed()));}
}
