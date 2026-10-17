package dev.crosstesseract.rcprobe;

import java.lang.instrument.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.jar.JarFile;
import org.objectweb.asm.*;

/** Explicit test-only instrumentation. Never included in the mod JAR. */
public final class ProbeAgent {
    public static void premain(String args, Instrumentation instrumentation) throws Exception {
        Path jar = Path.of(ProbeAgent.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        instrumentation.appendToBootstrapClassLoaderSearch(new JarFile(jar.resolveSibling("rc-probe-stats.jar").toFile()));
        Class<?> stats = Class.forName("dev.crosstesseract.rcprobe.WindowStats", true, null);
        stats.getMethod("configure", String.class).invoke(null, args);
        Module destination = stats.getModule();
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override public byte[] transform(Module module, ClassLoader loader, String name, Class<?> type,
                                              ProtectionDomain domain, byte[] bytes) {
                if (name == null || !selected(name)) return null;
                try {
                    Rewrite result = rewrite(name, bytes);
                    if (result == null) return null;
                    if (module != null && module.isNamed()) {
                        var opens = new HashMap<String, Set<Module>>();
                        for (String p : module.getPackages()) if (p.startsWith("dev.crosstesseract.")) opens.put(p, Set.of(destination));
                        instrumentation.redefineModule(module, Set.of(destination), Map.of(), opens, Set.of(), Map.of());
                    }
                    String origin = domain == null || domain.getCodeSource() == null ? "UNKNOWN" : domain.getCodeSource().getLocation().toString();
                    stats.getMethod("transformed", String.class, String.class, String.class, String.class)
                         .invoke(null, name, HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)), origin, result.methods());
                    return result.bytes();
                } catch (Throwable failure) {
                    // Instrumentation deliberately ignores transformer exceptions.
                    // Persist failure metadata; the native driver MUST reject it.
                    String reason=failure.getClass().getName()+": "+failure.getMessage();
                    System.err.println("RC_PROBE_TRANSFORM_FAILED " + name + " " + reason);
                    try { stats.getMethod("transformFailed",String.class,String.class).invoke(null,name,reason); }
                    catch (ReflectiveOperationException recording) { System.err.println("RC_PROBE_FAILURE_RECORDING_FAILED "+name); }
                    return null;
                }
            }
        });
        System.out.println("RC_PROBE_READY explicit_test_agent=true mod_JAR_unchanged=true native_hits_not_yet_verified=true");
    }
    record Rewrite(byte[] bytes,String methods) {}
    static Rewrite rewrite(String name,byte[] bytes) {
        var reader=new ClassReader(bytes);var writer=new ClassWriter(reader,0);var changed=new ArrayList<String>();
        reader.accept(new ClassVisitor(Opcodes.ASM9,writer) {
            @Override public MethodVisitor visitMethod(int access,String method,String desc,String signature,String[] exceptions) {
                MethodVisitor original=super.visitMethod(access,method,desc,signature,exceptions);
                int site=site(name,method,desc);
                if(site<0 || (access & (Opcodes.ACC_ABSTRACT|Opcodes.ACC_NATIVE))!=0)return original;
                changed.add(method+desc);
                return new MethodVisitor(Opcodes.ASM9,original) {
                    final Label start=new Label(),end=new Label(),handler=new Label();
                    private void call(String method,String descriptor){super.visitMethodInsn(Opcodes.INVOKESTATIC,"dev/crosstesseract/rcprobe/WindowStats",method,descriptor,false);}
                    private void number(int value){super.visitLdcInsn(value);}
                    @Override public void visitCode(){
                        super.visitCode();number(site);call("enter","(I)V");super.visitLabel(start);
                        if(site==2 && desc.equals("(Ldev/crosstesseract/block/TesseractBlockEntity;Ljava/lang/String;ZJ)V")){
                            super.visitVarInsn(Opcodes.ALOAD,1);super.visitVarInsn(Opcodes.ALOAD,2);
                            super.visitVarInsn(Opcodes.ILOAD,3);super.visitVarInsn(Opcodes.LLOAD,4);
                            call("local","(Ljava/lang/Object;Ljava/lang/String;ZJ)V");
                        }
                    }
                    @Override public void visitInsn(int opcode){
                        if(opcode>=Opcodes.IRETURN && opcode<=Opcodes.RETURN){
                            if(site==4 && opcode==Opcodes.ARETURN){super.visitInsn(Opcodes.DUP);call("captured","(Ljava/lang/Object;)V");}
                            else if(site==12 && opcode==Opcodes.RETURN && desc.equals("(Ldev/crosstesseract/core/LocalSnapshot;)V")){super.visitVarInsn(Opcodes.ALOAD,1);call("wal","(Ljava/lang/Object;)V");}
                            else if(site==13 && opcode==Opcodes.ARETURN){super.visitInsn(Opcodes.DUP);call("reserved","(Ljava/lang/Object;)V");}
                            else if(site==14 && opcode==Opcodes.ARETURN && desc.equals("(Ljava/util/UUID;Ljava/util/List;)Ljava/util/Map;")){super.visitInsn(Opcodes.DUP);super.visitVarInsn(Opcodes.ALOAD,2);call("published","(Ljava/lang/Object;Ljava/lang/Object;)V");}
                            else if(site==17 && opcode==Opcodes.RETURN && desc.equals("(Ldev/crosstesseract/core/LocalSnapshot$Credit;)V")){super.visitVarInsn(Opcodes.ALOAD,1);call("credit","(Ljava/lang/Object;)V");}
                            number(site);call("exit","(I)V");
                        }
                        super.visitInsn(opcode);
                    }
                    @Override public void visitMaxs(int stack,int locals){
                        // Append last: original business catch clauses keep priority.
                        // The handler uses no locals; TOP locals avoid loading game
                        // classes merely to recompute common-superclass frames.
                        super.visitTryCatchBlock(start,end,handler,"java/lang/Throwable");
                        super.visitLabel(end);super.visitLabel(handler);
                        super.visitFrame(Opcodes.F_FULL,0,new Object[0],1,new Object[]{"java/lang/Throwable"});
                        number(site);call("exceptionalExit","(I)V");super.visitInsn(Opcodes.ATHROW);
                        super.visitMaxs(stack+8,locals);
                    }
                };
            }
        },0);
        return changed.isEmpty()?null:new Rewrite(writer.toByteArray(),String.join(";",changed));
    }
    private static boolean selected(String name) {return name.equals("net/minecraft/server/MinecraftServer") || name.startsWith("dev/crosstesseract/");}
    private static int site(String type,String method,String desc) {
        if(type.equals("net/minecraft/server/MinecraftServer") && method.equals("tickServer") && desc.equals("(Ljava/util/function/BooleanSupplier;)V"))return 0;
        if(type.equals("dev/crosstesseract/runtime/RuntimeService"))return switch(method){
            case "tick"->1;case "localChanged"->2;case "wakeChannel"->3;case "capture"->4;
            case "preparePublication"->5;case "finish"->6;case "exchangeLocal"->7;
            case "flushClosing"->8;case "processTicketWork"->9;default->-1;
        };
        if(type.equals("dev/crosstesseract/block/TesseractBlockEntity")){
            if(method.equals("itemResource")||method.equals("fluidResource"))return 10;
            if(method.equals("decodeItem")||method.equals("decodeFluid"))return 11;
            if(method.equals("saveAdditional") && desc.equals("(Lnet/minecraft/nbt/CompoundTag;Lnet/minecraft/core/HolderLookup$Provider;)V"))return 19;
        }
        if(type.equals("dev/crosstesseract/backend/LocalJournal") && method.equals("write"))return 12;
        if(type.equals("dev/crosstesseract/backend/Authority")){
            if(method.equals("channelBatch"))return 13;if(method.equals("publishBatch"))return 14;
        }
        if(type.equals("dev/crosstesseract/backend/Sql") && method.equals("transaction"))return 15;
        if(type.startsWith("dev/crosstesseract/block/Ports$") && Set.of("receiveEnergy","extractEnergy","insertItem","extractItem","fill","drain").contains(method))return 16;
        if(type.equals("dev/crosstesseract/core/LocalBuffer") && method.equals("credit"))return 17;
        if(type.equals("dev/crosstesseract/test/ThreeServerHarness") && method.equals("tick"))return 18;
        // Exact own classes/methods only. ASM never resolves optional mod API types.
        if(Set.of("dev/crosstesseract/compat/CompatModule","dev/crosstesseract/compat/ae2/AeModule",
                  "dev/crosstesseract/compat/gregtech/GtModule","dev/crosstesseract/compat/mekanism/MekModule").contains(type)
            && method.equals("changed") && desc.equals("(Ldev/crosstesseract/block/TesseractBlockEntity;)V"))return 20;
        if(type.equals("dev/crosstesseract/compat/ae2/AeModule$Gateway") && Set.of("insert","extract","getAvailableStacks").contains(method))return 21;
        if(type.equals("dev/crosstesseract/compat/gregtech/GtModule$Port") && Set.of("acceptEnergyFromNetwork","changeEnergy").contains(method))return 21;
        if(type.equals("dev/crosstesseract/compat/mekanism/MekModule$ChemicalPort") && Set.of("insertChemical","extractChemical").contains(method))return 21;
        if(type.equals("dev/crosstesseract/compat/mekanism/MekModule$HeatPort") && method.equals("handleHeat"))return 21;
        return -1;
    }
}
