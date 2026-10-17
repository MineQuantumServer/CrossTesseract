package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.LocalBuffer;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.Protocol;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.level.storage.LevelResource;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** Real backpressure discards a useful hint; small native RX consumption must not slide discovery forever. */
@PrefixGameTestTemplate(false)
public final class RcDiscoveryGameTests {
    private record Transfer(UUID id,String kind,String state,long amount,long remaining){}
    private record Proof(List<Transfer> transfers,long pool,long unreceivedHints,LocalSnapshot source,LocalSnapshot receiver){}
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="rc_discovery",timeoutTicks=1_000_000)
    public static void continuousConsumptionCannotPostponeAuthorityDiscovery(GameTestHelper helper){
        Fixtures.bound(helper,source->{
            var runtime=source.runtime();UUID channel=source.channel();Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            boolean negative=Boolean.getBoolean("cross_tesseract.rcDiscoveryNegative");
            helper.assertTrue(runtime.limits().transfer().channelBatches() && runtime.limits().transfer().localFast(),"actual experimental path required");
            var receiver=new AtomicReference<TesseractBlockEntity>();var port=new AtomicReference<IEnergyStorage>();var failure=new AtomicReference<String>();
            var before=new AtomicReference<Proof>();var observed=new AtomicReference<Proof>();var terminal=new AtomicReference<Proof>();
            var sent=new AtomicInteger();var input=new AtomicLong();var output=new AtomicLong();var settled=new AtomicLong();
            var start=new AtomicLong();var lastOutput=new AtomicLong();var maxOutputGap=new AtomicLong();var nextOutput=new AtomicLong();var firstNewCredit=new AtomicLong();
            var observing=new AtomicBoolean();var stopped=new AtomicBoolean();
            int count=LocalBuffer.creditLimit(Protocol.FE);long initial=Math.multiplyExact(count,5L);
            IEnergyStorage sourcePort=helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,source.getBlockPos(),Direction.UP);
            helper.assertTrue(sourcePort!=null,"native source capability required");source.mode(Protocol.FE,Protocol.Mode.SEND);
            helper.startSequence()
                .thenExecute(()->{var pos=new BlockPos(3,1,1);helper.setBlock(pos,CrossTesseract.TESSERACT.get());var be=(TesseractBlockEntity)helper.getBlockEntity(pos);be.placed(source.owner());be.mode(Protocol.FE,Protocol.Mode.RECEIVE);receiver.set(be);port.set(helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP));})
                .thenWaitUntil(()->helper.assertTrue(receiver.get().registered(),"receiver registration pending"))
                .thenExecute(()->runtime.submit(a->a.bind(source.owner(),receiver.get().id(),receiver.get().endpointVersion(),channel),receiver.get()::applyEndpoint,failure::set))
                .thenWaitUntil(()->{
                    helper.assertTrue(failure.get()==null,"bind failed: "+failure.get());var be=receiver.get();
                    helper.assertTrue(channel.equals(be.channel()) && source.allowed(Protocol.FE,null,true) && be.allowed(Protocol.FE,null,false) && !source.inFlight() && !be.inFlight(),"fresh native permissions pending");
                })
                .thenWaitUntil(()->{
                    var be=receiver.get();int n=sent.get();
                    if(n<count && source.allowed(Protocol.FE,null,true) && be.allowed(Protocol.FE,null,false) && !source.inFlight() && !be.inFlight()
                        && source.buffer().sendAmount(Protocol.FE)==0 && be.buffer().receiveAmount(Protocol.FE)==n*5L){
                        helper.assertTrue(sourcePort.receiveEnergy(5,true)==5,"native simulation accepts without input");
                        helper.assertTrue(sourcePort.receiveEnergy(5,false)==5,"each original five FE enters through a real native port exactly once");input.addAndGet(5);sent.incrementAndGet();
                    }
                    helper.assertTrue(sent.get()==count && !source.inFlight() && !be.inFlight() && source.buffer().sendAmount(Protocol.FE)==0
                        && be.buffer().received(Protocol.FE).size()==count && be.buffer().receiveAmount(Protocol.FE)==initial,"fill actual independent native credits, not fabricated SQL/WAL assets");
                })
                .thenExecute(()->{helper.assertTrue(receiver.get().buffer().receiveRoom(Protocol.FE)==0,"positive-credit backpressure bound required");helper.assertTrue(sourcePort.receiveEnergy(128,false)==128,"new128 FE actually accepted once");input.addAndGet(128);})
                .thenWaitUntil(()->helper.assertTrue(!source.inFlight() && source.buffer().sendAmount(Protocol.FE)==0 && receiver.get().buffer().receiveAmount(Protocol.FE)==initial,"new input committed while receiver is full"))
                .thenExecute(()->settled.set(System.nanoTime()))
                .thenWaitUntil(()->helper.assertTrue(System.nanoTime()-settled.get()>=TimeUnit.MILLISECONDS.toNanos(2_500),"real notifications settle while receiver has no room"))
                .thenExecute(()->runtime.submit(a->proof(a,journal,channel,source.id(),receiver.get().id()),before::set,failure::set))
                .thenWaitUntil(()->{helper.assertTrue(failure.get()==null,"initial SQL observation failed: "+failure.get());helper.assertTrue(before.get()!=null,"SQL/WAL observation pending");})
                .thenExecute(()->{
                    helper.assertTrue(before.get().pool()==128 && before.get().unreceivedHints()==0,"new balance is real and its channel hints already reached SQL inbox before consumption");
                    helper.assertTrue(before.get().transfers().stream().filter(t->t.kind().equals("ALLOCATE")).count()==count,"no new allocation while all credit slots full");
                    helper.assertTrue(receiver.get().buffer().receiveRoom(Protocol.FE)==0,"native capacity still full");
                    source.mode(Protocol.FE,Protocol.Mode.OFF);long now=System.nanoTime();start.set(now);lastOutput.set(now);nextOutput.set(now);
                })
                .thenWaitUntil(()->{
                    long now=System.nanoTime();var be=receiver.get();
                    if(!stopped.get() && now>=nextOutput.get()){
                        helper.assertTrue(port.get().extractEnergy(1,false)==1,"continuous actual native output must stay positive");output.incrementAndGet();maxOutputGap.accumulateAndGet(now-lastOutput.get(),Math::max);lastOutput.set(now);nextOutput.set(now+TimeUnit.MILLISECONDS.toNanos(100));
                    }
                    if(firstNewCredit.get()==0 && be.buffer().received(Protocol.FE).stream().anyMatch(c->c.original()==128))firstNewCredit.set(now);
                    if(now-start.get()>=TimeUnit.SECONDS.toNanos(8) && observing.compareAndSet(false,true))runtime.submit(a->proof(a,journal,channel,source.id(),be.id()),observed::set,failure::set);
                    helper.assertTrue(failure.get()==null,"active SQL observation failed: "+failure.get());
                    helper.assertTrue(observed.get()!=null,"eight-second real consumption window and SQL proof pending");
                })
                .thenExecute(()->{
                    stopped.set(true);var p=observed.get();var be=receiver.get();
                    helper.assertTrue(output.get()>0 && output.get()<initial && maxOutputGap.get()<TimeUnit.MILLISECONDS.toNanos(1_500),"old LOCAL is still positive; no idle-size consumer gap can rescue discovery");
                    if(negative){helper.assertTrue(firstNewCredit.get()==0 && p.pool()==128 && p.transfers().stream().filter(t->t.kind().equals("ALLOCATE")).count()==count,"old Runtime reproduces sliding discovery with positive assets");be.mode(Protocol.FE,Protocol.Mode.OFF);}
                    else{
                        helper.assertTrue(firstNewCredit.get()!=0 && firstNewCredit.get()-start.get()<=TimeUnit.SECONDS.toNanos(4),"independent discovery deadline must serve new128 before old LOCAL runs out");
                        helper.assertTrue(p.pool()==0 && p.transfers().stream().filter(t->t.kind().equals("ALLOCATE") && t.amount()==128).count()==1,"new128 exclusively allocated exactly once");
                        long remaining=Math.subtractExact(input.get(),output.get());helper.assertTrue(port.get().extractEnergy(Math.toIntExact(remaining),false)==remaining,"actual native drain includes all remaining original and new FE");output.addAndGet(remaining);
                        helper.assertTrue(port.get().extractEnergy(128,false)==0,"duplicate native output is zero");be.mode(Protocol.FE,Protocol.Mode.OFF);
                    }
                })
                .thenWaitUntil(()->helper.assertTrue(!source.inFlight() && !receiver.get().inFlight() && !source.buffer().dirty() && !receiver.get().buffer().dirty(),"final actual checkpoints settle"))
                .thenExecute(()->runtime.submit(a->proof(a,journal,channel,source.id(),receiver.get().id()),terminal::set,failure::set))
                .thenWaitUntil(()->{helper.assertTrue(failure.get()==null,"terminal observation failed: "+failure.get());helper.assertTrue(terminal.get()!=null,"terminal ownership proof pending");})
                .thenExecute(()->{
                    var p=terminal.get();long owned=p.transfers().stream().filter(t->t.kind().equals("ALLOCATE")).mapToLong(Transfer::remaining).sum();
                    long wal=p.receiver().credits().stream().mapToLong(LocalSnapshot.Credit::remaining).sum();
                    helper.assertTrue(input.get()==initial+128 && p.source().deposits().isEmpty() && owned==wal && owned==receiver.get().buffer().receiveAmount(Protocol.FE),"SQL/WAL/RX are matching ownership mirrors, not multiple assets");
                    helper.assertTrue(Math.addExact(output.get(),Math.addExact(p.pool(),owned))==input.get(),"actual native input/output plus unique ownership stages conserve FE");
                    helper.assertTrue(p.transfers().stream().filter(t->t.kind().equals("DEPOSIT")).count()==count+1 && p.transfers().stream().map(Transfer::id).distinct().count()==p.transfers().size(),"all original business IDs remain unique");
                    CrossTesseract.LOG.info("CT_RC_DISCOVERY_{} source={} receiver={} native_input={} native_output={} pool={} owned={} WAL_mirror={} first_new_credit_ms={} max_consume_gap_ms={} old_LOCAL_not_exhausted=true",
                        negative?"NEGATIVE":"PASS",source.id(),receiver.get().id(),input.get(),output.get(),p.pool(),owned,wal,firstNewCredit.get()==0?-1:(firstNewCredit.get()-start.get())/1_000_000.0,maxOutputGap.get()/1_000_000.0);
                }).thenSucceed();
        });
    }
    private static Proof proof(Authority a,Path journal,UUID channel,UUID source,UUID receiver)throws Exception{
        var transfers=a.database().connection(c->Sql.query(c,"SELECT transfer_id,kind,state,amount,remaining FROM ct_transfers WHERE cluster_id=? AND channel_id=? ORDER BY transfer_id",a.session().cluster(),channel).stream().map(r->new Transfer(Sql.uuid(r,"transfer_id"),Sql.str(r,"kind"),Sql.str(r,"state"),Sql.num(r,"amount"),Sql.num(r,"remaining"))).toList());
        long pool=a.database().connection(c->Sql.num(Sql.one(c,"SELECT COALESCE(SUM(amount),0) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",a.session().cluster(),channel),"n"));
        long pending=a.database().connection(c->Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_outbox o LEFT JOIN ct_inbox i ON i.cluster_id=o.cluster_id AND i.server_id=? AND i.event_id=o.event_id WHERE o.cluster_id=? AND o.subject_id=? AND o.event_type='BALANCE_CHANGED' AND (o.published_at IS NULL OR i.event_id IS NULL)",a.session().server(),a.session().cluster(),channel),"n"));
        var store=new LocalJournal(journal);return new Proof(transfers,pool,pending,store.read(source).orElseThrow(),store.read(receiver).orElseThrow());
    }
    private RcDiscoveryGameTests(){}
}
