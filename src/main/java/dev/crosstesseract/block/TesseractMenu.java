package dev.crosstesseract.block;

import dev.crosstesseract.CrossTesseract;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.world.entity.player.*;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;

public final class TesseractMenu extends AbstractContainerMenu {
    private final BlockPos pos;
    private final Inventory inventory;
    private final java.util.UUID instance;
    public TesseractMenu(int id,Inventory inventory,RegistryFriendlyByteBuf buf) { this(id,inventory,buf.readBlockPos()); }
    public TesseractMenu(int id,Inventory inventory,BlockPos pos) { super(CrossTesseract.MENU.get(),id);this.pos=pos.immutable();this.inventory=inventory;this.instance=inventory.player.level().getBlockEntity(pos) instanceof TesseractBlockEntity be?be.id():null; }
    public BlockPos pos() { return pos; }
    @Override public ItemStack quickMoveStack(Player player,int index) { return ItemStack.EMPTY; }
    @Override public boolean stillValid(Player player) {
        boolean near=player.level()==inventory.player.level() && player.distanceToSqr(pos.getX()+.5,pos.getY()+.5,pos.getZ()+.5)<=64;
        if(player.level().isClientSide)return near && player.level().getBlockState(pos).is(CrossTesseract.TESSERACT.get());
        return near && player.level().getBlockEntity(pos) instanceof TesseractBlockEntity be && player.getUUID().equals(be.owner()) && java.util.Objects.equals(instance,be.id());
    }
}
