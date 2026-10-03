package dev.crosstesseract.test;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.*;
import dev.crosstesseract.core.*;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.component.DataComponents;
import net.minecraft.gametest.framework.*;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.*;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.gametest.GameTestHolder;

@GameTestHolder(CrossTesseract.ID)
@net.neoforged.neoforge.gametest.PrefixGameTestTemplate(false)
public final class GameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID)
    public static void unknownRegistriesDeepLargeAndHostileDeclaredArraysFailClosed(GameTestHelper helper){
        var missing=new net.minecraft.nbt.CompoundTag();missing.putString("id","absent_cross_tesseract_test:missing");missing.putInt("count",1);
        reject(helper,"registry_missing",()->StackCodec.item(StackCodec.tag(Protocol.ITEM,missing),helper.getLevel().registryAccess(),1));
        var deep=new net.minecraft.nbt.CompoundTag();var at=deep;for(int i=0;i<34;i++){var next=new net.minecraft.nbt.CompoundTag();at.put("child",next);at=next;}
        reject(helper,"payload_too_large",()->StackCodec.tag(Protocol.ITEM,deep));
        reject(helper,"payload_too_large",()->StackCodec.tag(Protocol.ITEM,new net.minecraft.nbt.ByteArrayTag(new byte[Resource.MAX_BYTES+1])));
        var bytes=java.nio.ByteBuffer.allocate(5).put((byte)12).putInt(Integer.MAX_VALUE).array();reject(helper,"payload_corrupt",()->StackCodec.tag(new Resource(Protocol.ITEM,bytes)));
        var map=new ItemStack(Items.FILLED_MAP);map.set(DataComponents.MAP_ID,new net.minecraft.world.level.saveddata.maps.MapId(5));reject(helper,"external_world_item",()->StackCodec.item(map,helper.getLevel().registryAccess()));
        helper.succeed();
    }
    private static void reject(GameTestHelper helper,String code,Runnable action){boolean rejected=false;try{action.run();}catch(DomainException e){rejected=e.code().equals(code);}helper.assertTrue(rejected,"expected safe refusal: "+code);}
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID)
    public static void registryAwareItemAndFluidRoundTrip(GameTestHelper helper){
        var registries=helper.getLevel().registryAccess();var stack=new ItemStack(Items.DIAMOND_PICKAXE);stack.setDamageValue(42);stack.set(DataComponents.CUSTOM_NAME,Component.literal("跨服组件 Δ"));
        var resource=StackCodec.item(stack,registries);var copy=StackCodec.item(resource,registries,1);
        helper.assertTrue(ItemStack.isSameItemSameComponents(stack,copy),"complete item components must round trip");
        var fluid=new FluidStack(Fluids.WATER,1234);fluid.set(DataComponents.CUSTOM_NAME,Component.literal("component fluid"));
        var decoded=StackCodec.fluid(StackCodec.fluid(fluid,registries),registries,1234);
        helper.assertTrue(FluidStack.matches(fluid,decoded),"complete fluid components must round trip");helper.succeed();
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID)
    public static void unownedDeviceFailsClosedAndCloneDropsNoAuthority(GameTestHelper helper){
        BlockPos pos=new BlockPos(1,1,1);helper.setBlock(pos,CrossTesseract.TESSERACT.get());
        var be=(TesseractBlockEntity)helper.getBlockEntity(pos);var input=new ItemStack(Items.STONE,64);
        var remainder=be.items(null).insertItem(0,input,false);helper.assertTrue(remainder.getCount()==64 && input.getCount()==64,"unowned device must reject without mutating caller");
        helper.assertTrue(be.energy(null).receiveEnergy(100,false)==0,"unauthorized FE input");
        helper.assertTrue(be.fluids(null).fill(new FluidStack(Fluids.WATER,1000),net.neoforged.neoforge.fluids.capability.IFluidHandler.FluidAction.EXECUTE)==0,"unauthorized fluid input");
        var clone=CrossTesseract.TESSERACT.get().getCloneItemStack(helper.getLevel(),helper.absolutePos(pos),CrossTesseract.TESSERACT.get().defaultBlockState());
        helper.assertTrue(clone.get(DataComponents.BLOCK_ENTITY_DATA)==null,"clone item cannot carry endpoint credentials or balances");helper.succeed();
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID)
    public static void sendReceiveBuffersCannotRecirculateAndPartialSimulationIsPure(GameTestHelper helper){
        var buffer=new LocalBuffer();var resource=StackCodec.item(new ItemStack(Items.STONE),helper.getLevel().registryAccess());
        helper.assertTrue(buffer.insert(resource,0,64,true)==64 && buffer.sendAmount(Protocol.ITEM)==0,"simulation must not mutate");
        helper.assertTrue(buffer.insert(resource,0,64,false)==64,"actual acceptance");
        UUID endpoint=UUID.randomUUID(),channel=UUID.randomUUID();var snapshot=buffer.snapshot(endpoint,UUID.randomUUID(),1,channel,true);
        helper.assertTrue(snapshot.deposits().size()==1,"bounded local batch");UUID credit=UUID.randomUUID();buffer.credit(new LocalSnapshot.Credit(credit,channel,resource,32,32));
        helper.assertTrue(buffer.extract(credit,12,true)==12 && buffer.receiveAmount(Protocol.ITEM)==32,"pure simulated extraction");
        helper.assertTrue(buffer.extract(credit,12,false)==12 && buffer.receiveAmount(Protocol.ITEM)==20,"partial extraction");
        helper.assertTrue(buffer.sendAmount(Protocol.ITEM)==64,"network receive must not become new sending inventory");helper.succeed();
    }
}
