package dev.crosstesseract.compat;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.Protocol;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.capabilities.RegisterCapabilitiesEvent;
import java.util.*;

public final class CompatLoader {
    private static final List<CompatModule> MODULES=new ArrayList<>();
    public static void register(RegisterCapabilitiesEvent event) {
        for(var spec:Map.of("ae2","ae2.AeModule","mekanism","mekanism.MekModule","gtceu","gregtech.GtModule").entrySet()) {
            if(!ModList.get().isLoaded(spec.getKey()) || !Boolean.parseBoolean(System.getProperty("cross_tesseract.compat."+spec.getKey(),"true"))) continue;
            try {
                // No optional type is referenced by a core descriptor, annotation or scanner entry.
                var module=(CompatModule)Class.forName("dev.crosstesseract.compat."+spec.getValue()).getConstructor().newInstance();
                module.register(event);MODULES.add(module);
            } catch(ReflectiveOperationException | LinkageError e) {
                throw new IllegalStateException("Installed optional mod API incompatible: "+spec.getKey(),e);
            }
        }
    }
    public static Set<String> resources() { var set=new HashSet<>(Protocol.BASE);for(var m:MODULES)set.addAll(m.resources());return Set.copyOf(set); }
    public static List<CompatModule> modules() { return Collections.unmodifiableList(MODULES); }
    public static Set<String> capabilities(){var set=new HashSet<>(resources());for(var module:MODULES)set.addAll(module.features());return Set.copyOf(set);}
    public static boolean aeAvailable(){return MODULES.stream().anyMatch(m->m.getClass().getName().endsWith("AeModule"));}
    private CompatLoader() {}
}
