package dev.crosstesseract.runtime;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.backend.*;
import dev.crosstesseract.block.*;
import dev.crosstesseract.compat.CompatLoader;
import dev.crosstesseract.core.*;
import dev.crosstesseract.core.Models.*;
import dev.crosstesseract.core.LocalSnapshot.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.storage.LevelResource;

/** A single server-owned runtime. The server thread never waits for IO or a future. */
public final class RuntimeService {
    @FunctionalInterface public interface Work<T>{T run(Authority backend) throws Exception;}
    private static final Map<MinecraftServer,RuntimeService> INSTANCES=Collections.synchronizedMap(new WeakHashMap<>());
    private final MinecraftServer server;
    private final BackendConfig config;
    private final RuntimeLimits limits;
    private final ThreadPoolExecutor workers,control,maintenance,notifications;
    private final ScheduledExecutorService scheduler;
    private final CompletionMailbox completions;
    private final AtomicReference<Runnable> maintenanceCompletion=new AtomicReference<>();
    private final AtomicBoolean maintenanceInFlight=new AtomicBoolean(),notificationsInFlight=new AtomicBoolean();
    private final ChannelCoordinator coordinator;
    private final LinkedHashSet<UUID> localReady=new LinkedHashSet<>(),dirtyChannels=new LinkedHashSet<>();
    private final Map<UUID,LinkedHashSet<UUID>> channelEndpoints=new HashMap<>();
    private final Map<UUID,UUID> indexedChannels=new HashMap<>();
    private record Scheduled(UUID endpoint,long due){}
    private final TreeSet<Scheduled> dueWork=new TreeSet<>(Comparator.comparingLong(Scheduled::due).thenComparing(Scheduled::endpoint));
    private final Map<UUID,Scheduled> dueByEndpoint=new HashMap<>();
    private final Map<UUID,Prepared> transfers=new HashMap<>();
    private final Map<UUID,Long> ioVersions=new HashMap<>();
    private final AtomicBoolean outboxDirty=new AtomicBoolean();
    private final ArrayBlockingQueue<RedisTransport.Hint> hints=new ArrayBlockingQueue<>(256);
    private long nextOutboxPoll;
    private final Map<UUID,Closing> closing=new HashMap<>();
    private final ArrayDeque<UUID> closingRotation=new ArrayDeque<>();
    private final LinkedHashMap<UUID,Long> locallyClosed=new LinkedHashMap<>();
    private final Map<UUID,Long> nextHeat=new HashMap<>();
    private final Set<UUID> heatInFlight=new HashSet<>();
    private static final class Closing{final TesseractBlockEntity be;String sealReason,quarantineReason;boolean writing;long retry;Closing(TesseractBlockEntity be,String reason){this.be=be;this.sealReason=reason;}}
    private static final class Prepared{final TesseractBlockEntity be;final TransferWork.Request request;final long started,ioVersion;Prepared(TesseractBlockEntity be,TransferWork.Request request,long started,long ioVersion){this.be=be;this.request=request;this.started=started;this.ioVersion=ioVersion;}}
    private final ConcurrentHashMap<UUID,TesseractBlockEntity> loaded=new ConcurrentHashMap<>();
    private final ArrayDeque<UUID> rotation=new ArrayDeque<>();
    private final Map<UUID,Long> nextPoll=new HashMap<>();
    private final Map<UUID,Integer> idle=new HashMap<>();
    private final AtomicBoolean controlInFlight=new AtomicBoolean();
    private volatile Authority backend;
    private volatile RedisTransport redis;
    private volatile LocalJournal journal;
    private volatile long onlineUntil;
    private volatile String status="connecting";
    private volatile boolean stopping;
    private UUID world;
    private final UUID boot=BusinessIds.next();
    private volatile boolean joined;
    private volatile boolean journalFailed;
    private boolean cleanPrepared;
    private ExecutorService shutdownIo;
    private int codecBudget=16,tickCounter;
    private final Metrics metrics=new Metrics();
    private final ChunkTickets tickets;
    private final Set<UUID> ticketConfirming=new HashSet<>();
    private volatile List<Grant> currentGrants=List.of();
    private volatile Map<UUID,Grant> grantByEndpoint=Map.of();
    private final LinkedHashMap<UUID,Grant> ticketWork=new LinkedHashMap<>();
    private volatile int effectiveQuota;
    private long lastLog;
    private volatile long lastInternalTrace;
    private long nextHistorySweep;
    private RuntimeService(MinecraftServer server,BackendConfig config,RuntimeLimits limits) {
        this.server=server;this.config=config;this.limits=limits;effectiveQuota=config.quota();tickets=new ChunkTickets(server);
        workers=pool("ct-backend",Math.max(1,config.poolSize()-1),config.queueSize());control=pool("ct-control",1,16);
        maintenance=pool("ct-maintenance",1,4);notifications=pool("ct-notifications",1,4);
        scheduler=Executors.newSingleThreadScheduledExecutor(threadFactory("ct-scheduler"));completions=new CompletionMailbox(config.queueSize()*2);coordinator=new ChannelCoordinator(limits.transfer().channelLimit(),limits.loadedLimit());
        if(!config.enabled()){status="backend_disabled";return;}
        control.execute(()->{
            try{
                Path directory=server.getWorldPath(LevelResource.ROOT).resolve("cross_tesseract");Files.createDirectories(directory);
                Path identity=directory.resolve("world-id");
                if(Files.exists(identity))world=UUID.fromString(Files.readString(identity,StandardCharsets.UTF_8).trim());else {world=BusinessIds.next();Files.writeString(identity,world.toString(),StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);}
                journal=new LocalJournal(directory.resolve("journal"));backend=new Authority(config);redis=new RedisTransport(config);
                redis.healthy();backend.join(world,boot,CompatLoader.capabilities());joined=true;
                maintain();
            }catch(Exception | LinkageError e){fail(e);}
        });
        scheduler.scheduleWithFixedDelay(()->{
            if(stopping || backend==null || controlInFlight.getAndSet(true))return;
            try{control.execute(()->{try{maintain();}catch(Exception e){fail(e);}finally{controlInFlight.set(false);}});}catch(RejectedExecutionException e){controlInFlight.set(false);status="backend_busy";metrics.rejected.increment();}
        },2,2,TimeUnit.SECONDS);
        scheduler.scheduleWithFixedDelay(()->{
            if(stopping || !online() || notificationsInFlight.getAndSet(true))return;
            try{notifications.execute(()->{try{notifyAndSweep();}catch(Exception e){fail(e);}finally{notificationsInFlight.set(false);}});}catch(RejectedExecutionException e){notificationsInFlight.set(false);metrics.rejected.increment();}
        },limits.transfer().notificationMillis(),limits.transfer().notificationMillis(),TimeUnit.MILLISECONDS);
    }
    private void maintain() throws Exception {
        if(backend==null)return;
        if(!joined){redis.healthy();backend.join(world,boot,CompatLoader.capabilities());joined=true;}
        redis.healthy();redis.online(config.server(),backend.session().boot(),backend.session().epoch());var state=backend.maintainState();
        onlineUntil=System.nanoTime()+TimeUnit.SECONDS.toNanos(8);status="online";
        var grants=state.grants();currentGrants=grants;grantByEndpoint=grants.stream().collect(java.util.stream.Collectors.toUnmodifiableMap(Grant::endpoint,Function.identity()));effectiveQuota=state.quota();
        if(!maintenanceInFlight.getAndSet(true))try{maintenance.execute(()->{try{
            long observedAt=System.nanoTime();List<UUID> ids=loaded.keySet().stream().sorted().toList();var permissions=new ArrayList<PermissionSnapshot>();
            for(int start=0;start<ids.size();start+=256)permissions.addAll(backend.refreshPermissions(ids.subList(start,Math.min(ids.size(),start+256))));
            post(()->{for(var permission:permissions){var be=loaded.get(permission.endpoint());if(be!=null){be.authorize(permission,Math.min(onlineUntil,observedAt+TimeUnit.SECONDS.toNanos(3)),observedAt);index(be);}}reconcileTickets(currentGrants);});
        }catch(Exception e){fail(e);}finally{maintenanceInFlight.set(false);}});}catch(RejectedExecutionException e){maintenanceInFlight.set(false);metrics.rejected.increment();}
    }
    private void notifyAndSweep() throws Exception {
        long now=System.nanoTime();if(outboxDirty.getAndSet(false)||now>=nextOutboxPoll){nextOutboxPoll=now+TimeUnit.SECONDS.toNanos(2);redis.dispatch(backend,128);}
        for(var hint:redis.drainHints(backend,config.server()).hints())if(!hints.offer(hint))metrics.hintDrops.increment(); // lossy, bounded wake hints; never assets
        if(now>=nextHistorySweep){nextHistorySweep=now+TimeUnit.MINUTES.toNanos(1);backend.sweepHistory();}
    }
    public static void start(MinecraftServer server){
        try{
            Path config=Path.of(System.getProperty("cross_tesseract.config","config/cross-tesseract.properties"));
            INSTANCES.put(server,new RuntimeService(server,BackendConfig.load(config),RuntimeLimits.load(config)));
        }catch(Exception e){CrossTesseract.LOG.error("CrossServer Tesseract configuration rejected: {}",errorCode(e));}
    }
    public static RuntimeService get(MinecraftServer server){return INSTANCES.get(server);}
    public RuntimeLimits limits(){return limits;}
    public MinecraftServer server(){return server;}
    public boolean online(){return !stopping && System.nanoTime()<onlineUntil && backend!=null;}
    public String status(){return online()?"online":status;}
    public String clusterId(){return config.cluster();}
    public String serverId(){return config.server();}
    public UUID worldId(){return world;}
    public Metrics metrics(){return metrics;}
    public int quotaLimit(){return effectiveQuota;}
    public int ticketCount(){return tickets.count();}
    public Map<String,Number> metricSnapshot(){var result=new LinkedHashMap<>(metrics.snapshot(loaded.size(),(int)loaded.values().stream().filter(be->be.registered()&&be.channel()!=null&&be.pauseReason().isEmpty()&&CompatLoader.resources().stream().anyMatch(kind->be.mode(kind)!=Protocol.Mode.OFF)).count(),workers.getQueue().size(),tickets.count()));if(backend!=null)result.putAll(backend.database().stats());if(journal!=null)result.putAll(journal.stats());result.put("completion_admitted",completions.count());result.put("ready_channels",coordinator.channelCount());result.put("ready_devices",coordinator.endpointCount());result.put("closing_devices",closing.size());result.put("mc_recorded_tick_ms_avg100",server.getAverageTickTimeNanos()/1_000_000.0);result.put("mc_target_ticks_per_second",server.tickRateManager().tickrate());return Collections.unmodifiableMap(result);}
    private static ThreadFactory threadFactory(String name){var counter=new AtomicInteger();return task->{var t=new Thread(task,name+"-"+counter.incrementAndGet());t.setDaemon(true);return t;};}
    private static ThreadPoolExecutor pool(String name,int threads,int capacity){return new ThreadPoolExecutor(threads,threads,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(capacity),threadFactory(name),new ThreadPoolExecutor.AbortPolicy());}
    private void post(Runnable action){maintenanceCompletion.set(action);}
    public boolean codecBudget(){if(codecBudget<=0)return false;codecBudget--;return true;}
    public <T> void submit(Work<T> task,Consumer<T> success,Consumer<String> failure){
        if(!online()){failure.accept(status());return;}
        var reservation=completions.tryReserve();if(reservation==null){metrics.rejected.increment();failure.accept("completion_queue_full");return;}
        long queued=System.nanoTime();
        try{workers.execute(()->{long start=System.nanoTime();if(limits.transfer().diagnostics())metrics.sample(Metrics.Timer.QUEUE,start-queued);try{T result=task.run(backend);metrics.transactions.increment();long ready=System.nanoTime();reservation.complete(()->{if(limits.transfer().diagnostics())metrics.sample(Metrics.Timer.APPLY,System.nanoTime()-ready);success.accept(result);});}catch(Exception | LinkageError e){metrics.errors.increment();String code=errorCode(e);if(Boolean.getBoolean("cross_tesseract.testHarness") && (e instanceof ClassCastException || e instanceof NullPointerException || e instanceof UnsupportedOperationException) && System.nanoTime()-lastInternalTrace>TimeUnit.SECONDS.toNanos(10)){lastInternalTrace=System.nanoTime();CrossTesseract.LOG.warn("CT_DEV_INTERNAL_FAILURE",e);}reservation.complete(()->failure.accept(code));}finally{metrics.sql(System.nanoTime()-start);if(limits.transfer().diagnostics())metrics.sample(Metrics.Timer.EXECUTION,System.nanoTime()-start);}});}catch(RejectedExecutionException e){metrics.rejected.increment();reservation.complete(()->failure.accept("backend_busy"));}
    }
    public void register(TesseractBlockEntity be){
        if(!loaded.containsKey(be.id()) && loaded.size()+closing.size()>=limits.loadedLimit()){be.pause("endpoint_load_limit");return;}
        TesseractBlockEntity old=loaded.putIfAbsent(be.id(),be);
        if(old!=null && old!=be && !old.isRemoved()){be.pause("cloned_endpoint");return;}
        if(old!=be){loaded.put(be.id(),be);rotation.remove(be.id());rotation.addLast(be.id());}
        if(closing.containsKey(be.id())){be.pause("endpoint_closing");return;}
        if(!online() || be.registering() || be.registered() || be.registrationRecoveryRequired())return;
        be.registering(true);
        UUID id=be.id();var pos=be.getBlockPos();
        Endpoint requested=new Endpoint(id,config.server(),world,be.owner(),null,be.getLevel().dimension().location().toString(),pos.getX(),pos.getY(),pos.getZ(),be.endpointVersion(),"ACTIVE",be.savedCheckpoint(),"");
        long trustedCheckpoint=Math.max(requested.checkpoint(),locallyClosed.getOrDefault(id,0L));
        submit(a->{var result=a.registerEndpoint(requested,trustedCheckpoint);
            try{var local=journal.read(id);DomainException.require(local.isPresent() || result.checkpoint()==0,"journal_missing");
                if(local.isPresent()){var s=local.orElseThrow();DomainException.require(s.world().equals(world) && s.generation()==a.session().generation() && s.revision()>=Math.max(trustedCheckpoint,result.checkpoint()),"journal_generation_conflict");local=Optional.of(a.restoreSnapshot(s));}return Map.entry(result,local);
            }catch(java.io.IOException | DomainException e){a.quarantineEndpoint(id,errorCode(e));throw e;}
        },result->{
            if(!be.id().equals(id) || !tracked(be))return;
            be.applyEndpoint(result.getKey());result.getValue().ifPresent(s->{try{be.buffer().restore(s);be.thermal().restore(s.thermal());}catch(DomainException e){be.quarantineLocal(e.code());submit(a->{a.quarantineEndpoint(id,e.code());return true;},x->{},x->{});}});
            if(same(be,id)){for(var m:CompatLoader.modules())m.attach(be);index(be);schedule(id,System.nanoTime());}
            if(be.chunkDesired() && !grantByEndpoint.containsKey(id))be.chunkDesired(false);
            Grant ownGrant=grantByEndpoint.get(id);if(ownGrant!=null)ticketWork.put(id,ownGrant);
            var close=closing.get(id);if(close!=null)flushClosing(close);
        },code->{if(be.id().equals(id) && tracked(be)){be.registering(false);if(Set.of("journal_missing","journal_generation_conflict","checkpoint_version_conflict","world_id_mismatch","cloned_endpoint","backup_generation_conflict","invalid_checkpoint","allocation_not_found","payload_corrupt","registry_missing","resource_unsupported","location_sealed").contains(code)){be.quarantineLocal(code);metrics.quarantined.increment();}else be.pause(code);var close=closing.get(id);if(close!=null)flushClosing(close);}});
    }
    private boolean same(TesseractBlockEntity be,UUID id){return !be.isRemoved() && be.id().equals(id) && loaded.get(id)==be;}
    public void requestStock(TesseractBlockEntity be,UUID actor,UUID request,Resource payload,long amount,boolean coalesce,Consumer<StockRequest> success,Consumer<String> failure){
        DomainException.require(server.isSameThread() && actor.equals(be.owner()) && !be.isRemoved(),"device_owner_required");
        DomainException.require(Set.of(Protocol.ITEM,Protocol.FLUID).contains(payload.kind()),"resource_unsupported");
        DomainException.require(be.allowed(payload.kind(),null,false),"forbidden");be.validate(payload);
        String registry=payload.kind().equals(Protocol.ITEM)?net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(be.decodeItem(payload,1).getItem()).toString():net.minecraft.core.registries.BuiltInRegistries.FLUID.getKey(be.decodeFluid(payload,1).getFluid()).toString();DomainException.require(be.acceptsId(registry),"resource_restricted");
        UUID id=be.id(),channel=be.channel();long expected=be.endpointVersion();
        submit(a->a.requestStock(actor,request,id,channel,expected,payload,amount,coalesce),result->{if(same(be,id) && channel.equals(be.channel())){schedule(id,0L);success.accept(result);}else failure.accept("binding_changed");},failure);
    }
    public void bindEndpoint(TesseractBlockEntity be,UUID actor,long expected,UUID channel,Consumer<Endpoint> success,Consumer<String> failure){
        DomainException.require(server.isSameThread() && actor.equals(be.owner()) && !be.isRemoved(),"device_owner_required");
        be.beginBinding(expected);UUID id=be.id();
        submit(a->a.bind(actor,id,expected,channel),endpoint->{
            if(same(be,id)){be.bindingSucceeded(endpoint);index(be);success.accept(endpoint);}else {if(tracked(be)){be.bindingSucceeded(endpoint);var close=closing.get(id);if(close!=null)flushClosing(close);}failure.accept("endpoint_not_found");}
        },code->{if(tracked(be))be.bindingFailed(code);failure.accept(code);});
    }
    public void unload(TesseractBlockEntity be){close(be,null);loaded.remove(be.id(),be);rotation.remove(be.id());unindex(be.id());nextPoll.remove(be.id());idle.remove(be.id());}
    public void seal(TesseractBlockEntity be,String reason){tickets.remove(be.id());be.chunkDesired(false);close(be,reason);}
    private void close(TesseractBlockEntity be,String reason){
        if(journal==null || backend==null)return;
        // The buffer was never restored. Its empty/default state is not a checkpoint.
        // Preserve the original WAL; physical removal can seal SQL ownership separately.
        if(be.registrationRecoveryRequired()){
            if(reason!=null){UUID id=be.id();submit(a->{a.sealEndpoint(id,reason);a.confirmChunkOff(id);return true;},x->{},x->{});}
            return;
        }
        var entry=closing.get(be.id());if(entry==null){entry=new Closing(be,reason);closing.put(be.id(),entry);closingRotation.addLast(be.id());}else if(reason!=null)entry.sealReason=reason;
        unindex(be.id());flushClosing(entry);
    }
    private void flushClosing(Closing entry){
        var be=entry.be;if(entry.writing || be.inFlight() || be.registering() || heatInFlight.contains(be.id()))return;
        if(be.registrationRecoveryRequired()){closing.remove(be.id(),entry);closingRotation.remove(be.id());close(be,entry.sealReason);return;}
        var reservation=completions.tryReserve();if(reservation==null){entry.retry=System.nanoTime()+TimeUnit.SECONDS.toNanos(1);return;}
        // IO is admitted even offline. Persistent quota is not released merely by losing a lease.
        var snapshot=be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot());String reason=entry.sealReason,review=entry.quarantineReason;entry.writing=true;
        try{workers.execute(()->{
            try{
                journal.write(snapshot);var remaining=new HashMap<UUID,Long>();for(var credit:snapshot.credits())remaining.put(credit.transaction(),credit.remaining());
                backend.checkpoint(snapshot.endpoint(),snapshot.revision(),remaining);
                if(review!=null)backend.quarantineEndpoint(snapshot.endpoint(),review);
                if(reason!=null){backend.sealEndpoint(snapshot.endpoint(),reason);backend.confirmChunkOff(snapshot.endpoint());if(snapshot.deposits().isEmpty() && snapshot.credits().stream().allMatch(c->c.remaining()==0) && snapshot.thermal().microjoules()==0 && snapshot.thermal().residual()==0 && snapshot.thermal().pending()==null)backend.retireEmptySealed(snapshot.endpoint());}
                reservation.complete(()->{
                    entry.writing=false;
                    if(!Objects.equals(reason,entry.sealReason) || !Objects.equals(review,entry.quarantineReason) || be.buffer().revision()!=snapshot.revision()){
                        entry.retry=0;flushClosing(entry);return;
                    }
                    if(closing.remove(snapshot.endpoint(),entry)){closingRotation.remove(snapshot.endpoint());idle.remove(snapshot.endpoint());nextPoll.remove(snapshot.endpoint());locallyClosed.put(snapshot.endpoint(),snapshot.revision());while(locallyClosed.size()>limits.loadedLimit())locallyClosed.remove(locallyClosed.keySet().iterator().next());ioVersions.remove(snapshot.endpoint());nextHeat.remove(snapshot.endpoint());var current=loaded.get(snapshot.endpoint());if(current!=null && current!=be){current.pause("connecting");schedule(current.id(),System.nanoTime());}}
                });
            }catch(Exception | LinkageError error){String code=errorCode(error);if(error instanceof java.io.IOException || code.equals("checkpoint_version_conflict"))journalFailed=true;reservation.complete(()->{entry.writing=false;entry.retry=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);be.pause(code);});}
        });}catch(RejectedExecutionException error){reservation.complete(()->{entry.writing=false;entry.retry=System.nanoTime()+TimeUnit.SECONDS.toNanos(1);});}
    }
    private void schedule(UUID id,long due){
        if(loaded.containsKey(id))nextPoll.put(id,due);else {nextPoll.remove(id);idle.remove(id);}var previous=dueByEndpoint.remove(id);if(previous!=null)dueWork.remove(previous);
        if(loaded.containsKey(id)){var next=new Scheduled(id,due);dueByEndpoint.put(id,next);dueWork.add(next);}
    }
    private boolean signal(UUID channel,UUID id){if(coordinator.signal(channel,id))return true;schedule(id,System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.batchMillis()));metrics.retries.increment();return false;}
    private void index(TesseractBlockEntity be){
        UUID previous=indexedChannels.get(be.id());if(Objects.equals(previous,be.channel()))return;
        if(previous!=null){var ids=channelEndpoints.get(previous);if(ids!=null){ids.remove(be.id());if(ids.isEmpty())channelEndpoints.remove(previous);}coordinator.remove(be.id());}
        if(be.channel()==null)indexedChannels.remove(be.id());else{indexedChannels.put(be.id(),be.channel());channelEndpoints.computeIfAbsent(be.channel(),x->new LinkedHashSet<>()).add(be.id());}
        schedule(be.id(),System.nanoTime());
    }
    private void unindex(UUID id){UUID old=indexedChannels.remove(id);if(old!=null){var ids=channelEndpoints.get(old);if(ids!=null){ids.remove(id);if(ids.isEmpty())channelEndpoints.remove(old);}}coordinator.remove(id);localReady.remove(id);var due=dueByEndpoint.remove(id);if(due!=null)dueWork.remove(due);}
    public void localChanged(TesseractBlockEntity be,String kind,boolean sending,long amount){
        metrics.localCalls.increment();if(sending)metrics.localInput.add(amount);else metrics.localOutput.add(amount);
        if(limits.transfer().localFast() && same(be,be.id())){ioVersions.merge(be.id(),1L,Math::addExact);if(be.channel()!=null)signal(be.channel(),be.id());metrics.localWake.increment();schedule(be.id(),System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(limits.transfer().activeMillis()));if(sending && be.channel()!=null && dirtyChannels.size()<limits.transfer().channelLimit())dirtyChannels.add(be.channel());}
    }
    private void wakeChannel(UUID channel,boolean remote){
        var ids=channelEndpoints.get(channel);if(ids==null)return;
        // At most the configured per-channel endpoint limit; hints do not create assets.
        for(UUID id:ids){var be=loaded.get(id);if(be!=null && be.registered() && be.pauseReason().isEmpty() && be.channel()!=null && !be.binding() && CompatLoader.resources().stream().anyMatch(kind->!kind.equals(Protocol.HEAT)&&be.allowed(kind,null,false)&&be.buffer().receiveRoom(kind)>0))signal(channel,id);}
        if(remote)metrics.remoteWake.increment();else metrics.localWake.increment();
    }
    private boolean tracked(TesseractBlockEntity be){var entry=closing.get(be.id());return loaded.get(be.id())==be || entry!=null && entry.be==be;}
    public void tick(){
        long start=System.nanoTime();codecBudget=limits.encodes();tickCounter++;
        if(!online()){tickets.clear();ticketWork.clear();}
        Runnable refresh=maintenanceCompletion.getAndSet(null);if(refresh!=null)try{refresh.run();}catch(RuntimeException error){fail(error);}
        for(int i=0;i<limits.completions() && System.nanoTime()-start<limits.tickNanos();i++){Runnable completion=completions.poll();if(completion==null)break;try{completion.run();}catch(RuntimeException e){fail(e);}}
        if(online())processTicketWork(start);
        int priority=limits.transfer().localFast()?Math.min(localReady.size(),Math.max(1,limits.checks()/2)):0;
        for(int i=0;i<priority && System.nanoTime()-start<limits.tickNanos();i++){UUID id=localReady.removeFirst();var be=loaded.get(id);if(be!=null)exchangeLocal(be);}
        int checks=Math.min(limits.checks()-priority,rotation.size());long now=System.nanoTime();
        for(int i=0;i<checks && System.nanoTime()-start<limits.tickNanos();i++){
            UUID id=rotation.pollFirst();var be=loaded.get(id);if(be==null || be.isRemoved())continue;rotation.addLast(id);
            if(!be.registered()){if(!be.registrationRecoveryRequired() && now>=nextPoll.getOrDefault(id,0L)){schedule(id,now+TimeUnit.SECONDS.toNanos(1));register(be);}continue;}
            index(be);
            if(!online() || be.channel()==null || !be.pauseReason().isEmpty()){for(var module:CompatLoader.modules())module.suspended(be);continue;}
            if(limits.transfer().localFast() || !be.inFlight() && now>=nextPoll.getOrDefault(id,0L))exchangeLocal(be);
            // Heat has its own timer. Its WAL phase cannot race an ordinary endpoint WAL.
            for(var module:CompatLoader.modules())module.tick(be);
        }
        if(online()){
            var wake=new LinkedHashSet<UUID>();for(int i=0;i<16;i++){var hint=hints.poll();if(hint==null)break;wake.add(hint.channel());if(hint.endpoint()!=null){var be=loaded.get(hint.endpoint());if(be!=null&&hint.channel().equals(be.channel()))signal(hint.channel(),hint.endpoint());}}for(UUID channel:wake)wakeChannel(channel,true);
            if(limits.transfer().localFast() && !dirtyChannels.isEmpty())wakeChannel(dirtyChannels.removeFirst(),false);
            for(int i=0;i<limits.checks() && !dueWork.isEmpty() && dueWork.first().due()<=now;i++){
                var due=dueWork.pollFirst();dueByEndpoint.remove(due.endpoint(),due);var be=loaded.get(due.endpoint());
                if(be!=null && be.registered() && be.channel()!=null && be.pauseReason().isEmpty()){signal(be.channel(),be.id());metrics.pollFallback.increment();}
                else if(be!=null)schedule(be.id(),now+TimeUnit.SECONDS.toNanos(1));
            }
            for(int jobs=0;jobs<Math.max(1,config.poolSize()-1) && System.nanoTime()-start<limits.tickNanos();jobs++){
                if(workers.getQueue().size()>=config.queueSize()*3/4 || completions.count()>=completions.capacity()-16)break;
                var lease=coordinator.poll(limits.transfer().channelBatches()?limits.transfer().devices():1);if(lease==null)break;transfer(lease);
            }
        }
        int closes=Math.min(2,closingRotation.size());for(int i=0;i<closes;i++){UUID id=closingRotation.pollFirst();var entry=closing.get(id);if(entry==null)continue;closingRotation.addLast(id);if(!entry.writing && now>=entry.retry)flushClosing(entry);}
        metrics.tick(System.nanoTime()-start);
    }
    private void exchangeLocal(TesseractBlockEntity be){
        if(!same(be,be.id()) || !online() || be.channel()==null || !be.pauseReason().isEmpty() || be.binding())return;
        long started=System.nanoTime();be.pumpNeighbors();if(limits.transfer().diagnostics())metrics.sample(Metrics.Timer.LOCAL,System.nanoTime()-started);
    }
    private TransferWork.Request capture(TesseractBlockEntity be){
        var sending=CompatLoader.resources().stream().filter(kind->!kind.equals(Protocol.HEAT)&&be.allowed(kind,null,true)).collect(java.util.stream.Collectors.toUnmodifiableSet());
        var wanted=new ArrayList<TransferWork.Demand>();
        for(String kind:CompatLoader.resources().stream().sorted().toList())if(!kind.equals(Protocol.HEAT)&&be.allowed(kind,null,false)&&be.buffer().receiveRoom(kind)>0){
            long room=Math.min(be.buffer().receiveRoom(kind),LocalBuffer.slotCapacity(kind));String profile=kind.equals(Protocol.EU)?new Resource(kind,java.nio.ByteBuffer.allocate(8).putLong(be.euVoltage).array()).hash():null;
            wanted.add(new TransferWork.Demand(BusinessIds.next(),kind,room,profile,kind.equals(Protocol.EU)?be.euVoltage:1));
        }
        if(!be.buffer().hasWork() && wanted.isEmpty())return null;
        boolean checkpoint=be.buffer().dirty();var snapshot=be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot());
        return new TransferWork.Request(snapshot,be.channel(),be.endpointVersion(),checkpoint,sending,wanted,limits.deposits());
    }
    private void transfer(ChannelCoordinator.Lease lease){
        var prepared=new LinkedHashMap<UUID,Prepared>();var requests=new ArrayList<TransferWork.Request>();int records=0;long bytes=0;
        for(UUID id:lease.endpoints()){
            var be=loaded.get(id);if(be==null || !same(be,id) || !be.registered() || !lease.channel().equals(be.channel()) || !be.pauseReason().isEmpty())continue;
            if(be.inFlight() || heatInFlight.contains(id) || be.thermal().frozen()){schedule(id,System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.batchMillis()));continue;}
            var request=capture(be);if(request==null){schedule(id,System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(limits.transfer().idleMillis()));continue;}
            int count=request.snapshot().credits().size()+request.snapshot().deposits().size()+request.demands().size();long payloadBytes=request.snapshot().credits().stream().mapToLong(c->c.resource().size()).sum()+request.snapshot().deposits().stream().mapToLong(d->d.resource().size()).sum();
            if(records+count>limits.transfer().records() || bytes+payloadBytes>limits.transfer().bytes()){be.buffer().touch();signal(lease.channel(),id);continue;}
            records+=count;bytes+=payloadBytes;var item=new Prepared(be,request,System.nanoTime(),ioVersions.getOrDefault(id,0L));prepared.put(id,item);transfers.put(id,item);be.inFlight(true);requests.add(request);
        }
        if(requests.isEmpty()){metrics.emptyBatches.increment();coordinator.complete(lease);return;}
        metrics.batchDevices.add(requests.size());metrics.batchRecords.add(records);metrics.batchBytes.add(bytes);
        var immutable=List.copyOf(requests);
        submit(a->{var ready=new ArrayList<TransferWork.Request>();var failures=new ArrayList<TransferWork.Result>();
            for(var request:immutable)try{if(request.checkpoint() || !request.snapshot().deposits().isEmpty()){journal.write(request.snapshot());if(!request.snapshot().deposits().isEmpty())dev.crosstesseract.test.Faults.hit("after_send_wal",request.endpoint());}ready.add(request);}catch(java.io.IOException | DomainException error){failures.add(TransferWork.Result.failed(request.endpoint(),errorCode(error)));}
            if(!ready.isEmpty()){var results=limits.transfer().channelBatches()?a.channelBatch(lease.channel(),ready):legacyPhase(a,ready.getFirst());failures.addAll(results);if(results.stream().anyMatch(r->!r.committed().isEmpty() || !r.received().isEmpty()))outboxDirty.set(true);
                for(var result:results){if(!result.committed().isEmpty())dev.crosstesseract.test.Faults.hit("after_deposit",result.endpoint());if(!result.received().isEmpty())dev.crosstesseract.test.Faults.hit("after_allocation",result.endpoint());}
            }
            return List.copyOf(failures);
        },results->preparePublication(lease,prepared,results),code->{for(var item:prepared.values())finish(item,code,false);coordinator.complete(lease);});
    }
    private List<TransferWork.Result> legacyPhase(Authority a,TransferWork.Request request) throws Exception {
        var snapshot=request.snapshot();var committed=new HashSet<UUID>();var consumed=new HashSet<UUID>();var known=new HashSet<UUID>();var remaining=new HashMap<UUID,Long>();
        for(var deposit:snapshot.deposits().stream().filter(d->request.sending().contains(d.resource().kind())).limit(request.depositLimit()).toList()){a.deposit(deposit.transaction(),request.endpoint(),deposit.channel(),deposit.resource(),deposit.amount());committed.add(deposit.transaction());}
        for(var credit:snapshot.credits()){known.add(credit.transaction());remaining.put(credit.transaction(),credit.remaining());if(credit.remaining()==0)consumed.add(credit.transaction());}
        if(request.checkpoint())a.checkpoint(request.endpoint(),snapshot.revision(),remaining);
        var received=new ArrayList<Credit>();for(var allocation:a.allocations(request.endpoint()))if(!known.contains(allocation.id())&&!"QUARANTINED".equals(allocation.state()))received.add(new Credit(allocation.id(),allocation.channel(),allocation.payload(),allocation.amount(),allocation.remaining()));
        for(var demand:request.demands())if(received.stream().noneMatch(c->c.resource().kind().equals(demand.kind()))){a.demand(request.endpoint(),request.channel(),demand.kind(),demand.room(),demand.profile(),demand.quantum());var allocation=a.allocate(demand.transaction(),request.endpoint(),request.channel(),demand.kind(),demand.room());allocation.ifPresent(value->received.add(new Credit(value.id(),value.channel(),value.payload(),value.amount(),value.remaining())));}
        return List.of(new TransferWork.Result(request.endpoint(),committed,consumed,received,null));
    }
    private void preparePublication(ChannelCoordinator.Lease lease,Map<UUID,Prepared> prepared,List<TransferWork.Result> results){
        var publications=new ArrayList<TransferWork.Publication>();var publishing=new HashMap<UUID,Prepared>();var phaseErrors=new HashMap<UUID,String>();
        for(var result:results){var item=prepared.get(result.endpoint());if(item==null || transfers.get(result.endpoint())!=item)continue;var be=item.be;
            try{
            DomainException.require(be.id().equals(item.request.endpoint()) && Objects.equals(be.channel(),item.request.channel()),"binding_changed");
            // Delta merge only: neither captured TX nor captured remaining overwrites later local IO.
            be.buffer().committed(result.committed());be.buffer().checkpointed(result.consumed());
            if(result.committed().isEmpty() && result.received().isEmpty()){metrics.allocationMiss.add(item.request.demands().size());finish(item,result.error(),false);continue;}
            var valid=new ArrayList<Credit>();var quarantine=new HashMap<UUID,String>();
            for(var credit:result.received())try{
                DomainException.require(credit.channel().equals(item.request.channel()),"binding_changed");
                // Heavy registry decodes share the server budget. Lack of time is not corrupt
                // data: leave the receipt RESERVED in SQL for a later bounded discovery.
                if(!credit.resource().kind().equals(Protocol.FE) && !codecBudget()){metrics.deferredDecodes.increment();continue;}
                be.validate(credit.resource());valid.add(credit);
            }catch(DomainException error){quarantine.put(credit.transaction(),error.code());metrics.quarantined.increment();}
            valid=new ArrayList<>(be.buffer().admissible(valid));
            be.buffer().touch(); // Fresh version, capturing ALL concurrent input/consumption before fsync.
            var current=be.buffer().snapshot(be.id(),world,backend.session().generation(),item.request.channel(),true).withThermal(be.thermal().snapshot());
            var durableCredits=new ArrayList<>(current.credits());durableCredits.addAll(valid);
            var durable=new LocalSnapshot(current.endpoint(),current.world(),current.generation(),current.revision(),current.deposits(),durableCredits,current.thermal());
            publications.add(new TransferWork.Publication(durable,item.request.channel(),item.request.endpointVersion(),valid,quarantine));publishing.put(be.id(),item);if(result.error()!=null)phaseErrors.put(be.id(),result.error());
            }catch(RuntimeException | LinkageError error){finish(item,errorCode(error),false);}
        }
        if(publications.isEmpty()){coordinator.complete(lease);return;}
        var immutable=List.copyOf(publications);
        submit(a->{var durable=new ArrayList<TransferWork.Publication>();var errors=new HashMap<UUID,String>();
            for(var publication:immutable)try{journal.write(publication.snapshot());if(!publication.received().isEmpty())dev.crosstesseract.test.Faults.hit("after_receive_wal",publication.snapshot().endpoint());durable.add(publication);}catch(java.io.IOException | DomainException error){errors.put(publication.snapshot().endpoint(),errorCode(error));}
            // The second snapshot includes input/consumption that happened during phase 1.
            // Split on its ACTUAL size, not the older request estimate. Never hold SQL locks for fsync.
            var group=new ArrayList<TransferWork.Publication>();int records=0;long bytes=0;
            for(var publication:durable){var snapshot=publication.snapshot();int count=snapshot.deposits().size()+snapshot.credits().size()+publication.quarantined().size();long size=snapshot.deposits().stream().mapToLong(d->d.resource().size()).sum()+snapshot.credits().stream().mapToLong(c->c.resource().size()).sum();
                if(!group.isEmpty() && (!limits.transfer().channelBatches() || group.size()>=limits.transfer().devices() || records+count>limits.transfer().records() || bytes+size>limits.transfer().bytes())){errors.putAll(a.publishBatch(lease.channel(),List.copyOf(group)));group.clear();records=0;bytes=0;}
                DomainException.require(count<=limits.transfer().records() && size<=limits.transfer().bytes(),"invalid_limit");group.add(publication);records+=count;bytes+=size;
            }
            if(!group.isEmpty())errors.putAll(a.publishBatch(lease.channel(),List.copyOf(group)));
            for(var publication:durable)if(!errors.containsKey(publication.snapshot().endpoint()) && !publication.received().isEmpty())dev.crosstesseract.test.Faults.hit("after_local_sql",publication.snapshot().endpoint());
            return Map.copyOf(errors);
        },errors->{
            try{for(var publication:immutable){UUID id=publication.snapshot().endpoint();var item=publishing.get(id);if(transfers.get(id)!=item)continue;String error=errors.get(id);
                try{
                    DomainException.require(item.be.id().equals(id) && Objects.equals(item.be.channel(),publication.channel()),"binding_changed");
                    if(error==null){for(var credit:publication.received()){item.be.buffer().credit(credit);metrics.delivered(System.nanoTime()-item.started);metrics.localPublications.increment();}
                        for(var module:CompatLoader.modules())if(!item.be.isRemoved())module.changed(item.be);
                        if(limits.transfer().localFast() && same(item.be,id) && !publication.received().isEmpty())localReady.add(id);
                    }
                }catch(RuntimeException | LinkageError invalid){error=errorCode(invalid);quarantineLocalIo(item.be,error);}
                finally{finish(item,error!=null?error:phaseErrors.get(id),true);}
            }}finally{coordinator.complete(lease);}
        },code->{for(var item:publishing.values())finish(item,code,false);coordinator.complete(lease);});
    }
    private void finish(Prepared item,String error,boolean progress){
        var be=item.be;if(!transfers.remove(item.request.endpoint(),item))return;
        if(!be.id().equals(item.request.endpoint())){metrics.quarantined.increment();return;}
        be.inFlight(false);be.setChanged();
        if(error!=null){be.buffer().touch();be.pause(error);if(error.equals("journal_unavailable") || error.equals("checkpoint_version_conflict"))journalFailed=true;}
        int backoff=progress?0:Math.min(10,idle.getOrDefault(be.id(),0)+1);if(loaded.get(be.id())==be)idle.put(be.id(),backoff);
        if(same(be,be.id()))schedule(be.id(),System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(error!=null?2000:limits.transfer().localFast() && ioVersions.getOrDefault(be.id(),0L)!=item.ioVersion?limits.transfer().activeMillis():Math.min(limits.transfer().idleMillis(),config.batchMillis()*(1L<<Math.min(backoff,3)))));
        var close=closing.get(be.id());if(close!=null)flushClosing(close);
    }
    public void reclaimSealed(UUID actor,UUID id,long expected,String confirmation,Consumer<Long> success,Consumer<String> failure){
        if(loaded.containsKey(id) || closing.containsKey(id)){failure.accept("endpoint_still_loaded");return;}
        submit(a->{var snapshot=journal.read(id).orElseGet(()->new LocalSnapshot(id,world,a.session().generation(),0,List.of(),List.of()));
            return a.reclaimSealed(actor,snapshot,expected,confirmation);
        },success,failure);
    }
    public void quarantineLocalIo(TesseractBlockEntity be,String reason){
        be.quarantineLocal(reason);tickets.remove(be.id());if(journal==null || backend==null)return;
        var entry=closing.get(be.id());if(entry==null){entry=new Closing(be,null);closing.put(be.id(),entry);closingRotation.addLast(be.id());}entry.quarantineReason=reason;unindex(be.id());flushClosing(entry);
    }
    public void chunkOn(TesseractBlockEntity be,UUID actor,UUID request,boolean admin,Consumer<String> result){
        UUID id=be.id();submit(a->a.reserveChunk(actor,id,request,admin),grant->{
            if(!same(be,grant.endpoint())){result.accept("endpoint_unloaded");return;}
            boolean installed=tickets.install(grant);be.chunkDesired(installed);
            submit(a->{a.confirmChunk(id,installed);return true;},ignored->result.accept(installed?"success":"ticket_install_failed"),result);
        },result);
    }
    public void heatExchange(TesseractBlockEntity be){
        UUID id=be.id();long now=System.nanoTime();if(be.inFlight() || heatInFlight.contains(id) || !online() || now<nextHeat.getOrDefault(id,0L))return;
        nextHeat.put(id,now+TimeUnit.MILLISECONDS.toNanos(config.batchMillis()));heatInFlight.add(id);
        ThermalBuffer.Pending pending=be.thermal().pending();if(pending!=null){completeHeat(be,pending);return;}
        be.thermal().preparing(true);long energy=be.thermal().energy();double capacity=be.heatCapacity,inverse=be.heatInverseConduction;UUID channel=be.channel();UUID exchangeId=BusinessIds.next();
        boolean sending=be.allowed(Protocol.HEAT,null,true),receiving=be.allowed(Protocol.HEAT,null,false);
        submit(a->a.prepareHeat(exchangeId,id,channel,energy,capacity,inverse,sending,receiving),result->{
            if(!tracked(be)){be.thermal().preparing(false);heatInFlight.remove(id);if(result.isPresent())submit(a->{a.cancelHeatBeforeApplication(id,result.orElseThrow().id());return true;},x->{},x->{});return;}
            if(result.isEmpty()){be.thermal().preparing(false);finishHeat(be,null);return;}
            ThermalBuffer.Pending exchange=result.orElseThrow();
            try{be.thermal().apply(exchange);be.buffer().touch();be.setChanged();completeHeat(be,exchange);}
            catch(DomainException error){be.thermal().preparing(false);submit(a->{a.cancelHeatBeforeApplication(id,exchange.id());return true;},x->finishHeat(be,null),code->finishHeat(be,code));}
        },code->{be.thermal().preparing(false);finishHeat(be,code);});
    }
    private void completeHeat(TesseractBlockEntity be,ThermalBuffer.Pending pending){
        UUID id=be.id();be.buffer().touch();LocalSnapshot snapshot=be.buffer().snapshot(id,world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot());
        submit(a->{journal.write(snapshot);a.completeHeat(id,pending);outboxDirty.set(true);return true;},x->{if(tracked(be)){be.thermal().committed(pending.id());be.buffer().touch();be.setChanged();}finishHeat(be,null);},code->finishHeat(be,code));
    }
    private void finishHeat(TesseractBlockEntity be,String error){heatInFlight.remove(be.id());nextHeat.put(be.id(),System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(error==null?config.batchMillis():2000));if(error!=null)be.pause(error);var close=closing.get(be.id());if(close!=null)flushClosing(close);}
    public void chunkOff(UUID actor,UUID id,boolean admin,Consumer<String> result){
        submit(a->{a.requestChunkOff(actor,id,admin);return true;},ignored->{
            var be=loaded.get(id);if(be!=null)be.chunkDesired(false);tickets.remove(id);
            if(be!=null)submit(a->{a.confirmChunkOff(id);return true;},x->result.accept("success"),result);else result.accept("revocation_pending");
        },result);
    }
    private void reconcileTickets(List<Grant> grants){
        if(!online()){tickets.clear();return;}
        var byId=grants.stream().collect(java.util.stream.Collectors.toMap(Grant::endpoint,Function.identity()));
        ticketWork.keySet().removeIf(id->!byId.containsKey(id));
        for(var grant:grants){if(!grant.desired() || !tickets.contains(grant.endpoint()) || !"ACTIVE".equals(grant.state()) || !"ACTIVE".equals(grant.location().state()))ticketWork.put(grant.endpoint(),grant);}
        for(UUID id:tickets.identities())if(!byId.containsKey(id))tickets.remove(id);
    }
    private void processTicketWork(long tickStart){
        for(int changes=0;changes<limits.ticketChanges() && !ticketWork.isEmpty() && System.nanoTime()-tickStart<limits.tickNanos();changes++){
            var entry=ticketWork.entrySet().iterator().next();Grant grant=entry.getValue();ticketWork.remove(entry.getKey());
            UUID id=grant.endpoint();
            var current=grantByEndpoint.get(id);if(current==null){tickets.remove(id);continue;}grant=current;
            if(!grant.desired()){
                tickets.remove(id);var be=loaded.get(id);if(be!=null)be.chunkDesired(false);
                if(!ticketConfirming.contains(id)){ticketConfirming.add(id);submit(a->{a.confirmChunkOff(id);return true;},x->ticketConfirming.remove(id),x->ticketConfirming.remove(id));}continue;
            }
            if(!"ACTIVE".equals(grant.location().state())){tickets.remove(id);continue;}
            boolean installed=tickets.install(grant);var be=loaded.get(id);
            if(installed && be!=null && be.registered() && be.endpointActive() && !ticketConfirming.contains(id)){
                ticketConfirming.add(id);submit(a->{a.confirmChunk(id,true);return true;},x->ticketConfirming.remove(id),code->{ticketConfirming.remove(id);tickets.remove(id);be.pause(code);});
            }
            if(!installed){submit(a->{a.sealEndpoint(id,"invalid_world_position");return true;},x->{},x->{});}
        }
    }
    private void fail(Throwable e){onlineUntil=0;status=errorCode(e);metrics.errors.increment();long now=System.nanoTime();if(now-lastLog>TimeUnit.SECONDS.toNanos(10)){lastLog=now;CrossTesseract.LOG.warn("CrossServer Tesseract paused: {} ({})",status,e.getClass().getSimpleName());if(Boolean.getBoolean("cross_tesseract.compatTests") && e instanceof net.minecraft.gametest.framework.GameTestAssertException)CrossTesseract.LOG.warn("CT_NATIVE_CALLBACK_ASSERTION",e);}}
    public static String errorCode(Throwable error){if(error instanceof DomainException e)return e.code();if(error instanceof java.sql.SQLException e)return e.getErrorCode()==1644&&"cross_tesseract_history_limit".equals(e.getMessage())?"history_limit":"database_unavailable";if(error instanceof java.io.IOException)return "journal_unavailable";if(error instanceof redis.clients.jedis.exceptions.JedisException)return "redis_unavailable";return "backend_error";}
    public void stop(){
        stopping=true;onlineUntil=0;tickets.clear();scheduler.shutdownNow();
        // A bounded shutdown wait is permitted here; none of these waits occurs in tick or capabilities.
        workers.shutdown();control.shutdown();maintenance.shutdown();notifications.shutdown();boolean clean=false;
        try{clean=workers.awaitTermination(8,TimeUnit.SECONDS)&&control.awaitTermination(4,TimeUnit.SECONDS)&&maintenance.awaitTermination(4,TimeUnit.SECONDS)&&notifications.awaitTermination(4,TimeUnit.SECONDS);
            if(clean && backend!=null && joined){
                Runnable refresh=maintenanceCompletion.getAndSet(null);if(refresh!=null)refresh.run();
                Runnable done;while((done=completions.poll())!=null)done.run();
                DomainException.require(completions.count()==0 && transfers.isEmpty() && heatInFlight.isEmpty(),"shutdown_inflight");
                var snapshots=new LinkedHashMap<UUID,LocalSnapshot>();var sealed=new HashMap<UUID,String>();var reviewed=new HashMap<UUID,String>();
                for(var be:loaded.values())if(be.registered()){
                    snapshots.put(be.id(),be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot()));
                }
                for(var entry:closing.values()){var be=entry.be;snapshots.put(be.id(),be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot()));if(entry.sealReason!=null)sealed.put(be.id(),entry.sealReason);if(entry.quarantineReason!=null)reviewed.put(be.id(),entry.quarantineReason);}
                shutdownIo=Executors.newSingleThreadExecutor(threadFactory("ct-shutdown"));
                var prepared=shutdownIo.submit(()->{
                    long renewed=System.nanoTime();backend.heartbeat();
                    for(var snapshot:List.copyOf(snapshots.values())){
                        journal.write(snapshot);var remaining=new HashMap<UUID,Long>();for(Credit c:snapshot.credits())remaining.put(c.transaction(),c.remaining());backend.checkpoint(snapshot.endpoint(),snapshot.revision(),remaining);
                        if(reviewed.containsKey(snapshot.endpoint()))backend.quarantineEndpoint(snapshot.endpoint(),reviewed.get(snapshot.endpoint()));
                        if(sealed.containsKey(snapshot.endpoint())){backend.sealEndpoint(snapshot.endpoint(),sealed.get(snapshot.endpoint()));backend.confirmChunkOff(snapshot.endpoint());}
                        if(System.nanoTime()-renewed>TimeUnit.SECONDS.toNanos(2)){backend.heartbeat();renewed=System.nanoTime();}
                    }
                    return !journalFailed;
                });
                clean=prepared.get(8,TimeUnit.SECONDS);
            }
        }catch(Exception e){clean=false;CrossTesseract.LOG.warn("CrossServer Tesseract shutdown requires recovery: {}",errorCode(e));}
        if(!clean){workers.shutdownNow();control.shutdownNow();maintenance.shutdownNow();notifications.shutdownNow();}
        cleanPrepared=clean;
        // The world is saved after ServerStoppingEvent. A crash before ServerStoppedEvent
        // must retain an unclean session, even when our own WAL is already durable.
    }
    public void stopped(){
        if(shutdownIo==null)shutdownIo=Executors.newSingleThreadExecutor(threadFactory("ct-shutdown"));
        try{shutdownIo.submit(()->{
            if(cleanPrepared && !journalFailed && backend!=null && joined)backend.stopClean();
            return true;
        }).get(4,TimeUnit.SECONDS);}catch(Exception e){CrossTesseract.LOG.warn("CrossServer Tesseract final shutdown remains unclean: {}",errorCode(e));}
        finally{shutdownIo.shutdownNow();if(redis!=null)redis.close();if(backend!=null)backend.close();INSTANCES.remove(server);}
    }
}
