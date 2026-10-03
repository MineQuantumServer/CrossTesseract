package dev.crosstesseract;

import dev.crosstesseract.core.*;
import java.util.*;
import net.jqwik.api.*;
import net.jqwik.api.constraints.IntRange;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BufferSafetyTest {
    @Test void definiteLocalPartialRemaindersReturnToOriginalCreditsAndNeverSending(){
        var b=new LocalBuffer();var r=new Resource(Protocol.FE,new byte[0]);var ch=BusinessIds.next();
        var first=new dev.crosstesseract.core.LocalSnapshot.Credit(BusinessIds.next(),ch,r,7,7);var second=new dev.crosstesseract.core.LocalSnapshot.Credit(BusinessIds.next(),ch,r,13,13);b.credit(first);b.credit(second);
        var before=b.received(Protocol.FE);assertEquals(15,b.extract(r,15,false));b.refundLocalRemainder(before,r,15,11);assertEquals(16,b.receiveAmount(Protocol.FE));assertEquals(0,b.sendAmount(Protocol.FE));assertEquals(Set.of(first.transaction(),second.transaction()),b.received(Protocol.FE).stream().map(dev.crosstesseract.core.LocalSnapshot.Credit::transaction).collect(java.util.stream.Collectors.toSet()));
        assertThrows(DomainException.class,()->b.refundLocalRemainder(before,r,15,11),"the same remainder cannot be applied twice");
    }
    @Test void allAcceptedRawSlotsEnterTheCheckpointEvenNearThePendingLimit(){
        var b=new LocalBuffer();var r=new Resource(Protocol.ITEM,new byte[]{1});UUID ch=BusinessIds.next(),id=BusinessIds.next(),world=BusinessIds.next();
        for(int i=0;i<31;i++){assertEquals(1,b.insert(r,0,1,false));b.snapshot(id,world,1,ch,true);}
        for(int i=0;i<9;i++)assertEquals(1,b.insert(r,i,1,false));
        var s=b.snapshot(id,world,1,ch,true);assertEquals(40,s.deposits().size());assertEquals(40,s.deposits().stream().mapToLong(d->d.amount()).sum());
        var restored=new LocalBuffer();restored.sendAmount(Protocol.ITEM);restored.restore(s);assertEquals(40,restored.sendAmount(Protocol.ITEM));
    }
    @Property(tries=200) void partialExtractionSimulationAndRepeatedCreditsConserve(@ForAll @IntRange(min=1,max=2000000) int quantity,@ForAll @IntRange(min=0,max=2000000) int ask){
        var b=new LocalBuffer();var r=new Resource(Protocol.FE,new byte[0]);var c=new dev.crosstesseract.core.LocalSnapshot.Credit(BusinessIds.next(),BusinessIds.next(),r,quantity,quantity);
        b.credit(c);b.credit(c);long expected=Math.min(quantity,ask);assertEquals(expected,b.extract(c.transaction(),ask,true));assertEquals(quantity,b.receiveAmount(Protocol.FE));
        assertEquals(expected,b.extract(c.transaction(),ask,false));b.credit(c);assertEquals(quantity-expected,b.receiveAmount(Protocol.FE));assertEquals(0,b.sendAmount(Protocol.FE));
    }
    @Test void oldTimeBearingBusinessIdsCannotBecomeFreshOperationsAfterHistoryPruning(){
        UUID now=BusinessIds.next();BusinessIds.fresh(now);long old=System.currentTimeMillis()-java.time.Duration.ofDays(31).toMillis();
        UUID expired=new UUID((old<<16)|0x7000L,0x8000000000000001L);assertThrows(DomainException.class,()->BusinessIds.fresh(expired));assertThrows(DomainException.class,()->BusinessIds.fresh(UUID.randomUUID()));
    }
}
