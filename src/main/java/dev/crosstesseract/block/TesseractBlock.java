package dev.crosstesseract.block;

import com.mojang.serialization.MapCodec;
import dev.crosstesseract.CrossTesseract;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.*;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import org.jetbrains.annotations.Nullable;

public final class TesseractBlock extends BaseEntityBlock {
    public static final MapCodec<TesseractBlock> CODEC=simpleCodec(TesseractBlock::new);
    public TesseractBlock(Properties properties) { super(properties); }
    @Override protected MapCodec<? extends BaseEntityBlock> codec() { return CODEC; }
    @Override protected RenderShape getRenderShape(BlockState state) { return RenderShape.MODEL; }
    @Override public BlockEntity newBlockEntity(BlockPos pos,BlockState state) { return new TesseractBlockEntity(pos,state); }
    @Override public void setPlacedBy(Level level,BlockPos pos,BlockState state,@Nullable LivingEntity placer,ItemStack stack) {
        super.setPlacedBy(level,pos,state,placer,stack);
        if(!level.isClientSide && level.getBlockEntity(pos) instanceof TesseractBlockEntity be && placer instanceof Player player) be.placed(player.getUUID());
    }
    @Override protected InteractionResult useWithoutItem(BlockState state,Level level,BlockPos pos,Player player,BlockHitResult hit) {
        if(player instanceof ServerPlayer sp && level.getBlockEntity(pos) instanceof TesseractBlockEntity be) {
            if(!sp.getUUID().equals(be.owner())) { sp.displayClientMessage(net.minecraft.network.chat.Component.translatable("ct.error.device_owner_required"),true);return InteractionResult.FAIL; }
            sp.openMenu(be,buf->buf.writeBlockPos(pos));
        }
        return InteractionResult.sidedSuccess(level.isClientSide);
    }
    @Override protected void onRemove(BlockState old,Level level,BlockPos pos,BlockState next,boolean moved) {
        if(!old.is(next.getBlock()) && level.getBlockEntity(pos) instanceof TesseractBlockEntity be && !level.isClientSide) be.seal(moved?"moved":"removed");
        super.onRemove(old,level,pos,next,moved);
    }
    @Override public ItemStack getCloneItemStack(LevelReader level,BlockPos pos,BlockState state) { return CrossTesseract.ITEM.get().getDefaultInstance(); }
}
