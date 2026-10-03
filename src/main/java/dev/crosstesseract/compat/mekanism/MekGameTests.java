package dev.crosstesseract.compat.mekanism;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.*;
import dev.crosstesseract.test.Fixtures;
import mekanism.api.Action;
import mekanism.api.MekanismAPI;
import mekanism.api.chemical.ChemicalStack;
import mekanism.common.capabilities.Capabilities;
import net.minecraft.core.Direction;
import net.minecraft.gametest.framework.*;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.gametest.*;

@PrefixGameTestTemplate(false)
public final class MekGameTests {
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void chemicalRemainderSimulationLongAmountAndDurableLoopback(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            be.mode(Protocol.CHEMICAL,Protocol.Mode.BOTH);be.rate(Protocol.CHEMICAL,64_000);
            var port=helper.getLevel().getCapability(Capabilities.CHEMICAL.block(),be.getBlockPos(),Direction.UP);
            var holder=MekanismAPI.CHEMICAL_REGISTRY.wrapAsHolder(MekanismAPI.CHEMICAL_REGISTRY.get(ResourceLocation.parse("mekanism:oxygen")));
            var input=new ChemicalStack(holder,(1L<<53)+123);
            var simulated=port.insertChemical(0,input,Action.SIMULATE);
            helper.assertTrue(input.getAmount()-simulated.getAmount()==64_000 && port.getChemicalInTank(0).isEmpty(),"simulation returns remainder, uses long and leaves caller/buffer unchanged");
            var rest=port.insertChemical(0,input,Action.EXECUTE);
            helper.assertTrue(input.getAmount()==(1L<<53)+123 && input.getAmount()-rest.getAmount()==64_000,"actual long partial insertion and caller immutability");
            var radioactive=new ChemicalStack(MekanismAPI.CHEMICAL_REGISTRY.wrapAsHolder(MekanismAPI.CHEMICAL_REGISTRY.get(ResourceLocation.parse("mekanism:nuclear_waste"))),100);
            helper.assertTrue(port.insertChemical(1,radioactive,Action.EXECUTE).getAmount()==100,"radioactive chemicals must be rejected");
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(be.buffer().receiveAmount(Protocol.CHEMICAL)==64_000,"real MySQL allocation and fsynced journal arrival pending"))
                .thenExecute(()->{long before=be.buffer().receiveAmount(Protocol.CHEMICAL);var copy=port.extractChemical(4,123,Action.SIMULATE);helper.assertTrue(copy.getAmount()==123 && be.buffer().receiveAmount(Protocol.CHEMICAL)==before,"pure simulated chemical extraction");var actual=port.extractChemical(4,123,Action.EXECUTE);helper.assertTrue(actual.getAmount()==123 && be.buffer().receiveAmount(Protocol.CHEMICAL)==before-123,"partial chemical extraction");})
                .thenSucceed();
        });
    }
    @GameTest(template="empty",templateNamespace=CrossTesseract.ID,timeoutTicks=1_000_000)
    public static void nativeHeatCapacityAndPassiveDurableExchange(GameTestHelper helper){
        Fixtures.bound(helper,be->{
            be.mode(Protocol.HEAT,Protocol.Mode.SEND);var port=helper.getLevel().getCapability(Capabilities.HEAT,be.getBlockPos(),Direction.UP);
            helper.assertTrue(port.getHeatCapacitorCount()==1 && port.getHeatCapacity(0)==10_000,"native finite thermal reservoir");
            port.handleHeat(0,1_000_000);long initial=be.thermal().energy();helper.assertTrue(port.getTemperature(0)==100,"heat energy / capacity sets temperature");
            boolean rejected=false;try{port.handleHeat(0,Double.NaN);}catch(DomainException e){rejected=true;}helper.assertTrue(rejected,"NaN is rejected");
            helper.startSequence().thenWaitUntil(()->helper.assertTrue(be.thermal().energy()<initial && !be.thermal().frozen(),"WAL and MySQL passive heat commit pending"))
                .thenExecute(()->helper.assertTrue(port.getTemperature(0)<100 && port.getTemperature(0)>=0,"temperature is not copied; actual local heat leaves reservoir"))
                .thenSucceed();
        });
    }
}
