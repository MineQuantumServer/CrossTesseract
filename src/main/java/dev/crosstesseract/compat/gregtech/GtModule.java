package dev.crosstesseract.compat.gregtech;

import com.gregtechceu.gtceu.api.capability.IEnergyContainer;
import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.compat.CompatModule;
import dev.crosstesseract.core.*;
import java.nio.ByteBuffer;
import java.util.*;
import net.minecraft.core.Direction;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.neoforged.neoforge.capabilities.*;

/** Compiled against the exact FortyTwoCn API. External transfers always use accepted amperes. */
public final class GtModule implements CompatModule {
    private static final BlockCapability<IEnergyContainer,Direction> CAPABILITY=BlockCapability.createSided(ResourceLocation.fromNamespaceAndPath("gtceu","energy_container"),IEnergyContainer.class);
    private final Map<TesseractBlockEntity,List<BlockCapabilityCache<IEnergyContainer,Direction>>> neighbors=new IdentityHashMap<>();
    @Override public Class<?> gameTests(){return GtGameTests.class;}
    @Override public Set<String> resources(){return Set.of(Protocol.EU);}
    @Override public void register(RegisterCapabilitiesEvent event){event.registerBlockEntity(CAPABILITY,CrossTesseract.ENTITY.get(),(be,side)->new Port(be,side));}
    @Override public void attach(TesseractBlockEntity be){if(be.getLevel() instanceof ServerLevel level && !neighbors.containsKey(be)){var caches=new ArrayList<BlockCapabilityCache<IEnergyContainer,Direction>>();for(Direction side:Direction.values())caches.add(BlockCapabilityCache.create(CAPABILITY,level,be.getBlockPos().relative(side),side.getOpposite(),()->!be.isRemoved(),()->{}));neighbors.put(be,caches);}}
    @Override public void detach(TesseractBlockEntity be){neighbors.remove(be);}
    @Override public void validate(TesseractBlockEntity be,Resource r){DomainException.require(r.bytes().length==8 && ByteBuffer.wrap(r.bytes()).getLong()==be.euVoltage,"voltage_mismatch");}
    @Override public void tick(TesseractBlockEntity be){
        attach(be);var caches=neighbors.get(be);if(caches==null)return;Resource eu=energy(be.euVoltage);
        for(Direction side:Direction.values())if(be.allowed(Protocol.EU,side,false)){
            IEnergyContainer machine=caches.get(side.get3DDataValue()).getCapability();if(machine==null || !machine.inputsEnergy(side.getOpposite()) || be.euVoltage>machine.getInputVoltage())continue;
            long available=be.buffer().received(Protocol.EU).stream().filter(c->c.resource().equals(eu)).mapToLong(LocalSnapshot.Credit::remaining).reduce(0,Math::addExact);
            long amp=Math.min(Math.min(be.euAmperage,machine.getInputAmperage()),available/be.euVoltage);if(amp<=0)continue;
            long amount=Math.multiplyExact(be.euVoltage,amp);long rate=be.budget(Protocol.EU,false,amount,true);amp=rate/be.euVoltage;if(amp<=0)continue;
            long accepted=machine.acceptEnergyFromNetwork(side.getOpposite(),be.euVoltage,amp);DomainException.require(accepted>=0 && accepted<=amp,"invalid_energy_handler");
            long used=Math.multiplyExact(be.euVoltage,accepted);if(used>0){be.buffer().extract(eu,used,false);be.budget(Protocol.EU,false,used,false);be.setChanged();}
        }
    }
    public static Resource energy(long voltage){DomainException.require(voltage>0,"invalid_voltage");return new Resource(Protocol.EU,ByteBuffer.allocate(8).putLong(voltage).array());}
    private record Port(TesseractBlockEntity be,Direction side) implements IEnergyContainer {
        @Override public long acceptEnergyFromNetwork(Direction input,long voltage,long amperage){
            if(voltage!=be.euVoltage || amperage<=0 || !inputsEnergy(input))return 0;
            long room=LocalBuffer.slotCapacity(Protocol.EU)-be.buffer().sendAmount(Protocol.EU);long packets=Math.min(amperage,Math.min(be.euAmperage,Math.max(0,room)/voltage));
            if(packets<=0)return 0;long desired=Math.multiplyExact(voltage,packets);long permitted=be.budget(Protocol.EU,true,desired,true);packets=permitted/voltage;
            long inserted=be.buffer().insert(energy(voltage),0,Math.multiplyExact(voltage,packets),false);be.budget(Protocol.EU,true,inserted,false);be.setChanged();return inserted/voltage;
        }
        @Override public boolean inputsEnergy(Direction input){return be.allowed(Protocol.EU,input,true);}
        @Override public boolean outputsEnergy(Direction output){return be.allowed(Protocol.EU,output,false);}
        @Override public long changeEnergy(long difference){
            // This changes this container internally only. It is never used to credit a neighboring machine.
            Resource eu=energy(be.euVoltage);long changed=0;
            if(difference>0 && be.allowed(Protocol.EU,side,true)){changed=be.buffer().insert(eu,0,Math.min(difference,be.budget(Protocol.EU,true,difference,true)),false);be.budget(Protocol.EU,true,changed,false);}
            if(difference<0 && difference!=Long.MIN_VALUE && be.allowed(Protocol.EU,side,false)){long removed=be.buffer().extract(eu,Math.min(-difference,be.budget(Protocol.EU,false,-difference,true)),false);be.budget(Protocol.EU,false,removed,false);changed=-removed;}
            if(changed!=0)be.setChanged();return changed;
        }
        @Override public long getEnergyStored(){return be.buffer().sendAmount(Protocol.EU)+be.buffer().receiveAmount(Protocol.EU);}
        @Override public long getEnergyCapacity(){return 2*LocalBuffer.slotCapacity(Protocol.EU);}
        @Override public long getInputVoltage(){return be.euVoltage;}
        @Override public long getOutputVoltage(){return be.euVoltage;}
        @Override public long getInputAmperage(){return be.euAmperage;}
        @Override public long getOutputAmperage(){return be.euAmperage;}
    }
}
