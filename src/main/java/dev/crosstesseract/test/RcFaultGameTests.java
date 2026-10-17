package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.runtime.RuntimeService;
import dev.crosstesseract.backend.*;
import java.util.Map;
import net.minecraft.world.level.storage.LevelResource;
import java.util.concurrent.atomic.*;
import net.minecraft.core.Direction;
import net.minecraft.gametest.framework.*;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** Opt-in separate native fault batch with real positive assets; never run in performance windows. */
@PrefixGameTestTemplate(false)
public final class RcFaultGameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="rc_capacity",timeoutTicks=1_000_000)
    public static void fullCompletionAdmissionRetainsAlreadyAcceptedPositiveTransfer(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var runtime=be.runtime();var endpoint=be.id();var journalPath=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");be.mode(Protocol.FE,Protocol.Mode.BOTH);
            var port=helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP);
            var hold=new AtomicReference<Faults.Hold>();var capacity=new AtomicReference<RuntimeService.TestCapacity>();
            var attempted=new AtomicInteger();var rejection=new AtomicReference<String>();
            var evidence=new AtomicReference<Map<String,Object>>();
            helper.startSequence()
                .thenExecute(()->{hold.set(Faults.hold(runtime.clusterId(),"after_send_wal",be.id()));helper.assertTrue(port.receiveEnergy(128,false)==128,"128 real native FE accepted");})
                .thenWaitUntil(()->helper.assertTrue(hold.get().reached() && !hold.get().timedOut(),"real source WAL barrier pending"))
                .thenExecute(()->{
                    capacity.set(runtime.testOccupyCompletionCapacity());
                    try{
                        helper.assertTrue(be.inFlight() && capacity.get().held()>0 && capacity.get().full(),"one real transfer plus reservations fills actual mailbox");
                        runtime.submit(a->{attempted.incrementAndGet();return true;},ok->helper.assertTrue(false,"rejected job cannot complete"),rejection::set);
                        helper.assertTrue("completion_queue_full".equals(rejection.get()) && attempted.get()==0,"rejected work never reaches SQL/WAL");
                    }finally{hold.get().release();}
                })
                .thenWaitUntil(()->helper.assertTrue(!be.inFlight() && be.buffer().receiveAmount(Protocol.FE)==128,"already admitted positive transfer completes despite full admission"))
                .thenExecute(()->{
                    capacity.get().close();
                    helper.assertTrue(port.extractEnergy(128,false)==128,"exclusive RX can be consumed once");
                    helper.assertTrue(port.extractEnergy(128,false)==0 && attempted.get()==0,"no duplicate consumption or rejected task execution");
                    CrossTesseract.LOG.info("CT_RC_CAPACITY_PASS endpoint={} input=128 external_native_output=128 duplicate_output=0 rejected_task_executions=0",be.id());
                })
                .thenWaitUntil(()->helper.assertTrue(!be.inFlight() && be.buffer().receiveAmount(Protocol.FE)==0 && be.buffer().sendAmount(Protocol.FE)==0,"in-flight reaches terminal state after release"))
                .thenWaitUntil(()->helper.assertTrue(!be.inFlight() && !be.buffer().dirty(),"consumption and zero-tombstone checkpoints must finish on actual backend time"))
                .thenExecute(()->runtime.submit(a->{
                    var snapshot=new LocalJournal(journalPath).read(endpoint).orElseThrow();
                    var observed=a.database().connection(c->Sql.one(c,"SELECT SUM(kind='DEPOSIT') AS deposits,SUM(CASE WHEN kind='DEPOSIT' THEN amount ELSE 0 END) AS input,SUM(kind='ALLOCATE') AS allocations,SUM(CASE WHEN kind='ALLOCATE' THEN remaining ELSE 0 END) AS remaining FROM ct_transfers WHERE cluster_id=? AND endpoint_id=?",a.session().cluster(),endpoint));
                    helperEvidence(snapshot.deposits().isEmpty() && snapshot.credits().stream().allMatch(credit->credit.remaining()==0));return observed;
                },evidence::set,code->helper.assertTrue(false,"independent ownership evidence failed: "+code)))
                .thenWaitUntil(()->helper.assertTrue(evidence.get()!=null,"SQL and WAL confirmation pending"))
                .thenExecute(()->{
                    var observed=evidence.get();helper.assertTrue(Sql.num(observed,"deposits")==1 && Sql.num(observed,"input")==128 && Sql.num(observed,"allocations")==1 && Sql.num(observed,"remaining")==0,"one original deposit and one exhausted allocation; no refund or duplicate asset");
                })
                .thenSucceed();
        });
    }
    private static void helperEvidence(boolean valid){if(!valid)throw new IllegalStateException("positive capacity test WAL did not drain");}
    private RcFaultGameTests(){}
}
