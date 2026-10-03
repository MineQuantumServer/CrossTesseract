package dev.crosstesseract.compat.ae2;

import appeng.api.AECapabilities;
import appeng.api.config.Actionable;
import appeng.api.features.IPlayerRegistry;
import appeng.api.networking.*;
import appeng.api.networking.security.*;
import appeng.api.stacks.*;
import appeng.api.storage.*;
import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.compat.CompatModule;
import dev.crosstesseract.core.*;
import java.util.*;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.neoforged.neoforge.capabilities.RegisterCapabilitiesEvent;

/** Level 1: one native managed node and one provider per physical endpoint. No remote synchronous IO. */
public final class AeModule implements CompatModule {
    private final Map<TesseractBlockEntity,Gateway> gateways=new IdentityHashMap<>();
    private final Map<IGrid,UUID> gridIds=new WeakHashMap<>();
    private final boolean prototype=Boolean.getBoolean("cross_tesseract.aeNetworkPrototype");
    @Override public Set<String> resources(){return Set.of();}
    @Override public Class<?> gameTests(){return AeGameTests.class;}
    @Override public Set<String> features(){return prototype?Set.of("cross_tesseract:ae_storage_v1","cross_tesseract:ae_proxy_v1"):Set.of("cross_tesseract:ae_storage_v1");}
    @Override public void register(RegisterCapabilitiesEvent event){
        event.registerBlockEntity(AECapabilities.IN_WORLD_GRID_NODE_HOST,CrossTesseract.ENTITY.get(),(be,ignored)->gateways.get(be));
        // Intentionally do not expose ME_STORAGE as well: mounting one buffer both through our node and a
        // storage bus would inflate AE inventory reports. Native item/fluid capabilities are disabled in AE mode.
    }
    @Override public void attach(TesseractBlockEntity be){if(be.aeEnabled && be.getLevel() instanceof ServerLevel && !gateways.containsKey(be)){var gateway=new Gateway(be);gateways.put(be,gateway);gateway.node.create(be.getLevel(),be.getBlockPos());be.getLevel().invalidateCapabilities(be.getBlockPos());}}
    @Override public void detach(TesseractBlockEntity be){Gateway gateway=gateways.remove(be);if(gateway!=null){gateway.clearShadows();gateway.node.saveToNBT(be.aeNodeData);gateway.node.destroy();}}
    @Override public void suspended(TesseractBlockEntity be){var gateway=gateways.get(be);if(gateway!=null){gateway.clearShadows();gateway.proxyReady=false;be.aeState="ae_suspended";}}
    @Override public void tick(TesseractBlockEntity be){
        if(!be.aeEnabled){detach(be);be.aeState="disabled";return;}attach(be);
        Gateway gateway=gateways.get(be);if(gateway==null)return;
        be.aeState=gateway.node.isActive()?"local_storage":!gateway.node.isPowered()?"unpowered":!gateway.node.hasGridBooted()?"booting":"channel_shortage";
        if(prototype)proxyTick(gateway);
        if(gateway.dirty && gateway.node.isReady()){var node=gateway.node.getNode();if(node!=null)node.getGrid().getStorageService().invalidateCache();gateway.dirty=false;}
    }
    /** Real native nodes consume local AE channels and power for remote demand. This is a bounded
     * service-proxy experiment, NOT native grid, controller, energy or crafting merging. */
    private void proxyTick(Gateway gateway){
        var be=gateway.be;var nativeNode=gateway.node.getNode();long now=System.nanoTime();
        if(nativeNode==null || be.runtime()==null || !be.runtime().online()){gateway.clearShadows();return;}
        IGrid grid=nativeNode.getGrid();UUID gridId=gridIds.computeIfAbsent(grid,g->UUID.randomUUID());
        if(gateways.values().stream().filter(g->g.node.getGrid()==grid).map(g->g.be.channel()).distinct().count()>1){gateway.clearShadows();gateway.proxyReady=false;be.aeState="ae_channel_conflict";return;}
        Gateway leader=gateways.values().stream().filter(g->g.node.getGrid()==grid).min(Comparator.comparing(g->g.be.id())).orElse(gateway);
        if(leader!=gateway){gateway.clearShadows();gateway.proxyReady=leader.proxyReady;return;}
        if(gateway.proxyUntil<now){gateway.clearShadows();gateway.proxyReady=false;be.aeState="ae_peer_unconfirmed";}
        // Destroying/creating shadows makes native pathing rebuild. Do not advertise its
        // previous cached channel count as new local demand during that rebuild.
        if(grid.getPathingService().isNetworkBooting()){gateway.proxyReady=false;be.aeState="ae_proxy_rebuilding";return;}
        if(gateway.proxyInFlight || now<gateway.nextAdvertisement)return;
        gateway.nextAdvertisement=now+java.util.concurrent.TimeUnit.SECONDS.toNanos(2);gateway.proxyInFlight=true;
        UUID endpoint=be.id(),channel=be.channel();
        int localShadows=gateways.values().stream().filter(g->g.node.getGrid()==grid).mapToInt(g->(int)g.shadows.stream().filter(IManagedGridNode::isActive).count()).sum();
        int used=Math.max(0,grid.getPathingService().getUsedChannels()-localShadows);
        boolean powered=gateway.node.isActive();
        String controller=grid.getPathingService().getControllerState().name();String server=be.runtime().serverId();
        if(channel==null){gateway.proxyInFlight=false;gateway.clearShadows();return;}
        be.runtime().submit(a->a.advertiseAe(endpoint,channel,gridId,used,powered,controller),peers->{
            gateway.proxyInFlight=false;
            if(be.isRemoved() || !gateways.containsKey(be) || gateway.node.getGrid()!=grid)return;
            var plan=AeProxyPlanner.plan(server,gridId,peers);gateway.proxyUntil=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(5);
            gateway.proxyReady=plan.ready();
            if(!plan.ready()){gateway.clearShadows();be.aeState=plan.reason();return;}
            int wanted=plan.shadowNodes();
            // At most four changes per refresh; grid rebuilds cannot explode in one tick.
            for(int i=0;i<4 && gateway.shadows.size()!=wanted;i++){
                if(gateway.shadows.size()>wanted)gateway.shadows.removeLast().destroy();
                else{
                    var shadow=GridHelper.createManagedNode(gateway,new IGridNodeListener<Gateway>(){@Override public void onSaveChanges(Gateway owner,IGridNode node){}})
                        .setFlags(GridFlags.REQUIRE_CHANNEL).setInWorldNode(false).setIdlePowerUsage(1);
                    shadow.setOwningPlayerId(IPlayerRegistry.getMapping(be.getLevel()).getPlayerId(be.owner()));shadow.create(be.getLevel(),be.getBlockPos());
                    GridHelper.createConnection(Objects.requireNonNull(shadow.getNode()),grid.getPivot());gateway.shadows.add(shadow);
                }
            }
            gateway.proxyReady=gateway.shadows.size()==wanted && gateway.shadows.stream().allMatch(IManagedGridNode::isActive);
            be.aeState=gateway.proxyReady?"ae_proxy_experimental":"ae_proxy_rebuilding";
        },code->{gateway.proxyInFlight=false;gateway.proxyReady=false;gateway.clearShadows();be.aeState=code;});
    }
    @Override public void changed(TesseractBlockEntity be){if(!be.aeEnabled){detach(be);be.aeState="disabled";}else{attach(be);Gateway gateway=gateways.get(be);if(gateway!=null){gateway.dirty=true;var sides=EnumSet.noneOf(Direction.class);for(Direction side:Direction.values())if((be.sideMask(Protocol.ITEM)&(1<<side.get3DDataValue()))!=0)sides.add(side);gateway.node.setExposedOnSides(sides);}}}
    @Override public String testCommand(TesseractBlockEntity be,String action,String[] arguments){
        var gateway=gateways.get(be);DomainException.require(gateway!=null && gateway.node.getNode()!=null,"ae_peer_unconfirmed");
        if(action.equals("state")){var grid=gateway.node.getGrid();return new com.google.gson.Gson().toJson(Map.of("state",be.aeState,"grid",gridIds.computeIfAbsent(grid,g->UUID.randomUUID()).toString(),"used",grid.getPathingService().getUsedChannels(),"shadows",gateway.shadows.size(),"activeShadows",gateway.shadows.stream().filter(IManagedGridNode::isActive).count(),"active",gateway.node.isActive(),"powered",gateway.node.isPowered()));}
        DomainException.require(arguments.length==2 && Set.of("insert","extract").contains(action),"invalid_action");
        var id=net.minecraft.resources.ResourceLocation.parse(arguments[0]);DomainException.require(net.minecraft.core.registries.BuiltInRegistries.ITEM.containsKey(id),"registry_missing");
        var key=AEItemKey.of(new net.minecraft.world.item.ItemStack(net.minecraft.core.registries.BuiltInRegistries.ITEM.get(id)));long amount=Long.parseLong(arguments[1]);DomainException.require(amount>0 && amount<=1_000_000,"invalid_amount");
        var source=IActionSource.ofMachine(gateway);return Long.toString(action.equals("insert")?gateway.insert(key,amount,Actionable.MODULATE,source):gateway.extract(key,amount,Actionable.MODULATE,source));
    }
    private final class Gateway implements IInWorldGridNodeHost,IActionHost,IStorageProvider,MEStorage {
        private final TesseractBlockEntity be;
        private final IManagedGridNode node;
        private boolean dirty=true;
        private boolean inside;
        private final List<IManagedGridNode> shadows=new ArrayList<>();
        private long proxyUntil,nextAdvertisement;
        private boolean proxyReady,proxyInFlight;
        private final LinkedHashMap<String,Long> requests=new LinkedHashMap<>();
        private void clearShadows(){for(var shadow:shadows)shadow.destroy();shadows.clear();}
        Gateway(TesseractBlockEntity be){
            this.be=be;
            node=GridHelper.createManagedNode(this,new IGridNodeListener<Gateway>(){
                @Override public void onSaveChanges(Gateway gateway,IGridNode node){gateway.node.saveToNBT(be.aeNodeData);be.setChanged();}
                @Override public void onStateChanged(Gateway gateway,IGridNode node,State state){gateway.dirty=true;}
            }).setFlags(GridFlags.REQUIRE_CHANNEL).setInWorldNode(true).setIdlePowerUsage(1).setVisualRepresentation(CrossTesseract.ITEM.get()).addService(IStorageProvider.class,this);
            node.setOwningPlayerId(IPlayerRegistry.getMapping(be.getLevel()).getPlayerId(be.owner()));
            node.loadFromNBT(be.aeNodeData);
        }
        @Override public IGridNode getGridNode(Direction side){return be.aeEnabled && (be.sideMask(Protocol.ITEM)&(1<<side.get3DDataValue()))!=0?node.getNode():null;}
        @Override public IGridNode getActionableNode(){return node.getNode();}
        @Override public void mountInventories(IStorageMounts mounts){mounts.mount(this);}
        @Override public Component getDescription(){return Component.translatable("ct.ae.local_inventory");}
        private boolean authorized(String kind,boolean send,IActionSource source){
            if(!be.aeEnabled || !node.isActive() || !be.allowed(kind,null,send) || inside || prototype && (!proxyReady || System.nanoTime()>=proxyUntil))return false;
            // A player action is authoritative for that player. Machine actions use the already-authorized
            // device binding; pipe/AE machines do not reveal a reliable human identity behind them.
            return source.player().map(player->player.getUUID().equals(be.owner()) || be.runtime().server().getPlayerList().getPlayer(player.getUUID())==player && be.owner().equals(player.getUUID())).orElse(true);
        }
        private Resource resource(AEKey key){
            if(key instanceof AEItemKey item){DomainException.require(be.acceptsId(net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(item.toStack().getItem()).toString()),"resource_restricted");return be.itemResource(item.toStack());}
            if(key instanceof AEFluidKey fluid){DomainException.require(be.acceptsId(net.minecraft.core.registries.BuiltInRegistries.FLUID.getKey(fluid.toStack(1).getFluid()).toString()),"resource_restricted");return be.fluidResource(fluid.toStack(1));}
            throw new DomainException("resource_unsupported");
        }
        private static String kind(AEKey key){return key instanceof AEItemKey?Protocol.ITEM:key instanceof AEFluidKey?Protocol.FLUID:"";}
        @Override public long insert(AEKey key,long amount,Actionable mode,IActionSource source){
            MEStorage.checkPreconditions(key,amount,mode,source);String kind=kind(key);if(!authorized(kind,true,source))return 0;
            try{Resource resource=resource(key);long limited=be.budget(kind,true,amount,true);long inserted=be.buffer().insert(resource,limited,mode.isSimulate());if(!mode.isSimulate()){be.budget(kind,true,inserted,false);be.setChanged();dirty=true;}return inserted;}catch(DomainException e){return 0;}
        }
        @Override public long extract(AEKey key,long amount,Actionable mode,IActionSource source){
            MEStorage.checkPreconditions(key,amount,mode,source);String kind=kind(key);if(!authorized(kind,false,source))return 0;
            try{Resource resource=resource(key);long limited=be.budget(kind,false,amount,true);long extracted=be.buffer().extract(resource,limited,mode.isSimulate());if(!mode.isSimulate()){
                be.budget(kind,false,extracted,false);be.setChanged();dirty=true;
                if(extracted<limited && be.runtime()!=null){String identity=kind+resource.hash();long now=System.nanoTime();if(now>=requests.getOrDefault(identity,0L)){
                    if(requests.size()>=16 && !requests.containsKey(identity))requests.remove(requests.keySet().iterator().next());requests.put(identity,now+java.util.concurrent.TimeUnit.SECONDS.toNanos(2));
                    be.runtime().requestStock(be,be.owner(),BusinessIds.next(),resource,Math.min(limited-extracted,LocalBuffer.slots(kind)*LocalBuffer.slotCapacity(kind)),true,x->{},code->{});
                }}
            }return extracted;}catch(DomainException e){return 0;}
        }
        @Override public void getAvailableStacks(KeyCounter out){
            if(!be.aeEnabled || !node.isActive() || inside || prototype && (!proxyReady || System.nanoTime()>=proxyUntil))return;
            inside=true;
            try{for(String kind:List.of(Protocol.ITEM,Protocol.FLUID))if(be.allowed(kind,null,false))for(var credit:be.buffer().received(kind)){
                AEKey key=kind.equals(Protocol.ITEM)?AEItemKey.of(be.decodeItem(credit.resource(),1)):AEFluidKey.of(be.decodeFluid(credit.resource(),1));if(key!=null)out.add(key,credit.remaining());
            }}finally{inside=false;}
        }
    }
}
