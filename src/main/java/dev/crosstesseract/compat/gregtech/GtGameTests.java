package dev.crosstesseract.compat.gregtech;

import com.gregtechceu.gtceu.api.capability.IEnergyContainer;
import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.*;
import dev.crosstesseract.test.Fixtures;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.*;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.capabilities.BlockCapability;

@net.neoforged.neoforge.gametest.PrefixGameTestTemplate(false)
public final class GtGameTests {
    private static final BlockCapability<IEnergyContainer,Direction> ENERGY=BlockCapability.createSided(ResourceLocation.fromNamespaceAndPath("gtceu","energy_container"),IEnergyContainer.class);
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void nativeGtVoltageAmperageAndRealLedgerLoopback(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            be.mode(Protocol.EU,Protocol.Mode.BOTH);be.euVoltage=32;be.euAmperage=2;
            var port=helper.getLevel().getCapability(ENERGY,be.getBlockPos(),Direction.UP);
            helper.assertTrue(port!=null && port.getInputVoltage()==32 && port.getInputAmperage()==2,"exact FortyTwoCn native capability and LV strategy");
            helper.assertTrue(port.acceptEnergyFromNetwork(Direction.UP,128,5)==0,"reject a mismatched voltage rather than free transformation");
            helper.assertTrue(port.acceptEnergyFromNetwork(Direction.UP,32,Long.MAX_VALUE)==2,"accepted amperes bounded; multiplication cannot overflow");
            helper.assertTrue(be.buffer().sendAmount(Protocol.EU)==64,"two native amps are exactly 64 EU");
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.EU)==64,"real SQL/WAL exclusive EU arrival pending"))
                .thenExecute(()->{helper.assertTrue(port.changeEnergy(-32)==-32 && be.buffer().receiveAmount(Protocol.EU)==32,"own buffer extraction is partial and conserves EU");})
                .thenSucceed();
        });
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void realForkEnergyHatchAcceptsNetworkPackets(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            be.mode(Protocol.EU,Protocol.Mode.BOTH);be.euVoltage=32;be.euAmperage=1;
            var id=ResourceLocation.parse("gtceu:lv_energy_input_hatch");helper.assertTrue(BuiltInRegistries.BLOCK.containsKey(id),"actual fork machine registered");
            var pos=be.getBlockPos().relative(Direction.EAST);var state=BuiltInRegistries.BLOCK.get(id).defaultBlockState();
            for(var property:state.getProperties())if(property instanceof net.minecraft.world.level.block.state.properties.DirectionProperty direction && direction.getPossibleValues().contains(Direction.WEST))state=state.setValue(direction,Direction.WEST);
            helper.getLevel().setBlockAndUpdate(pos,state);
            var hatch=helper.getLevel().getCapability(ENERGY,pos,Direction.WEST);helper.assertTrue(hatch!=null && hatch.inputsEnergy(Direction.WEST) && hatch.getInputVoltage()==32,"real GT machine electrical rules");
            long before=hatch.getEnergyStored();var source=helper.getLevel().getCapability(ENERGY,be.getBlockPos(),Direction.UP);helper.assertTrue(source.acceptEnergyFromNetwork(Direction.UP,32,1)==1,"local source accepts a packet");
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(hatch.getEnergyStored()-before==32,"module must invoke actual acceptEnergyFromNetwork on adjacent GT hatch"))
                .thenExecute(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.EU)==0,"only the accepted amp is deducted"))
                .thenSucceed();
        });
    }
}
