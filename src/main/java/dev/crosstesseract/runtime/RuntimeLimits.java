package dev.crosstesseract.runtime;

import dev.crosstesseract.core.*;
import java.nio.file.*;
import java.util.*;

/** Independent server work/buffer limits. Changes require restart; no existing assets are discarded. */
public record RuntimeLimits(int checks,int completions,int encodes,long tickNanos,int deposits,int loadedLimit,int ticketChanges,Set<String> blacklist,Set<String> whitelist,TransferTuning transfer){
    public record TransferTuning(boolean channelBatches,boolean localFast,int devices,int records,int bytes,int activeMillis,int idleMillis,int notificationMillis,int channelLimit,boolean diagnostics){}
    public static RuntimeLimits load(Path path) throws java.io.IOException {
        var p=new Properties();if(Files.exists(path))try(var in=Files.newInputStream(path)){p.load(in);}
        var capacities=new HashMap<String,Long>();capacities.put(Protocol.ITEM,number(p,"buffers.itemPerSlot",64,1,64));capacities.put(Protocol.FLUID,number(p,"buffers.fluidPerSlot",16000,1,1000000000));
        capacities.put(Protocol.FE,number(p,"buffers.fe",2000000,1,1000000000));capacities.put(Protocol.EU,number(p,"buffers.eu",16777216,1,Long.MAX_VALUE/128));capacities.put(Protocol.CHEMICAL,number(p,"buffers.chemicalPerSlot",64000,1,1000000000000L));LocalBuffer.configureCapacities(capacities);
        var tuning=new TransferTuning(flag(p,"transfer.channelBatches",true),flag(p,"transfer.localFastPath",true),(int)number(p,"transfer.maxBatchDevices",8,1,16),(int)number(p,"transfer.maxBatchRecords",256,192,2048),(int)number(p,"transfer.maxBatchPayloadBytes",8388608,8388608,16777216),(int)number(p,"transfer.activeWakeMillis",50,50,2000),(int)number(p,"transfer.idlePollMillis",2000,500,6000),(int)number(p,"transfer.notificationMillis",100,50,2000),(int)number(p,"limits.readyChannels",1024,32,8192),flag(p,"diagnostics.transferSampling",true));
        return new RuntimeLimits((int)number(p,"limits.endpointChecksPerTick",16,1,256),(int)number(p,"limits.completionsPerTick",64,1,256),(int)number(p,"limits.serializationsPerTick",16,1,128),number(p,"limits.localWorkBudgetMicros",2000,100,10000)*1000,(int)number(p,"transfer.maxDepositsPerBatch",8,1,32),(int)number(p,"limits.loadedEndpoints",8192,100,65536),(int)number(p,"limits.ticketChangesPerTick",2,1,16),ids(p,"filters.blacklist"),ids(p,"filters.whitelist"),tuning);
    }
    public boolean accepts(String id){return !blacklist.contains(id) && (whitelist.isEmpty() || whitelist.contains(id));}
    private static Set<String> ids(Properties p,String key){var result=new HashSet<String>();for(String id:p.getProperty(key,"").split(","))if(!id.isBlank()){DomainException.require(id.matches("[a-z0-9_.-]+:[a-z0-9_/.-]+")&&id.length()<=128,"invalid_filter");result.add(id);}DomainException.require(result.size()<=256,"invalid_filter");return Set.copyOf(result);}
    private static long number(Properties p,String key,long fallback,long min,long max){long value=Long.parseLong(p.getProperty(key,Long.toString(fallback)));DomainException.require(value>=min&&value<=max,"invalid_config");return value;}
    private static boolean flag(Properties p,String key,boolean fallback){String value=p.getProperty(key,Boolean.toString(fallback));DomainException.require(value.equals("true")||value.equals("false"),"invalid_config");return Boolean.parseBoolean(value);}
}
