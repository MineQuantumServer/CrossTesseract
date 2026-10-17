package dev.crosstesseract;

import dev.crosstesseract.runtime.*;
import dev.crosstesseract.core.*;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class DemandRefreshTest {
    @Test void localCheckpointAndDemandRenewalCannotPostponeInventoryDiscovery(){
        var refresh=new DemandRefresh();long interval=2_000_000_000L;
        assertTrue(refresh.discoveryDue(0,interval));refresh.discovered(0);
        for(int i=1;i<=40;i++){
            long now=i*100_000_000L;
            refresh.confirmed(Protocol.FE,100+i,null,1,now); // successful metadata renewal/checkpoint, not discovery
            assertEquals(Math.max(0,interval-now),refresh.discoveryRemaining(now,interval));
            assertEquals(now>=interval,refresh.discoveryDue(now,interval));
        }
    }
    @Test void successfulDiscoveryAdvancesFromCaptureRatherThanCompletion(){
        var refresh=new DemandRefresh();long interval=2_000_000_000L;
        refresh.discovered(100); // callback arrives 1.5 seconds after this capture
        assertEquals(500_000_000L,refresh.discoveryRemaining(1_500_000_100L,interval));
        assertTrue(refresh.discoveryDue(2_000_000_100L,interval));
        refresh.discovered(2_000_000_100L);
        assertFalse(refresh.discoveryDue(2_000_000_101L,interval));
    }
    @Test void olderCompletionCannotMoveDiscoveryClockBackward(){
        var refresh=new DemandRefresh();refresh.discovered(-10_000);refresh.discovered(-20_000);
        assertEquals(1_000,refresh.discoveryRemaining(-9_000,2_000));
        assertTrue(refresh.discoveryDue(-8_000,2_000));
        assertThrows(IllegalArgumentException.class,()->refresh.discoveryRemaining(0,0));
    }
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
