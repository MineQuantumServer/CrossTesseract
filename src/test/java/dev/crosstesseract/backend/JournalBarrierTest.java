package dev.crosstesseract.backend;

import dev.crosstesseract.core.*;
import java.nio.file.*;
import java.nio.channels.FileChannel;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class JournalBarrierTest {
    @Test void identicalVisibleFileCannotAcknowledgeFailedDirectoryBarrier(@TempDir Path root)throws Exception{
        var attempts=new AtomicInteger();
        var journal=new LocalJournal(root,path->{if(attempts.incrementAndGet()<=2)throw new IOException("controlled directory force failure; not hardware power loss");try(var directory=FileChannel.open(path,StandardOpenOption.READ)){directory.force(true);}});
        var id=BusinessIds.next();var business=BusinessIds.next();
        var snapshot=new LocalSnapshot(id,BusinessIds.next(),1,1,List.of(new LocalSnapshot.Deposit(business,BusinessIds.next(),new Resource(Protocol.FE,new byte[0]),128)),List.of());
        assertThrows(IOException.class,()->journal.write(snapshot));
        assertEquals(snapshot,journal.read(id).orElseThrow(),"move succeeded, but durability remains unproved");
        assertThrows(IOException.class,()->journal.write(snapshot),"same version must retry the missing barrier");
        journal.write(snapshot);journal.write(snapshot);
        assertEquals(3,attempts.get());assertEquals(1,journal.stats().get("wal_unproved_barrier_retries").intValue());
        assertEquals(business,journal.read(id).orElseThrow().deposits().getFirst().transaction());
        assertEquals(128,journal.read(id).orElseThrow().deposits().getFirst().amount());
        var restarted=new LocalJournal(root);restarted.write(snapshot);
        assertEquals(1,restarted.stats().get("wal_unproved_barrier_retries").intValue(),"new process must re-establish proof before treating same bytes as durable");
    }
}
