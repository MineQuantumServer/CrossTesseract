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
    private final ThreadPoolExecutor workers,control;
    private final ScheduledExecutorService scheduler;
    private final ArrayBlockingQueue<Runnable> completions;
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
        scheduler=Executors.newSingleThreadScheduledExecutor(threadFactory("ct-scheduler"));completions=new ArrayBlockingQueue<>(config.queueSize()*2);
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
    }
    private void maintain() throws Exception {
        if(backend==null)return;
        if(!joined){redis.healthy();backend.join(world,boot,CompatLoader.capabilities());joined=true;}
        redis.healthy();redis.online(config.server(),backend.session().boot(),backend.session().epoch());backend.heartbeat();
        onlineUntil=System.nanoTime()+TimeUnit.SECONDS.toNanos(8);status="online";
        var grants=backend.localGrants();currentGrants=grants;grantByEndpoint=grants.stream().collect(java.util.stream.Collectors.toUnmodifiableMap(Grant::endpoint,Function.identity()));effectiveQuota=backend.policy().get("quota_limit").intValue();
        long permissionsObservedAt=System.nanoTime();
        List<UUID> ids=loaded.keySet().stream().sorted().toList();var permissions=new ArrayList<PermissionSnapshot>();
        for(int start=0;start<ids.size();start+=256)permissions.addAll(backend.refreshPermissions(ids.subList(start,Math.min(ids.size(),start+256))));
        post(()->{
            for(var permission:permissions){var be=loaded.get(permission.endpoint());if(be!=null)be.authorize(permission,Math.min(onlineUntil,System.nanoTime()+TimeUnit.SECONDS.toNanos(3)),permissionsObservedAt);}
            reconcileTickets(grants);
        });
        redis.dispatch(backend,128);redis.drain(backend,config.server());
        if(System.nanoTime()>=nextHistorySweep){nextHistorySweep=System.nanoTime()+TimeUnit.MINUTES.toNanos(1);backend.sweepHistory();}
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
    public Map<String,Number> metricSnapshot(){var result=new LinkedHashMap<>(metrics.snapshot(loaded.size(),(int)loaded.values().stream().filter(be->be.registered()&&be.channel()!=null&&be.pauseReason().isEmpty()&&CompatLoader.resources().stream().anyMatch(kind->be.mode(kind)!=Protocol.Mode.OFF)).count(),workers.getQueue().size(),tickets.count()));if(backend!=null)result.putAll(backend.database().stats());return Collections.unmodifiableMap(result);}
    private static ThreadFactory threadFactory(String name){var counter=new AtomicInteger();return task->{var t=new Thread(task,name+"-"+counter.incrementAndGet());t.setDaemon(true);return t;};}
    private static ThreadPoolExecutor pool(String name,int threads,int capacity){return new ThreadPoolExecutor(threads,threads,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(capacity),threadFactory(name),new ThreadPoolExecutor.AbortPolicy());}
    private void post(Runnable action){if(!completions.offer(action)){onlineUntil=0;status="completion_queue_full";metrics.rejected.increment();}}
    public boolean codecBudget(){if(codecBudget<=0)return false;codecBudget--;return true;}
    public <T> void submit(Work<T> task,Consumer<T> success,Consumer<String> failure){
        if(!online()){failure.accept(status());return;}
        try{workers.execute(()->{long start=System.nanoTime();try{T result=task.run(backend);metrics.transactions.increment();post(()->success.accept(result));}catch(Exception e){metrics.errors.increment();String code=errorCode(e);if(Boolean.getBoolean("cross_tesseract.testHarness") && (e instanceof ClassCastException || e instanceof NullPointerException || e instanceof UnsupportedOperationException) && System.nanoTime()-lastInternalTrace>TimeUnit.SECONDS.toNanos(10)){lastInternalTrace=System.nanoTime();CrossTesseract.LOG.warn("CT_DEV_INTERNAL_FAILURE",e);}post(()->failure.accept(code));}finally{metrics.sql(System.nanoTime()-start);}});}catch(RejectedExecutionException e){metrics.rejected.increment();failure.accept("backend_busy");}
    }
    public void register(TesseractBlockEntity be){
        if(!loaded.containsKey(be.id()) && loaded.size()>=limits.loadedLimit()){be.pause("endpoint_load_limit");return;}
        TesseractBlockEntity old=loaded.putIfAbsent(be.id(),be);
        if(old!=null && old!=be && !old.isRemoved()){be.pause("cloned_endpoint");return;}
        if(old!=be){loaded.put(be.id(),be);rotation.addLast(be.id());}
        if(!online() || be.registering() || be.registered())return;
        be.registering(true);
        UUID id=be.id();var pos=be.getBlockPos();
        Endpoint requested=new Endpoint(id,config.server(),world,be.owner(),null,be.getLevel().dimension().location().toString(),pos.getX(),pos.getY(),pos.getZ(),be.endpointVersion(),"ACTIVE",be.savedCheckpoint(),"");
        submit(a->{var result=a.registerEndpoint(requested,requested.checkpoint());
            try{var local=journal.read(id);DomainException.require(local.isPresent() || result.checkpoint()==0,"journal_missing");
                if(local.isPresent()){var s=local.orElseThrow();DomainException.require(s.world().equals(world) && s.generation()==a.session().generation() && s.revision()>=result.checkpoint(),"journal_generation_conflict");local=Optional.of(a.restoreSnapshot(s));}return Map.entry(result,local);
            }catch(java.io.IOException | DomainException e){a.quarantineEndpoint(id,errorCode(e));throw e;}
        },result->{
            if(!same(be,id))return;
            be.applyEndpoint(result.getKey());result.getValue().ifPresent(s->{try{be.buffer().restore(s);be.thermal().restore(s.thermal());}catch(DomainException e){be.quarantineLocal(e.code());submit(a->{a.quarantineEndpoint(id,e.code());return true;},x->{},x->{});}});
            for(var m:CompatLoader.modules())m.attach(be);
            if(be.chunkDesired() && !grantByEndpoint.containsKey(id))be.chunkDesired(false);
            Grant ownGrant=grantByEndpoint.get(id);if(ownGrant!=null)ticketWork.put(id,ownGrant);
        },code->{if(same(be,id)){be.registering(false);be.pause(code);}});
    }
    private boolean same(TesseractBlockEntity be,UUID id){return !be.isRemoved() && be.id().equals(id) && loaded.get(id)==be;}
    public void requestStock(TesseractBlockEntity be,UUID actor,UUID request,Resource payload,long amount,boolean coalesce,Consumer<StockRequest> success,Consumer<String> failure){
        DomainException.require(server.isSameThread() && actor.equals(be.owner()) && !be.isRemoved(),"device_owner_required");
        DomainException.require(Set.of(Protocol.ITEM,Protocol.FLUID).contains(payload.kind()),"resource_unsupported");
        DomainException.require(be.allowed(payload.kind(),null,false),"forbidden");be.validate(payload);
        String registry=payload.kind().equals(Protocol.ITEM)?net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(be.decodeItem(payload,1).getItem()).toString():net.minecraft.core.registries.BuiltInRegistries.FLUID.getKey(be.decodeFluid(payload,1).getFluid()).toString();DomainException.require(be.acceptsId(registry),"resource_restricted");
        UUID id=be.id(),channel=be.channel();long expected=be.endpointVersion();
        submit(a->a.requestStock(actor,request,id,channel,expected,payload,amount,coalesce),result->{if(same(be,id) && channel.equals(be.channel())){nextPoll.put(id,0L);success.accept(result);}else failure.accept("binding_changed");},failure);
    }
    public void bindEndpoint(TesseractBlockEntity be,UUID actor,long expected,UUID channel,Consumer<Endpoint> success,Consumer<String> failure){
        DomainException.require(server.isSameThread() && actor.equals(be.owner()) && !be.isRemoved(),"device_owner_required");
        be.beginBinding(expected);UUID id=be.id();
        submit(a->a.bind(actor,id,expected,channel),endpoint->{
            if(same(be,id)){be.bindingSucceeded(endpoint);success.accept(endpoint);}else failure.accept("endpoint_not_found");
        },code->{if(same(be,id))be.bindingFailed(code);failure.accept(code);});
    }
    public void unload(TesseractBlockEntity be){
        if(online() && be.registered()){
            var snapshot=be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot());
            submit(a->{journal.write(snapshot);var remaining=new HashMap<UUID,Long>();for(Credit c:snapshot.credits())remaining.put(c.transaction(),c.remaining());a.checkpoint(snapshot.endpoint(),snapshot.revision(),remaining);return true;},x->{},code->fail(new DomainException(code)));
        }
        loaded.remove(be.id(),be);nextPoll.remove(be.id());idle.remove(be.id());
    }
    public void seal(TesseractBlockEntity be,String reason){
        tickets.remove(be.id());be.chunkDesired(false);
        if(be.registered() && journal!=null && backend!=null){
            var snapshot=be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot());
            // Capture resources before the block entity disappears. Journal IO can still run
            // while the backend is offline; SQL failure leaves a recoverable sealed checkpoint.
            try{workers.execute(()->{try{journal.write(snapshot);backend.checkpoint(be.id(),snapshot.revision(),snapshot.credits().stream().collect(java.util.stream.Collectors.toMap(Credit::transaction,Credit::remaining)));backend.sealEndpoint(be.id(),reason);backend.confirmChunkOff(be.id());if(snapshot.deposits().isEmpty() && snapshot.credits().stream().allMatch(c->c.remaining()==0) && snapshot.thermal().microjoules()==0 && snapshot.thermal().residual()==0 && snapshot.thermal().pending()==null)backend.retireEmptySealed(be.id());}catch(Exception e){journalFailed=true;fail(e);}});}catch(RejectedExecutionException e){journalFailed=true;fail(e);}
        }
    }
    public void tick(){
        long start=System.nanoTime();codecBudget=limits.encodes();tickCounter++;
        if(!online()){tickets.clear();for(var be:loaded.values())if(be.pauseReason().isEmpty())be.pause(status());}
        for(int i=0;i<limits.completions() && System.nanoTime()-start<limits.tickNanos();i++){Runnable completion=completions.poll();if(completion==null)break;try{completion.run();}catch(RuntimeException e){fail(e);}}
        if(online())processTicketWork(start);else ticketWork.clear();
        int checks=Math.min(limits.checks(),rotation.size());long now=System.nanoTime();
        for(int i=0;i<checks && System.nanoTime()-start<limits.tickNanos();i++){
            UUID id=rotation.pollFirst();var be=loaded.get(id);if(be==null || be.isRemoved())continue;rotation.addLast(id);
            if(!be.registered()){if(now>=nextPoll.getOrDefault(id,0L)){nextPoll.put(id,now+TimeUnit.SECONDS.toNanos(1));register(be);}continue;}
            if(!online() || be.channel()==null || !be.pauseReason().isEmpty()){for(var module:CompatLoader.modules())module.suspended(be);continue;}
            if(be.inFlight() || now<nextPoll.getOrDefault(id,0L))continue;
            be.pumpNeighbors();
            if(!be.pauseReason().isEmpty())continue;
            for(var module:CompatLoader.modules())module.tick(be);
            if(be.inFlight())continue;
            transfer(be);
        }
        metrics.tick(System.nanoTime()-start);
    }
    private record BatchResult(Set<UUID> committed,Set<UUID> consumed,List<Credit> newCredits,long duration){}
    private record Demand(long room,String profile,long quantum){}
    private void transfer(TesseractBlockEntity be){
        UUID id=be.id(),channel=be.channel();long start=System.nanoTime();
        // Keep capacity for registration/management; an unsubmitted periodic poll is safe to defer.
        if(workers.getQueue().size()>=config.queueSize()*3/4){nextPoll.put(id,start+TimeUnit.MILLISECONDS.toNanos(config.batchMillis()));return;}
        var sendingKinds=CompatLoader.resources().stream().filter(kind->be.allowed(kind,null,true)).collect(java.util.stream.Collectors.toUnmodifiableSet());
        var wanted=new HashMap<String,Demand>();for(String kind:CompatLoader.resources())if(!kind.equals(Protocol.HEAT) && be.allowed(kind,null,false) && be.buffer().receiveRoom(kind)>0){
            long room=Math.min(be.buffer().receiveRoom(kind),LocalBuffer.slotCapacity(kind));
            String profile=kind.equals(Protocol.EU)?new Resource(kind,java.nio.ByteBuffer.allocate(8).putLong(be.euVoltage).array()).hash():null;
            wanted.put(kind,new Demand(room,profile,kind.equals(Protocol.EU)?be.euVoltage:1));
        }
        if((!be.buffer().hasWork() || !be.buffer().dirty() && sendingKinds.isEmpty()) && wanted.isEmpty()){nextPoll.put(id,start+TimeUnit.SECONDS.toNanos(2));return;}
        boolean checkpointNeeded=be.buffer().dirty();
        LocalSnapshot snapshot=be.buffer().snapshot(id,world,backend.session().generation(),channel,true).withThermal(be.thermal().snapshot());be.inFlight(true);
        submit(a->{
            if(checkpointNeeded || !snapshot.deposits().isEmpty()){journal.write(snapshot);if(!snapshot.deposits().isEmpty())dev.crosstesseract.test.Faults.hit("after_send_wal",id);}
            Set<UUID> committed=new HashSet<>(),consumed=new HashSet<>();
            for(Deposit d:snapshot.deposits().stream().filter(d->sendingKinds.contains(d.resource().kind())).limit(limits.deposits()).toList()){a.deposit(d.transaction(),id,d.channel(),d.resource(),d.amount());dev.crosstesseract.test.Faults.hit("after_deposit",id);committed.add(d.transaction());}
            Map<UUID,Long> remaining=new HashMap<>();for(Credit c:snapshot.credits()){remaining.put(c.transaction(),c.remaining());if(c.remaining()==0)consumed.add(c.transaction());}
            if(checkpointNeeded)a.checkpoint(id,snapshot.revision(),remaining);
            List<Credit> received=new ArrayList<>();
            Set<UUID> known=new HashSet<>();for(Credit credit:snapshot.credits())known.add(credit.transaction());
            for(Allocation outstanding:a.allocations(id))if(!known.contains(outstanding.id()) && !outstanding.state().equals("QUARANTINED")){
                received.add(new Credit(outstanding.id(),outstanding.channel(),outstanding.payload(),outstanding.amount(),outstanding.remaining()));
            }
            for(var request:wanted.entrySet()){
                if(received.stream().anyMatch(c->c.resource().kind().equals(request.getKey())))continue;
                Demand demand=request.getValue();a.demand(id,channel,request.getKey(),demand.room(),demand.profile(),demand.quantum());
                var grant=a.allocate(BusinessIds.next(),id,channel,request.getKey(),demand.room());
                if(grant.isPresent()){dev.crosstesseract.test.Faults.hit("after_allocation",id);var allocation=grant.orElseThrow();received.add(new Credit(allocation.id(),allocation.channel(),allocation.payload(),allocation.amount(),allocation.remaining()));}
            }
            var durableCredits=new ArrayList<>(snapshot.credits());durableCredits.addAll(received);
            if(!committed.isEmpty() || !received.isEmpty())journal.write(new LocalSnapshot(id,world,a.session().generation(),snapshot.revision(),snapshot.deposits().stream().filter(d->!committed.contains(d.transaction())).toList(),durableCredits,snapshot.thermal()));
            if(!received.isEmpty())dev.crosstesseract.test.Faults.hit("after_receive_wal",id);
            for(Credit credit:received)a.markLocal(id,credit.transaction());
            return new BatchResult(Set.copyOf(committed),Set.copyOf(consumed),List.copyOf(received),System.nanoTime()-start);
        },result->{
            if(!same(be,id))return;
            be.inFlight(false);be.buffer().committed(result.committed());be.buffer().checkpointed(result.consumed());
            for(Credit credit:result.newCredits()){
                try{be.validate(credit.resource());be.buffer().credit(credit);for(var m:CompatLoader.modules())m.changed(be);metrics.delivered(result.duration());}
                catch(DomainException e){metrics.quarantined.increment();submit(a->{a.quarantineAllocation(id,credit.transaction(),e.code());return true;},x->{},x->{});}
            }
            int backoff=result.committed().isEmpty() && result.newCredits().isEmpty()?Math.min(10,idle.getOrDefault(id,0)+1):0;idle.put(id,backoff);
            nextPoll.put(id,System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(Math.min(2000,config.batchMillis()*(1L<<Math.min(backoff,3)))));be.setChanged();
        },code->{if(same(be,id)){be.inFlight(false);be.buffer().touch();be.pause(code);if(code.equals("journal_unavailable"))journalFailed=true;nextPoll.put(id,System.nanoTime()+TimeUnit.SECONDS.toNanos(2));}});
    }
    public void reclaimSealed(UUID actor,UUID id,long expected,String confirmation,Consumer<Long> success,Consumer<String> failure){
        if(loaded.containsKey(id)){failure.accept("endpoint_still_loaded");return;}
        submit(a->{var snapshot=journal.read(id).orElseGet(()->new LocalSnapshot(id,world,a.session().generation(),0,List.of(),List.of()));
            var remaining=new HashMap<UUID,Long>();for(Credit c:snapshot.credits())remaining.put(c.transaction(),c.remaining());a.checkpoint(id,snapshot.revision(),remaining);
            return a.reclaimSealed(actor,snapshot,expected,confirmation);
        },success,failure);
    }
    public void quarantineLocalIo(TesseractBlockEntity be,String reason){
        be.quarantineLocal(reason);tickets.remove(be.id());
        if(journal==null || backend==null)return;
        var snapshot=be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot());
        try{workers.execute(()->{try{journal.write(snapshot);backend.quarantineEndpoint(snapshot.endpoint(),reason);}catch(Exception e){journalFailed=true;fail(e);}});}catch(RejectedExecutionException e){journalFailed=true;fail(e);}
    }
    public void chunkOn(TesseractBlockEntity be,UUID actor,UUID request,boolean admin,Consumer<String> result){
        submit(a->a.reserveChunk(actor,be.id(),request,admin),grant->{
            if(!same(be,grant.endpoint())){result.accept("endpoint_unloaded");return;}
            boolean installed=tickets.install(grant);be.chunkDesired(installed);
            submit(a->{a.confirmChunk(be.id(),installed);return true;},ignored->result.accept(installed?"success":"ticket_install_failed"),result);
        },result);
    }
    public void heatExchange(TesseractBlockEntity be){
        if(be.inFlight() || !online())return;
        UUID id=be.id();be.inFlight(true);
        ThermalBuffer.Pending pending=be.thermal().pending();
        if(pending!=null){completeHeat(be,pending);return;}
        be.thermal().preparing(true);long energy=be.thermal().energy();double capacity=be.heatCapacity,inverse=be.heatInverseConduction;UUID channel=be.channel();
        boolean sending=be.allowed(Protocol.HEAT,null,true),receiving=be.allowed(Protocol.HEAT,null,false);
        submit(a->a.prepareHeat(BusinessIds.next(),id,channel,energy,capacity,inverse,sending,receiving),result->{
            if(!same(be,id))return;
            if(result.isEmpty()){be.thermal().preparing(false);be.inFlight(false);nextPoll.put(id,System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.batchMillis()));return;}
            ThermalBuffer.Pending exchange=result.orElseThrow();
            try{be.thermal().apply(exchange);be.buffer().touch();be.setChanged();completeHeat(be,exchange);}
            catch(DomainException e){be.thermal().preparing(false);submit(a->{a.cancelHeatBeforeApplication(id,exchange.id());return true;},x->{be.inFlight(false);},code->{be.inFlight(false);be.pause(code);});}
        },code->{if(same(be,id)){be.thermal().preparing(false);be.inFlight(false);be.pause(code);}});
    }
    private void completeHeat(TesseractBlockEntity be,ThermalBuffer.Pending pending){
        UUID id=be.id();LocalSnapshot snapshot=be.buffer().snapshot(id,world,backend.session().generation(),be.channel(),false).withThermal(be.thermal().snapshot());
        submit(a->{journal.write(snapshot);a.completeHeat(id,pending);return true;},x->{if(same(be,id)){be.thermal().committed(pending.id());be.buffer().touch();be.inFlight(false);be.setChanged();nextPoll.put(id,System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.batchMillis()));}},code->{if(same(be,id)){be.inFlight(false);be.pause(code);}});
    }
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
    private void fail(Throwable e){onlineUntil=0;status=errorCode(e);metrics.errors.increment();long now=System.nanoTime();if(now-lastLog>TimeUnit.SECONDS.toNanos(10)){lastLog=now;CrossTesseract.LOG.warn("CrossServer Tesseract paused: {} ({})",status,e.getClass().getSimpleName());}}
    public static String errorCode(Throwable error){if(error instanceof DomainException e)return e.code();if(error instanceof java.sql.SQLException e)return e.getErrorCode()==1644&&"cross_tesseract_history_limit".equals(e.getMessage())?"history_limit":"database_unavailable";if(error instanceof java.io.IOException)return "journal_unavailable";if(error instanceof redis.clients.jedis.exceptions.JedisException)return "redis_unavailable";return "backend_error";}
    public void stop(){
        stopping=true;onlineUntil=0;tickets.clear();scheduler.shutdownNow();
        // A bounded shutdown wait is permitted here; none of these waits occurs in tick or capabilities.
        workers.shutdown();control.shutdown();boolean clean=false;
        try{clean=workers.awaitTermination(8,TimeUnit.SECONDS)&&control.awaitTermination(4,TimeUnit.SECONDS);
            if(clean && backend!=null && joined){
                Runnable done;while((done=completions.poll())!=null)done.run();
                var snapshots=new ArrayList<LocalSnapshot>();
                for(var be:loaded.values())if(be.registered()){
                    snapshots.add(be.buffer().snapshot(be.id(),world,backend.session().generation(),be.channel(),true).withThermal(be.thermal().snapshot()));
                }
                shutdownIo=Executors.newSingleThreadExecutor(threadFactory("ct-shutdown"));
                var prepared=shutdownIo.submit(()->{
                    long renewed=System.nanoTime();backend.heartbeat();
                    for(var snapshot:List.copyOf(snapshots)){
                        journal.write(snapshot);var remaining=new HashMap<UUID,Long>();for(Credit c:snapshot.credits())remaining.put(c.transaction(),c.remaining());backend.checkpoint(snapshot.endpoint(),snapshot.revision(),remaining);
                        if(System.nanoTime()-renewed>TimeUnit.SECONDS.toNanos(2)){backend.heartbeat();renewed=System.nanoTime();}
                    }
                    return !journalFailed;
                });
                clean=prepared.get(8,TimeUnit.SECONDS);
            }
        }catch(Exception e){clean=false;CrossTesseract.LOG.warn("CrossServer Tesseract shutdown requires recovery: {}",errorCode(e));}
        if(!clean){workers.shutdownNow();control.shutdownNow();}
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
