package dev.crosstesseract.core;

import java.util.*;

/** Server-thread bounded limiter shared by packets and player commands. */
public final class ManagementLimiter {
    private static final LinkedHashMap<UUID,long[]> PLAYERS=new LinkedHashMap<>(16,.75f,true);
    public static boolean allow(UUID player){
        long now=System.nanoTime();var state=PLAYERS.computeIfAbsent(player,p->new long[]{now,0});
        if(now-state[0]>1_000_000_000L){state[0]=now;state[1]=0;}
        while(PLAYERS.size()>4096)PLAYERS.remove(PLAYERS.keySet().iterator().next());return ++state[1]<=8;
    }
    private ManagementLimiter(){}
}
