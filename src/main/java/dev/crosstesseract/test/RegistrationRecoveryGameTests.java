package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.Protocol;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import net.minecraft.core.Direction;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.level.storage.LevelResource;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

@PrefixGameTestTemplate(false)
public final class RegistrationRecoveryGameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void failedJournalIdentityStopsRegistrationRetriesAndPreservesUnrestoredAssets(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var runtime=be.runtime();var level=helper.getLevel();var position=be.getBlockPos();UUID id=be.id();
            Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var replacement=new AtomicReference<TesseractBlockEntity>();var before=new AtomicReference<Evidence>();var after=new AtomicReference<Evidence>();long[] observed={0};
            be.mode(Protocol.FE,Protocol.Mode.BOTH);
            helper.startSequence()
                .thenExecute(()->helper.assertTrue(be.energy(null).receiveEnergy(128,false)==128,"native input for the durable recovery fixture"))
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==128 && !be.inFlight(),"real LOCAL receipt and WAL pending"))
                .thenExecute(()->{
                    var saved=be.saveWithFullMetadata(level.registryAccess());saved.putLong("checkpoint",Long.MAX_VALUE);
                    level.removeBlockEntity(position);
                    var fresh=new TesseractBlockEntity(position,be.getBlockState());fresh.loadWithComponents(saved,level.registryAccess());level.setBlockEntity(fresh);fresh.onLoad();replacement.set(fresh);
                })
                .thenWaitUntil(()->helper.assertTrue(replacement.get().registrationRecoveryRequired(),"a checkpoint beyond the fsynced WAL requires terminal local review"))
                .thenExecute(()->runtime.submit(a->observe(a,id,journal),value->{before.set(value);observed[0]=System.nanoTime();},code->helper.assertTrue(false,code)))
                .thenWaitUntil(()->helper.assertTrue(before.get()!=null && System.nanoTime()-observed[0]>=3_000_000_000L,"three wall-clock seconds of registration rotations pending"))
                .thenExecute(()->runtime.submit(a->observe(a,id,journal),after::set,code->helper.assertTrue(false,code)))
                .thenWaitUntil(()->helper.assertTrue(after.get()!=null,"durable after-observation pending"))
                .thenExecute(()->{
                    var fresh=replacement.get();var first=before.get();var last=after.get();
                    helper.assertTrue(!fresh.registered() && fresh.registrationRecoveryRequired() && fresh.energy(null).receiveEnergy(1,false)==0 && fresh.energy(null).extractEnergy(128,false)==0,"failed registration cannot open capabilities");
                    helper.assertTrue(first.state().equals("QUARANTINED") && last.state().equals("QUARANTINED") && first.remaining()==128 && last.remaining()==128,"exclusive SQL ownership remains isolated, without refund or destruction");
                    helper.assertTrue(first.lastSeen().equals(last.lastSeen()),"terminal registration cannot repeatedly update SQL last_seen");
                    helper.assertTrue(first.checkpoint().equals(last.checkpoint()) && last.checkpoint().credits().stream().mapToLong(LocalSnapshot.Credit::remaining).sum()==128,"unrestored empty memory cannot rewrite the original durable WAL");
                    helper.assertTrue(fresh.saveWithFullMetadata(level.registryAccess()).getLong("checkpoint")==Long.MAX_VALUE,"saving quarantined NBT cannot erase the checkpoint conflict");
                })
                .thenSucceed();
        });
    }

    /** The database stays running: one explicitly armed worker injects a checked SQLException
     * after restoring/fsyncing the WAL and before obtaining the checkpoint confirmation. */
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void unloadedRegistrationWithInjectedSqlConfirmationFailurePreservesWalAndAllowsFreshRecovery(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var runtime=be.runtime();var level=helper.getLevel();var position=be.getBlockPos();UUID id=be.id();
            Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var saved=new AtomicReference<CompoundTag>();var credit=new AtomicReference<UUID>();
            var interrupted=new AtomicReference<TesseractBlockEntity>();var recovered=new AtomicReference<TesseractBlockEntity>();
            var hold=new AtomicReference<Faults.Hold>();
            var before=new AtomicReference<ConfirmationEvidence>();var held=new AtomicReference<ConfirmationEvidence>();
            var failed=new AtomicReference<ConfirmationEvidence>();var consumed=new AtomicReference<ConfirmationEvidence>();
            be.mode(Protocol.FE,Protocol.Mode.BOTH);
            helper.startSequence()
                .thenExecute(()->{
                    var energy=level.getCapability(Capabilities.EnergyStorage.BLOCK,position,Direction.UP);
                    helper.assertTrue(energy!=null && energy.receiveEnergy(128,false)==128,"actual native capability accepts the sole 128 FE input");
                })
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==128 && be.buffer().sendAmount(Protocol.FE)==0 && !be.inFlight(),"real SQL/WAL loopback receipt pending"))
                .thenExecute(()->{
                    helper.assertTrue(be.buffer().received(Protocol.FE).size()==1,"one original exclusive credit");
                    credit.set(be.buffer().received(Protocol.FE).getFirst().transaction());
                    be.mode(Protocol.FE,Protocol.Mode.OFF);saved.set(be.saveWithFullMetadata(level.registryAccess()));
                    // Removing only the actual block entity models unload without physical sealing.
                    level.removeBlockEntity(position);
                })
                .thenWaitUntil(()->helper.assertTrue(runtime.metricSnapshot().get("closing_devices").intValue()==0,"initial unload must finish its durable closing barrier"))
                .thenExecute(()->runtime.submit(a->observeConfirmation(a,id,credit.get(),journal),before::set,code->helper.assertTrue(false,"initial durable observation: "+code)))
                .thenWaitUntil(()->helper.assertTrue(before.get()!=null,"original closed WAL/SQL observation pending"))
                .thenExecute(()->{
                    var original=before.get();
                    helper.assertTrue(original.endpoint().state().equals("ACTIVE") && original.endpoint().remaining()==128,"unload retains 128 FE exclusive SQL ownership");
                    helper.assertTrue(original.sqlCheckpoint()==original.endpoint().checkpoint().revision(),"initial unload establishes one matching WAL/SQL checkpoint");
                    helper.assertTrue(original.endpoint().checkpoint().credits().size()==1 && original.creditState().equals("LOCAL"),"original 128 FE receipt is already published locally");
                    hold.set(Faults.holdLostRegistrationConfirmation(runtime.clusterId(),id));
                    var fresh=new TesseractBlockEntity(position,be.getBlockState());
                    fresh.loadWithComponents(saved.get().copy(),level.registryAccess());level.setBlockEntity(fresh);fresh.onLoad();interrupted.set(fresh);
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(!hold.get().timedOut(),"registration must reach the restored WAL within the bounded five-second hold");
                    helper.assertTrue(hold.get().reached(),"real registration worker restored WAL hold pending");
                })
                .thenExecute(()->runtime.submit(a->observeConfirmation(a,id,credit.get(),journal),held::set,code->helper.assertTrue(false,"held restored-WAL observation: "+code)))
                .thenWaitUntil(()->helper.assertTrue(held.get()!=null,"read actual fsynced restored WAL while its worker is held"))
                .thenExecute(()->{
                    var point=hold.get();
                    try{
                        var fresh=interrupted.get();var original=before.get();var durable=held.get();
                        helper.assertTrue(!point.timedOut() && fresh.registering() && !fresh.registered() && fresh.buffer().empty(),"held registration has not hydrated or opened main-thread memory");
                        helper.assertTrue(fresh.energy(Direction.DOWN).extractEnergy(128,false)==0,"unrestored native memory cannot spend the SQL receipt");
                        helper.assertTrue(durable.endpoint().checkpoint().revision()==original.endpoint().checkpoint().revision()+1 && sameAssets(original.endpoint().checkpoint(),durable.endpoint().checkpoint()),"restored WAL advances one revision and preserves every asset identity/quantity");
                        helper.assertTrue(durable.endpoint().remaining()==128 && durable.sqlCheckpoint()==original.sqlCheckpoint(),"the hold occurs after fsync and before the new SQL checkpoint confirmation");
                        saved.set(fresh.saveWithFullMetadata(level.registryAccess()));level.removeBlockEntity(position);
                        helper.assertTrue(fresh.isRemoved() && fresh.registering(),"main-thread unload occurs while the real registration worker is still held");
                    }finally{point.release();}
                })
                .thenWaitUntil(()->helper.assertTrue(hold.get().failureInjected() && !interrupted.get().registering() && runtime.metricSnapshot().get("closing_devices").intValue()==0,"injected SQL confirmation failure must terminate registration and release closing"))
                .thenExecute(()->runtime.submit(a->observeConfirmation(a,id,credit.get(),journal),failed::set,code->helper.assertTrue(false,"after failed registration observation: "+code)))
                .thenWaitUntil(()->helper.assertTrue(failed.get()!=null,"observe durable ownership after failed unhydrated unload"))
                .thenExecute(()->{
                    var last=failed.get();var durable=held.get();var fresh=interrupted.get();
                    helper.assertTrue(!hold.get().timedOut() && !fresh.registered() && !fresh.registrationRecoveryRequired(),"a checked transient SQL failure is neither a successful hydration nor a permanent local quarantine");
                    helper.assertTrue(last.endpoint().state().equals("ACTIVE") && last.endpoint().remaining()==128 && last.creditState().equals("LOCAL"),"test-injected SQLException keeps the same 128 FE SQL asset, without Domain quarantine or refund");
                    helper.assertTrue(last.endpoint().checkpoint().equals(durable.endpoint().checkpoint()) && last.sqlCheckpoint()==durable.sqlCheckpoint(),"unhydrated close must preserve the exact latest WAL and cannot invent an empty checkpoint");
                    assertSingleBusinessAsset(helper,last);
                    var next=new TesseractBlockEntity(position,be.getBlockState());
                    next.loadWithComponents(saved.get().copy(),level.registryAccess());level.setBlockEntity(next);next.onLoad();recovered.set(next);
                })
                .thenWaitUntil(()->{
                    var next=recovered.get();
                    helper.assertTrue(next.registered() && !next.registering() && next.pauseReason().isEmpty() && next.channelOwner()!=null,"fresh same-ID reload must pass the released closing barrier and fresh SQL authorization");
                    helper.assertTrue(next.buffer().receiveAmount(Protocol.FE)==128 && next.buffer().sendAmount(Protocol.FE)==0,"fresh reload restores exactly the existing 128 FE");
                })
                .thenIdle(100)
                .thenExecute(()->{
                    var next=recovered.get();
                    helper.assertTrue(next.id().equals(id) && next.buffer().received(Protocol.FE).size()==1 && next.buffer().received(Protocol.FE).getFirst().transaction().equals(credit.get()),"fresh recovery retains the original endpoint and full credit identity");
                    next.mode(Protocol.FE,Protocol.Mode.RECEIVE);
                    var energy=level.getCapability(Capabilities.EnergyStorage.BLOCK,position,Direction.DOWN);
                    helper.assertTrue(energy!=null && energy.extractEnergy(128,false)==128 && energy.extractEnergy(128,false)==0,"actual native capability redeems 128 FE once and cannot duplicate the old receipt");
                })
                .thenIdle(1)
                .thenWaitUntil(()->helper.assertTrue(!recovered.get().inFlight() && !recovered.get().buffer().hasWork() && recovered.get().buffer().receiveAmount(Protocol.FE)==0,"real SQL/WAL consumption checkpoint must finish before final evidence"))
                .thenExecute(()->runtime.submit(a->observeConfirmation(a,id,credit.get(),journal),consumed::set,code->helper.assertTrue(false,"consumed durable evidence: "+code)))
                .thenWaitUntil(()->helper.assertTrue(consumed.get()!=null,"consumed SQL/WAL observation pending"))
                .thenExecute(()->{
                    var last=consumed.get();assertSingleBusinessAsset(helper,last);
                    helper.assertTrue(last.endpoint().remaining()==0 && last.creditState().equals("CONSUMED") && last.creditRemaining()==0,"the one original SQL receipt is durably consumed, not rediscovered");
                    helper.assertTrue(last.endpoint().checkpoint().deposits().isEmpty() && last.endpoint().checkpoint().credits().stream().allMatch(c->c.remaining()==0),"latest actual world WAL contains no positive or replayable balance");
                    helper.assertTrue(recovered.get().energy(Direction.DOWN).extractEnergy(1,false)==0,"idle recovery cannot restore already extracted FE");
                })
                .thenSucceed();
        });
    }

    private static boolean sameAssets(LocalSnapshot first,LocalSnapshot last){
        return first.endpoint().equals(last.endpoint()) && first.world().equals(last.world()) && first.generation()==last.generation()
            && first.deposits().equals(last.deposits()) && first.credits().equals(last.credits()) && first.thermal().equals(last.thermal());
    }
    private record ConfirmationEvidence(Evidence endpoint,long sqlCheckpoint,long balance,long deposited,long depositCount,
                                        long allocated,long allocationCount,String creditState,long creditRemaining){}
    private static ConfirmationEvidence observeConfirmation(Authority authority,UUID endpoint,UUID credit,Path journal) throws Exception {
        var evidence=observe(authority,endpoint,journal);
        return authority.database().connection(c->{
            String cluster=authority.session().cluster();
            var ep=Sql.one(c,"SELECT checkpoint,channel_id FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster,endpoint);
            var balance=Sql.one(c,"SELECT COALESCE(SUM(amount),0) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",cluster,Sql.uuid(ep,"channel_id"));
            var deposits=Sql.one(c,"SELECT COUNT(*) AS n,COALESCE(SUM(amount),0) AS amount FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='DEPOSIT'",cluster,endpoint);
            var allocations=Sql.one(c,"SELECT COUNT(*) AS n,COALESCE(SUM(amount),0) AS amount FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='ALLOCATE'",cluster,endpoint);
            var original=Sql.one(c,"SELECT state,remaining FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND transfer_id=? AND kind='ALLOCATE'",cluster,endpoint,credit);
            return new ConfirmationEvidence(evidence,Sql.num(ep,"checkpoint"),Sql.num(balance,"n"),Sql.num(deposits,"amount"),Sql.num(deposits,"n"),
                Sql.num(allocations,"amount"),Sql.num(allocations,"n"),Sql.str(original,"state"),Sql.num(original,"remaining"));
        });
    }
    private static void assertSingleBusinessAsset(GameTestHelper helper,ConfirmationEvidence evidence){
        helper.assertTrue(evidence.balance()==0 && evidence.deposited()==128 && evidence.depositCount()==1 && evidence.allocated()==128 && evidence.allocationCount()==1,"all registration retries reuse the sole original 128 FE deposit and allocation business IDs, without a duplicate channel balance");
    }
    private record Evidence(String state,Instant lastSeen,long remaining,LocalSnapshot checkpoint){}
    private static Evidence observe(Authority authority,UUID endpoint,Path journal) throws Exception {
        var checkpoint=new LocalJournal(journal).read(endpoint).orElseThrow();
        return authority.database().connection(c->{
            var row=Sql.one(c,"SELECT state,last_seen FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",authority.session().cluster(),endpoint);
            var owned=Sql.one(c,"SELECT COALESCE(SUM(remaining),0) AS n FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='ALLOCATE'",authority.session().cluster(),endpoint);
            return new Evidence(Sql.str(row,"state"),((Timestamp)row.get("last_seen")).toInstant(),Sql.num(owned,"n"),checkpoint);
        });
    }
    private RegistrationRecoveryGameTests(){}
}
