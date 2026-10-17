package dev.crosstesseract.rcprobe;

import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import org.objectweb.asm.*;

/** Offline verifier tests only; this class is excluded from both agent JARs. */
public final class ProbeSelfTest {
    static final class Loader extends ClassLoader {Class<?> load(String name,byte[] bytes){return defineClass(name,bytes,0,bytes.length);}}
    static byte[] fixture(){
        String owner="dev/crosstesseract/runtime/RuntimeService";
        var w=new ClassWriter(ClassWriter.COMPUTE_FRAMES|ClassWriter.COMPUTE_MAXS);
        w.visit(Opcodes.V21,Opcodes.ACC_PUBLIC,owner,null,"java/lang/Object",null);
        var m=w.visitMethod(Opcodes.ACC_PUBLIC,"<init>","()V",null,null);m.visitCode();m.visitVarInsn(Opcodes.ALOAD,0);m.visitMethodInsn(Opcodes.INVOKESPECIAL,"java/lang/Object","<init>","()V",false);m.visitInsn(Opcodes.RETURN);m.visitMaxs(0,0);m.visitEnd();
        m=w.visitMethod(Opcodes.ACC_PRIVATE,"processTicketWork","(J)V",null,null);m.visitCode();var done=new Label();m.visitVarInsn(Opcodes.LLOAD,1);m.visitInsn(Opcodes.LCONST_0);m.visitInsn(Opcodes.LCMP);m.visitJumpInsn(Opcodes.IFEQ,done);m.visitLdcInsn("not-an-integer");m.visitMethodInsn(Opcodes.INVOKESTATIC,"java/lang/Integer","parseInt","(Ljava/lang/String;)I",false);m.visitInsn(Opcodes.POP);m.visitLabel(done);m.visitInsn(Opcodes.RETURN);m.visitMaxs(0,0);m.visitEnd();
        m=w.visitMethod(Opcodes.ACC_PUBLIC,"tick","()V",null,null);m.visitCode();var start=new Label();var end=new Label();var handler=new Label();var after=new Label();m.visitTryCatchBlock(start,end,handler,"java/lang/NumberFormatException");m.visitLabel(start);m.visitVarInsn(Opcodes.ALOAD,0);m.visitInsn(Opcodes.LCONST_1);m.visitMethodInsn(Opcodes.INVOKESPECIAL,owner,"processTicketWork","(J)V",false);m.visitLabel(end);m.visitJumpInsn(Opcodes.GOTO,after);m.visitLabel(handler);m.visitInsn(Opcodes.POP);m.visitLabel(after);m.visitVarInsn(Opcodes.ALOAD,0);m.visitInsn(Opcodes.LCONST_0);m.visitMethodInsn(Opcodes.INVOKESPECIAL,owner,"processTicketWork","(J)V",false);m.visitInsn(Opcodes.RETURN);m.visitMaxs(0,0);m.visitEnd();
        m=w.visitMethod(Opcodes.ACC_PUBLIC,"wakeChannel","(Ljava/util/UUID;Z)V",null,null);m.visitCode();m.visitVarInsn(Opcodes.ALOAD,0);m.visitInsn(Opcodes.LCONST_1);m.visitMethodInsn(Opcodes.INVOKESPECIAL,owner,"processTicketWork","(J)V",false);m.visitInsn(Opcodes.RETURN);m.visitMaxs(0,0);m.visitEnd();
        w.visitEnd();return w.toByteArray();
    }
    static byte[] signatureFixture(String owner,String method,String descriptor){
        var w=new ClassWriter(ClassWriter.COMPUTE_FRAMES|ClassWriter.COMPUTE_MAXS);
        w.visit(Opcodes.V21,Opcodes.ACC_PUBLIC,owner,null,"java/lang/Object",null);
        var m=w.visitMethod(Opcodes.ACC_PUBLIC,method,descriptor,null,null);m.visitCode();
        switch(org.objectweb.asm.Type.getReturnType(descriptor).getSort()){
            case org.objectweb.asm.Type.VOID->m.visitInsn(Opcodes.RETURN);
            case org.objectweb.asm.Type.LONG->{m.visitInsn(Opcodes.LCONST_0);m.visitInsn(Opcodes.LRETURN);}
            default->{m.visitInsn(Opcodes.ACONST_NULL);m.visitInsn(Opcodes.ARETURN);}
        }
        m.visitMaxs(0,0);m.visitEnd();w.visitEnd();return w.toByteArray();
    }
    static void whitelistTest(){
        String save="(Lnet/minecraft/nbt/CompoundTag;Lnet/minecraft/core/HolderLookup$Provider;)V";
        for(String[] entry:new String[][]{
            {"dev/crosstesseract/block/TesseractBlockEntity","saveAdditional",save},
            {"dev/crosstesseract/compat/CompatModule","changed","(Ldev/crosstesseract/block/TesseractBlockEntity;)V"},
            {"dev/crosstesseract/compat/ae2/AeModule$Gateway","insert","(Ljava/lang/Object;JLjava/lang/Object;Ljava/lang/Object;)J"},
            {"dev/crosstesseract/compat/ae2/AeModule$Gateway","extract","(Ljava/lang/Object;JLjava/lang/Object;Ljava/lang/Object;)J"},
            {"dev/crosstesseract/compat/ae2/AeModule$Gateway","getAvailableStacks","(Ljava/lang/Object;)V"},
            {"dev/crosstesseract/compat/gregtech/GtModule$Port","acceptEnergyFromNetwork","(Ljava/lang/Object;JJ)J"},
            {"dev/crosstesseract/compat/gregtech/GtModule$Port","changeEnergy","(J)J"},
            {"dev/crosstesseract/compat/mekanism/MekModule$ChemicalPort","insertChemical","(ILjava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;"},
            {"dev/crosstesseract/compat/mekanism/MekModule$ChemicalPort","extractChemical","(IJLjava/lang/Object;)Ljava/lang/Object;"},
            {"dev/crosstesseract/compat/mekanism/MekModule$HeatPort","handleHeat","(ID)V"}}){
            var rewritten=ProbeAgent.rewrite(entry[0],signatureFixture(entry[0],entry[1],entry[2]));
            if(rewritten==null || !rewritten.methods().equals(entry[1]+entry[2]))throw new AssertionError("Missing explicit entry: "+Arrays.toString(entry));
        }
        for(String[] entry:new String[][]{
            {"dev/crosstesseract/block/TesseractBlockEntity","saveAdditional","()V"},
            {"dev/crosstesseract/compat/ae2/AeModule$Gateway","unlisted","()V"},
            {"dev/crosstesseract/compat/OtherModule","changed","(Ldev/crosstesseract/block/TesseractBlockEntity;)V"}})
            if(ProbeAgent.rewrite(entry[0],signatureFixture(entry[0],entry[1],entry[2]))!=null)throw new AssertionError("Unlisted entry instrumented");
    }
    @SuppressWarnings("unchecked") static Map<String,Object> snapshot(Object session)throws Exception{
        var method=session.getClass().getDeclaredMethod("snapshot");method.setAccessible(true);
        return (Map<String,Object>)method.invoke(session);
    }
    static long spanSum(Map<String,Object> body,String site){return ((Number)((Map<?,?>)((Map<?,?>)((Map<?,?>)body.get("spans")).get(site)).get("inclusive")).get("sum_ns")).longValue();}
    static long metric(Map<?,?> values,String name){return ((Number)values.get(name)).longValue();}
    static Map<?,?> roots(Map<String,Object> body){return (Map<?,?>)body.get("mod_roots");}
    static Map<?,?> perTick(Map<String,Object> body){return (Map<?,?>)roots(body).get("per_complete_tick");}
    static void rootsTest(Field active,Constructor<?> constructor)throws Exception{
        Object session=constructor.newInstance(UUID.randomUUID().toString(),false);active.set(null,session);
        WindowStats.enter(0);WindowStats.enter(1);WindowStats.enter(16);WindowStats.enter(10);
        WindowStats.exit(10);WindowStats.exit(16);WindowStats.exit(1);
        var nested=snapshot(session);long expected=spanSum(nested,"runtime_tick"),nestedPort=spanSum(nested,"port");
        WindowStats.enter(16);WindowStats.exit(16);expected+=spanSum(snapshot(session),"port")-nestedPort;WindowStats.exit(0);
        var body=snapshot(session);
        if(metric(perTick(body),"count")!=1 || metric(perTick(body),"sum_ns")!=expected)throw new AssertionError("Nested mod roots double counted");
        WindowStats.enter(0);WindowStats.exit(0); // An idle tick contributes a real zero.
        long beforePort=spanSum(snapshot(session),"port");
        WindowStats.enter(0);WindowStats.enter(18);WindowStats.enter(16);WindowStats.exit(16);WindowStats.exit(18);WindowStats.exit(0);
        expected+=spanSum(snapshot(session),"port")-beforePort;
        WindowStats.enter(0);WindowStats.enter(19);WindowStats.enter(10);WindowStats.exit(10);WindowStats.exit(19);
        WindowStats.enter(20);WindowStats.exit(20);WindowStats.enter(21);WindowStats.exit(21);WindowStats.exit(0);
        body=snapshot(session);expected+=spanSum(body,"save_additional")+spanSum(body,"compat_changed")+spanSum(body,"compat_port");
        if(metric(perTick(body),"count")!=4 || metric(perTick(body),"sum_ns")!=expected || metric(roots(body),"root_calls_inside_ticks")!=6)throw new AssertionError("Idle/generator/save/compat root accounting");
        boolean zero=false;for(Object bin:(List<?>)perTick(body).get("histogram_upper_ns_count")){var pair=(List<?>)bin;if(((Number)pair.getFirst()).longValue()==0 && ((Number)pair.getLast()).longValue()==1)zero=true;}
        if(!zero)throw new AssertionError("Idle zero sample missing");
        WindowStats.enter(16);WindowStats.exit(16);
        var worker=new Thread(()->{WindowStats.enter(16);WindowStats.enter(10);WindowStats.exit(10);WindowStats.exit(16);});worker.start();worker.join();
        body=snapshot(session);
        if(metric((Map<?,?>)roots(body).get("outside_tick_main_thread_roots"),"count")!=1 || metric((Map<?,?>)roots(body).get("non_main_thread_roots"),"count")!=1 || metric(perTick(body),"sum_ns")!=expected || !Boolean.TRUE.equals(roots(body).get("valid")))throw new AssertionError("Outside-tick/worker mixed into tick roots");
        var rewritten=ProbeAgent.rewrite("dev/crosstesseract/runtime/RuntimeService",fixture());
        Class<?> type=new Loader().load("dev.crosstesseract.runtime.RuntimeService",rewritten.bytes());Object object=type.getConstructor().newInstance();
        WindowStats.enter(0);
        try{type.getMethod("wakeChannel",UUID.class,boolean.class).invoke(object,UUID.randomUUID(),true);throw new AssertionError("Expected original business exception");}
        catch(InvocationTargetException expectedFailure){if(!(expectedFailure.getCause() instanceof NumberFormatException))throw expectedFailure;}
        WindowStats.exit(0);body=snapshot(session);
        if(metric(perTick(body),"count")!=5 || !Boolean.TRUE.equals(roots(body).get("valid")))throw new AssertionError("Exceptional mod root leaked");
        if(metric((Map<?,?>)roots(body).get("per_complete_logical_tick_cycle"),"count")!=4)throw new AssertionError("Live complete-cycle prefix count");
        var stop=WindowStats.class.getDeclaredField("pendingStop");stop.setAccessible(true);
        var token=session.getClass().getDeclaredField("token");token.setAccessible(true);stop.set(null,token.get(session));
        WindowStats.enter(0);WindowStats.exit(0); // Boundary closes the old cycle, not a new tick frame.
        body=snapshot(session);var cycle=(Map<?,?>)roots(body).get("per_complete_logical_tick_cycle");
        long outside=metric((Map<?,?>)roots(body).get("outside_tick_main_thread_roots"),"sum_ns");
        if(!Boolean.TRUE.equals(body.get("window_closed")) || active.get(null)!=null || metric(perTick(body),"count")!=5 || metric(cycle,"count")!=5
            || metric(cycle,"sum_ns")!=metric(perTick(body),"sum_ns")+outside || !Boolean.TRUE.equals(roots(body).get("valid")))throw new AssertionError("Final complete-cycle flush/outside accounting");
        session=constructor.newInstance(UUID.randomUUID().toString(),false);active.set(null,session);
        WindowStats.enter(0);for(int i=0;i<80;i++)WindowStats.enter(16);for(int i=0;i<80;i++)WindowStats.exit(16);WindowStats.exit(0);
        body=snapshot(session);
        if(metric(body,"frame_overflow_calls")!=17 || metric(roots(body),"invalid_ticks")!=1 || metric(perTick(body),"count")!=0 || Boolean.TRUE.equals(roots(body).get("valid")))throw new AssertionError("Overflow incorrectly qualified");
        session=constructor.newInstance(UUID.randomUUID().toString(),false);active.set(null,session);
        WindowStats.enter(0);WindowStats.enter(16);WindowStats.exit(10);WindowStats.exit(16);WindowStats.exit(0);
        body=snapshot(session);
        if(metric(body,"frame_depth_mismatches")!=1 || metric(roots(body),"invalid_ticks")!=1 || Boolean.TRUE.equals(roots(body).get("valid")))throw new AssertionError("Mismatched root incorrectly qualified");
        var frames=WindowStats.class.getDeclaredField("FRAMES");frames.setAccessible(true);Object f=((ThreadLocal<?>)frames.get(null)).get();
        for(String name:List.of("depth","overflow","modDepth","serverSlot")){var field=f.getClass().getDeclaredField(name);field.setAccessible(true);if(field.getInt(f)!=(name.equals("serverSlot")?-1:0))throw new AssertionError("Root frame leak: "+name);}
    }
    @SuppressWarnings("unchecked") public static void main(String[] args)throws Exception{
        var active=WindowStats.class.getDeclaredField("active");active.setAccessible(true);
        Class<?> sessionType=Class.forName("dev.crosstesseract.rcprobe.WindowStats$Session");
        var constructor=sessionType.getDeclaredConstructor(String.class,boolean.class);constructor.setAccessible(true);
        Object session=constructor.newInstance(UUID.randomUUID().toString(),false);active.set(null,session);
        try{
            var rewrite=ProbeAgent.rewrite("dev/crosstesseract/runtime/RuntimeService",fixture());
            Class<?> fixture=new Loader().load("dev.crosstesseract.runtime.RuntimeService",rewrite.bytes());Object object=fixture.getConstructor().newInstance();
            fixture.getMethod("tick").invoke(object); // Original local catch must retain precedence.
            try{fixture.getMethod("wakeChannel",UUID.class,boolean.class).invoke(object,UUID.randomUUID(),true);throw new AssertionError("Business exception swallowed");}
            catch(InvocationTargetException expected){if(!(expected.getCause() instanceof NumberFormatException))throw expected;}
            fixture.getMethod("tick").invoke(object);
            for(int i=0;i<80;i++)WindowStats.enter(16);for(int i=0;i<80;i++)WindowStats.exit(16);
            WindowStats.enter(5);active.set(null,null);WindowStats.enter(16);WindowStats.exit(16);active.set(null,session);WindowStats.exit(5);
            var frames=WindowStats.class.getDeclaredField("FRAMES");frames.setAccessible(true);Object f=((ThreadLocal<?>)frames.get(null)).get();
            for(String name:List.of("depth","overflow")){var field=f.getClass().getDeclaredField(name);field.setAccessible(true);if(field.getInt(f)!=0)throw new AssertionError("Frame leak: "+name);}
            var remember=sessionType.getDeclaredMethod("remember",String.class,String.class);var known=sessionType.getDeclaredMethod("known",String.class);var endpoint=sessionType.getDeclaredMethod("endpoint",String.class);var error=sessionType.getDeclaredMethod("traceFailure");
            for(var method:List.of(remember,known,endpoint,error)){method.setAccessible(true);if(!Modifier.isSynchronized(method.getModifiers()))throw new AssertionError("Shared trace state method not synchronized");}
            var pool=Executors.newFixedThreadPool(8);var futures=new ArrayList<Future<?>>();
            for(int t=0;t<8;t++)futures.add(pool.submit(()->{try{for(int i=0;i<1000;i++){String id="op"+(i%256);remember.invoke(session,id,"endpoint");if(!known.invoke(session,id).equals(true)||!endpoint.invoke(session,id).equals("endpoint"))throw new AssertionError("Concurrent map visibility");error.invoke(session);}}catch(Exception x){throw new RuntimeException(x);}}));
            for(var future:futures)future.get();pool.shutdown();
            var snapshot=sessionType.getDeclaredMethod("snapshot");snapshot.setAccessible(true);var body=(Map<String,Object>)snapshot.invoke(session);var spans=(Map<String,Object>)body.get("spans");
            var ticks=(Map<String,Object>)spans.get("runtime_tick");var tickets=(Map<String,Object>)spans.get("tickets");
            if(((Number)((Map<?,?>)ticks.get("inclusive")).get("count")).longValue()!=2 || ((Number)tickets.get("exceptional_returns")).longValue()!=3 || ((Number)body.get("frame_depth_mismatches")).longValue()!=0 || ((Number)body.get("trace_errors")).longValue()!=8000)throw new AssertionError("Exception/map/counter accounting");
            whitelistTest();rootsTest(active,constructor);
            System.out.println("RC_PROBE_TRANSFORM_SELFTEST_PASS revision=v2_mod_roots verifier=true original_catch_preserved=true implicit_exception_depth_zero=true concurrent_trace_state=true overflow_balanced=true nested_roots_deduplicated=true idle_zero=true generator_separate=true outside_tick_worker_separate=true logical_cycles_include_outside=true live_prefix_minus_one=true final_cycle_boundary_flushed=true invalid_tick_rejected=true explicit_save_compat_whitelist=true no_native_execution=true");
        }finally{active.set(null,null);}
    }
}
