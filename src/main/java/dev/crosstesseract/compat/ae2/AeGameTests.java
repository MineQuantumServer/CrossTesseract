package dev.crosstesseract.compat.ae2;

import appeng.api.AECapabilities;
import appeng.api.config.Actionable;
import appeng.api.networking.*;
import appeng.api.networking.security.*;
import appeng.api.stacks.*;
import appeng.api.storage.MEStorage;
import appeng.core.definitions.AEBlocks;
import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.compat.CompatLoader;
import dev.crosstesseract.core.*;
import dev.crosstesseract.test.Fixtures;
import java.util.*;
import net.minecraft.core.*;
import net.minecraft.gametest.framework.*;
import net.minecraft.world.item.*;
import net.neoforged.neoforge.gametest.*;

@PrefixGameTestTemplate(false)
public final class AeGameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void materialBridgeExposesOnlyDurableLocalCreditsAndOneMount(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            be.mode(Protocol.ITEM,Protocol.Mode.BOTH);be.aeEnabled=true;for(var module:CompatLoader.modules())module.changed(be);
            helper.setBlock(new BlockPos(2,1,1),AEBlocks.CREATIVE_ENERGY_CELL.block());
            var host=helper.getLevel().getCapability(AECapabilities.IN_WORLD_GRID_NODE_HOST,be.getBlockPos(),null);
            helper.assertTrue(host!=null && helper.getLevel().getCapability(AECapabilities.ME_STORAGE,be.getBlockPos(),null)==null,"exactly one provider, no duplicate storage-bus capability");
            var storage=(MEStorage)host;var source=IActionSource.ofMachine((IActionHost)host);var key=AEItemKey.of(new ItemStack(Items.DIAMOND));
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(host.getGridNode(Direction.UP).isActive(),"AE grid power/channel boot pending"))
                .thenExecute(()->{helper.assertTrue(storage.insert(key,16,Actionable.SIMULATE,source)==16 && be.buffer().sendAmount(Protocol.ITEM)==0,"synchronous simulation uses local room");helper.assertTrue(storage.extract(key,16,Actionable.MODULATE,source)==0,"known remote demand is never immediately extractable");helper.assertTrue(storage.insert(key,16,Actionable.MODULATE,source)==16,"AE actual insertion");helper.assertTrue(be.items(null).insertItem(0,new ItemStack(Items.STONE),false).getCount()==1,"generic storage access disabled while AE gateway mounts this inventory");})
                .thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.ITEM)==16,"exclusive SQL allocation and WAL delivery pending"))
                .thenExecute(()->{var counts=new KeyCounter();storage.getAvailableStacks(counts);helper.assertTrue(counts.get(key)==16,"only arrived credits are advertised");helper.assertTrue(storage.extract(key,7,Actionable.SIMULATE,source)==7 && be.buffer().receiveAmount(Protocol.ITEM)==16,"AE extraction simulation is pure");helper.assertTrue(storage.extract(key,7,Actionable.MODULATE,source)==7 && be.buffer().receiveAmount(Protocol.ITEM)==9,"partial synchronous extraction");})
                .thenSucceed();
        });
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void nativeShortfallQueuesDirectedDemandButSimulationNeverDoes(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            be.mode(Protocol.ITEM,Protocol.Mode.BOTH);be.aeEnabled=true;for(var module:CompatLoader.modules())module.changed(be);helper.setBlock(new BlockPos(2,1,1),AEBlocks.CREATIVE_ENERGY_CELL.block());
            var host=helper.getLevel().getCapability(AECapabilities.IN_WORLD_GRID_NODE_HOST,be.getBlockPos(),null);var storage=(MEStorage)host;var source=IActionSource.ofMachine((IActionHost)host);
            var stack=new ItemStack(Items.DIAMOND);stack.set(net.minecraft.core.component.DataComponents.CUSTOM_NAME,net.minecraft.network.chat.Component.literal("directed component profile"));var wanted=AEItemKey.of(stack);var other=AEItemKey.of(new ItemStack(Items.GOLD_INGOT));
            var simulated=new java.util.concurrent.atomic.AtomicBoolean();var queued=new java.util.concurrent.atomic.AtomicBoolean();
            var observing=new java.util.concurrent.atomic.AtomicBoolean();
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(host!=null && host.getGridNode(Direction.UP).isActive(),"real AE grid active pending"))
                .thenExecute(()->{helper.assertTrue(storage.extract(wanted,5,Actionable.SIMULATE,source)==0,"simulation cannot expose remote inventory");UUID owner=be.owner(),id=be.id(),channel=be.channel();be.runtime().submit(a->a.stock(owner,id,channel,null),page->{helper.assertTrue(page.requests().isEmpty(),"AE simulate must not create persistent demand");simulated.set(true);},code->helper.assertTrue(false,code));})
                .thenWaitUntil(()->helper.assertTrue(simulated.get(),"simulation backend observation pending"))
                .thenExecute(()->{helper.assertTrue(storage.extract(wanted,5,Actionable.MODULATE,source)==0,"actual miss returns zero immediately, without waiting for SQL");UUID owner=be.owner(),id=be.id(),channel=be.channel();be.runtime().submit(a->a.stock(owner,id,channel,null),page->{if(page.requests().isEmpty())return;helper.assertTrue(page.requests().getFirst().amount()==5,"directed demand uses native shortage");queued.set(true);},code->helper.assertTrue(false,code));})
                // GameTest ticks run faster than wall-clock Minecraft ticks. Keep one SQL
                // observation in flight so the test driver cannot flood the bounded workers.
                .thenWaitUntil(()->{if(!queued.get() && observing.compareAndSet(false,true)){UUID owner=be.owner(),id=be.id(),channel=be.channel();be.runtime().submit(a->a.stock(owner,id,channel,null),page->{observing.set(false);if(!page.requests().isEmpty())queued.set(true);},code->{observing.set(false);helper.assertTrue(false,code);});}helper.assertTrue(queued.get(),"persistent directed demand pending");})
                .thenExecute(()->{helper.assertTrue(storage.insert(other,12,Actionable.MODULATE,source)==12 && storage.insert(wanted,12,Actionable.MODULATE,source)==12,"actual AE inserts fund the common channel");})
                .thenWaitUntil(()->{var counts=new KeyCounter();storage.getAvailableStacks(counts);helper.assertTrue(counts.get(wanted)>=5,"requested full component profile must arrive through SQL/WAL");})
                .thenExecute(()->{var counts=new KeyCounter();storage.getAvailableStacks(counts);helper.assertTrue(counts.get(wanted)<=12 && counts.get(other)<=12,"remote-known values cannot inflate native immediately available inventory");helper.assertTrue(storage.extract(wanted,5,Actionable.MODULATE,source)==5,"actual delivered component profile is immediately redeemable");})
                .thenSucceed();
        });
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void prototypeUsesActualManagedNodesAndRebuildsAfterChannelShortage(GameTestHelper helper){
        var pos=new BlockPos(1,1,1);helper.setBlock(pos,AEBlocks.CREATIVE_ENERGY_CELL.block());
        var host=helper.getLevel().getCapability(AECapabilities.IN_WORLD_GRID_NODE_HOST,helper.absolutePos(pos),null);
        var shadows=new ArrayList<IManagedGridNode>();
        helper.startSequence().thenWaitUntil(()->helper.assertTrue(host!=null && host.getGridNode(Direction.UP)!=null,"native AE energy node pending"))
            .thenExecute(()->{for(int i=0;i<9;i++){
                var node=GridHelper.createManagedNode(new Object(),new IGridNodeListener<Object>(){@Override public void onSaveChanges(Object owner,IGridNode changed){}}).setFlags(GridFlags.REQUIRE_CHANNEL).setInWorldNode(false).setIdlePowerUsage(1);
                node.create(helper.getLevel(),helper.absolutePos(pos));GridHelper.createConnection(Objects.requireNonNull(node.getNode()),host.getGridNode(Direction.UP));shadows.add(node);
            }})
            .thenWaitUntil(()->helper.assertTrue(!host.getGridNode(Direction.UP).getGrid().getPathingService().isNetworkBooting(),"native pathing rebuild pending"))
            .thenExecute(()->{helper.assertTrue(shadows.stream().anyMatch(n->!n.isActive()),"nine real consumers exceed ad-hoc native AE eight-channel capacity");shadows.removeLast().destroy();})
            .thenWaitUntil(()->helper.assertTrue(shadows.stream().allMatch(IManagedGridNode::isActive),"removing the ninth real node must recover native channels"))
            .thenExecute(()->{for(var node:shadows)node.destroy();})
            .thenSucceed();
    }
}
