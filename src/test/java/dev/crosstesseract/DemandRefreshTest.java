package dev.crosstesseract;

import dev.crosstesseract.runtime.*;
import dev.crosstesseract.core.*;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class DemandRefreshTest {
    @Test void smallConsumptionDoesNotRenewEveryCreditButDepletionAndExpiryDo(){
        var refresh=new DemandRefresh();String kind=Protocol.FE;
        assertTrue(refresh.announce(kind,2_000_000,null,1,2_000_000,0));
        refresh.confirmed(kind,2_000_000,null,1,0);refresh.allocated(kind,32_000);
        assertFalse(refresh.announce(kind,1_968_000,null,1,2_000_000,1));
        assertFalse(refresh.announce(kind,2_000_000,null,1,2_000_000,1),"local output does not imply a fresh full inventory query");
        assertTrue(refresh.announce(kind,0,null,1,2_000_000,1),"full/disabled receiver withdraws stale space");
        assertTrue(refresh.announce(kind,2_000_000,null,1,2_000_000,DemandRefresh.RENEW_NANOS));
        refresh.allocated(kind,1_968_000);assertTrue(refresh.announce(kind,2_000_000,null,1,2_000_000,2));
    }
    @Test void profilesQuantumAndTinyCapacitiesRemainDistinct(){
        var refresh=new DemandRefresh();refresh.confirmed(Protocol.EU,64,"a",32,0);
        assertTrue(refresh.announce(Protocol.EU,64,"b",32,64,1));
        assertTrue(refresh.announce(Protocol.EU,64,"a",64,64,1));
        refresh.confirmed(Protocol.ITEM,1,null,1,0);refresh.allocated(Protocol.ITEM,1);
        assertTrue(refresh.announce(Protocol.ITEM,1,null,1,1,1));
    }
    @Test void missingConfigurationIsConservative(@TempDir Path root)throws Exception{
        var defaults=RuntimeLimits.load(root.resolve("absent.properties"));
        assertFalse(defaults.transfer().channelBatches());assertFalse(defaults.transfer().localFast());
    }
}
