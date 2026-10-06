package dev.crosstesseract;

import dev.crosstesseract.core.*;
import dev.crosstesseract.core.LocalSnapshot.Credit;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/** Room probes drive scheduling; they must never release unconfirmed ownership or mutate it. */
class LocalRoomTest {
    @Test void positiveCredentialLimitAndPartialConsumptionControlAdmissionSeparatelyFromCapacity() {
        UUID channel=BusinessIds.next();
        for(String kind:List.of(Protocol.ITEM,Protocol.FLUID,Protocol.CHEMICAL,Protocol.FE,Protocol.EU)) {
            var buffer=new LocalBuffer();var resource=new Resource(kind,new byte[]{1});
            var first=new Credit(BusinessIds.next(),channel,resource,2,2);buffer.credit(first);
            for(int i=1;i<LocalBuffer.creditLimit(kind);i++)buffer.credit(new Credit(BusinessIds.next(),channel,resource,1,1));
            assertEquals(0,buffer.receiveRoom(kind),kind+" credential cap, despite unused quantity capacity");
            assertEquals(1,buffer.extract(first.transaction(),1,false));
            assertEquals(0,buffer.receiveRoom(kind),kind+" partial output does not free a credential");
            assertEquals(1,buffer.extract(first.transaction(),1,false));
            long remaining=LocalBuffer.creditLimit(kind)-1;
            long capacity=LocalBuffer.slots(kind)*LocalBuffer.slotCapacity(kind);
            long version=buffer.revision();boolean dirty=buffer.dirty();
            for(int i=0;i<8;i++) {
                assertEquals(remaining,buffer.receiveAmount(kind));assertEquals(capacity-remaining,buffer.receiveRoom(kind));
                assertEquals(version,buffer.revision());assertEquals(dirty,buffer.dirty());
            }
            buffer.credit(first); // Repeated completion never restores the consumed tombstone.
            assertEquals(remaining,buffer.receiveAmount(kind));assertEquals(capacity-remaining,buffer.receiveRoom(kind));
            var incoming=new Credit(BusinessIds.next(),channel,resource,1,1);buffer.credit(incoming);
            assertEquals(0,buffer.receiveRoom(kind));
            assertEquals(LocalBuffer.creditLimit(kind)+1,buffer.snapshot(BusinessIds.next(),BusinessIds.next(),1,channel,false).credits().size());
        }
    }

    @Test void globalTombstoneBoundNeedsConfirmedCheckpointEvenWhenEveryRemainingIsZero() {
        UUID channel=BusinessIds.next();var resource=new Resource(Protocol.FE,new byte[0]);var credits=new ArrayList<Credit>();
        for(int i=0;i<64;i++)credits.add(new Credit(BusinessIds.next(),channel,resource,1,0));
        var buffer=new LocalBuffer();buffer.restore(new LocalSnapshot(BusinessIds.next(),BusinessIds.next(),1,3,List.of(),credits));
        buffer.snapshot(BusinessIds.next(),BusinessIds.next(),1,channel,false);
        long version=buffer.revision();assertFalse(buffer.dirty());
        for(String kind:List.of(Protocol.ITEM,Protocol.FLUID,Protocol.CHEMICAL,Protocol.FE,Protocol.EU)) {
            assertEquals(0,buffer.receiveAmount(kind));assertEquals(0,buffer.receiveRoom(kind));
        }
        assertEquals(version,buffer.revision());assertFalse(buffer.dirty());
        buffer.checkpointed(Set.of(credits.getFirst().transaction()));
        assertEquals(LocalBuffer.slotCapacity(Protocol.FE),buffer.receiveRoom(Protocol.FE));
        var incoming=new Credit(BusinessIds.next(),channel,resource,7,7);buffer.credit(incoming);
        assertEquals(7,buffer.receiveAmount(Protocol.FE));assertEquals(0,buffer.receiveRoom(Protocol.ITEM));
        assertEquals(7,buffer.extract(incoming.transaction(),7,false));
        assertEquals(0,buffer.receiveRoom(Protocol.FE),"local consumption alone does not free the global tombstone slot");
    }
}
