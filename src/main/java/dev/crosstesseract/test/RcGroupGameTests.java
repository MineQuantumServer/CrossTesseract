package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.*;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.*;
import dev.crosstesseract.core.LocalSnapshot.*;
import dev.crosstesseract.core.Models.Endpoint;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import net.minecraft.core.*;
import net.minecraft.gametest.framework.*;
import net.minecraft.world.level.storage.LevelResource;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** Natural 192 -> 196 record growth across the actual Runtime publication splitter. */
@PrefixGameTestTemplate(false)
public final class RcGroupGameTests {
    private record Bound(List<Endpoint> endpoints,long generation){}
    private record Fixture(Map<UUID,LocalSnapshot> restored,Map<UUID,UUID> unseen,Set<UUID> sourceDeposits){}
    private record Evidence(List<String> states,long quantity,Map<UUID,Set<UUID>> pending){}

    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,batch="rc_groups",timeoutTicks=1_000_000)
    public static void partialPublicationGroupsRetainOriginalOwnershipAndRecover(GameTestHelper helper){
        Fixtures.bound(helper,source->{
            var runtime=source.runtime();UUID channel=source.channel(),owner=source.owner();
            helper.assertTrue(runtime.limits().transfer().channelBatches() && runtime.limits().transfer().records()==192 && runtime.limits().transfer().devices()>=4,"separate RC fixture requires batch=true / records=192 / devices>=4");
            Path journalPath=runtime.server().getWorldPath(LevelResource.ROOT).resolve("cross_tesseract/journal");
            var devices=new ArrayList<TesseractBlockEntity>();var bound=new AtomicReference<Bound>();var fixture=new AtomicReference<Fixture>();
            var sendHolds=new ArrayList<Faults.Hold>();var groupHold=new AtomicReference<Faults.Hold>();var observed=new AtomicReference<Evidence>();
            var finalEvidence=new AtomicReference<Evidence>();var ports=new ArrayList<IEnergyStorage>();
            var sourceSnapshot=new AtomicReference<LocalSnapshot>();
            helper.startSequence()
                .thenExecute(()->{
                    for(BlockPos pos:List.of(new BlockPos(0,1,0),new BlockPos(2,1,0),new BlockPos(0,1,2),new BlockPos(2,1,2))){
                        helper.setBlock(pos,CrossTesseract.TESSERACT.get());var be=(TesseractBlockEntity)helper.getBlockEntity(pos);be.placed(owner);devices.add(be);
                    }
                })
                .thenWaitUntil(()->helper.assertTrue(devices.stream().allMatch(TesseractBlockEntity::registered),"four actual native endpoints register"))
                .thenExecute(()->{
                    var captured=devices.stream().map(be->new Endpoint(be.id(),runtime.serverId(),runtime.worldId(),owner,null,helper.getLevel().dimension().location().toString(),be.getBlockPos().getX(),be.getBlockPos().getY(),be.getBlockPos().getZ(),be.endpointVersion(),"ACTIVE",0,"")).toList();
                    runtime.submit(a->{var endpoints=new ArrayList<Endpoint>();for(var be:captured)endpoints.add(a.bind(owner,be.id(),be.version(),channel));return new Bound(List.copyOf(endpoints),a.session().generation());},bound::set,code->helper.assertTrue(false,code));
                })
                .thenWaitUntil(()->helper.assertTrue(bound.get()!=null,"binding results pending"))
                .thenExecute(()->{for(int i=0;i<devices.size();i++)devices.get(i).applyEndpoint(bound.get().endpoints().get(i));})
                .thenWaitUntil(()->helper.assertTrue(devices.stream().allMatch(be->channel.equals(be.channel()) && be.pauseReason().isEmpty() && be.channelOwner()!=null),"fresh authoritative permissions pending"))
                .thenExecute(()->{
                    source.mode(Protocol.FE,Protocol.Mode.SEND);
                    var port=helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,source.getBlockPos(),Direction.UP);
                    helper.assertTrue(port.receiveEnergy(256,false)==256,"all fixture SQL funds originate in actual native FE input");
                    source.mode(Protocol.FE,Protocol.Mode.OFF);source.inFlight(true);for(var be:devices)be.inFlight(true);
                    var snapshot=source.buffer().snapshot(source.id(),runtime.worldId(),bound.get().generation(),channel,true);sourceSnapshot.set(snapshot);
                    var targets=bound.get().endpoints();long sourceVersion=source.endpointVersion();
                    runtime.submit(a->prepare(a,journalPath,channel,sourceVersion,snapshot,targets),fixture::set,code->helper.assertTrue(false,"fixture preparation: "+code));
                })
                .thenWaitUntil(()->helper.assertTrue(fixture.get()!=null,"real SQL and destination WAL fixture pending"))
                .thenExecute(()->{
                    source.buffer().committed(fixture.get().sourceDeposits());source.inFlight(false);
                    for(var be:devices){
                        be.buffer().restore(fixture.get().restored().get(be.id()));be.mode(Protocol.FE,Protocol.Mode.SEND);
                        var port=helper.getLevel().getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP);ports.add(port);
                        for(int i=0;i<31;i++){helper.assertTrue(port.receiveEnergy(1,false)==1,"native pending input accepted");be.buffer().snapshot(be.id(),runtime.worldId(),bound.get().generation(),channel,true);}
                        be.mode(Protocol.FE,Protocol.Mode.RECEIVE);sendHolds.add(Faults.hold(runtime.clusterId(),"after_send_wal",be.id()));be.inFlight(false);
                    }
                    runtime.testReadyBatch(devices.stream().map(TesseractBlockEntity::id).toList());
                })
                .thenWaitUntil(()->helper.assertTrue(sendHolds.stream().anyMatch(Faults.Hold::reached),"the actual four-device captured send WAL hold pending"))
                .thenExecute(()->{
                    helper.assertTrue(devices.stream().allMatch(TesseractBlockEntity::inFlight),"all four devices share the admitted batch, not four test calls");
                    try{for(int i=0;i<4;i++){devices.get(i).mode(Protocol.FE,Protocol.Mode.BOTH);helper.assertTrue(ports.get(i).receiveEnergy(1,false)==1,"concurrent native input grows each publication to49 records");}}
                    finally{for(var hold:sendHolds)hold.release();}
                    UUID first=devices.stream().map(TesseractBlockEntity::id).min(UUID::compareTo).orElseThrow();groupHold.set(Faults.holdFailedPublicationGroupOnce(runtime.clusterId(),first));
                })
                .thenWaitUntil(()->helper.assertTrue(groupHold.get().reached() && !groupHold.get().timedOut(),"actual first publication group commit reached"))
                .thenExecute(()->{
                    for(var be:devices)be.mode(Protocol.FE,Protocol.Mode.RECEIVE); // Preserve all 128 pending TX as independently owned assets.
                    var ids=fixture.get().unseen();runtime.submit(a->observe(a,journalPath,ids),observed::set,code->helper.assertTrue(false,"intermediate evidence: "+code));
                })
                .thenWaitUntil(()->helper.assertTrue(observed.get()!=null,"independent intermediate SQL and WAL evidence pending"))
                .thenExecute(()->{
                    try{
                        var proof=observed.get();helper.assertTrue(proof.states().equals(List.of("LOCAL","LOCAL","LOCAL","RESERVED")),"one real three-device group committed while the fourth remains RESERVED");
                        helper.assertTrue(proof.quantity()==256 && proof.pending().size()==4 && proof.pending().values().stream().allMatch(ids->ids.size()==32),"SQL has256 unique units, each future WAL has original32 pending IDs");
                    }finally{groupHold.get().release();}
                })
                .thenWaitUntil(()->helper.assertTrue(devices.stream().allMatch(be->!be.inFlight() && be.buffer().receiveAmount(Protocol.FE)==64 && be.buffer().sendAmount(Protocol.FE)==32),"partial-group worker failure must recover all four original credits without sending held TX"))
                .thenExecute(()->{
                    helper.assertTrue(groupHold.get().failureInjected(),"controlled worker exception was injected after real SQL commit; not hardware or ACK loss");
                    for(var port:ports){helper.assertTrue(port.extractEnergy(64,false)==64,"native extraction of64 owned FE succeeds exactly once");helper.assertTrue(port.extractEnergy(64,false)==0,"no duplicate native extraction");}
                })
                .thenWaitUntil(()->helper.assertTrue(devices.stream().allMatch(be->!be.inFlight() && !be.buffer().dirty()),"all real consumption checkpoints complete"))
                .thenExecute(()->{var ids=fixture.get().unseen();runtime.submit(a->observe(a,journalPath,ids),finalEvidence::set,code->helper.assertTrue(false,"final evidence: "+code));})
                .thenWaitUntil(()->helper.assertTrue(finalEvidence.get()!=null,"final SQL/WAL evidence pending"))
                .thenExecute(()->{
                    var proof=finalEvidence.get();helper.assertTrue(proof.quantity()==0,"all256 allocated FE actually consumed, no refund balance");
                    helper.assertTrue(proof.pending().equals(observed.get().pending()),"all128 unsent FE keep their original32 per-endpoint WAL business IDs");
                    helper.assertTrue(devices.stream().allMatch(be->be.buffer().sendAmount(Protocol.FE)==32 && !be.inFlight()),"held positive TX remains legal, recoverable and out of in-flight");
                    CrossTesseract.LOG.info("CT_RC_GROUP_PASS endpoints={} initial_native_input=384 actual_native_output=256 retained_TX=128 actual_groups=3+1 first_LOCAL=3 first_RESERVED=1 original_TX_ids_preserved=true",devices.stream().map(TesseractBlockEntity::id).toList());
                }).thenSucceed();
        });
    }
    private static Fixture prepare(Authority a,Path path,UUID channel,long version,LocalSnapshot source,List<Endpoint> targets)throws Exception{
        var journal=new LocalJournal(path);journal.write(source);
        var request=new TransferWork.Request(source,channel,version,true,Set.of(Protocol.FE),List.of(),8,false);
        var result=a.channelBatch(channel,List.of(request)).getFirst();DomainException.require(result.error()==null && !result.committed().isEmpty(),"fixture_source_failed");
        var resource=new Resource(Protocol.FE,new byte[0]);var credits=new HashMap<UUID,List<Credit>>();var unseen=new HashMap<UUID,UUID>();
        for(var target:targets)credits.put(target.id(),new ArrayList<>());
        for(int i=0;i<16;i++)for(var target:targets){a.demand(target.id(),channel,Protocol.FE,1);var allocated=a.allocate(BusinessIds.next(),target.id(),channel,Protocol.FE,1).orElseThrow();credits.get(target.id()).add(new Credit(allocated.id(),channel,resource,1,1));}
        var restored=new HashMap<UUID,LocalSnapshot>();var publications=new ArrayList<TransferWork.Publication>();
        for(var target:targets){
            var durable=new LocalSnapshot(target.id(),source.world(),source.generation(),16,List.of(),credits.get(target.id()));journal.write(durable);
            publications.add(new TransferWork.Publication(durable,channel,target.version(),durable.credits(),Map.of()));
            restored.put(target.id(),new LocalSnapshot(target.id(),source.world(),source.generation(),15,List.of(),durable.credits()));
        }
        DomainException.require(a.publishBatch(channel,publications).isEmpty(),"fixture_publish_failed");
        for(var target:targets){a.demand(target.id(),channel,Protocol.FE,48);unseen.put(target.id(),a.allocate(BusinessIds.next(),target.id(),channel,Protocol.FE,48).orElseThrow().id());}
        var cleaned=new LocalSnapshot(source.endpoint(),source.world(),source.generation(),source.revision()+1,List.of(),List.of());journal.write(cleaned);a.checkpoint(source.endpoint(),cleaned.revision(),Map.of());
        return new Fixture(Map.copyOf(restored),Map.copyOf(unseen),result.committed());
    }
    private static Evidence observe(Authority a,Path path,Map<UUID,UUID> unseen)throws Exception{
        var states=new ArrayList<String>();var pending=new HashMap<UUID,Set<UUID>>();var journal=new LocalJournal(path);long quantity=0;
        for(UUID endpoint:unseen.keySet().stream().sorted().toList()){
            var row=a.database().connection(c->Sql.one(c,"SELECT state FROM ct_transfers WHERE cluster_id=? AND transfer_id=?",a.session().cluster(),unseen.get(endpoint)));states.add(Sql.str(row,"state"));
            var sums=a.database().connection(c->Sql.one(c,"SELECT COALESCE(SUM(remaining),0) AS n FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind='ALLOCATE'",a.session().cluster(),endpoint));quantity=Math.addExact(quantity,Sql.num(sums,"n"));
            var snapshot=journal.read(endpoint).orElseThrow();DomainException.require(snapshot.deposits().size()==32 && snapshot.deposits().stream().allMatch(d->d.amount()==1),"fixture_pending_changed");
            pending.put(endpoint,Set.copyOf(snapshot.deposits().stream().map(Deposit::transaction).toList()));
        }
        return new Evidence(List.copyOf(states),quantity,Map.copyOf(pending));
    }
    private RcGroupGameTests(){}
}
