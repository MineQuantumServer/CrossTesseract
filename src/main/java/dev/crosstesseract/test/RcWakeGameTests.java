package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.DomainException;
import dev.crosstesseract.core.LocalBuffer;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.Protocol;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.level.storage.LevelResource;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** A queued checkpoint is not a queued inventory-discovery intent. Real SQL/WAL/native assets. */
@PrefixGameTestTemplate(false)
public final class RcWakeGameTests {
    private record Transfer(UUID id,UUID endpoint,String kind,String state,long amount,long remaining){}
    private record Evidence(List<Transfer> transfers,long pool,LocalSnapshot source,LocalSnapshot receiver){}

    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="rc_wake",timeoutTicks=1_000_000)
    public static void channelHintUpgradesPendingCheckpointBeforeTheFirstAllocation(GameTestHelper helper){
        Fixtures.bound(helper,source->{
            var runtime=source.runtime();UUID channel=source.channel(),sourceId=source.id();
            helper.assertTrue(runtime.limits().transfer().localFast() && runtime.limits().transfer().channelBatches()
                && runtime.limits().transfer().devices()>=2,"isolated RC optimized two-device batch required");
            Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var receiver=new AtomicReference<TesseractBlockEntity>();var receiverPort=new AtomicReference<IEnergyStorage>();
            var hold=new AtomicReference<Faults.Hold>();var first=new AtomicReference<Evidence>();var drained=new AtomicReference<Evidence>();
            var failure=new AtomicReference<String>();var settledAt=new AtomicLong();var refreshedAt=new AtomicLong();
            IEnergyStorage sourcePort=helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,source.getBlockPos(),Direction.UP);
            helper.assertTrue(sourcePort!=null,"real native source FE capability registered");source.mode(Protocol.FE,Protocol.Mode.SEND);

            helper.startSequence()
                .thenExecute(()->{
                    var pos=new BlockPos(3,1,1);helper.setBlock(pos,CrossTesseract.TESSERACT.get());
                    var be=(TesseractBlockEntity)helper.getBlockEntity(pos);be.placed(source.owner());receiver.set(be);
                    be.mode(Protocol.FE,Protocol.Mode.RECEIVE);
                    receiverPort.set(helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP));
                    helper.assertTrue(receiverPort.get()!=null,"real native receiver FE capability registered");
                })
                .thenWaitUntil(()->helper.assertTrue(receiver.get().registered(),"second actual endpoint registration pending"))
                .thenExecute(()->{
                    var be=receiver.get();UUID id=be.id();long version=be.endpointVersion();
                    runtime.submit(a->a.bind(source.owner(),id,version,channel),be::applyEndpoint,failure::set);
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(failure.get()==null,"binding failed: "+failure.get());var be=receiver.get();
                    helper.assertTrue(channel.equals(be.channel()) && source.allowed(Protocol.FE,null,true)
                        && be.allowed(Protocol.FE,null,false) && !source.inFlight() && !be.inFlight(),"fresh permissions and initial backend work pending");
                })
                // Real wall time lets ordinary initial binding notifications settle. No tick sleep or IO wait.
                .thenExecute(()->settledAt.set(System.nanoTime()))
                .thenWaitUntil(()->helper.assertTrue(System.nanoTime()-settledAt.get()>=TimeUnit.MILLISECONDS.toNanos(2_200),"initial notification wall-clock settling pending"))
                .thenWaitUntil(()->{
                    var be=receiver.get();helper.assertTrue(source.allowed(Protocol.FE,null,true) && be.allowed(Protocol.FE,null,false)
                        && !source.inFlight() && !be.inFlight() && !source.buffer().dirty() && !be.buffer().dirty(),"authorized empty endpoints reach a real terminal checkpoint");
                })
                .thenExecute(()->{
                    var be=receiver.get();helper.assertTrue(source.buffer().empty() && be.buffer().empty(),"new isolated fixture has no pre-existing asset");
                    // A real ordinary capture initializes/refreshes the demand cache; no SQL-side fabrication.
                    be.buffer().touch();refreshedAt.set(System.nanoTime());runtime.testReadyBatch(List.of(be.id()));
                })
                .thenWaitUntil(()->helper.assertTrue(!receiver.get().inFlight() && !receiver.get().buffer().dirty(),"real initial demand/checkpoint callback pending"))
                .thenExecute(()->{
                    var be=receiver.get();helper.assertTrue(System.nanoTime()-refreshedAt.get()<TimeUnit.SECONDS.toNanos(2),"initialization exceeded the intended discovery-cache wall-clock window");
                    helper.assertTrue(source.allowed(Protocol.FE,null,true) && be.allowed(Protocol.FE,null,false),"current native permission gates remain open");
                    helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==0 && be.buffer().receiveRoom(Protocol.FE)==LocalBuffer.slotCapacity(Protocol.FE),"receiver remains empty with actual FE room");
                    var point=Faults.hold(runtime.clusterId(),"after_deposit",sourceId);hold.set(point);
                    try{
                        // This hook records ONLY RX_CONSUMED and signals the existing coordinator.
                        // touch() creates a real zero-asset checkpoint, not a synthetic credit/consumption.
                        be.buffer().touch();runtime.testReadyCheckpointBatch(List.of(be.id()));
                        helper.assertTrue(sourcePort.receiveEnergy(128,false)==128,"all128 FE originate in actual native source input");
                        runtime.testReadyBatch(List.of(sourceId));runtime.testWakeChannel(channel);
                    }catch(RuntimeException | Error error){point.release();throw error;}
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(!hold.get().timedOut(),"actual first channelBatch did not reach the five-second deposit barrier");
                    helper.assertTrue(hold.get().reached(),"real committed deposit worker barrier pending");
                })
                .thenExecute(()->{
                    var be=receiver.get();var point=hold.get();
                    try{
                        helper.assertTrue(source.inFlight() && be.inFlight(),"source and checkpoint-only receiver share this first admitted lease");
                        helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==0,"RESERVED credit is not exposed before destination WAL/publication");
                        UUID receiverId=be.id();
                        runtime.submit(a->observe(a,journal,channel,sourceId,receiverId),first::set,code->{failure.set(code);point.release();});
                    }catch(RuntimeException | Error error){point.release();throw error;}
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(failure.get()==null,"first committed SQL/WAL observation failed: "+failure.get());
                    helper.assertTrue(!hold.get().timedOut(),"first-batch evidence exceeded the worker-only barrier deadline");
                    helper.assertTrue(first.get()!=null,"independent first-batch SQL/WAL observation pending");
                })
                .thenExecute(()->{
                    try{
                        var proof=first.get();var be=receiver.get();
                        assertTransfers(helper,proof,sourceId,be.id(),"RESERVED",128);
                        helper.assertTrue(source.inFlight() && be.inFlight() && be.buffer().receiveAmount(Protocol.FE)==0,"same channel lease is still held before any native RX publication");
                        var deposit=proof.transfers().stream().filter(t->t.kind().equals("DEPOSIT")).findFirst().orElseThrow();
                        helper.assertTrue(proof.source().deposits().size()==1 && proof.source().deposits().getFirst().transaction().equals(deposit.id())
                            && proof.source().deposits().getFirst().amount()==128,"first real send WAL keeps the original128 FE business ID until publication");
                        helper.assertTrue(proof.receiver().deposits().isEmpty() && proof.receiver().credits().isEmpty(),"first SQL allocation precedes receiver WAL credit and LOCAL promotion");
                    }finally{hold.get().release();}
                })
                .thenWaitUntil(()->helper.assertTrue(!source.inFlight() && !receiver.get().inFlight()
                    && source.buffer().sendAmount(Protocol.FE)==0 && receiver.get().buffer().receiveAmount(Protocol.FE)==128,"first-batch128 FE becomes native RX only after durable publication"))
                .thenExecute(()->{
                    var be=receiver.get();var allocation=first.get().transfers().stream().filter(t->t.kind().equals("ALLOCATE")).findFirst().orElseThrow();
                    helper.assertTrue(be.buffer().received(Protocol.FE).size()==1 && be.buffer().received(Protocol.FE).getFirst().transaction().equals(allocation.id()),"native RX is the original first-batch SQL allocation");
                    helper.assertTrue(receiverPort.get().extractEnergy(128,false)==128,"all128 FE actually leave through the native receiver");
                    helper.assertTrue(receiverPort.get().extractEnergy(128,false)==0 && sourcePort.extractEnergy(128,false)==0,"duplicate output is zero");
                })
                .thenWaitUntil(()->helper.assertTrue(!source.inFlight() && !receiver.get().inFlight() && !source.buffer().dirty()
                    && !receiver.get().buffer().dirty() && source.buffer().empty() && receiver.get().buffer().empty(),"actual consumption, zero tombstones and flights reach terminal state"))
                .thenExecute(()->{UUID receiverId=receiver.get().id();runtime.submit(a->observe(a,journal,channel,sourceId,receiverId),drained::set,failure::set);})
                .thenWaitUntil(()->{
                    helper.assertTrue(failure.get()==null,"final committed SQL/WAL observation failed: "+failure.get());
                    helper.assertTrue(drained.get()!=null,"final independent SQL/WAL observation pending");
                })
                .thenExecute(()->{
                    var proof=drained.get();assertTransfers(helper,proof,sourceId,receiver.get().id(),"CONSUMED",0);
                    helper.assertTrue(proof.transfers().stream().map(Transfer::id).toList().equals(first.get().transfers().stream().map(Transfer::id).toList()),"no later poll manufactured another transfer or refund");
                    helper.assertTrue(emptyWal(proof.source()) && emptyWal(proof.receiver()),"both actual WALs retain no pending input or spendable credit");
                    helper.assertTrue(!source.inFlight() && !receiver.get().inFlight(),"both endpoint flights ended");
                    CrossTesseract.LOG.info("CT_RC_WAKE_PASS source={} receiver={} input=128 first_batch_RESERVED=128 prepublication_RX=0 external_native_output=128 duplicate_output=0 final_SQL_pool=0 final_SQL_remaining=0 final_WAL_assets=0",sourceId,receiver.get().id());
                }).thenSucceed();
        });
    }

    private static Evidence observe(Authority a,Path path,UUID channel,UUID source,UUID receiver)throws Exception{
        var transfers=a.database().connection(c->Sql.query(c,"SELECT transfer_id,endpoint_id,kind,state,amount,remaining FROM ct_transfers WHERE cluster_id=? AND channel_id=? ORDER BY transfer_id",a.session().cluster(),channel)
            .stream().map(row->new Transfer(Sql.uuid(row,"transfer_id"),Sql.uuid(row,"endpoint_id"),Sql.str(row,"kind"),Sql.str(row,"state"),Sql.num(row,"amount"),Sql.num(row,"remaining"))).toList());
        long pool=a.database().connection(c->Sql.num(Sql.one(c,"SELECT COALESCE(SUM(amount),0) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",a.session().cluster(),channel),"n"));
        var journal=new LocalJournal(path);var sourceWal=journal.read(source).orElseThrow();var receiverWal=journal.read(receiver).orElseThrow();
        DomainException.require(sourceWal.endpoint().equals(source) && receiverWal.endpoint().equals(receiver),"fixture_journal_identity_conflict");
        return new Evidence(transfers,pool,sourceWal,receiverWal);
    }
    private static void assertTransfers(GameTestHelper helper,Evidence proof,UUID source,UUID receiver,String state,long remaining){
        helper.assertTrue(proof.transfers().size()==2 && proof.pool()==0,"exactly two original SQL transfers and no pooled refund balance");
        var deposits=proof.transfers().stream().filter(t->t.kind().equals("DEPOSIT")).toList();
        var allocations=proof.transfers().stream().filter(t->t.kind().equals("ALLOCATE")).toList();
        helper.assertTrue(deposits.size()==1 && deposits.getFirst().endpoint().equals(source) && deposits.getFirst().amount()==128
            && deposits.getFirst().remaining()==0 && deposits.getFirst().state().equals("COMMITTED"),"one original native128 FE deposit is committed once");
        helper.assertTrue(allocations.size()==1 && allocations.getFirst().endpoint().equals(receiver) && allocations.getFirst().amount()==128
            && allocations.getFirst().remaining()==remaining && allocations.getFirst().state().equals(state),"first admitted receiver allocation must already be128 "+state+"; later POLL cannot rescue this assertion");
    }
    private static boolean emptyWal(LocalSnapshot snapshot){
        return snapshot.deposits().isEmpty() && snapshot.credits().stream().allMatch(credit->credit.remaining()==0)
            && snapshot.thermal().microjoules()==0 && snapshot.thermal().pending()==null;
    }
    private RcWakeGameTests(){}
}
