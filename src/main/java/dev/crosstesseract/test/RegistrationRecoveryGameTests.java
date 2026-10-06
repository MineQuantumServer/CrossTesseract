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
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.level.storage.LevelResource;
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
