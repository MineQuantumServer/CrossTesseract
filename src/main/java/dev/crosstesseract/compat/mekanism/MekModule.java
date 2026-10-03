package dev.crosstesseract.compat.mekanism;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.*;
import dev.crosstesseract.compat.CompatModule;
import dev.crosstesseract.core.*;
import java.util.*;
import mekanism.api.Action;
import mekanism.api.chemical.*;
import mekanism.api.chemical.attribute.ChemicalAttributeValidator;
import mekanism.common.capabilities.Capabilities;
import net.minecraft.core.Direction;
import net.minecraft.nbt.NbtOps;
import net.neoforged.neoforge.capabilities.RegisterCapabilitiesEvent;
import mekanism.api.heat.IHeatHandler;

public final class MekModule implements CompatModule {
    @Override public Set<String> resources(){return Set.of(Protocol.CHEMICAL,Protocol.HEAT);}
    @Override public Class<?> gameTests(){return MekGameTests.class;}
    @Override public void register(RegisterCapabilitiesEvent event){event.registerBlockEntity(Capabilities.CHEMICAL.block(),CrossTesseract.ENTITY.get(),(be,side)->new ChemicalPort(be,side));event.registerBlockEntity(Capabilities.HEAT,CrossTesseract.ENTITY.get(),(be,side)->new HeatPort(be,side));}
    @Override public void validate(TesseractBlockEntity be,Resource resource){DomainException.require(resource.kind().equals(Protocol.CHEMICAL),"resource_unsupported");decode(be,resource,1);}
    @Override public void tick(TesseractBlockEntity be){if(be.runtime()!=null && (be.allowed(Protocol.HEAT,null,true)||be.allowed(Protocol.HEAT,null,false)))be.runtime().heatExchange(be);}
    private static boolean valid(ChemicalStack stack){return !stack.isEmpty() && stack.getChemicalHolder().getKey()!=null && !stack.isRadioactive() && ChemicalAttributeValidator.DEFAULT.process(stack);}
    private static Resource encode(TesseractBlockEntity be,ChemicalStack stack){DomainException.require(valid(stack),"chemical_restricted");return StackCodec.tag(Protocol.CHEMICAL,stack.copyWithAmount(1).save(be.getLevel().registryAccess()));}
    private static ChemicalStack decode(TesseractBlockEntity be,Resource resource,long amount){
        ChemicalStack stack=ChemicalStack.CODEC.parse(be.getLevel().registryAccess().createSerializationContext(NbtOps.INSTANCE),StackCodec.tag(resource)).getOrThrow(message->new DomainException("registry_missing"));
        DomainException.require(valid(stack) && stack.getAmount()==1,"chemical_restricted");return stack.copyWithAmount(amount);
    }
    private record ChemicalPort(TesseractBlockEntity be,Direction side) implements IChemicalHandler {
        @Override public int getChemicalTanks(){return 8;}
        @Override public ChemicalStack getChemicalInTank(int tank){
            if(tank<0 || tank>=8 || !be.allowed(Protocol.CHEMICAL,side,tank<4))return ChemicalStack.EMPTY;
            if(tank<4){var stack=be.buffer().sent(Protocol.CHEMICAL,tank);return stack==null?ChemicalStack.EMPTY:decode(be,stack.resource(),stack.amount());}
            var list=be.buffer().received(Protocol.CHEMICAL);return tank-4<list.size()?decode(be,list.get(tank-4).resource(),list.get(tank-4).remaining()):ChemicalStack.EMPTY;
        }
        @Override public void setChemicalInTank(int tank,ChemicalStack stack){throw new UnsupportedOperationException("Use insertChemical/extractChemical");}
        @Override public long getChemicalTankCapacity(int tank){return tank>=0 && tank<8?LocalBuffer.slotCapacity(Protocol.CHEMICAL):0;}
        @Override public boolean isValid(int tank,ChemicalStack stack){return tank>=0 && tank<4 && be.allowed(Protocol.CHEMICAL,side,true) && valid(stack) && be.acceptsId(stack.getChemicalHolder().getKey().location().toString());}
        @Override public ChemicalStack insertChemical(int tank,ChemicalStack stack,Action action){
            if(!isValid(tank,stack))return stack.copy();
            try{Resource resource=encode(be,stack);long rate=be.budget(Protocol.CHEMICAL,true,stack.getAmount(),true);long accepted=be.buffer().insert(resource,tank,rate,action.simulate());if(action.execute()){be.budget(Protocol.CHEMICAL,true,accepted,false);be.setChanged();}return stack.copyWithAmount(stack.getAmount()-accepted);}catch(DomainException e){return stack.copy();}
        }
        @Override public ChemicalStack extractChemical(int tank,long amount,Action action){
            if(tank<4 || tank>=8 || amount<=0 || !be.allowed(Protocol.CHEMICAL,side,false))return ChemicalStack.EMPTY;
            var list=be.buffer().received(Protocol.CHEMICAL);if(tank-4>=list.size())return ChemicalStack.EMPTY;var credit=list.get(tank-4);
            long rate=be.budget(Protocol.CHEMICAL,false,amount,true);long extracted=be.buffer().extract(credit.transaction(),rate,action.simulate());if(action.execute()){be.budget(Protocol.CHEMICAL,false,extracted,false);be.setChanged();}return extracted==0?ChemicalStack.EMPTY:decode(be,credit.resource(),extracted);
        }
    }
    private record HeatPort(TesseractBlockEntity be,Direction side) implements IHeatHandler {
        private boolean active(){return (be.allowed(Protocol.HEAT,side,true)||be.allowed(Protocol.HEAT,side,false)) && !be.thermal().frozen();}
        @Override public int getHeatCapacitorCount(){return active()?1:0;}
        @Override public double getTemperature(int capacitor){DomainException.require(capacitor==0,"invalid_slot");return be.thermal().energy()/1_000_000.0/be.heatCapacity;}
        @Override public double getInverseConduction(int capacitor){DomainException.require(capacitor==0,"invalid_slot");return active()?be.heatInverseConduction:Double.MAX_VALUE;}
        @Override public double getHeatCapacity(int capacitor){DomainException.require(capacitor==0,"invalid_slot");return be.heatCapacity;}
        @Override public void handleHeat(int capacitor,double transfer){DomainException.require(capacitor==0 && active(),"invalid_heat");be.thermal().change(transfer);be.buffer().touch();be.setChanged();}
    }
}
