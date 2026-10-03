package dev.crosstesseract.block;

import dev.crosstesseract.core.*;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;
import net.neoforged.neoforge.items.IItemHandler;
import org.jetbrains.annotations.Nullable;

final class Ports {
    record ItemPort(TesseractBlockEntity be,@Nullable Direction side) implements IItemHandler {
        @Override public int getSlots(){return 18;}
        @Override public ItemStack getStackInSlot(int slot){
            if(be.aeEffective() || !be.allowed(Protocol.ITEM,side,slot<9))return ItemStack.EMPTY;
            if(slot<0 || slot>=18)return ItemStack.EMPTY;
            if(slot<9){var stack=be.buffer().sent(Protocol.ITEM,slot);return stack==null?ItemStack.EMPTY:be.decodeItem(stack.resource(),(int)Math.min(64,stack.amount()));}
            var list=be.buffer().received(Protocol.ITEM);return slot-9<list.size()?be.decodeItem(list.get(slot-9).resource(),(int)Math.min(64,list.get(slot-9).remaining())):ItemStack.EMPTY;
        }
        @Override public ItemStack insertItem(int slot,ItemStack stack,boolean simulate){
            if(!isItemValid(slot,stack))return stack.copy();
            try {
                Resource resource=be.itemResource(stack);var prior=be.buffer().sent(Protocol.ITEM,slot);long room=Math.max(0,stack.getMaxStackSize()-(prior==null?0:prior.amount()));long rate=be.budget(Protocol.ITEM,true,Math.min(stack.getCount(),room),true);
                long inserted=be.buffer().insert(resource,slot,rate,simulate);
                if(!simulate){be.budget(Protocol.ITEM,true,inserted,false);be.setChanged();}
                return inserted==stack.getCount()?ItemStack.EMPTY:stack.copyWithCount(stack.getCount()-(int)inserted);
            }catch(DomainException e){return stack.copy();}
        }
        @Override public ItemStack extractItem(int slot,int amount,boolean simulate){
            if(be.aeEffective() || slot<9 || slot>=18 || amount<=0 || !be.allowed(Protocol.ITEM,side,false))return ItemStack.EMPTY;
            var list=be.buffer().received(Protocol.ITEM);if(slot-9>=list.size())return ItemStack.EMPTY;var credit=list.get(slot-9);
            int max=be.decodeItem(credit.resource(),1).getMaxStackSize();long rate=be.budget(Protocol.ITEM,false,Math.min(amount,max),true);
            long extracted=be.buffer().extract(credit.transaction(),rate,simulate);if(extracted==0)return ItemStack.EMPTY;
            if(!simulate){be.budget(Protocol.ITEM,false,extracted,false);be.setChanged();}
            return be.decodeItem(credit.resource(),(int)extracted);
        }
        @Override public int getSlotLimit(int slot){return slot>=0&&slot<18?64:0;}
        @Override public boolean isItemValid(int slot,ItemStack stack){return !be.aeEffective() && slot>=0 && slot<9 && !stack.isEmpty() && be.allowed(Protocol.ITEM,side,true) && be.acceptsId(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());}
    }
    record FluidPort(TesseractBlockEntity be,@Nullable Direction side) implements IFluidHandler {
        @Override public int getTanks(){return 8;}
        @Override public FluidStack getFluidInTank(int tank){
            if(be.aeEffective() || !be.allowed(Protocol.FLUID,side,tank<4))return FluidStack.EMPTY;
            if(tank<0 || tank>=8)return FluidStack.EMPTY;
            if(tank<4){var stack=be.buffer().sent(Protocol.FLUID,tank);return stack==null?FluidStack.EMPTY:be.decodeFluid(stack.resource(),(int)stack.amount());}
            var list=be.buffer().received(Protocol.FLUID);return tank-4<list.size()?be.decodeFluid(list.get(tank-4).resource(),(int)list.get(tank-4).remaining()):FluidStack.EMPTY;
        }
        @Override public int getTankCapacity(int tank){return tank>=0&&tank<8?(int)LocalBuffer.slotCapacity(Protocol.FLUID):0;}
        @Override public boolean isFluidValid(int tank,FluidStack stack){return !be.aeEffective() && tank>=0 && tank<4 && !stack.isEmpty() && be.allowed(Protocol.FLUID,side,true) && be.acceptsId(BuiltInRegistries.FLUID.getKey(stack.getFluid()).toString());}
        @Override public int fill(FluidStack stack,FluidAction action){
            if(!isFluidValid(0,stack))return 0;
            try{Resource resource=be.fluidResource(stack);long rate=be.budget(Protocol.FLUID,true,stack.getAmount(),true);long inserted=be.buffer().insert(resource,rate,action.simulate());if(action.execute()){be.budget(Protocol.FLUID,true,inserted,false);be.setChanged();}return (int)inserted;}catch(DomainException e){return 0;}
        }
        @Override public FluidStack drain(FluidStack stack,FluidAction action){
            if(be.aeEffective() || stack.isEmpty() || !be.allowed(Protocol.FLUID,side,false))return FluidStack.EMPTY;
            try{return drainResource(be.fluidResource(stack),stack.getAmount(),action);}catch(DomainException e){return FluidStack.EMPTY;}
        }
        @Override public FluidStack drain(int amount,FluidAction action){
            if(be.aeEffective() || amount<=0 || !be.allowed(Protocol.FLUID,side,false))return FluidStack.EMPTY;
            var list=be.buffer().received(Protocol.FLUID);return list.isEmpty()?FluidStack.EMPTY:drainResource(list.getFirst().resource(),amount,action);
        }
        private FluidStack drainResource(Resource resource,int amount,FluidAction action){long rate=be.budget(Protocol.FLUID,false,amount,true);long extracted=be.buffer().extract(resource,rate,action.simulate());if(action.execute()){be.budget(Protocol.FLUID,false,extracted,false);be.setChanged();}return extracted==0?FluidStack.EMPTY:be.decodeFluid(resource,(int)extracted);}
    }
    record EnergyPort(TesseractBlockEntity be,@Nullable Direction side) implements IEnergyStorage {
        private static final Resource ENERGY=new Resource(Protocol.FE,new byte[0]);
        @Override public int receiveEnergy(int requested,boolean simulate){if(requested<=0 || !canReceive())return 0;long limit=be.budget(Protocol.FE,true,requested,true);long inserted=be.buffer().insert(ENERGY,0,limit,simulate);if(!simulate){be.budget(Protocol.FE,true,inserted,false);be.setChanged();}return(int)inserted;}
        @Override public int extractEnergy(int requested,boolean simulate){if(requested<=0 || !canExtract())return 0;long limit=be.budget(Protocol.FE,false,requested,true);long extracted=be.buffer().extract(ENERGY,limit,simulate);if(!simulate){be.budget(Protocol.FE,false,extracted,false);be.setChanged();}return(int)extracted;}
        @Override public int getEnergyStored(){return canReceive()||canExtract()?(int)Math.min(Integer.MAX_VALUE,be.buffer().sendAmount(Protocol.FE)+be.buffer().receiveAmount(Protocol.FE)):0;}
        @Override public int getMaxEnergyStored(){return (int)Math.min(Integer.MAX_VALUE,2*LocalBuffer.slotCapacity(Protocol.FE));}
        @Override public boolean canExtract(){return be.allowed(Protocol.FE,side,false);}
        @Override public boolean canReceive(){return be.allowed(Protocol.FE,side,true);}
    }
}
