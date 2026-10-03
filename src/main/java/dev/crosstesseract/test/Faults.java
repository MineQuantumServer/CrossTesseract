package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.DomainException;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

/** Opt-in isolated console fault injection. No production or player packet entrypoint. */
public final class Faults {
    private record Point(String phase,UUID endpoint){}
    private static final AtomicReference<Point> armed=new AtomicReference<>();
    public static void arm(String cluster,String phase,UUID endpoint){DomainException.require(Boolean.getBoolean("cross_tesseract.testHarness") && (cluster.startsWith("dev_")||cluster.startsWith("test_")) && Set.of("after_send_wal","after_deposit","after_allocation","after_receive_wal").contains(phase),"forbidden");armed.set(new Point(phase,endpoint));}
    public static void hit(String phase,UUID endpoint){var point=armed.get();if(point!=null && point.phase().equals(phase) && point.endpoint().equals(endpoint) && armed.compareAndSet(point,null)){CrossTesseract.LOG.error("CT_FAULT {} endpoint={} halt=97",phase,endpoint);Runtime.getRuntime().halt(97);}}
    private Faults(){}
}
