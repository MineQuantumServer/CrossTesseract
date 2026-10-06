import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import jdk.jfr.EventType;
import jdk.jfr.consumer.*;

/** Standalone Java 21 offline reader. Never compiled into the mod or attached to a JVM. */
class OptimizationJfr {
    static final Set<String> SAMPLES=Set.of("jdk.ExecutionSample","jdk.NativeMethodSample");
    static final Set<String> DURATIONS=Set.of("jdk.GarbageCollection","jdk.GCPhasePause","jdk.JavaMonitorEnter","jdk.ThreadPark","jdk.ThreadSleep");
    static final Set<String> SETTINGS=Set.of("jdk.ExecutionSample","jdk.NativeMethodSample","jdk.ObjectAllocationSample","jdk.GarbageCollection","jdk.GCPhasePause","jdk.JavaMonitorEnter","jdk.ThreadPark","jdk.ThreadSleep","jdk.CPULoad","jdk.DataLoss");
    static int top,maxFrames,maxStacks,maxMethods,stackCount,methodCount;
    static long maxOutput;
    static String revision;

    static void inc(Map<String,Long> values,String key,int cap){
        if(!values.containsKey(key)&&values.size()>=cap)throw new IllegalStateException("Counter cardinality limit exceeded");
        values.merge(key,1L,Math::addExact);
    }
    static String text(Object value){return value==null?"<missing>":value.toString();}
    static String role(String name){return name.equals("Server thread")?"MAIN":name.startsWith("ct-backend-")?"BACKEND":name.startsWith("ct-control-")?"CONTROL":"OTHER";}
    static RecordedThread thread(RecordedEvent event){return event.hasField("sampledThread")?event.getThread("sampledThread"):event.getThread();}
    static String threadName(RecordedEvent event){var thread=thread(event);return thread==null?"<missing>":text(thread.getJavaName());}
    static List<Map<String,Object>> frames(RecordedEvent event){
        var trace=event.getStackTrace();var result=new ArrayList<Map<String,Object>>();if(trace==null)return result;
        for(var frame:trace.getFrames()){
            if(result.size()>=maxFrames)break;
            var method=frame.getMethod();if(method==null)continue;
            String owner=text(method.getType().getName()),name=text(method.getName()),descriptor=text(method.getDescriptor());
            if(owner.length()>512||name.length()>256||descriptor.length()>512)throw new IllegalStateException("Frame identity string exceeds limit");
            var row=new LinkedHashMap<String,Object>();row.put("class",owner);row.put("method",name);row.put("descriptor",descriptor);
            row.put("line",frame.getLineNumber());row.put("bytecode_index",frame.getBytecodeIndex());row.put("frame_type",frame.getType());
            if(owner.startsWith("dev.crosstesseract.")){
                row.put("source_revision",revision);row.put("source_path","src/main/java/"+owner.split("\\$",2)[0].replace('.','/')+".java");
            }
            result.add(row);
        }
        return result;
    }
    static String method(Map<String,Object> frame){return frame.get("class")+"."+frame.get("method")+frame.get("descriptor");}
    static boolean runtime(List<Map<String,Object>> frames){return frames.stream().anyMatch(f->"dev.crosstesseract.runtime.RuntimeService".equals(f.get("class"))&&"tick".equals(f.get("method")));}
    static List<Map<String,Object>> sortedCounts(Map<String,Long> counts,int limit){
        return counts.entrySet().stream().sorted(Map.Entry.<String,Long>comparingByValue().reversed().thenComparing(Map.Entry.comparingByKey()))
            .limit(limit).map(e->{var row=new LinkedHashMap<String,Object>();row.put("identity",e.getKey());row.put("count",e.getValue());return (Map<String,Object>)row;}).toList();
    }
    static class Sampling {
        long samples,missingStacks,truncatedStacks,runtimeSamples;
        final Map<String,Long> leaves=new HashMap<>(),inclusive=new HashMap<>(),runtimeLeaves=new HashMap<>();
        final Map<String,Long> states=new TreeMap<>();
        final Map<String,Long> stacks=new HashMap<>();final Map<String,List<Map<String,Object>>> traces=new HashMap<>();
        final Map<String,String> firstStackUtc=new HashMap<>();
        final Map<String,Map<String,Object>> locations=new HashMap<>();
        void methodCount(Map<String,Long> target,String key,Map<String,Object> frame){
            if(!target.containsKey(key)&&++methodCount>maxMethods)throw new IllegalStateException("Method histogram limit exceeded");
            target.merge(key,1L,Math::addExact);locations.putIfAbsent(key,frame);
        }
        void sample(RecordedEvent event,List<Map<String,Object>> frames){
            samples++;inc(states,event.hasField("state")?text(event.getValue("state")):"<not recorded>",64);if(frames.isEmpty()){missingStacks++;return;}
            if(event.getStackTrace().isTruncated()||event.getStackTrace().getFrames().size()>maxFrames)truncatedStacks++;
            methodCount(leaves,method(frames.getFirst()),frames.getFirst());var seen=new HashSet<String>();
            for(var frame:frames)if(seen.add(method(frame)))methodCount(inclusive,method(frame),frame);
            boolean hasRuntime=runtime(frames);if(hasRuntime){runtimeSamples++;methodCount(runtimeLeaves,method(frames.getFirst()),frames.getFirst());}
            String key=frames.toString();if(!stacks.containsKey(key)){if(++stackCount>maxStacks)throw new IllegalStateException("Unique stack limit exceeded");traces.put(key,frames);firstStackUtc.put(key,event.getStartTime().toString());}
            stacks.merge(key,1L,Math::addExact);
        }
        List<Map<String,Object>> methods(Map<String,Long> counts){
            var result=sortedCounts(counts,top);for(var row:result){row.put("recorded_frame",locations.get(row.get("identity")));row.put("fraction_of_role_samples",(double)(long)row.get("count")/samples);}return result;
        }
        Map<String,Object> output(){
            var result=new LinkedHashMap<String,Object>();result.put("samples",samples);result.put("sampled_states",states);result.put("missing_stack_samples",missingStacks);result.put("truncated_stack_samples",truncatedStacks);result.put("runtime_tick_inclusive_samples",runtimeSamples);
            result.put("top_leaf_methods",methods(leaves));result.put("top_inclusive_methods",methods(inclusive));result.put("top_leaf_methods_when_runtime_tick_in_stack",methods(runtimeLeaves));
            result.put("top_stacks",stackRows(false));result.put("top_runtime_tick_stacks",stackRows(true));result.put("unique_stacks",stacks.size());return result;
        }
        List<Map<String,Object>> stackRows(boolean runtimeOnly){
            var rows=new ArrayList<Map<String,Object>>();for(var entry:stacks.entrySet().stream().filter(e->!runtimeOnly||runtime(traces.get(e.getKey()))).sorted(Map.Entry.<String,Long>comparingByValue().reversed().thenComparing(Map.Entry.comparingByKey())).limit(top).toList()){
                var row=new LinkedHashMap<String,Object>();row.put("samples",entry.getValue());row.put("fraction_of_role_samples",(double)entry.getValue()/samples);row.put("first_sample_utc",firstStackUtc.get(entry.getKey()));row.put("frames_leaf_to_root",traces.get(entry.getKey()));rows.add(row);
            }
            return rows;
        }
    }
    static class Timing {
        final List<Long> nanos=new ArrayList<>();final List<Map<String,Object>> events=new ArrayList<>();
        long total;double pauseSumMs,longestPauseMs;boolean pauseSumRecorded,longestPauseRecorded;
        void add(RecordedEvent event){
            if(nanos.size()>=8192)throw new IllegalStateException("Duration event count exceeds limit");
            long value=event.getDuration().toNanos();nanos.add(value);total=Math.addExact(total,value);
            if(event.hasField("sumOfPauses")){pauseSumRecorded=true;pauseSumMs+=event.getDuration("sumOfPauses").toNanos()/1e6;}
            if(event.hasField("longestPause")){longestPauseRecorded=true;longestPauseMs=Math.max(longestPauseMs,event.getDuration("longestPause").toNanos()/1e6);}
            if(events.size()<128){var row=new LinkedHashMap<String,Object>();row.put("start_utc",event.getStartTime().toString());row.put("end_utc",event.getEndTime().toString());row.put("duration_ms",value/1e6);
                for(String field:List.of("gcId","name","cause"))if(event.hasField(field))row.put(field,event.getValue(field));events.add(row);}
        }
        Map<String,Object> output(){
            var sorted=nanos.stream().sorted().toList();var result=new LinkedHashMap<String,Object>();result.put("recorded_events",sorted.size());result.put("duration_sum_ms",total/1e6);
            result.put("duration_sum_scope","Sum within this one event type and role only; concurrent waits may overlap; never sum nested GC event types.");
            result.put("max_ms",sorted.isEmpty()?null:sorted.getLast()/1e6);for(int p:new int[]{50,95,99})result.put("p"+p+"_ms",sorted.isEmpty()?null:sorted.get(Math.max(0,(int)Math.ceil(sorted.size()*p/100.0)-1))/1e6);
            result.put("gc_recorded_sum_of_pauses_ms",pauseSumRecorded?pauseSumMs:null);result.put("gc_recorded_longest_pause_ms",longestPauseRecorded?longestPauseMs:null);result.put("first_recorded_events",events);result.put("raw_event_list_capped",sorted.size()>events.size());return result;
        }
    }
    static class Window {
        final String name;final Instant start,end;final double seconds;
        final Map<String,Long> eventCounts=new TreeMap<>(),threadCounts=new TreeMap<>(),crossing=new TreeMap<>();
        final Map<String,Sampling> sampling=new TreeMap<>();final Map<String,Timing> timing=new TreeMap<>();
        final Map<String,Long> allocationClasses=new HashMap<>(),allocationWeights=new HashMap<>();
        long allocationSamples,allocationWeight,mainRuntimeAllocationSamples,mainRuntimeAllocationWeight;
        final List<Map<String,Object>> dataLoss=new ArrayList<>();
        final Map<String,List<Double>> cpuLoad=new TreeMap<>();
        Window(String name,Instant start,Instant end){this.name=name;this.start=start;this.end=end;this.seconds=Duration.between(start,end).toNanos()/1e9;if(seconds<=0||seconds>600)throw new IllegalArgumentException("Invalid window length");}
        void event(RecordedEvent event,String type){
            boolean inside=!event.getStartTime().isBefore(start)&&event.getStartTime().isBefore(end);
            boolean overlap=event.getStartTime().isBefore(end)&&event.getEndTime().isAfter(start);
            if(DURATIONS.contains(type)&&overlap&&(!inside||event.getEndTime().isAfter(end))){inc(crossing,type,64);return;}
            if(!inside)return;inc(eventCounts,type,1024);
            if(SAMPLES.contains(type)){
                String thread=threadName(event),role=role(thread);inc(threadCounts,type+":"+thread,512);
                sampling.computeIfAbsent(type+":"+role,key->new Sampling()).sample(event,frames(event));
            }else if(DURATIONS.contains(type)){
                String role=type.startsWith("jdk.GC")||type.equals("jdk.GarbageCollection")?"GLOBAL":role(threadName(event));
                timing.computeIfAbsent(type+":"+role,key->new Timing()).add(event);
            }else if(type.equals("jdk.ObjectAllocationSample")){
                String role=role(threadName(event));Object klass=event.getValue("objectClass");String className=klass instanceof RecordedClass value?value.getName():"<missing>";
                if(!event.hasField("weight"))throw new IllegalStateException("ObjectAllocationSample weight field missing");
                String key=role+":"+className;long weight=event.getLong("weight");
                if(weight<0)throw new IllegalStateException("Negative allocation weight");inc(allocationClasses,key,2048);allocationWeights.merge(key,weight,Math::addExact);
                allocationSamples++;allocationWeight=Math.addExact(allocationWeight,weight);
                if(role.equals("MAIN")&&runtime(frames(event))){mainRuntimeAllocationSamples++;mainRuntimeAllocationWeight=Math.addExact(mainRuntimeAllocationWeight,weight);}
            }else if(type.equals("jdk.DataLoss")){
                if(dataLoss.size()>=128)throw new IllegalStateException("DataLoss event count exceeds limit");
                var row=new LinkedHashMap<String,Object>();row.put("start_utc",event.getStartTime().toString());for(String key:List.of("amount","total"))if(event.hasField(key))row.put(key,event.getValue(key));dataLoss.add(row);
            }else if(type.equals("jdk.CPULoad")){
                for(String key:List.of("jvmUser","jvmSystem","machineTotal"))if(event.hasField(key)){
                    var values=cpuLoad.computeIfAbsent(key,ignored->new ArrayList<>());if(values.size()>=8192)throw new IllegalStateException("CPU load sample count exceeds limit");values.add(((Number)event.getValue(key)).doubleValue());
                }
            }
        }
        Map<String,Object> output(){
            var result=new LinkedHashMap<String,Object>();result.put("name",name);result.put("start_utc",start.toString());result.put("end_utc",end.toString());result.put("seconds",seconds);
            result.put("started_event_counts",eventCounts);result.put("sampled_thread_counts",threadCounts);result.put("excluded_cross_boundary_duration_events",crossing);
            var sampleResult=new TreeMap<String,Object>();sampling.forEach((key,value)->sampleResult.put(key,value.output()));result.put("sampling",sampleResult);
            var timingResult=new TreeMap<String,Object>();timing.forEach((key,value)->timingResult.put(key,value.output()));result.put("duration_events",timingResult);
            var cpu=new TreeMap<String,Object>();cpuLoad.forEach((key,values)->{var row=new LinkedHashMap<String,Object>();row.put("recorded_samples",values.size());row.put("mean",values.stream().mapToDouble(Double::doubleValue).average().orElseThrow());row.put("min",values.stream().mapToDouble(Double::doubleValue).min().orElseThrow());row.put("max",values.stream().mapToDouble(Double::doubleValue).max().orElseThrow());cpu.put(key,row);});result.put("periodic_cpu_load_fractions",cpu);
            var allocation=new LinkedHashMap<String,Object>();allocation.put("sample_events",allocationSamples);allocation.put("estimated_weight_bytes",allocationWeight);
            allocation.put("main_runtime_sample_events",mainRuntimeAllocationSamples);allocation.put("main_runtime_estimated_weight_bytes",mainRuntimeAllocationWeight);
            var rows=sortedCounts(allocationClasses,top);for(var row:rows)row.put("estimated_weight_bytes",allocationWeights.get(row.get("identity")));allocation.put("top_classes_by_sample_count",rows);allocation.put("weight_scope","JFR ObjectAllocationSample statistical weights; not exact allocation counts/bytes or retained heap.");result.put("allocation_sampling",allocation);result.put("data_loss_events",dataLoss);return result;
        }
    }
    static void json(StringBuilder out,Object value){
        if(out.length()>maxOutput)throw new IllegalStateException("JSON character limit exceeded");
        if(value==null){out.append("null");return;}
        if(value instanceof String text){out.append('"');for(char c:text.toCharArray())switch(c){case '"'->out.append("\\\"");case '\\'->out.append("\\\\");case '\n'->out.append("\\n");case '\r'->out.append("\\r");case '\t'->out.append("\\t");default->{if(c<32)out.append(String.format("\\u%04x",(int)c));else out.append(c);}}out.append('"');return;}
        if(value instanceof Number number){if(number instanceof Double d&&!Double.isFinite(d)||number instanceof Float f&&!Float.isFinite(f))throw new IllegalStateException("Nonfinite JSON number");out.append(number);return;}
        if(value instanceof Boolean){out.append(value);return;}
        if(value instanceof Map<?,?> map){out.append('{');boolean first=true;for(var entry:map.entrySet()){if(!first)out.append(',');first=false;json(out,text(entry.getKey()));out.append(':');json(out,entry.getValue());}out.append('}');return;}
        if(value instanceof Collection<?> list){out.append('[');boolean first=true;for(var element:list){if(!first)out.append(',');first=false;json(out,element);}out.append(']');return;}
        throw new IllegalStateException("Unsupported JSON value: "+value.getClass());
    }
    static void run(String[] args)throws Exception{
        if(args.length<16||(args.length-10)%3!=0)throw new IllegalArgumentException("Expected file, output, limits, revision and name/start/end windows");
        var input=Path.of(args[0]);var output=Path.of(args[1]);long maxBytes=Long.parseLong(args[2]),maxEvents=Long.parseLong(args[3]);top=Integer.parseInt(args[4]);maxFrames=Integer.parseInt(args[5]);maxStacks=Integer.parseInt(args[6]);maxMethods=Integer.parseInt(args[7]);maxOutput=Long.parseLong(args[8]);revision=args[9];
        if(!Files.isRegularFile(input)||Files.size(input)>maxBytes||maxBytes<=0||maxBytes>256L*1024*1024||maxEvents<=0||maxEvents>20000000||top<1||top>100||maxFrames<1||maxFrames>96||maxStacks<1||maxStacks>4096||maxMethods<1||maxMethods>32768||maxOutput<1||maxOutput>32L*1024*1024)throw new IllegalArgumentException("Input/limits rejected");
        var windows=new ArrayList<Window>();for(int i=10;i<args.length;i+=3)windows.add(new Window(args[i],Instant.parse(args[i+1]),Instant.parse(args[i+2])));if(windows.size()>4)throw new IllegalArgumentException("Too many windows");
        var allCounts=new TreeMap<String,Long>();var jvm=new ArrayList<Map<String,Object>>();var settings=new TreeMap<String,Object>();var availableTypes=new TreeSet<String>();var idNames=new HashMap<Long,String>();
        Instant first=null,last=null;long scanned=0;
        try(var recording=new RecordingFile(input)){
            for(EventType type:recording.readEventTypes()){if(SETTINGS.contains(type.getName())){availableTypes.add(type.getName());idNames.put(type.getId(),type.getName());}}
            while(recording.hasMoreEvents()){
                if(++scanned>maxEvents)throw new IllegalStateException("Scanned event limit exceeded");var event=recording.readEvent();String type=event.getEventType().getName();inc(allCounts,type,1024);
                if(first==null||event.getStartTime().isBefore(first))first=event.getStartTime();if(last==null||event.getEndTime().isAfter(last))last=event.getEndTime();
                if(type.equals("jdk.JVMInformation")&&jvm.size()<8){var row=new LinkedHashMap<String,Object>();row.put("event_utc",event.getStartTime().toString());for(String key:List.of("pid","jvmName","jvmVersion","jvmStartTime"))if(event.hasField(key))row.put(key,event.getValue(key));for(String key:List.of("jvmArguments","jvmFlags","javaArguments"))if(event.hasField(key))row.put(key+"_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text(event.getValue(key)).getBytes(StandardCharsets.UTF_8))));jvm.add(row);}
                if(type.equals("jdk.ActiveSetting")){String eventName=idNames.get(event.getLong("id"));if(eventName!=null){String key=eventName+":"+event.getString("name");String value=event.getString("value");var values=(Set<String>)settings.computeIfAbsent(key,ignored->new TreeSet<String>());if(values.size()>=16&&!values.contains(value))throw new IllegalStateException("Too many setting transitions");values.add(value);}}
                for(var window:windows)window.event(event,type);
            }
        }
        if(first==null||last==null)throw new IllegalStateException("Recording has no timestamped events");for(var window:windows)if(first.isAfter(window.start)||last.isBefore(window.end))throw new IllegalStateException("JFR event range does not bracket selected window");
        var result=new LinkedHashMap<String,Object>();result.put("reader","Java21 jdk.jfr.consumer.RecordingFile streamed read");result.put("java_runtime_version",System.getProperty("java.runtime.version"));result.put("source_revision",revision);result.put("scanned_events",scanned);result.put("all_recording_event_counts",allCounts);result.put("event_range_first_utc",first.toString());result.put("event_range_last_utc",last.toString());
        result.put("jvm_information",jvm);result.put("relevant_metadata_event_types",availableTypes);result.put("observed_active_settings",settings);result.put("metadata_scope","Event type metadata alone does not prove a type was enabled. ActiveSetting values are observed across the whole recording, not an inferred window-local configuration.");
        result.put("windows",windows.stream().map(Window::output).toList());var encoded=new StringBuilder();json(encoded,result);byte[] bytes=encoded.toString().getBytes(StandardCharsets.UTF_8);if(bytes.length>maxOutput)throw new IllegalStateException("UTF-8 output size exceeds limit");Files.write(output,bytes,StandardOpenOption.CREATE_NEW);
    }
    public static void main(String[] args){try{run(args);}catch(Exception error){String message=text(error.getMessage());System.err.println("OFFLINE_JFR_READER_FAILED: "+error.getClass().getName()+": "+message.substring(0,Math.min(message.length(),2048)));System.exit(2);}}
}
