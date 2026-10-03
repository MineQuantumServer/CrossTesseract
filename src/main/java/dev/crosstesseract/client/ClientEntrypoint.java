package dev.crosstesseract.client;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.network.Packets;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.RegisterMenuScreensEvent;

@Mod(value=CrossTesseract.ID,dist=Dist.CLIENT)
public final class ClientEntrypoint {
    public ClientEntrypoint(IEventBus bus){
        bus.addListener((RegisterMenuScreensEvent event)->event.register(CrossTesseract.MENU.get(),TesseractScreen::new));
        if(Boolean.getBoolean("cross_tesseract.uiSmoke"))net.neoforged.neoforge.common.NeoForge.EVENT_BUS.addListener(UiSmoke::tick);
        Packets.clientReceiver=view->{if(Minecraft.getInstance().screen instanceof TesseractScreen screen && screen.getMenu().containerId==view.menu())screen.apply(view);};
    }
}
