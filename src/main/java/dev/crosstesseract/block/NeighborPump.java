package dev.crosstesseract.block;

import dev.crosstesseract.core.*;
import java.util.*;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.capabilities.*;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;
import net.neoforged.neoforge.items.IItemHandler;

/** One side and one external item slot per scheduled endpoint check. No IO or full inventory scan. */
public final class NeighborPump {
    private final TesseractBlockEntity be;
    private final Map<Direction,BlockCapabilityCache<IItemHandler,Direction>> items=new EnumMap<>(Direction.class);
    private final Map<Direction,BlockCapabilityCache<IFluidHandler,Direction>> fluids=new EnumMap<>(Direction.class);
    private final Map<Direction,BlockCapabilityCache<IEnergyStorage,Direction>> energy=new EnumMap<>(Direction.class);
    private final int[] sourceSlots=new int[6],destinationSlots=new int[6];
    private int side;
    public NeighborPump(TesseractBlockEntity be){this.be=be;}
    public void tick(){
        if(!(be.getLevel() instanceof ServerLevel level))return;Direction direction=Direction.from3DDataValue(Math.floorMod(side++,6));var pos=be.getBlockPos().relative(direction);
        if(!level.hasChunkAt(pos) || level.getBlockEntity(pos) instanceof TesseractBlockEntity)return;
        try{
            if(!be.aeEffective() && (be.allowed(Protocol.ITEM,direction,true)||be.allowed(Protocol.ITEM,direction,false))){var cache=items.computeIfAbsent(direction,d->BlockCapabilityCache.create(Capabilities.ItemHandler.BLOCK,level,pos,d.getOpposite(),()->!be.isRemoved(),()->{}));var target=cache.getCapability();if(target!=null)item(target,direction);}
            if(!be.aeEffective() && (be.allowed(Protocol.FLUID,direction,true)||be.allowed(Protocol.FLUID,direction,false))){var cache=fluids.computeIfAbsent(direction,d->BlockCapabilityCache.create(Capabilities.FluidHandler.BLOCK,level,pos,d.getOpposite(),()->!be.isRemoved(),()->{}));var target=cache.getCapability();if(target!=null)fluid(target,direction);}
            if(be.allowed(Protocol.FE,direction,true)||be.allowed(Protocol.FE,direction,false)){var cache=energy.computeIfAbsent(direction,d->BlockCapabilityCache.create(Capabilities.EnergyStorage.BLOCK,level,pos,d.getOpposite(),()->!be.isRemoved(),()->{}));var target=cache.getCapability();if(target!=null)energy(target,direction);}
        }catch(RuntimeException e){be.externalIo(false);be.runtime().quarantineLocalIo(be,"external_io_uncertain");}
    }
    private void preserve(Resource resource,long amount){if(amount>0)be.buffer().holdForReview(be.channel(),resource,amount);be.runtime().quarantineLocalIo(be,"external_io_uncertain");}
    private void item(IItemHandler target,Direction direction){
        int slots=target.getSlots();if(slots<=0)return;var own=be.items(direction);int index=direction.get3DDataValue();
        if(be.mode(Protocol.ITEM)==Protocol.Mode.SEND && be.allowed(Protocol.ITEM,direction,true)){
            int from=Math.floorMod(sourceSlots[index]++,slots);var preview=target.extractItem(from,64,true);
            if(!preview.isEmpty())for(int slot=0;slot<9;slot++){
                int accepted=preview.getCount()-own.insertItem(slot,preview.copy(),true).getCount();if(accepted<=0)continue;
                ItemStack actual;be.externalIo(true);try{actual=target.extractItem(from,accepted,false);}finally{be.externalIo(false);}
                if(actual.isEmpty())break;
                if(actual.getCount()>accepted || !ItemStack.isSameItemSameComponents(actual,preview)){preserve(be.itemResource(actual),actual.getCount());return;}
                var remainder=own.insertItem(slot,actual.copy(),false);
                if(!remainder.isEmpty()){be.externalIo(true);try{remainder=target.insertItem(from,remainder.copy(),false);}finally{be.externalIo(false);}if(!remainder.isEmpty()){preserve(be.itemResource(remainder),remainder.getCount());return;}}
                break;
            }
        }
        if(be.allowed(Protocol.ITEM,direction,false)){
            var preview=own.extractItem(9,64,true);if(preview.isEmpty())return;int into=Math.floorMod(destinationSlots[index]++,slots);
            int accepted=preview.getCount()-target.insertItem(into,preview.copy(),true).getCount();if(accepted<=0)return;
            Resource resource=be.itemResource(preview);var before=be.buffer().received(Protocol.ITEM);var actual=own.extractItem(9,accepted,false);if(actual.isEmpty())return;
            ItemStack rest;be.externalIo(true);try{rest=target.insertItem(into,actual.copy(),false);}finally{be.externalIo(false);}
            if(!rest.isEmpty() && (!ItemStack.isSameItemSameComponents(rest,actual)||rest.getCount()>actual.getCount())){preserve(be.itemResource(rest),rest.getCount());return;}
            be.buffer().refundLocalRemainder(before,resource,actual.getCount(),rest.getCount());
        }
    }
    private void fluid(IFluidHandler target,Direction direction){
        var own=be.fluids(direction);int limit=(int)Math.min(Integer.MAX_VALUE,be.rate(Protocol.FLUID));
        if(be.mode(Protocol.FLUID)==Protocol.Mode.SEND && be.allowed(Protocol.FLUID,direction,true)){
            var preview=target.drain(limit,IFluidHandler.FluidAction.SIMULATE);int room=preview.isEmpty()?0:own.fill(preview.copy(),IFluidHandler.FluidAction.SIMULATE);
            if(room>0){var request=preview.copyWithAmount(room);net.neoforged.neoforge.fluids.FluidStack actual;be.externalIo(true);try{actual=target.drain(request,IFluidHandler.FluidAction.EXECUTE);}finally{be.externalIo(false);}
                if(!actual.isEmpty()){if(actual.getAmount()>room || !net.neoforged.neoforge.fluids.FluidStack.isSameFluidSameComponents(actual,preview)){preserve(be.fluidResource(actual),actual.getAmount());return;}int accepted=own.fill(actual.copy(),IFluidHandler.FluidAction.EXECUTE);if(accepted<actual.getAmount()){var rest=actual.copyWithAmount(actual.getAmount()-accepted);be.externalIo(true);int returned;try{returned=target.fill(rest.copy(),IFluidHandler.FluidAction.EXECUTE);}finally{be.externalIo(false);}DomainException.require(returned>=0 && returned<=rest.getAmount(),"external_io_uncertain");if(returned<rest.getAmount()){preserve(be.fluidResource(rest),rest.getAmount()-returned);return;}}}}
        }
        if(be.allowed(Protocol.FLUID,direction,false)){
            var preview=own.drain(limit,IFluidHandler.FluidAction.SIMULATE);if(preview.isEmpty())return;int room=target.fill(preview.copy(),IFluidHandler.FluidAction.SIMULATE);if(room<=0)return;
            var before=be.buffer().received(Protocol.FLUID);var actual=own.drain(preview.copyWithAmount(Math.min(room,preview.getAmount())),IFluidHandler.FluidAction.EXECUTE);if(actual.isEmpty())return;
            be.externalIo(true);int accepted;try{accepted=target.fill(actual.copy(),IFluidHandler.FluidAction.EXECUTE);}finally{be.externalIo(false);}DomainException.require(accepted>=0 && accepted<=actual.getAmount(),"external_io_uncertain");be.buffer().refundLocalRemainder(before,be.fluidResource(actual),actual.getAmount(),actual.getAmount()-accepted);
        }
    }
    private void energy(IEnergyStorage target,Direction direction){
        var own=be.energy(direction);
        if(be.mode(Protocol.FE)==Protocol.Mode.SEND && be.allowed(Protocol.FE,direction,true) && target.canExtract()){
            int room=own.receiveEnergy(Integer.MAX_VALUE,true);int preview=target.extractEnergy(room,true);
            if(preview>0){be.externalIo(true);int actual;try{actual=target.extractEnergy(Math.min(room,preview),false);}finally{be.externalIo(false);}DomainException.require(actual>=0 && actual<=Math.min(room,preview),"external_io_uncertain");int accepted=own.receiveEnergy(actual,false);if(accepted<actual){preserve(new Resource(Protocol.FE,new byte[0]),actual-accepted);return;}}
        }
        if(be.allowed(Protocol.FE,direction,false) && target.canReceive()){
            int available=own.extractEnergy(Integer.MAX_VALUE,true);int room=target.receiveEnergy(available,true);if(room<=0)return;
            var before=be.buffer().received(Protocol.FE);int actual=own.extractEnergy(Math.min(available,room),false);be.externalIo(true);int accepted;try{accepted=target.receiveEnergy(actual,false);}finally{be.externalIo(false);}DomainException.require(accepted>=0 && accepted<=actual,"external_io_uncertain");be.buffer().refundLocalRemainder(before,new Resource(Protocol.FE,new byte[0]),actual,actual-accepted);
        }
    }
}
