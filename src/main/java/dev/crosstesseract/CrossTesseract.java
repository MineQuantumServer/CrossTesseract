package dev.crosstesseract;

import com.mojang.logging.LogUtils;
import dev.crosstesseract.block.*;
import dev.crosstesseract.network.*;
import dev.crosstesseract.runtime.*;
import dev.crosstesseract.compat.CompatLoader;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.*;
import net.minecraft.world.inventory.MenuType;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.material.MapColor;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.capabilities.*;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.common.extensions.IMenuTypeExtension;
import net.neoforged.neoforge.registries.*;
import org.slf4j.Logger;

@Mod(CrossTesseract.ID)
public final class CrossTesseract {
    public static final String ID="cross_tesseract";
    public static final Logger LOG=LogUtils.getLogger();
    public static final DeferredRegister.Blocks BLOCKS=DeferredRegister.createBlocks(ID);
    public static final DeferredRegister.Items ITEMS=DeferredRegister.createItems(ID);
    public static final DeferredRegister<BlockEntityType<?>> ENTITIES=DeferredRegister.create(Registries.BLOCK_ENTITY_TYPE,ID);
    public static final DeferredRegister<MenuType<?>> MENUS=DeferredRegister.create(Registries.MENU,ID);
    public static final DeferredRegister<CreativeModeTab> TABS=DeferredRegister.create(Registries.CREATIVE_MODE_TAB,ID);
    public static final DeferredBlock<TesseractBlock> TESSERACT=BLOCKS.register("tesseract",()->new TesseractBlock(BlockBehaviour.Properties.of().mapColor(MapColor.METAL).strength(5,12).requiresCorrectToolForDrops().noOcclusion()));
    public static final DeferredItem<BlockItem> ITEM=ITEMS.registerSimpleBlockItem("tesseract",TESSERACT);
    public static final DeferredHolder<BlockEntityType<?>,BlockEntityType<TesseractBlockEntity>> ENTITY=ENTITIES.register("tesseract",()->BlockEntityType.Builder.of(TesseractBlockEntity::new,TESSERACT.get()).build(null));
    public static final DeferredHolder<MenuType<?>,MenuType<TesseractMenu>> MENU=MENUS.register("tesseract",()->IMenuTypeExtension.create(TesseractMenu::new));
    public static final DeferredHolder<CreativeModeTab,CreativeModeTab> TAB=TABS.register("main",()->CreativeModeTab.builder().title(Component.translatable("itemGroup.cross_tesseract")).icon(()->ITEM.get().getDefaultInstance()).displayItems((p,out)->out.accept(ITEM.get())).build());
    public CrossTesseract(IEventBus bus) {
        BLOCKS.register(bus);ITEMS.register(bus);ENTITIES.register(bus);MENUS.register(bus);TABS.register(bus);
        bus.addListener((RegisterCapabilitiesEvent e)->{
            e.registerBlockEntity(Capabilities.ItemHandler.BLOCK,ENTITY.get(),(be,side)->be.items(side));
            e.registerBlockEntity(Capabilities.FluidHandler.BLOCK,ENTITY.get(),(be,side)->be.fluids(side));
            e.registerBlockEntity(Capabilities.EnergyStorage.BLOCK,ENTITY.get(),(be,side)->be.energy(side));
            CompatLoader.register(e);
        });
        bus.addListener(Packets::register);
        bus.addListener((net.neoforged.neoforge.common.world.chunk.RegisterTicketControllersEvent e)->e.register(ChunkTickets.CONTROLLER));
        bus.addListener((net.neoforged.neoforge.event.RegisterGameTestsEvent e)->{
            e.register(dev.crosstesseract.test.GameTests.class);
            // Optional test classes are reached only through the already-loaded optional module.
            if(Boolean.getBoolean("cross_tesseract.compatTests"))e.register(dev.crosstesseract.test.CoreBackendGameTests.class);
            if(Boolean.getBoolean("cross_tesseract.compatTests"))e.register(dev.crosstesseract.test.RuntimeDeltaGameTests.class);
            if(Boolean.getBoolean("cross_tesseract.compatTests"))e.register(dev.crosstesseract.test.RegistrationRecoveryGameTests.class);
            if(Boolean.getBoolean("cross_tesseract.compatTests"))for(var module:CompatLoader.modules())if(module.gameTests()!=null)e.register(module.gameTests());
        });
        NeoForge.EVENT_BUS.addListener(RuntimeEvents::starting);
        NeoForge.EVENT_BUS.addListener(RuntimeEvents::tick);
        NeoForge.EVENT_BUS.addListener(RuntimeEvents::stopping);
        NeoForge.EVENT_BUS.addListener(RuntimeEvents::stopped);
        NeoForge.EVENT_BUS.addListener(Commands::register);
        NeoForge.EVENT_BUS.addListener(dev.crosstesseract.test.ThreeServerHarness::register);
        NeoForge.EVENT_BUS.addListener(dev.crosstesseract.test.ThreeServerHarness::tick);
    }
    public static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath(ID,path); }
}
