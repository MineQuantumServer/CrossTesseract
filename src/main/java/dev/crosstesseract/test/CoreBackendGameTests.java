package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.*;
import dev.crosstesseract.core.*;
import net.minecraft.core.*;
import net.minecraft.core.component.DataComponents;
import net.minecraft.gametest.framework.*;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.*;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.neoforge.capabilities.*;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;

@net.neoforged.neoforge.gametest.PrefixGameTestTemplate(false)
public final class CoreBackendGameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void asyncBindingStopsAdmissionRejectsStaleSnapshotsAndReconcilesFailure(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var rt=be.runtime();be.mode(Protocol.FE,Protocol.Mode.SEND);
            var old=new Models.PermissionSnapshot(be.id(),be.channel(),be.channelOwner(),be.channelVersion(),be.endpointVersion(),31,"ACTIVE","");
            var changed=new java.util.concurrent.atomic.AtomicBoolean();var failed=new java.util.concurrent.atomic.AtomicBoolean();var target=new java.util.UUID[1];java.util.UUID owner=be.owner();
            rt.submit(a->a.createChannel(owner,"binding_"+BusinessIds.next().toString().substring(28,36),BusinessIds.next()),channel->{
                target[0]=channel;rt.bindEndpoint(be,owner,be.endpointVersion(),channel,x->changed.set(true),code->helper.assertTrue(false,code));
                helper.assertTrue(be.binding() && be.energy(Direction.UP).receiveEnergy(99,false)==0,"native input must stop before the async SQL bind returns");
                be.authorize(old,System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(3),System.nanoTime());
                helper.assertTrue(be.binding() && be.buffer().empty(),"queued old authorization cannot unlock an in-progress bind");
            },code->helper.assertTrue(false,code));
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(changed.get() && target[0].equals(be.channel()) && be.pauseReason().isEmpty(),"new channel authoritative refresh pending"))
                .thenExecute(()->{
                    be.authorize(old,System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(3),System.nanoTime());
                    helper.assertTrue(target[0].equals(be.channel()) && be.endpointVersion()>old.endpointVersion(),"old endpoint version cannot roll the binding back");
                    var cached=new Models.PermissionSnapshot(be.id(),be.channel(),be.channelOwner(),be.channelVersion(),be.endpointVersion(),31,"ACTIVE","");long beforeRequest=System.nanoTime();
                    rt.bindEndpoint(be,owner,be.endpointVersion(),java.util.UUID.randomUUID(),x->helper.assertTrue(false,"missing channel must not bind"),code->{
                        failed.set(true);be.authorize(cached,System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(3),beforeRequest);
                        helper.assertTrue(be.binding() && be.energy(Direction.UP).receiveEnergy(99,false)==0,"failed or uncertain bind requires a post-result SQL observation, not an earlier cached reply");
                    });
                }).thenWaitUntil(()->helper.assertTrue(failed.get() && !be.binding() && target[0].equals(be.channel()) && be.pauseReason().isEmpty(),"fresh real SQL reconciliation pending"))
                .thenExecute(()->helper.assertTrue(be.energy(Direction.UP).receiveEnergy(1,false)==1,"native input resumes only for the confirmed original binding after rejected switch"))
                .thenSucceed();
        });
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void realVanillaChestAutoPullAndPushWithoutRecycling(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            var first=helper.absolutePos(new BlockPos(1,1,1));var second=helper.absolutePos(new BlockPos(3,1,1));var level=helper.getLevel();
            level.setBlockAndUpdate(second,CrossTesseract.TESSERACT.get().defaultBlockState());var receiver=(TesseractBlockEntity)level.getBlockEntity(second);receiver.placed(be.owner());
            level.setBlockAndUpdate(first.west(),net.minecraft.world.level.block.Blocks.CHEST.defaultBlockState());level.setBlockAndUpdate(second.east(),net.minecraft.world.level.block.Blocks.CHEST.defaultBlockState());
            var source=(net.minecraft.world.level.block.entity.ChestBlockEntity)level.getBlockEntity(first.west());var target=(net.minecraft.world.level.block.entity.ChestBlockEntity)level.getBlockEntity(second.east());
            var stack=new ItemStack(Items.DIAMOND,24);stack.set(DataComponents.CUSTOM_NAME,Component.literal("vanilla native auto transfer"));source.setItem(0,stack.copy());target.setItem(0,stack.copyWithCount(60));be.mode(Protocol.ITEM,Protocol.Mode.SEND);receiver.mode(Protocol.ITEM,Protocol.Mode.BOTH);
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(receiver.registered(),"second real endpoint registering"))
                .thenExecute(()->be.runtime().submit(a->a.bind(be.owner(),receiver.id(),receiver.endpointVersion(),be.channel()),receiver::applyEndpoint,code->helper.assertTrue(false,code)))
                .thenWaitUntil(()->helper.assertTrue(target.getItem(0).getCount()==64 && target.getItem(1).getCount()==20,"partial native slot fill then next slot; vanilla -> owned TX -> SQL/WAL -> RX -> vanilla pending"))
                .thenExecute(()->helper.assertTrue(source.getItem(0).isEmpty() && ItemStack.isSameItemSameComponents(target.getItem(0),stack) && ItemStack.isSameItemSameComponents(target.getItem(1),stack),"actual quantities and components conserved"))
                .thenIdle(100).thenExecute(()->helper.assertTrue(target.getItem(0).getCount()+target.getItem(1).getCount()==84 && receiver.buffer().sendAmount(Protocol.ITEM)==0,"BOTH cannot auto-pull received output back into sending"))
                .thenSucceed();
        });
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void nativeSidedSimulationStackLimitsCacheInvalidationAndActualArrival(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            for(String kind:Protocol.BASE)be.mode(kind,Protocol.Mode.BOTH);
            var level=helper.getLevel();var item=level.getCapability(Capabilities.ItemHandler.BLOCK,be.getBlockPos(),Direction.UP);var fluid=level.getCapability(Capabilities.FluidHandler.BLOCK,be.getBlockPos(),Direction.UP);var fe=level.getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP);
            var tool=new ItemStack(Items.DIAMOND_PICKAXE);tool.setDamageValue(42);tool.set(DataComponents.CUSTOM_NAME,Component.literal("native component tool"));
            helper.assertTrue(item.insertItem(0,tool,true).isEmpty() && be.buffer().sendAmount(Protocol.ITEM)==0,"successful simulation must not mutate owned inventory");
            helper.assertTrue(item.insertItem(0,tool,false).isEmpty() && item.insertItem(0,tool,false).getCount()==1,"non-stackable item slot cannot stack a second tool");helper.assertTrue(tool.getCount()==1 && tool.getDamageValue()==42,"caller unchanged");
            var water=new FluidStack(Fluids.WATER,32000);water.set(DataComponents.CUSTOM_NAME,Component.literal("fluid component"));
            helper.assertTrue(fluid.fill(water,IFluidHandler.FluidAction.SIMULATE)==2000 && be.buffer().sendAmount(Protocol.FLUID)==0,"pure partial fluid simulation");helper.assertTrue(fluid.fill(water,IFluidHandler.FluidAction.EXECUTE)==2000 && water.getAmount()==32000,"bounded actual fill and caller unchanged");
            helper.assertTrue(fe.receiveEnergy(Integer.MAX_VALUE,true)==32000 && be.buffer().sendAmount(Protocol.FE)==0,"int FE interface simulation");helper.assertTrue(fe.receiveEnergy(Integer.MAX_VALUE,false)==32000,"per tick bounded int FE acceptance");
            int[] invalidations={0};var cache=BlockCapabilityCache.create(Capabilities.ItemHandler.BLOCK,level,be.getBlockPos(),Direction.UP,()->!be.isRemoved(),()->invalidations[0]++);cache.getCapability();be.sideMask(Protocol.ITEM,63^(1<<Direction.UP.get3DDataValue()));helper.assertTrue(invalidations[0]==1 && item.insertItem(1,new ItemStack(Items.STONE),false).getCount()==1,"capability cache invalidation and stale handler side denial");be.sideMask(Protocol.ITEM,63);
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.ITEM)==1 && be.buffer().receiveAmount(Protocol.FLUID)==2000 && be.buffer().receiveAmount(Protocol.FE)==32000,"real multi-resource SQL/WAL arrival pending"))
                .thenExecute(()->{var arrived=item.extractItem(9,64,false);helper.assertTrue(ItemStack.isSameItemSameComponents(tool,arrived),"registry-aware components after actual delivery");var simulated=fluid.drain(777,IFluidHandler.FluidAction.SIMULATE);helper.assertTrue(simulated.getAmount()==777 && be.buffer().receiveAmount(Protocol.FLUID)==2000,"partial RX simulation");helper.assertTrue(fluid.drain(777,IFluidHandler.FluidAction.EXECUTE).getAmount()==777 && be.buffer().receiveAmount(Protocol.FLUID)==1223,"partial actual RX");helper.assertTrue(fe.extractEnergy(123,false)==123 && be.buffer().receiveAmount(Protocol.FE)==31877,"partial integer energy RX");helper.assertTrue(be.buffer().sendAmount(Protocol.FE)==0,"received FE does not recirculate");})
                .thenSucceed();
        });
    }
}
