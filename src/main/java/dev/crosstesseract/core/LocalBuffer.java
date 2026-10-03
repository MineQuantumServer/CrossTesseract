package dev.crosstesseract.core;

import dev.crosstesseract.core.LocalSnapshot.*;
import java.util.*;

/** Main-thread only. Send and receive ownership never share a slot or automatically recirculate. */
public final class LocalBuffer {
    public record Stack(Resource resource,long amount) {}
    private final Map<String,Stack[]> sending=new HashMap<>();
    private final LinkedHashMap<UUID,Deposit> deposits=new LinkedHashMap<>();
    private final LinkedHashMap<UUID,Credit> credits=new LinkedHashMap<>();
    private long revision;
    private boolean dirty;
    public static int slots(String kind) { return switch(kind) {case Protocol.ITEM -> 9;case Protocol.FLUID,Protocol.CHEMICAL -> 4;default -> 1;}; }
    private static volatile Map<String,Long> capacities=Map.of();
    public static void configureCapacities(Map<String,Long> values){capacities=Map.copyOf(values);}
    public static long slotCapacity(String kind) { return capacities.getOrDefault(kind,defaultCapacity(kind)); }
    private static long defaultCapacity(String kind) { return switch(kind) {case Protocol.ITEM -> 64;case Protocol.FLUID -> 16_000;case Protocol.FE -> 2_000_000;case Protocol.EU -> 16_777_216;case Protocol.CHEMICAL -> 64_000;case Protocol.HEAT -> 10_000_000_000_000L;default -> 0;}; }
    public long revision() { return revision; }
    public void touch(){changed();}
    public boolean dirty() { return dirty; }
    public long sendAmount(String kind) {
        long count=0; for(Stack stack:tx(kind)) if(stack!=null)count=Math.addExact(count,stack.amount());
        for(Deposit deposit:deposits.values()) if(deposit.resource().kind().equals(kind))count=Math.addExact(count,deposit.amount()); return count;
    }
    public long receiveAmount(String kind) { return credits.values().stream().filter(c->c.resource().kind().equals(kind)).mapToLong(Credit::remaining).reduce(0,Math::addExact); }
    public Stack sent(String kind,int slot) { DomainException.require(slot>=0 && slot<slots(kind),"invalid_slot"); return tx(kind)[slot]; }
    private Stack[] tx(String kind) { return sending.computeIfAbsent(kind,k->new Stack[slots(k)]); }
    public List<Credit> received(String kind) { return credits.values().stream().filter(c->c.resource().kind().equals(kind) && c.remaining()>0).toList(); }
    private static int creditLimit(String kind){return kind.equals(Protocol.FE)||kind.equals(Protocol.EU)?32:slots(kind);}
    public long receiveRoom(String kind) {
        int used=received(kind).size(); return credits.size()>=64 || used>=creditLimit(kind)?0:slots(kind)*slotCapacity(kind)-Math.min(slots(kind)*slotCapacity(kind),receiveAmount(kind));
    }
    public long insert(Resource resource,int slot,long amount,boolean simulate) {
        DomainException.require(amount>=0 && slot>=0 && slot<slots(resource.kind()),"invalid_amount");
        if(deposits.size()>=32) return 0;
        String kind=resource.kind(); Stack[] buffer=tx(kind);Stack previous=buffer[slot];
        if(previous!=null && !previous.resource().equals(resource)) return 0;
        long inSlot=previous==null?0:previous.amount();
        long room=Math.min(slotCapacity(kind)-inSlot,slots(kind)*slotCapacity(kind)-sendAmount(kind));
        long inserted=Math.min(Math.max(0,room),amount);
        if(inserted>0 && !simulate) { buffer[slot]=new Stack(resource,inSlot+inserted);changed(); } return inserted;
    }
    public long insert(Resource resource,long amount,boolean simulate) {
        DomainException.require(amount>=0,"invalid_amount");
        long allowed=Math.min(amount,Math.max(0,slots(resource.kind())*slotCapacity(resource.kind())-sendAmount(resource.kind())));
        long remaining=allowed;
        for(int i=0;i<slots(resource.kind()) && remaining>0;i++) remaining-=insert(resource,i,remaining,simulate);
        return allowed-remaining;
    }
    public long extract(UUID transaction,long amount,boolean simulate) {
        DomainException.require(amount>=0,"invalid_amount"); Credit credit=credits.get(transaction);if(credit==null)return 0;
        long extracted=Math.min(amount,credit.remaining());
        if(extracted>0 && !simulate) { credits.put(transaction,new Credit(credit.transaction(),credit.channel(),credit.resource(),credit.original(),credit.remaining()-extracted));changed(); }
        return extracted;
    }
    public long extract(Resource resource,long amount,boolean simulate) {
        long remaining=amount;
        for(Credit credit:List.copyOf(credits.values())) if(credit.resource().equals(resource) && remaining>0) remaining-=extract(credit.transaction(),remaining,simulate);
        return amount-remaining;
    }
    /** Roll back only a definite native remainder from this same, reentrancy-guarded local call.
     * This is never an asynchronous timeout refund and never creates a new sending deposit. */
    public void refundLocalRemainder(List<Credit> before,Resource resource,long extracted,long remainder){
        DomainException.require(extracted>=0 && remainder>=0 && remainder<=extracted,"invalid_remainder");
        long spent=0;for(var old:before)if(old.resource().equals(resource)){var now=credits.get(old.transaction());DomainException.require(now!=null && now.remaining()<=old.remaining(),"external_io_uncertain");spent=Math.addExact(spent,old.remaining()-now.remaining());}
        DomainException.require(spent==extracted,"external_io_uncertain");
        for(var old:before.reversed())if(remainder>0 && old.resource().equals(resource)){var now=credits.get(old.transaction());long restore=Math.min(remainder,old.remaining()-now.remaining());if(restore>0){credits.put(now.transaction(),new Credit(now.transaction(),now.channel(),now.resource(),now.original(),now.remaining()+restore));remainder-=restore;changed();}}
        DomainException.require(remainder==0,"external_io_uncertain");
    }
    public void holdForReview(UUID channel,Resource resource,long amount){DomainException.require(channel!=null && amount>0 && deposits.size()<64,"recovery_buffer_full");var id=BusinessIds.next();deposits.put(id,new Deposit(id,channel,resource,amount));changed();}
    public LocalSnapshot snapshot(UUID endpoint,UUID world,long generation,UUID channel,boolean stage) {
        if(stage && channel!=null) {
            // Persist every raw sending slot. Limiting SQL batch size must never leave accepted
            // local slots out of the owned checkpoint. Admission stops at 32 pending entries;
            // at most 19 raw slots can remain, so the 64-entry snapshot covers both sets.
            int budget=64-deposits.size();
            for(var entry:sending.entrySet()) for(int i=0;i<entry.getValue().length;i++) {
                Stack stack=entry.getValue()[i]; if(stack!=null && budget>0 && deposits.size()<64) {
                    UUID id=BusinessIds.next(); deposits.put(id,new Deposit(id,channel,stack.resource(),stack.amount()));entry.getValue()[i]=null;budget--;changed();
                }
            }
        }
        dirty=false;
        return new LocalSnapshot(endpoint,world,generation,revision,List.copyOf(deposits.values()),List.copyOf(credits.values()));
    }
    public void restore(LocalSnapshot snapshot) {
        DomainException.require(deposits.isEmpty() && credits.isEmpty() && sending.values().stream().allMatch(a->Arrays.stream(a).allMatch(Objects::isNull)),"restore_not_empty");
        sending.clear();
        for(Deposit d:snapshot.deposits()) DomainException.require(deposits.put(d.transaction(),d)==null,"duplicate_checkpoint");
        for(Credit c:snapshot.credits()) DomainException.require(credits.put(c.transaction(),c)==null,"duplicate_checkpoint");
        revision=snapshot.revision();dirty=true;
    }
    public void committed(Collection<UUID> transactions) { for(UUID id:transactions) if(deposits.remove(id)!=null)changed(); }
    public void checkpointed(Collection<UUID> zeroTransactions) { for(UUID id:zeroTransactions) { Credit c=credits.get(id); if(c!=null && c.remaining()==0) { credits.remove(id);changed(); } } }
    public void credit(Credit credit) {
        Credit previous=credits.get(credit.transaction());
        if(previous!=null) { DomainException.require(previous.channel().equals(credit.channel()) && previous.resource().equals(credit.resource()) && previous.original()==credit.original(),"idempotency_conflict"); return; }
        DomainException.require(credits.size()<64 && received(credit.resource().kind()).size()<creditLimit(credit.resource().kind()) && credit.remaining()<=receiveRoom(credit.resource().kind()),"receive_buffer_full");
        credits.put(credit.transaction(),credit);changed();
    }
    public boolean hasWork() { return dirty || !deposits.isEmpty(); }
    public boolean empty() { return deposits.isEmpty() && receiveAmountAll()==0 && sending.values().stream().allMatch(a->Arrays.stream(a).allMatch(Objects::isNull)); }
    private long receiveAmountAll() { long result=0;for(Credit c:credits.values()) if(c.remaining()>0)result++;return result; }
    private void changed() { revision=Math.addExact(revision,1);dirty=true; }
}
