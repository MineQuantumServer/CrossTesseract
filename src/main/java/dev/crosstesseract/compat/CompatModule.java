package dev.crosstesseract.compat;

import dev.crosstesseract.block.TesseractBlockEntity;
import net.neoforged.neoforge.capabilities.RegisterCapabilitiesEvent;
import java.util.Set;
import dev.crosstesseract.core.Resource;

public interface CompatModule {
    Set<String> resources();
    default Set<String> features(){return Set.of();}
    default Class<?> gameTests(){return null;}
    void register(RegisterCapabilitiesEvent event);
    default void attach(TesseractBlockEntity be) {}
    default void tick(TesseractBlockEntity be) {}
    default void suspended(TesseractBlockEntity be) {}
    default void detach(TesseractBlockEntity be) {}
    default void changed(TesseractBlockEntity be) {}
    default void validate(TesseractBlockEntity be,Resource resource) {}
    default String testCommand(TesseractBlockEntity be,String action,String[] arguments){throw new dev.crosstesseract.core.DomainException("resource_unsupported");}
}
