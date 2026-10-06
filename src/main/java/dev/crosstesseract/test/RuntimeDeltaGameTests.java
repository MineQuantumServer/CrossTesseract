package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.Models.Allocation;
import dev.crosstesseract.core.Protocol;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import net.minecraft.core.Direction;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.level.storage.LevelResource;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** Real Minecraft capabilities, runtime workers, MySQL ownership and the world's fsynced WAL. */
@PrefixGameTestTemplate(false)
public final class RuntimeDeltaGameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void localInputAndConsumptionContinueDuringCapturedSendWithoutReplayingOldRemaining(
            GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var runtime=be.runtime();
            helper.assertTrue(runtime.limits().transfer().localFast(),"requires the optimized local exchange path");
            be.mode(Protocol.FE,Protocol.Mode.BOTH);
            var energy=helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP);
            helper.assertTrue(energy!=null,"real native FE capability must be registered");
            UUID endpoint=be.id(),channel=be.channel();
            Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var hold=new AtomicReference<Faults.Hold>();
            var oldCredit=new AtomicReference<UUID>();
            var evidence=new AtomicReference<Evidence>();
            helper.startSequence()
                .thenExecute(()->helper.assertTrue(energy.receiveEnergy(128,false)==128,"initial native self-send must accept 128 FE"))
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==128 && be.buffer().sendAmount(Protocol.FE)==0 && !be.inFlight(),"initial real SQL/WAL RX pending"))
                .thenExecute(()->{
                    helper.assertTrue(be.buffer().received(Protocol.FE).size()==1,"initial RX has one exclusive credit");
                    oldCredit.set(be.buffer().received(Protocol.FE).getFirst().transaction());
                    var point=Faults.hold(runtime.clusterId(),"after_send_wal",endpoint);hold.set(point);
                    try{helper.assertTrue(energy.receiveEnergy(64,false)==64,"held ordinary transfer must accept another 64 FE");}
                    catch(RuntimeException | Error failure){point.release();throw failure;}
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(!hold.get().timedOut(),"backend did not reach the send WAL hold within five seconds");
                    helper.assertTrue(hold.get().reached(),"captured send WAL worker hold pending");
                })
                .thenExecute(()->{
                    var point=hold.get();
                    try{
                        helper.assertTrue(!point.timedOut() && be.inFlight(),"a real background transfer must still be held");
                        long capturedRevision=be.buffer().revision();
                        helper.assertTrue(energy.extractEnergy(23,false)==23,"old RX remains spendable while the captured send is held");
                        helper.assertTrue(energy.receiveEnergy(7,false)==7,"new native input remains accepted while the worker is held");
                        helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==105,"old RX consumption remains a local delta");
                        helper.assertTrue(be.buffer().sendAmount(Protocol.FE)==71,"captured 64 and later 7 remain distinct owned input");
                        helper.assertTrue(be.buffer().revision()>capturedRevision,"local IO must advance the captured WAL revision");
                    }finally{point.release();}
                })
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==176 && be.buffer().sendAmount(Protocol.FE)==0 && !be.inFlight(),"both captured and later input must arrive exactly once after release"))
                .thenIdle(100)
                .thenExecute(()->{
                    helper.assertTrue(!hold.get().timedOut(),"hold was explicitly released before timeout");
                    helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==176 && be.buffer().sendAmount(Protocol.FE)==0,"idle fallback and repeated callbacks cannot restore the spent 23 FE");
                    runtime.submit(a->observe(a,endpoint,channel,journal),evidence::set,code->helper.assertTrue(false,"SQL/WAL evidence failed: "+code));
                })
                .thenWaitUntil(()->helper.assertTrue(evidence.get()!=null,"actual SQL/WAL evidence pending"))
                .thenExecute(()->verify(helper,evidence.get(),endpoint,channel,oldCredit.get()))
                .thenSucceed();
        });
    }

    private record Evidence(long balance,long deposited,long depositCount,List<Allocation> allocations,
                            LocalSnapshot checkpoint){
        private Evidence{allocations=List.copyOf(allocations);}
    }

    /** Runs only on a backend worker; the GameTest server thread never reads disk or waits for SQL. */
    private static Evidence observe(Authority authority,UUID endpoint,UUID channel,Path journal) throws Exception {
        var allocations=authority.allocations(endpoint);
        var checkpoint=new LocalJournal(journal).read(endpoint).orElseThrow();
        String cluster=authority.session().cluster();
        return authority.database().connection(connection->{
            var balance=Sql.one(connection,"SELECT COALESCE(SUM(amount),0) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",cluster,channel);
            var deposits=Sql.one(connection,"SELECT COUNT(*) AS n,COALESCE(SUM(amount),0) AS amount FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND kind='DEPOSIT'",cluster,endpoint,channel);
            return new Evidence(Sql.num(balance,"n"),Sql.num(deposits,"amount"),Sql.num(deposits,"n"),allocations,checkpoint);
        });
    }

    private static void verify(GameTestHelper helper,Evidence evidence,UUID endpoint,UUID channel,UUID oldCredit){
        helper.assertTrue(evidence.balance()==0 && evidence.deposited()==199 && evidence.depositCount()==3,"actual SQL must contain exactly the 128, 64 and later 7 FE deposits");
        helper.assertTrue(evidence.allocations().size()==3 && evidence.allocations().stream().allMatch(a->a.endpoint().equals(endpoint) && a.channel().equals(channel) && a.state().equals("LOCAL")),"all three exclusive SQL allocations are published locally");
        helper.assertTrue(evidence.allocations().stream().mapToLong(Allocation::amount).sum()==199 && evidence.allocations().stream().mapToLong(Allocation::remaining).sum()==176,"actual SQL original minus consumed quantities must conserve 199 FE");
        helper.assertTrue(evidence.allocations().stream().anyMatch(a->a.id().equals(oldCredit) && a.amount()==128 && a.remaining()==105),"the old captured 128 FE credit must retain its consumed remaining=105");
        var checkpoint=evidence.checkpoint();
        helper.assertTrue(checkpoint.endpoint().equals(endpoint) && checkpoint.deposits().isEmpty(),"the actual world WAL has no uncommitted TX");
        helper.assertTrue(checkpoint.credits().stream().mapToLong(LocalSnapshot.Credit::remaining).sum()==176,"fsynced WAL preserves late consumption and new credits");
        helper.assertTrue(checkpoint.credits().stream().map(LocalSnapshot.Credit::transaction).collect(Collectors.toSet()).equals(evidence.allocations().stream().map(Allocation::id).collect(Collectors.toSet())),"WAL and SQL identify the same three credits without duplicates");
        helper.assertTrue(evidence.balance()+evidence.allocations().stream().mapToLong(Allocation::remaining).sum()+23==199,"SQL pool, owned RX and actual native extraction conserve every FE unit");
    }

    private RuntimeDeltaGameTests(){}
}
