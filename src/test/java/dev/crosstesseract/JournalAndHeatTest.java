package dev.crosstesseract;

import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.core.*;
import dev.crosstesseract.core.LocalSnapshot.*;
import java.util.*;
import net.jqwik.api.*;
import net.jqwik.api.constraints.IntRange;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class JournalAndHeatTest {
    @Test void localCheckpointsRoundTripAndCorruptionFailsClosed(@TempDir Path directory) throws Exception {
        var r=new Resource(Protocol.ITEM,"{id:\"minecraft:stone\",count:1}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        UUID endpoint=UUID.randomUUID();
        var s=new LocalSnapshot(endpoint,UUID.randomUUID(),1,9,List.of(new Deposit(UUID.randomUUID(),UUID.randomUUID(),r,64)),List.of(new Credit(UUID.randomUUID(),UUID.randomUUID(),r,Long.MAX_VALUE,Long.MAX_VALUE-2)));
        var journal=new LocalJournal(directory); journal.write(s); assertEquals(s,journal.read(endpoint).orElseThrow());
        byte[] bytes=LocalJournal.encode(s); bytes[17]^=1; assertThrows(java.io.IOException.class,()->LocalJournal.decode(bytes));
        assertThrows(DomainException.class,()->journal.write(new LocalSnapshot(endpoint,s.world(),1,8,s.deposits(),s.credits())));
        assertThrows(DomainException.class,()->new Resource(Protocol.ITEM,new byte[Resource.MAX_BYTES+1]));
    }
    @Property(tries=300) void passiveHeatNeverOvershootsOrCreatesEnergy(@ForAll @IntRange(min=301,max=10_000) int hot,
            @ForAll @IntRange(min=1,max=10_000) int ch,@ForAll @IntRange(min=1,max=10_000) int cc) {
        var exchange=HeatModel.exchange(hot,ch,300,cc,10,0.2,0,1_000_000_000_000L);
        double q=exchange.microjoules()/1_000_000.0;
        double nextHot=hot-q/ch, nextCold=300+q/cc;
        assertTrue(nextHot>=nextCold);assertTrue(q>=0);
        assertEquals(hot*(double)ch+300.0*cc,nextHot*ch+nextCold*cc,1e-6);
    }
    @Test void heatRejectsNaNInfinityIllegalCapacityAndColdToHot() {
        for(double invalid:List.of(Double.NaN,Double.POSITIVE_INFINITY,-1.0)) assertThrows(DomainException.class,()->HeatModel.exchange(invalid,100,300,100,10,0.2,0,100));
        assertThrows(DomainException.class,()->HeatModel.exchange(500,0,300,100,10,0.2,0,100));
        assertEquals(0,HeatModel.exchange(200,100,300,100,10,0.2,0,100).microjoules());
    }
}
