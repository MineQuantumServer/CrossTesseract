package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.BusinessIds;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.core.Resource;
import dev.crosstesseract.runtime.RuntimeService;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import net.minecraft.core.BlockPos;
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

    /** Real physical removal of an unrestored 128 FE endpoint; both SQL failures are
     * explicit checked test injections while the actual database remains running. */
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="unhydrated_sql_seal_retry",timeoutTicks=1_000_000)
    public static void physicallyRemovedUnhydratedEndpointRetriesFailedSqlSealWithoutRewritingWal(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var runtime=be.runtime();var level=helper.getLevel();var position=be.getBlockPos();UUID id=be.id();
            Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var saved=new AtomicReference<CompoundTag>();var credit=new AtomicReference<UUID>();
            var interrupted=new AtomicReference<TesseractBlockEntity>();
            var registrationHold=new AtomicReference<Faults.Hold>();var sealHold=new AtomicReference<Faults.Hold>();
            var before=new AtomicReference<ConfirmationEvidence>();var held=new AtomicReference<SealEvidence>();var sealed=new AtomicReference<SealEvidence>();
            be.mode(Protocol.FE,Protocol.Mode.BOTH);
            helper.startSequence()
                .thenExecute(()->{
                    var energy=level.getCapability(Capabilities.EnergyStorage.BLOCK,position,Direction.UP);
                    helper.assertTrue(energy!=null && energy.receiveEnergy(128,false)==128,"actual native capability accepts the sole physical-removal fixture input");
                })
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==128 && be.buffer().sendAmount(Protocol.FE)==0 && !be.inFlight(),"real SQL/WAL loopback receipt pending before physical-removal recovery"))
                .thenExecute(()->{
                    helper.assertTrue(be.buffer().received(Protocol.FE).size()==1,"the physical-removal fixture owns one original credit");
                    credit.set(be.buffer().received(Protocol.FE).getFirst().transaction());
                    be.mode(Protocol.FE,Protocol.Mode.OFF);saved.set(be.saveWithFullMetadata(level.registryAccess()));level.removeBlockEntity(position);
                })
                .thenWaitUntil(()->helper.assertTrue(runtime.metricSnapshot().get("closing_devices").intValue()==0,"initial ordinary unload must finish the original durable checkpoint"))
                .thenExecute(()->runtime.submit(a->observeConfirmation(a,id,credit.get(),journal),before::set,code->helper.assertTrue(false,"physical-removal initial ownership: "+code)))
                .thenWaitUntil(()->helper.assertTrue(before.get()!=null,"original physical-removal WAL/SQL observation pending"))
                .thenExecute(()->{
                    var original=before.get();assertSingleBusinessAsset(helper,original);
                    helper.assertTrue(original.endpoint().state().equals("ACTIVE") && original.creditState().equals("LOCAL") && original.creditRemaining()==128,"original SQL owns one published 128 FE receipt");
                    helper.assertTrue(original.sqlCheckpoint()==original.endpoint().checkpoint().revision(),"ordinary unload has matching WAL/SQL revisions");
                    registrationHold.set(Faults.holdLostRegistrationConfirmation(runtime.clusterId(),id));
                    var fresh=new TesseractBlockEntity(position,be.getBlockState());fresh.loadWithComponents(saved.get().copy(),level.registryAccess());level.setBlockEntity(fresh);fresh.onLoad();interrupted.set(fresh);
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(!registrationHold.get().timedOut(),"physical-removal registration must reach its five-second restored-WAL hold");
                    helper.assertTrue(registrationHold.get().reached(),"physical-removal restored-WAL worker pending");
                })
                .thenExecute(()->runtime.submit(a->observeSeal(a,id,credit.get(),journal),held::set,code->helper.assertTrue(false,"physical-removal restored-WAL evidence: "+code)))
                .thenWaitUntil(()->helper.assertTrue(held.get()!=null,"read exact restored WAL before the physical removal"))
                .thenExecute(()->{
                    var point=registrationHold.get();
                    try{
                        var fresh=interrupted.get();var original=before.get();var durable=held.get().assets();
                        helper.assertTrue(!point.timedOut() && fresh.registering() && !fresh.registered() && fresh.buffer().empty(),"physical removal races real registration before any main-thread hydration");
                        helper.assertTrue(durable.endpoint().checkpoint().revision()==original.endpoint().checkpoint().revision()+1 && sameAssets(original.endpoint().checkpoint(),durable.endpoint().checkpoint()),"worker fsynced the restored revision with the original full 128 FE credit");
                        helper.assertTrue(durable.sqlCheckpoint()==original.sqlCheckpoint() && durable.creditRemaining()==128,"registration SQL checkpoint has not been confirmed");
                        helper.assertTrue(level.removeBlock(position,false) && fresh.isRemoved() && fresh.registering(),"real block onRemove seals while the registration worker is held");
                        helper.assertTrue(fresh.energy(Direction.DOWN).extractEnergy(128,false)==0,"removed unhydrated native capability cannot consume the credit");
                    }finally{point.release();}
                    // The release removes the first hold. The next main-thread completion
                    // starts closing, so the second bounded hold is armed before its worker.
                    sealHold.set(Faults.holdFailUnhydratedSealOnce(runtime.clusterId(),id));
                })
                .thenWaitUntil(()->{
                    helper.assertTrue(!sealHold.get().timedOut(),"retained removal intent must reach the bounded SQL seal hold");
                    helper.assertTrue(registrationHold.get().failureInjected() && !interrupted.get().registering() && sealHold.get().reached(),"failed registration must retain physical seal intent and submit its real closing worker");
                })
                .thenExecute(()->{
                    var point=sealHold.get();
                    try{helper.assertTrue(runtime.metricSnapshot().get("closing_devices").intValue()>0 && !interrupted.get().registered(),"unrestored SQL sealing remains represented by Closing");}
                    finally{point.release();}
                })
                .thenWaitUntil(()->helper.assertTrue(sealHold.get().failureInjected(),"one explicit checked SQL seal failure must be injected"))
                .thenExecute(()->helper.assertTrue(runtime.metricSnapshot().get("closing_devices").intValue()>0,"failed SQL seal cannot discard its Closing retry intent"))
                .thenWaitUntil(()->helper.assertTrue(runtime.metricSnapshot().get("closing_devices").intValue()==0,"the retained intent must retry and confirm SQL sealing"))
                .thenExecute(()->runtime.submit(a->observeSeal(a,id,credit.get(),journal),sealed::set,code->helper.assertTrue(false,"physical-removal final sealed evidence: "+code)))
                .thenWaitUntil(()->helper.assertTrue(sealed.get()!=null,"real SQL/WAL evidence after confirmed seal pending"))
                .thenExecute(()->{
                    var last=sealed.get();var durable=held.get();var assets=last.assets();assertSingleBusinessAsset(helper,assets);
                    helper.assertTrue(!registrationHold.get().timedOut() && !sealHold.get().timedOut(),"both failures used explicit release, not timeout");
                    helper.assertTrue(assets.endpoint().state().equals("SEALED") && last.chunkGrants()==0,"real SQL sealing succeeded and no chunk authorization remains");
                    helper.assertTrue(assets.endpoint().remaining()==128 && assets.creditState().equals("LOCAL") && assets.creditRemaining()==128,"physical removal preserves exclusive ownership without consumption, refund or retirement");
                    helper.assertTrue(assets.endpoint().checkpoint().equals(durable.assets().endpoint().checkpoint()) && last.walHash().equals(durable.walHash()) && assets.sqlCheckpoint()==durable.assets().sqlCheckpoint(),"unhydrated SQL retry preserves exact WAL bytes and never submits an empty or invented SQL checkpoint");
                    helper.assertTrue(level.getBlockEntity(position)==null && !interrupted.get().registered() && interrupted.get().energy(Direction.DOWN).extractEnergy(128,false)==0,"the physically removed unrestored endpoint never opens native extraction");
                })
                .thenSucceed();
        });
    }

    /** Both actual capabilities stay closed. One worker fails before SQL registration;
     * the other fails after a real SQL commit, without ever creating a WAL. */
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="unhydrated_sql_absence",timeoutTicks=1_000_000)
    public static void emptyUnhydratedRemovalDistinguishesConfirmedSqlAbsenceFromCommittedRegistration(GameTestHelper helper){
        var level=helper.getLevel();var runtime=RuntimeService.get(level.getServer());
        UUID absentId=BusinessIds.next(),committedId=BusinessIds.next(),owner=BusinessIds.next();
        Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
        var absent=new AtomicReference<TesseractBlockEntity>();var committed=new AtomicReference<TesseractBlockEntity>();
        var beforeSql=new AtomicReference<Faults.Hold>();var afterSql=new AtomicReference<Faults.Hold>();
        var held=new AtomicReference<EmptyRemovalEvidence>();var finished=new AtomicReference<EmptyRemovalEvidence>();
        helper.startSequence()
            .thenWaitUntil(()->helper.assertTrue(runtime.online(),"real backend must be online for authoritative SQL absence"))
            .thenExecute(()->{
                beforeSql.set(Faults.holdFailedBeforeSqlRegistration(runtime.clusterId(),absentId));
                afterSql.set(Faults.holdLostAfterSqlRegistration(runtime.clusterId(),committedId));
                // Use trusted fixture NBT to know the new IDs before onLoad submits work.
                // Neither identity has ever been admitted to SQL or accepted native input.
                absent.set(newEmptyRegistration(helper,new BlockPos(1,1,1),absentId,owner));
                committed.set(newEmptyRegistration(helper,new BlockPos(2,1,1),committedId,owner));
            })
            .thenWaitUntil(()->{
                helper.assertTrue(!beforeSql.get().timedOut() && !afterSql.get().timedOut(),"both isolated registration boundaries must reach their five-second worker holds");
                helper.assertTrue(beforeSql.get().reached() && afterSql.get().reached(),"before-SQL and actual post-commit registration workers pending");
            })
            .thenExecute(()->runtime.submit(a->observeEmptyRemoval(a,absentId,committedId,journal),held::set,code->helper.assertTrue(false,"held empty-registration evidence: "+code)))
            .thenWaitUntil(()->helper.assertTrue(held.get()!=null,"real absence and committed-row observations pending"))
            .thenExecute(()->{
                try{
                    var evidence=held.get();
                    helper.assertTrue(evidence.absentEndpointRows()==0 && evidence.committedState().equals("ACTIVE") && evidence.committedCheckpoint()==0 && evidence.transferRows()==0 && evidence.grantRows()==0 && evidence.walAbsent(),"real SQL distinguishes never-created identity from a committed empty registration, with no WAL or asset history");
                    for(var be:new TesseractBlockEntity[]{absent.get(),committed.get()}){
                        helper.assertTrue(be.registering() && !be.registered() && be.buffer().empty() && be.energy(Direction.UP).receiveEnergy(128,false)==0 && be.energy(Direction.DOWN).extractEnergy(128,false)==0,"neither held registration can admit or spend resources");
                        helper.assertTrue(level.removeBlock(be.getBlockPos(),false) && be.isRemoved(),"actual physical removal must preserve each unresolved SQL seal intent");
                    }
                }finally{beforeSql.get().release();afterSql.get().release();}
            })
            .thenWaitUntil(()->helper.assertTrue(beforeSql.get().failureInjected() && afterSql.get().failureInjected() && !absent.get().registering() && !committed.get().registering() && runtime.metricSnapshot().get("closing_devices").intValue()==0,"both checked failures must finish: fenced absence releases Closing, committed SQL row is sealed"))
            .thenExecute(()->runtime.submit(a->observeEmptyRemoval(a,absentId,committedId,journal),finished::set,code->helper.assertTrue(false,"final empty-removal evidence: "+code)))
            .thenWaitUntil(()->helper.assertTrue(finished.get()!=null,"confirmed empty-removal SQL/WAL evidence pending"))
            .thenExecute(()->{
                var evidence=finished.get();
                helper.assertTrue(!beforeSql.get().timedOut() && !afterSql.get().timedOut(),"failures were explicitly released, not worker timeouts");
                helper.assertTrue(evidence.absentEndpointRows()==0 && evidence.committedState().equals("SEALED") && evidence.committedCheckpoint()==0,"no-registration absence terminates without inventing a SQL endpoint; post-commit uncertainty must seal the real row");
                helper.assertTrue(evidence.transferRows()==0 && evidence.grantRows()==0 && evidence.walAbsent(),"neither default buffer creates a WAL/checkpoint, transfer, ticket, refund or retirement");
                helper.assertTrue(level.getBlockEntity(absent.get().getBlockPos())==null && level.getBlockEntity(committed.get().getBlockPos())==null && !absent.get().registered() && !committed.get().registered(),"both physical removals stay unhydrated and cannot reopen capabilities");
            })
            .thenSucceed();
    }
    private static TesseractBlockEntity newEmptyRegistration(GameTestHelper helper,BlockPos relative,UUID endpoint,UUID owner){
        helper.setBlock(relative,CrossTesseract.TESSERACT.get());
        var be=(TesseractBlockEntity)helper.getBlockEntity(relative);var tag=new CompoundTag();
        tag.putUUID("instance",endpoint);tag.putUUID("device_owner",owner);tag.putLong("checkpoint",0);
        be.loadWithComponents(tag,helper.getLevel().registryAccess());be.onLoad();return be;
    }
    private record EmptyRemovalEvidence(long absentEndpointRows,String committedState,long committedCheckpoint,long transferRows,long grantRows,boolean walAbsent){}
    private static EmptyRemovalEvidence observeEmptyRemoval(Authority authority,UUID absent,UUID committed,Path journal) throws Exception {
        var present=authority.endpoint(committed); // fresh fencing, not a stale test-side assertion
        var local=new LocalJournal(journal);boolean noWal=local.read(absent).isEmpty() && local.read(committed).isEmpty();
        for(UUID id:new UUID[]{absent,committed})noWal&=Files.notExists(journal.resolve(id+".ctj"),java.nio.file.LinkOption.NOFOLLOW_LINKS) && Files.notExists(journal.resolve(id+".pending"),java.nio.file.LinkOption.NOFOLLOW_LINKS);
        final boolean walAbsent=noWal;
        return authority.database().connection(c->{
            String cluster=authority.session().cluster();
            long absentRows=Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?",cluster,absent),"n");
            long transfers=Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND endpoint_id IN (?,?)",cluster,absent,committed),"n");
            long grants=Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id IN (?,?)",cluster,absent,committed),"n");
            return new EmptyRemovalEvidence(absentRows,present.state(),present.checkpoint(),transfers,grants,walAbsent);
        });
    }

    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="cloned_physical_removal",timeoutTicks=1_000_000)
    public static void physicallyRemovedSameIdCloneCannotSealOriginalOrRemoveItsActualChunkTicket(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var runtime=be.runtime();var level=helper.getLevel();UUID id=be.id();
            Path journal=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var credit=new AtomicReference<UUID>();var on=new AtomicReference<String>();var off=new AtomicReference<String>();
            var afterClone=new AtomicReference<CloneRemovalEvidence>();var consumed=new AtomicReference<CloneRemovalEvidence>();
            long[] originalVersion={0};be.mode(Protocol.FE,Protocol.Mode.BOTH);
            helper.startSequence()
                .thenExecute(()->helper.assertTrue(be.energy(Direction.UP).receiveEnergy(128,false)==128,"original native capability accepts the one real 128 FE clone-safety fixture input"))
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.FE)==128 && be.buffer().sendAmount(Protocol.FE)==0 && !be.inFlight(),"original published SQL/WAL credit pending"))
                .thenExecute(()->{
                    helper.assertTrue(be.buffer().received(Protocol.FE).size()==1,"one original credit before clone removal");credit.set(be.buffer().received(Protocol.FE).getFirst().transaction());
                    be.mode(Protocol.FE,Protocol.Mode.RECEIVE);runtime.chunkOn(be,be.owner(),BusinessIds.next(),false,on::set);
                })
                .thenWaitUntil(()->helper.assertTrue("success".equals(on.get()) && be.chunkDesired() && runtime.ticketCount()>0 && be.allowed(Protocol.FE,Direction.DOWN,false),"actual original chunk ticket and native RECEIVE authorization pending"))
                .thenExecute(()->{
                    int tickets=runtime.ticketCount(),closing=runtime.metricSnapshot().get("closing_devices").intValue();originalVersion[0]=be.endpointVersion();
                    var port=level.getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.DOWN);helper.assertTrue(port!=null,"original cached capability exists before cloned removal");
                    var clonePosition=helper.absolutePos(new BlockPos(3,1,1));level.setBlockAndUpdate(clonePosition,CrossTesseract.TESSERACT.get().defaultBlockState());
                    var clone=(TesseractBlockEntity)level.getBlockEntity(clonePosition);clone.loadWithComponents(be.saveWithFullMetadata(level.registryAccess()).copy(),level.registryAccess());clone.onLoad();
                    helper.assertTrue(clone.id().equals(id) && !clone.registered() && clone.pauseReason().equals("cloned_endpoint"),"real cloned NBT instance is rejected while the original object remains loaded");
                    helper.assertTrue(level.removeBlock(clonePosition,false) && clone.isRemoved(),"real clone block onRemove and BE unload execute");
                    helper.assertTrue(!be.isRemoved() && level.getBlockEntity(be.getBlockPos())==be && be.chunkDesired() && runtime.ticketCount()==tickets,"clone physical removal cannot remove the original object or its installed ticket");
                    helper.assertTrue(runtime.metricSnapshot().get("closing_devices").intValue()==closing && be.allowed(Protocol.FE,Direction.DOWN,false) && port.extractEnergy(128,true)==128,"clone cannot start original closing, suspend its native capability or change the owned receipt");
                })
                .thenExecute(()->runtime.submit(a->observeCloneRemoval(a,id,credit.get(),journal),afterClone::set,code->helper.assertTrue(false,"original SQL after clone removal: "+code)))
                .thenWaitUntil(()->helper.assertTrue(afterClone.get()!=null,"actual original SQL/grant observation pending"))
                .thenExecute(()->{
                    var last=afterClone.get();var assets=last.assets();assertSingleBusinessAsset(helper,assets);
                    helper.assertTrue(assets.endpoint().state().equals("ACTIVE") && last.endpointVersion()==originalVersion[0] && assets.creditState().equals("LOCAL") && assets.creditRemaining()==128,"clone removal cannot seal, version or consume original SQL ownership");
                    helper.assertTrue(last.grantCount()==1 && last.grantState().equals("ACTIVE") && last.desired() && be.chunkDesired(),"original persistent authorization and installed ticket remain active");
                    var port=level.getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.DOWN);helper.assertTrue(port!=null && port.extractEnergy(128,false)==128 && port.extractEnergy(128,false)==0,"original real capability still redeems its one credit exactly once");
                    runtime.chunkOff(be.owner(),id,false,off::set);
                })
                .thenWaitUntil(()->helper.assertTrue("success".equals(off.get()) && !be.chunkDesired() && !be.inFlight() && !be.buffer().hasWork() && be.buffer().receiveAmount(Protocol.FE)==0,"explicit original ticket revocation and resource consumption checkpoint pending"))
                .thenExecute(()->runtime.submit(a->observeCloneRemoval(a,id,credit.get(),journal),consumed::set,code->helper.assertTrue(false,"final original SQL after native consumption: "+code)))
                .thenWaitUntil(()->helper.assertTrue(consumed.get()!=null,"final original durable observation pending"))
                .thenExecute(()->{
                    var last=consumed.get();assertSingleBusinessAsset(helper,last.assets());
                    helper.assertTrue(last.assets().endpoint().state().equals("ACTIVE") && last.endpointVersion()==originalVersion[0] && last.assets().creditState().equals("CONSUMED") && last.assets().creditRemaining()==0 && last.grantCount()==0,"only explicit original actions consumed its credit and revoked its grant, without clone sealing or duplication");
                })
                .thenSucceed();
        });
    }
    private record CloneRemovalEvidence(ConfirmationEvidence assets,long endpointVersion,long grantCount,String grantState,boolean desired){}
    private static CloneRemovalEvidence observeCloneRemoval(Authority authority,UUID endpoint,UUID credit,Path journal) throws Exception {
        var assets=observeConfirmation(authority,endpoint,credit,journal);var current=authority.endpoint(endpoint);
        return authority.database().connection(c->{
            var grant=Sql.one(c,"SELECT state,desired FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",authority.session().cluster(),endpoint);
            return new CloneRemovalEvidence(assets,current.version(),grant==null?0:1,grant==null?"":Sql.str(grant,"state"),grant!=null && Boolean.TRUE.equals(grant.get("desired")));
        });
    }

    private record SealEvidence(ConfirmationEvidence assets,String walHash,long chunkGrants){}
    private static SealEvidence observeSeal(Authority authority,UUID endpoint,UUID credit,Path journal) throws Exception {
        var assets=observeConfirmation(authority,endpoint,credit,journal);
        var hash=Resource.hash(Files.readAllBytes(journal.resolve(endpoint+".ctj")));
        long grants=authority.database().connection(c->Sql.num(Sql.one(c,"SELECT COUNT(*) AS n FROM ct_chunk_grants WHERE cluster_id=? AND endpoint_id=?",authority.session().cluster(),endpoint),"n"));
        return new SealEvidence(assets,hash,grants);
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
