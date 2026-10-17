package dev.crosstesseract.rcprobe;

import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.atomic.*;

/** Bootstrap-visible, bounded full-window test recorder. File IO occurs on its daemon only. */
public final class WindowStats {
    private static final String[] NAMES = {"server_tick", "runtime_tick", "local_changed", "notification_fanout",
        "capture", "prepare_publication", "finish", "neighbor_exchange", "closing", "tickets", "encode",
        "decode", "wal_write", "channel_SQL", "publish_SQL", "SQL_transaction", "port", "credit_apply", "generator",
        "save_additional", "compat_changed", "compat_port"};
    private static volatile Session active, closed;
    private static volatile String pendingStart, pendingStop;
    private static volatile boolean pendingTrace;
    private static Path control, output;
    private static final Map<String,Object> transformed = new TreeMap<>();
    private static final Map<String,Object> transformFailures = new TreeMap<>();
    private static final ThreadLocal<Frames> FRAMES = ThreadLocal.withInitial(Frames::new);
    private static final int MAX_EVENTS = 8192, MAX_OPS = 4096;
    private static boolean modScope(int site) { return site > 0 && site < NAMES.length && site != 18; }
    public static void configure(String args) throws Exception {
        if (args == null) throw new IllegalArgumentException("control;output-directory required");
        String[] parts = args.split(";", -1);
        if (parts.length != 2) throw new IllegalArgumentException("control;output-directory required");
        control = Path.of(parts[0]).toAbsolutePath().normalize(); output = Path.of(parts[1]).toAbsolutePath().normalize();
        if (!control.isAbsolute() || !output.isAbsolute() || Files.isSymbolicLink(control) || Files.isSymbolicLink(output)) throw new IllegalArgumentException("regular explicit test paths required");
        Files.createDirectories(output);
        Thread thread = new Thread(WindowStats::watch, "rc-probe-file-IO"); thread.setDaemon(true); thread.start();
    }
    public static synchronized void transformed(String name, String sha, String origin, String methods) {
        transformed.put(name, Map.of("original_class_sha256", sha, "code_source", origin, "methods", methods));
    }
    public static synchronized void transformFailed(String name, String failure) { transformFailures.put(name, failure); }
    private static synchronized void provenance(Map<String,Object> body) {
        body.put("transformed_classes",new TreeMap<>(transformed));
        body.put("transform_failures",new TreeMap<>(transformFailures));
    }
    private static void watch() {
        String last = ""; Session written = null, announced = null;
        for (;;) try {
            if (Files.isRegularFile(control, LinkOption.NOFOLLOW_LINKS) && Files.size(control) <= 4096) {
                String command = Files.readString(control, StandardCharsets.US_ASCII).trim();
                if (!command.equals(last)) {
                    String[] p = command.split(" +");
                    if (p.length >= 2 && p.length <= 3) {
                        UUID.fromString(p[1]);
                        if (p[0].equals("start") && active == null && pendingStart == null) {
                            pendingTrace = p.length == 3 && p[2].equals("item"); pendingStart = p[1];
                        } else if (p[0].equals("stop")) pendingStop = p[1];
                        else if(p[0].equals("snapshot") && p.length==3 && p[2].matches("[a-z0-9_-]{1,32}") && active!=null && active.token.equals(p[1])) {
                            var body=active.snapshot();body.put("checkpoint_name",p[2]);provenance(body);
                            Files.writeString(output.resolve(p[1]+"."+p[2]+".json"),json(body)+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
                        }
                        else throw new IllegalArgumentException("invalid probe control state");
                        last = command;
                    }
                }
            }
            Session current = active;
            if(current!=null && current!=announced){
                var start = new LinkedHashMap<String,Object>(); start.put("token",current.token);start.put("state","ACTIVE");
                start.put("wall_start_ms",current.wallStart);start.put("nano_start",current.nanoStart);provenance(start);
                Files.writeString(output.resolve(current.token+".start.json"),json(start)+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
                announced=current;
            }
            Session result = closed;
            if (result != null && result != written) {
                var body = result.snapshot();
                provenance(body);
                Path target = output.resolve(result.token + ".json");
                Files.writeString(target, json(body) + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
                written = result;
            }
            Thread.sleep(25);
        } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); return; }
          catch (Throwable failure) { System.err.println("RC_PROBE_CONTROL_FAILURE " + failure.getClass().getSimpleName()); try { Thread.sleep(100); } catch (InterruptedException end) { return; } }
    }
    public static void enter(int site) {
        if (site == 0 && active == null && pendingStart != null) {
            active = new Session(pendingStart, pendingTrace); pendingStart = null;
        }
        Session session = active;
        Frames f = FRAMES.get();
        if (f.overflow>0 || f.depth == 64) {
            f.overflow++;
            if(session!=null){session.frameOverflow();if(f.tickSession==session)f.tickInvalid=true;if(f.cycleSession==session)f.cycleInvalid=true;}
            return;
        }
        if(session==null && f.depth==0)return;
        int slot = f.depth++; f.site[slot] = site; f.time[slot] = System.nanoTime(); f.children[slot] = 0; f.session[slot] = session;
        f.rootLocation[slot]=0;
        if(site==0){
            if(session!=null && Thread.currentThread()==session.mainThread){
                if(f.cycleSession!=session){
                    f.cycleSession=session;f.cycleStart=f.time[slot];f.cycleModNanos=0;f.cycleInvalid=false;f.completedCycleReady=false;
                }else if(slot==0 && f.modDepth==0 && session.token.equals(pendingStop)){
                    // Next tick start ends the final complete start-to-start cycle.
                    // This new tick is not part of the sealed window.
                    session.close(f.time[slot],f.cycleModNanos,f.time[slot]-f.cycleStart,f.cycleInvalid);
                    f.cycleSession=null;f.completedCycleReady=false;f.depth--;f.session[slot]=null;
                    active=null;closed=session;pendingStop=null;return;
                }else{
                    f.completedCycleReady=true;f.completedCycleNanos=f.cycleModNanos;
                    f.completedCycleElapsed=f.time[slot]-f.cycleStart;f.completedCycleInvalid=f.cycleInvalid || f.modDepth!=0 || slot!=0;
                    f.cycleStart=f.time[slot];f.cycleModNanos=0;f.cycleInvalid=f.modDepth!=0 || slot!=0;
                }
            }
            if(f.serverSlot>=0){if(session!=null)session.depthMismatch();f.tickInvalid=true;}
            else{f.serverSlot=slot;f.tickSession=session;f.tickModNanos=0;
                f.tickInvalid=f.modDepth!=0 || session!=null && Thread.currentThread()!=session.mainThread;}
        }else if(modScope(site) && f.modDepth++==0 && session!=null){
            f.rootLocation[slot]=(byte)(f.serverSlot>=0 && f.tickSession==session?1:
                Thread.currentThread()==session.mainThread?2:3);
        }
    }
    public static void exit(int site) { exit(site,false); }
    public static void exceptionalExit(int site) { exit(site,true); }
    private static void exit(int site,boolean exceptional) {
        Frames f = FRAMES.get(); if (f.overflow > 0) { f.overflow--; return; }
        if (f.depth == 0) return;
        int slot = f.depth - 1;
        if (f.site[slot] != site) {
            Session s=active;if(s!=null){s.depthMismatch();if(f.tickSession==s)s.invalidTick();}
            if(f.cycleSession==s)f.cycleInvalid=true;
            f.depth=0;f.modDepth=0;f.serverSlot=-1;f.tickSession=null;f.tickModNanos=0;f.tickInvalid=false;
            Arrays.fill(f.session,null);return;
        }
        long now = System.nanoTime(), duration = Math.max(0, now - f.time[slot]);
        f.depth--; Session session = f.session[slot]; f.session[slot] = null;
        byte rootLocation=f.rootLocation[slot];f.rootLocation[slot]=0;
        if(modScope(site))f.modDepth--;
        if (f.depth > 0) f.children[f.depth - 1] += duration;
        long tickModNanos=0,cycleNanos=0,cycleElapsed=0;boolean invalidTick=false,cycleReady=false,invalidCycle=false;
        if(site==0){
            tickModNanos=f.tickModNanos;invalidTick=f.tickInvalid || f.modDepth!=0 || f.serverSlot!=slot;
            cycleReady=f.completedCycleReady;cycleNanos=f.completedCycleNanos;cycleElapsed=f.completedCycleElapsed;invalidCycle=f.completedCycleInvalid;
            f.completedCycleReady=false;
            if(f.serverSlot==slot){f.serverSlot=-1;f.tickSession=null;f.tickModNanos=0;f.tickInvalid=false;}
        }else{
            if(rootLocation==1 && f.tickSession==session)f.tickModNanos+=duration;
            if((rootLocation==1 || rootLocation==2) && f.cycleSession==session)f.cycleModNanos+=duration;
        }
        if (session == null || session != active) return;
        session.record(site, duration, Math.max(0, duration - f.children[slot]), exceptional, f.time[slot], now,
            rootLocation,tickModNanos,invalidTick,cycleReady,cycleNanos,cycleElapsed,invalidCycle);
        if (site == 0) {
            if(session.ticks>=180000)pendingStop=session.token;
        }
    }
    private static final class Frames {
        int depth, overflow, modDepth, serverSlot=-1;
        long tickModNanos; boolean tickInvalid; Session tickSession;
        long cycleStart,cycleModNanos,completedCycleNanos,completedCycleElapsed;
        boolean cycleInvalid,completedCycleReady,completedCycleInvalid;Session cycleSession;
        final int[] site = new int[64]; final long[] time = new long[64], children = new long[64];
        final byte[] rootLocation=new byte[64];
        final Session[] session = new Session[64];
    }
    static final class Histogram {
        final long[] bins = new long[2049]; long count, sum, max;
        static int index(long value) { if (value <= 0) return 0; int e = 63 - Long.numberOfLeadingZeros(value); int sub = e < 5 ? (int)((value - (1L << e)) << (5 - e)) : (int)((value >>> (e - 5)) - 32); return 1 + e * 32 + sub; }
        static long upper(int index) { if (index == 0) return 0; int e = (index - 1) / 32, sub = (index - 1) % 32; if (e < 5) return 1L << e | sub >>> (5 - e); if (e == 62 && sub == 31) return Long.MAX_VALUE; return ((33L + sub) << (e - 5)) - 1; }
        void add(long value) { value = Math.max(0, value); bins[index(value)]++; count++; sum = Math.addExact(sum, value); max = Math.max(max, value); }
        Map<String,Object> snapshot() { var result = new LinkedHashMap<String,Object>(); result.put("count",count); result.put("sum_ns",sum); result.put("max_ns",max); var sparse = new ArrayList<List<Long>>(); long seen=0; for(int i=0;i<bins.length;i++)if(bins[i]>0){sparse.add(List.of(upper(i),bins[i]));seen+=bins[i];for(int p:new int[]{50,95,99})if(!result.containsKey("p"+p+"_ns_upper")&&seen>=Math.ceil(count*p/100.0))result.put("p"+p+"_ns_upper",Math.min(max,upper(i)));} result.put("histogram_upper_ns_count",sparse);return result; }
    }
    private static final class Session {
        final String token; final boolean tracing;
        final Thread mainThread=Thread.currentThread();
        final Histogram[] inclusive=new Histogram[NAMES.length], exclusive=new Histogram[NAMES.length];
        final Histogram intervals=new Histogram(); final ArrayList<Map<String,Object>> events=new ArrayList<>();
        final Histogram modPerTick=new Histogram(), outsideTickMainRoots=new Histogram(), nonMainRoots=new Histogram();
        final Histogram modPerCycle=new Histogram(), cycleIntervals=new Histogram();
        final Map<String,String> operations=new HashMap<>(), endpoints=new HashMap<>();
        final long[] exceptionalReturns=new long[NAMES.length];
        boolean sealed;
        long ticks, firstTick, lastTick, lastEnd, droppedEvents, traceErrors, depthMismatches, frameOverflows,
            invalidTicks, invalidCycles, rootsInsideTicks, nanoStart=System.nanoTime(), wallStart=System.currentTimeMillis(), nanoEnd, wallEnd;
        Session(String token,boolean tracing){this.token=token;this.tracing=tracing;for(int i=0;i<NAMES.length;i++){inclusive[i]=new Histogram();exclusive[i]=new Histogram();}}
        synchronized void record(int site,long in,long own,boolean exceptional,long start,long end,
                                 byte rootLocation,long tickModNanos,boolean invalidTick,
                                 boolean cycleReady,long cycleNanos,long cycleElapsed,boolean invalidCycle){
            if(sealed)return;inclusive[site].add(in);exclusive[site].add(own);if(exceptional)exceptionalReturns[site]++;
            if(rootLocation==1)rootsInsideTicks++;
            else if(rootLocation==2)outsideTickMainRoots.add(in);
            else if(rootLocation==3)nonMainRoots.add(in);
            if(site==0){tick(start,end);if(invalidTick || tickModNanos<0 || tickModNanos>in)invalidTicks++;else modPerTick.add(tickModNanos);}
            if(site==0 && cycleReady)cycle(cycleNanos,cycleElapsed,invalidCycle);
        }
        private void cycle(long total,long elapsed,boolean invalid){
            if(invalid || total<0 || elapsed<0 || total>elapsed)invalidCycles++;
            else{modPerCycle.add(total);cycleIntervals.add(elapsed);}
        }
        synchronized void close(long now,long finalCycleNanos,long finalCycleElapsed,boolean invalidCycle){
            cycle(finalCycleNanos,finalCycleElapsed,invalidCycle);nanoEnd=now;wallEnd=System.currentTimeMillis();sealed=true;
        }
        synchronized void depthMismatch(){depthMismatches++;}
        synchronized void frameOverflow(){frameOverflows++;}
        synchronized void invalidTick(){invalidTicks++;}
        synchronized void traceFailure(){traceErrors++;}
        synchronized boolean known(String operation){return operations.containsKey(operation);}
        synchronized String endpoint(String operation){return endpoints.getOrDefault(operation,"");}
        synchronized void tick(long start,long end){if(ticks++==0)firstTick=start;else intervals.add(start-lastTick);lastTick=start;lastEnd=end;}
        synchronized void event(String phase,String endpoint,String operation,long amount,long revision){if(sealed)return;if(events.size()>=MAX_EVENTS){droppedEvents++;return;}events.add(Map.of("phase",phase,"endpoint",endpoint,"operation",operation,"amount",amount,"revision",revision,"nano_time",System.nanoTime()));}
        synchronized void remember(String operation,String endpoint){if(sealed)return;if(operations.containsKey(operation)||operations.size()<MAX_OPS){operations.put(operation,"item");endpoints.put(operation,endpoint);}}
        synchronized Map<String,Object> snapshot(){
            var m=new LinkedHashMap<String,Object>();m.put("schema",2);m.put("probe_revision","v2_mod_roots");m.put("token",token);
            m.put("scope","Explicit test agent. All complete tickServer calls (normal or exceptional) in this window, including Neo Pre/Post; fixed bounded histograms, not rolling samples. Named nested method spans are inclusive/exclusive, not all summed. No game objects or file IO on server-thread probe callbacks.");
            m.put("clock",Map.of("wall_start_ms",wallStart,"nano_start",nanoStart,"wall_end_ms",sealed?wallEnd:System.currentTimeMillis(),"nano_end",sealed?nanoEnd:System.nanoTime(),"mapping_limit","Same-host shared OS realtime anchors, 1ms quantization plus observed drift. Never subtract raw nanoTime from different JVMs."));
            m.put("window_closed",sealed);m.put("first_tick_start_ns",firstTick);m.put("last_tick_end_ns",lastEnd);m.put("ticks",ticks);m.put("elapsed_tick_starts_ns",Math.max(0,lastTick-firstTick));m.put("actual_tps",ticks<2?0:(ticks-1)*1e9/(lastTick-firstTick));
            m.put("histogram_precision","Upper bounds, <=3.125% width above32ns; count/sum/max exact; each window is bounded to180000 ticks.");
            var spans=new LinkedHashMap<String,Object>();for(int i=0;i<NAMES.length;i++)spans.put(NAMES[i],Map.of("inclusive",inclusive[i].snapshot(),"exclusive",exclusive[i].snapshot(),"exceptional_returns",exceptionalReturns[i]));m.put("spans",spans);m.put("tick_intervals",intervals.snapshot());
            var roots=new LinkedHashMap<String,Object>();roots.put("per_complete_tick",modPerTick.snapshot());roots.put("outside_tick_main_thread_roots",outsideTickMainRoots.snapshot());roots.put("non_main_thread_roots",nonMainRoots.snapshot());roots.put("root_calls_inside_ticks",rootsInsideTicks);roots.put("invalid_ticks",invalidTicks);
            roots.put("main_thread_id",mainThread.threadId());roots.put("main_thread_name",mainThread.getName());
            roots.put("valid",invalidTicks==0 && invalidCycles==0 && frameOverflows==0 && depthMismatches==0 && modPerTick.count==ticks
                && modPerCycle.count==(sealed?ticks:Math.max(0,ticks-1)));
            roots.put("included_sites",List.of("sites1..17", "save_additional", "compat_changed", "compat_port"));
            roots.put("scope","Per complete tickServer on that thread: union of outermost selected mod method intervals, including zero on idle ticks. Nested scopes counted once. Generator is not a mod root, but selected children are. Outside-tick main-thread and non-main-thread roots are separate per-call wall histograms, never assigned to a nearby tick. This is wall time, not CPU time or all mod work.");
            roots.put("coverage_limits","Explicit whitelist only. Includes actual TesseractBlockEntity.saveAdditional and selected compat.changed/AE insert-extract-inventory/GT energy mutation/Mek chemical-heat mutation entries. Uninstrumented GUI, other save/load hooks, other compat callbacks/getters, method prefixes/suffixes, and outside-tick work are excluded from the per-tick sum. Optional compat hooks with no actual calls remain unexercised; transformed_classes records actual loaded descriptors.");m.put("mod_roots",roots);
            roots.put("per_complete_logical_tick_cycle",modPerCycle.snapshot());roots.put("logical_tick_cycle_intervals",cycleIntervals.snapshot());roots.put("invalid_cycles",invalidCycles);
            roots.put("logical_tick_cycle_scope","Main-thread selected mod root union from one tickServer start to the next, including main-thread roots outside tickServer. Zero-work cycles count zero. A fixed live snapshot has one fewer completed cycle than completed tick frames; the current incomplete cycle is excluded. Stop seals at the next tick start, flushes the final complete cycle, and excludes that new tick frame; sealed cycles must equal tick frames. No raw cross-JVM clock subtraction and no claim of uninstrumented mod work or CPU time.");
            m.put("item_events",new ArrayList<>(events));m.put("trace_events_dropped",droppedEvents);m.put("trace_errors",traceErrors);m.put("frame_depth_mismatches",depthMismatches);m.put("frame_overflow_calls",frameOverflows);
            m.put("limits","Methods crossing window cutoffs/exceptional returns are not backend latency observations. Server/runtime samples include all completed instrumented calls; exceptional returns are separately counted. Calls crossing the cutoffs are excluded. Heap/GC/SQL asset counters are measured separately. Tracing copies identifiers/amounts only on the original calling thread.");return m;
        }
    }
    private static Object get(Object object,String method) throws ReflectiveOperationException { return object.getClass().getMethod(method).invoke(object); }
    private static String text(Object value){return value==null?"":value.toString();}
    private static boolean item(Object credit) throws ReflectiveOperationException { return "cross_tesseract:item".equals(get(get(credit,"resource"),"kind")); }
    private static Session trace(){Session s=active;return s!=null&&s.tracing?s:null;}
    public static void local(Object be,String kind,boolean sending,long amount){Session s=trace();if(s==null||!kind.equals("cross_tesseract:item"))return;try{s.event(sending?"local_input":"local_RX_consumed",text(get(be,"id")),"",amount,0);}catch(Throwable x){s.traceFailure();}}
    public static void captured(Object request){Session s=trace();if(s==null||request==null)return;try{snapshot(s,get(request,"snapshot"),"capture");}catch(Throwable x){s.traceFailure();}}
    public static void wal(Object value){Session s=trace();if(s==null)return;try{snapshot(s,value,"wal_return");}catch(Throwable x){s.traceFailure();}}
    private static void snapshot(Session s,Object value,String phase) throws Exception {String ep=text(get(value,"endpoint"));long revision=((Number)get(value,"revision")).longValue();for(String list:new String[]{"deposits","credits"})for(Object op:(List<?>)get(value,list))if(item(op)){String id=text(get(op,"transaction"));s.remember(id,ep);s.event(phase+"_"+list,ep,id,((Number)get(op,list.equals("deposits")?"amount":"remaining")).longValue(),revision);}}
    public static void reserved(Object value){Session s=trace();if(s==null)return;try{for(Object result:(List<?>)value){String ep=text(get(result,"endpoint"));for(Object id:(Set<?>)get(result,"committed"))if(s.known(text(id)))s.event("sql_deposit_confirmed",ep,text(id),0,0);for(Object credit:(List<?>)get(result,"received"))if(item(credit)){String id=text(get(credit,"transaction"));s.remember(id,ep);s.event("sql_reserved_confirmed",ep,id,((Number)get(credit,"remaining")).longValue(),0);}}}catch(Throwable x){s.traceFailure();}}
    public static void published(Object errors,Object values){Session s=trace();if(s==null)return;try{for(Object pub:(List<?>)values){Object snap=get(pub,"snapshot");Object ep=get(snap,"endpoint");if(((Map<?,?>)errors).containsKey(ep))continue;for(Object credit:(List<?>)get(pub,"received"))if(item(credit))s.event("sql_LOCAL_confirmed",text(ep),text(get(credit,"transaction")),((Number)get(credit,"remaining")).longValue(),((Number)get(snap,"revision")).longValue());}}catch(Throwable x){s.traceFailure();}}
    public static void credit(Object credit){Session s=trace();if(s==null)return;try{if(item(credit)){String id=text(get(credit,"transaction"));s.event("RX_apply",s.endpoint(id),id,((Number)get(credit,"remaining")).longValue(),0);}}catch(Throwable x){s.traceFailure();}}
    private static String quote(String s){var b=new StringBuilder("\"");for(char c:s.toCharArray()){if(c=='"'||c=='\\')b.append('\\');if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}return b.append('"').toString();}
    static String json(Object v){if(v==null)return"null";if(v instanceof String s)return quote(s);if(v instanceof Number||v instanceof Boolean)return v.toString();if(v instanceof Map<?,?> m){var j=new StringJoiner(",","{","}");for(var e:m.entrySet())j.add(quote(e.getKey().toString())+":"+json(e.getValue()));return j.toString();}if(v instanceof Iterable<?> l){var j=new StringJoiner(",","[","]");for(Object x:l)j.add(json(x));return j.toString();}throw new IllegalArgumentException("Unsupported probe JSON");}
    public static void main(String[] args) {for(long n:new long[]{0,1,2,31,32,33,1000,1_000_000,3_000_000_000L,Long.MAX_VALUE}){int i=Histogram.index(n);if(Histogram.upper(i)<n)throw new AssertionError("hist upper");}var h=new Histogram();for(int i=0;i<72000;i++)h.add(1_000_000+i);if(h.count!=72000||((Number)h.snapshot().get("count")).intValue()!=72000)throw new AssertionError("full window dropped");System.out.println("RC_PROBE_OFFLINE_SELFTEST_PASS full_window_samples=72000 no_native_execution=true");}
    private WindowStats(){}
}
