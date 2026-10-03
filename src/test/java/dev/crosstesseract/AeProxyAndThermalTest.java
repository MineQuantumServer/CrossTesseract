package dev.crosstesseract;

import dev.crosstesseract.core.*;
import dev.crosstesseract.core.Models.AeNetwork;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AeProxyAndThermalTest {
    @Test void duplicateBridgeAndLoopAdvertisementsAreCountedOnce(){
        UUID local=UUID.randomUUID(),remote=UUID.randomUUID();var ad=new AeNetwork("B",remote,3,true,"NO_CONTROLLER");
        assertEquals(3,AeProxyPlanner.plan("A",local,List.of(ad,ad,new AeNetwork("A",local,2,true,"NO_CONTROLLER"))).shadowNodes());
        assertEquals("ae_multiple_controllers",AeProxyPlanner.plan("A",local,List.of(new AeNetwork("A",local,1,true,"CONTROLLER_ONLINE"),new AeNetwork("B",remote,1,true,"CONTROLLER_ONLINE"))).reason());
        assertEquals("ae_peer_inactive",AeProxyPlanner.plan("A",local,List.of(new AeNetwork("B",remote,3,false,"NO_CONTROLLER"))).reason());
        assertEquals("ae_proxy_capacity",AeProxyPlanner.plan("A",local,List.of(new AeNetwork("B",remote,33,true,"NO_CONTROLLER"))).reason());
    }
    @Test void thermalPendingIsFrozenDurableAndResidualIsConserved(){
        var buffer=new ThermalBuffer();buffer.change(1.0000005);assertEquals(1_000_000,buffer.energy());
        var p=new ThermalBuffer.Pending(UUID.randomUUID(),UUID.randomUUID(),100,buffer.energy(),10_000,0,0);buffer.preparing(true);buffer.apply(p);
        assertThrows(DomainException.class,()->buffer.change(1));var restored=new ThermalBuffer();restored.restore(buffer.snapshot());assertTrue(restored.frozen());assertEquals(999_900,restored.energy());
        restored.committed(p.id());restored.change(.0000005);assertEquals(999_901,restored.energy());
        assertThrows(DomainException.class,()->restored.change(Double.NaN));assertThrows(DomainException.class,()->restored.change(Double.POSITIVE_INFINITY));
    }
}
