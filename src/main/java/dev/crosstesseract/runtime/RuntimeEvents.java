package dev.crosstesseract.runtime;

import net.neoforged.neoforge.event.server.*;
import net.neoforged.neoforge.event.tick.ServerTickEvent;

public final class RuntimeEvents {
    public static void starting(ServerAboutToStartEvent event){RuntimeService.start(event.getServer());}
    public static void tick(ServerTickEvent.Pre event){var rt=RuntimeService.get(event.getServer());if(rt!=null)rt.tick();}
    public static void stopping(ServerStoppingEvent event){var rt=RuntimeService.get(event.getServer());if(rt!=null)rt.stop();}
    public static void stopped(ServerStoppedEvent event){var rt=RuntimeService.get(event.getServer());if(rt!=null)rt.stopped();}
    private RuntimeEvents(){}
}
