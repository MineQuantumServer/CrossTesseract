package dev.crosstesseract.core;

import java.util.UUID;

/** One finite physical reservoir per device, separately frozen during a durable handoff. */
public final class ThermalBuffer {
    public record Pending(UUID id,UUID channel,long signedMicrojoules,long localBefore,double capacity,long poolBefore,long poolAfter) {
        public Pending {DomainException.require(signedMicrojoules!=0 && signedMicrojoules!=Long.MIN_VALUE && localBefore>=0 && Double.isFinite(capacity)&&capacity>=1 && poolBefore>=0 && poolAfter>=0,"invalid_heat");}
    }
    public record Snapshot(long microjoules,double residual,Pending pending){
        public static final Snapshot EMPTY=new Snapshot(0,0,null);
        public Snapshot{DomainException.require(microjoules>=0 && Double.isFinite(residual)&&residual>=0&&residual<1,"invalid_heat");}
    }
    private long microjoules;
    private double residual;
    private Pending pending;
    private boolean preparing;
    public long energy(){return microjoules;}
    public boolean frozen(){return preparing || pending!=null;}
    public Pending pending(){return pending;}
    public void preparing(boolean value){preparing=value;}
    public Snapshot snapshot(){return new Snapshot(microjoules,residual,pending);}
    public void restore(Snapshot value){microjoules=value.microjoules();residual=value.residual();pending=value.pending();}
    public void change(double heat){
        DomainException.require(!frozen() && Double.isFinite(heat),"invalid_heat");
        double exact=heat*1_000_000+residual;
        DomainException.require(Double.isFinite(exact) && exact>Long.MIN_VALUE && exact<Long.MAX_VALUE,"quantity_overflow");
        long whole=(long)Math.floor(exact),next;
        try{next=Math.addExact(microjoules,whole);}catch(ArithmeticException e){throw new DomainException("quantity_overflow");}
        DomainException.require(next>=0,"invalid_heat");microjoules=next;residual=exact-whole;
    }
    public void apply(Pending exchange){
        DomainException.require(pending==null && exchange.localBefore()==microjoules,"heat_state_changed");
        // Positive means local -> pool, negative means pool -> local.
        long next;
        try{next=Math.subtractExact(microjoules,exchange.signedMicrojoules());}catch(ArithmeticException e){throw new DomainException("quantity_overflow");}
        DomainException.require(next>=0,"invalid_heat");microjoules=next;pending=exchange;preparing=false;
    }
    public void committed(UUID id){DomainException.require(pending!=null && pending.id().equals(id),"idempotency_conflict");pending=null;preparing=false;}
}
