package dev.crosstesseract.block;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.compat.CompatLoader;
import dev.crosstesseract.core.*;
import dev.crosstesseract.core.Models.Endpoint;
import dev.crosstesseract.runtime.RuntimeService;
import java.util.*;
import net.minecraft.core.*;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.MenuProvider;
import net.minecraft.world.entity.player.*;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;
import net.neoforged.neoforge.items.IItemHandler;
import org.jetbrains.annotations.Nullable;

public final class TesseractBlockEntity extends BlockEntity implements MenuProvider {
    private static final UUID UNOWNED=new UUID(0,0);
    private UUID id=UUID.randomUUID(), owner=UNOWNED,channel;
    private UUID channelOwner;
    private long endpointVersion=1, channelVersion, permissionUntil, savedCheckpoint;
    private int permissions;
    private boolean registered, registering, inFlight, chunkDesired, sealed, binding;
    private long bindingReconcileAfter;
    private String pause="connecting";
    private final LocalBuffer buffer=new LocalBuffer();
    private final ThermalBuffer thermal=new ThermalBuffer();
    private final Map<String,Protocol.Mode> modes=new HashMap<>();
    private final Map<String,Integer> sides=new HashMap<>();
    private final Map<String,Long> rates=new HashMap<>();
    private final Map<String,long[]> budgets=new HashMap<>();
    private final LinkedHashMap<Resource,Object> decoded=new LinkedHashMap<>();
    private final List<Map.Entry<ItemStack,Resource>> itemCache=new ArrayList<>();
    private final List<Map.Entry<FluidStack,Resource>> fluidCache=new ArrayList<>();
    private long budgetTick=Long.MIN_VALUE;
    private Set<String> filter=Set.of();
    private boolean whitelist;
    private final Ports.ItemPort[] itemPorts=new Ports.ItemPort[7];
    private final Ports.FluidPort[] fluidPorts=new Ports.FluidPort[7];
    private final Ports.EnergyPort[] energyPorts=new Ports.EnergyPort[7];
    public long euVoltage=32,euAmperage=1;
    public double heatCapacity=10_000,heatInverseConduction=1_000;
    public double heatResidual;
    public boolean aeEnabled;
    public String aeState="disabled";
    public CompoundTag aeNodeData=new CompoundTag();
    public boolean aeEffective(){return aeEnabled && CompatLoader.aeAvailable();}
    private boolean endpointActive;
    private String recoveryError="";
    private boolean externalIo;
    private final NeighborPump neighbors=new NeighborPump(this);
    public void externalIo(boolean value){externalIo=value;}
    public void pumpNeighbors(){neighbors.tick();}
    private long settingsVersion=1;
    public long settingsVersion(){return settingsVersion;}
    public void settingsChanged(){settingsVersion=Math.addExact(settingsVersion,1);setChanged();}
    public TesseractBlockEntity(BlockPos pos,BlockState state) {
        super(CrossTesseract.ENTITY.get(),pos,state);
        for(int i=0;i<7;i++) { Direction side=i==6?null:Direction.from3DDataValue(i);itemPorts[i]=new Ports.ItemPort(this,side);fluidPorts[i]=new Ports.FluidPort(this,side);energyPorts[i]=new Ports.EnergyPort(this,side); }
    }
    public UUID id() { return id; }
    public UUID owner() { return owner; }
    public UUID channel() { return channel; }
    public UUID channelOwner() { return channelOwner; }
    public long endpointVersion() { return endpointVersion; }
    public long channelVersion() { return channelVersion; }
    public LocalBuffer buffer() { return buffer; }
    public ThermalBuffer thermal(){return thermal;}
    public long savedCheckpoint() { return savedCheckpoint; }
    public boolean registering() { return registering; }
    public void registering(boolean value) { registering=value; }
    public boolean registered() { return registered; }
    public boolean endpointActive(){return endpointActive && recoveryError.isEmpty() && !binding;}
    public boolean binding(){return binding;}
    public void beginBinding(long expected){
        DomainException.require(!binding,"binding_pending");
        DomainException.require(registered && endpointVersion==expected,"stale_version");
        DomainException.require(!inFlight && buffer.empty() && thermal.energy()==0 && thermal.snapshot().residual()==0 && !thermal.frozen(),"endpoint_not_empty");
        binding=true;bindingReconcileAfter=Long.MAX_VALUE;pause("binding_pending");
    }
    public void bindingSucceeded(Endpoint endpoint){
        applyEndpoint(endpoint);binding=false;bindingReconcileAfter=0;channelOwner=null;channelVersion=0;permissions=0;
        pause(channel==null?"unbound":"connecting");
    }
    public void bindingFailed(String reason){
        // A transport exception can follow a committed SQL bind. Resume only after a fresh read.
        bindingReconcileAfter=System.nanoTime();pause(reason);
    }
    public boolean inFlight() { return inFlight; }
    public void inFlight(boolean value) { inFlight=value; }
    public boolean chunkDesired() { return chunkDesired; }
    public void chunkDesired(boolean value) { chunkDesired=value;setChanged(); }
    public String pauseReason() { return pause; }
    public void pause(String reason) { pause=reason;permissionUntil=0; }
    public void quarantineLocal(String reason){recoveryError=reason;endpointActive=false;pause(reason);}
    public RuntimeService runtime() { return level instanceof ServerLevel sl?RuntimeService.get(sl.getServer()):null; }
    public void placed(UUID player) {
        // Clear all copied instance authority, including creative/custom-data placement.
        id=UUID.randomUUID();owner=player;channel=null;channelOwner=null;endpointVersion=1;channelVersion=0;permissionUntil=0;registered=false;registering=false;inFlight=false;binding=false;bindingReconcileAfter=0;sealed=false;endpointActive=false;recoveryError="";chunkDesired=false;permissions=0;savedCheckpoint=0;aeNodeData=new CompoundTag();
        setChanged(); if(runtime()!=null)runtime().register(this);
    }
    @Override public void onLoad() { super.onLoad(); if(level instanceof ServerLevel && !owner.equals(UNOWNED) && runtime()!=null)runtime().register(this); }
    @Override public void setRemoved() {
        if(runtime()!=null)runtime().unload(this);
        for(var m:CompatLoader.modules())m.detach(this);
        super.setRemoved();
    }
    public void applyEndpoint(Endpoint endpoint) {
        DomainException.require(id.equals(endpoint.id()) && owner.equals(endpoint.owner()),"cloned_endpoint");
        if(endpoint.version()<endpointVersion)return;
        endpointVersion=endpoint.version();channel=endpoint.channel();registered=true;registering=false;
        endpointActive="ACTIVE".equals(endpoint.state());
        pause="ACTIVE".equals(endpoint.state())?"":endpoint.reason();
        if(!"ACTIVE".equals(endpoint.state()))permissionUntil=0;
        setChanged();
    }
    public void authorize(Models.Channel data,long until) { if(binding || !Objects.equals(channel,data.id()) || data.version()<channelVersion)return;channelOwner=data.owner();channelVersion=data.version();permissions=data.permissions();permissionUntil=until;if(registered && !sealed)pause=""; }
    public void authorize(Models.PermissionSnapshot data,long until) {authorize(data,until,0);}
    public void authorize(Models.PermissionSnapshot data,long until,long observedAt) {
        if(!id.equals(data.endpoint()))return;
        if(data.endpointVersion()<endpointVersion || (Objects.equals(channel,data.channel()) && data.channelVersion()<channelVersion))return;
        if(binding){if(observedAt<=bindingReconcileAfter)return;binding=false;bindingReconcileAfter=0;}
        if(!Objects.equals(channel,data.channel())) { if(inFlight || !buffer.empty() || thermal.frozen() || thermal.energy()>0){pause("binding_conflict");return;}channel=data.channel(); }
        endpointVersion=data.endpointVersion();channelOwner=data.channelOwner();channelVersion=data.channelVersion();permissions=data.permissions();
        endpointActive="ACTIVE".equals(data.endpointState());
        permissionUntil="ACTIVE".equals(data.endpointState()) && data.permissions()>0?until:0;
        pause=!recoveryError.isEmpty()?recoveryError:!"ACTIVE".equals(data.endpointState())?data.reason():data.channel()==null?"unbound":data.permissions()==0?"forbidden":"";
    }
    public boolean allowed(String kind,@Nullable Direction side,boolean sending) {
        if(isRemoved() || !(level instanceof ServerLevel sl) || !sl.getServer().isSameThread() || !registered || binding || sealed || externalIo || !recoveryError.isEmpty() || channel==null || System.nanoTime()>=permissionUntil || runtime()==null || !runtime().online())return false;
        if(side!=null && (sideMask(kind)&(1<<side.get3DDataValue()))==0)return false;
        Protocol.Mode mode=mode(kind);
        return (sending?mode.send:mode.receive) && Protocol.permits(permissions,sending?Protocol.SEND:Protocol.RECEIVE);
    }
    public boolean acceptsId(String id) {
        if(id.equals("minecraft:filled_map") || id.equals("cross_tesseract:tesseract"))return false;
        return (runtime()==null || runtime().limits().accepts(id)) && (filter.isEmpty() || (whitelist==filter.contains(id)));
    }
    public void filter(String value,boolean whitelist) {
        var entries=new HashSet<String>();
        for(String part:value.split(",")) if(!part.isBlank()) { DomainException.require(part.matches("[a-z0-9_]+:[a-z0-9_/.-]+") && part.length()<=128,"invalid_filter");entries.add(part); }
        DomainException.require(entries.size()<=16,"invalid_filter");this.filter=Set.copyOf(entries);this.whitelist=whitelist;settingsChanged();
    }
    public String filterText() { return String.join(",",new TreeSet<>(filter)); }
    public boolean whitelist() { return whitelist; }
    public Protocol.Mode mode(String kind) { return modes.getOrDefault(kind,Protocol.Mode.OFF); }
    public int sideMask(String kind) { return sides.getOrDefault(kind,63); }
    public long rate(String kind) { return rates.getOrDefault(kind,switch(kind){case Protocol.ITEM->64L;case Protocol.FLUID->2000L;case Protocol.FE->32_000L;case Protocol.CHEMICAL->4000L;default->LocalBuffer.slotCapacity(kind);}); }
    public void mode(String kind,Protocol.Mode mode) { DomainException.require(CompatLoader.resources().contains(kind),"resource_unsupported");modes.put(kind,mode);settingsChanged(); }
    public void sideMask(String kind,int mask) { DomainException.require(mask>=0 && mask<=63,"invalid_side");sides.put(kind,mask);settingsChanged(); if(level!=null)level.invalidateCapabilities(worldPosition);for(var module:CompatLoader.modules())module.changed(this); }
    public void rate(String kind,long value) { DomainException.require(value>=1 && value<=LocalBuffer.slotCapacity(kind)*LocalBuffer.slots(kind),"invalid_rate");rates.put(kind,value);settingsChanged(); }
    public long budget(String kind,boolean sending,long requested,boolean simulate) {
        long tick=level==null?0:level.getGameTime();if(tick!=budgetTick) {budgets.clear();budgetTick=tick;}
        long[] used=budgets.computeIfAbsent(kind,k->new long[2]);int index=sending?0:1;
        long grant=Math.min(Math.max(0,requested),Math.max(0,rate(kind)-used[index]));if(!simulate){used[index]+=grant;if(grant>0 && runtime()!=null)runtime().localChanged(this,kind,sending,grant);}return grant;
    }
    public Resource itemResource(ItemStack stack) {
        for(var e:itemCache)if(ItemStack.isSameItemSameComponents(e.getKey(),stack))return e.getValue();
        if(runtime()!=null && !runtime().codecBudget())throw new DomainException("local_budget_exhausted");
        Resource r=StackCodec.item(stack,level.registryAccess());
        if(itemCache.size()>=18)itemCache.removeFirst();itemCache.add(Map.entry(stack.copyWithCount(1),r));decoded.put(r,stack.copyWithCount(1));trimDecoded();return r;
    }
    public Resource fluidResource(FluidStack stack) {
        for(var e:fluidCache)if(FluidStack.isSameFluidSameComponents(e.getKey(),stack))return e.getValue();
        if(runtime()!=null && !runtime().codecBudget())throw new DomainException("local_budget_exhausted");
        Resource r=StackCodec.fluid(stack,level.registryAccess());if(fluidCache.size()>=8)fluidCache.removeFirst();fluidCache.add(Map.entry(stack.copyWithAmount(1),r));decoded.put(r,stack.copyWithAmount(1));trimDecoded();return r;
    }
    public ItemStack decodeItem(Resource r,int count) {
        Object template=decoded.get(r);if(!(template instanceof ItemStack)) {template=StackCodec.item(r,level.registryAccess(),1);decoded.put(r,template);trimDecoded();}
        var stack=(ItemStack)template;return stack.copyWithCount(Math.min(count,stack.getMaxStackSize()));
    }
    public FluidStack decodeFluid(Resource r,int amount) {
        Object template=decoded.get(r);if(!(template instanceof FluidStack)) {template=StackCodec.fluid(r,level.registryAccess(),1);decoded.put(r,template);trimDecoded();}
        return ((FluidStack)template).copyWithAmount(amount);
    }
    public void validate(Resource r) { switch(r.kind()){case Protocol.ITEM->decodeItem(r,1);case Protocol.FLUID->decodeFluid(r,1);case Protocol.FE->DomainException.require(r.bytes().length==0,"invalid_resource");default->{DomainException.require(CompatLoader.resources().contains(r.kind()),"resource_unsupported");for(var module:CompatLoader.modules())if(module.resources().contains(r.kind()))module.validate(this,r);}} }
    private void trimDecoded() {while(decoded.size()>64)decoded.remove(decoded.keySet().iterator().next());}
    private static int side(@Nullable Direction side) {return side==null?6:side.get3DDataValue();}
    public IItemHandler items(@Nullable Direction side) {return itemPorts[side(side)];}
    public IFluidHandler fluids(@Nullable Direction side) {return fluidPorts[side(side)];}
    public IEnergyStorage energy(@Nullable Direction side) {return energyPorts[side(side)];}
    public void seal(String reason) {sealed=true;pause(reason);if(runtime()!=null)runtime().seal(this,reason);}
    @Override public Component getDisplayName() {return Component.translatable("block.cross_tesseract.tesseract");}
    @Override public AbstractContainerMenu createMenu(int id,Inventory inventory,Player player) {return new TesseractMenu(id,inventory,worldPosition);}
    @Override protected void saveAdditional(CompoundTag tag,HolderLookup.Provider registries) {
        super.saveAdditional(tag,registries);tag.putUUID("instance",id);tag.putUUID("device_owner",owner);tag.putLong("checkpoint",buffer.revision());
        if(channel!=null)tag.putUUID("channel",channel);tag.putBoolean("chunk_desired",chunkDesired);
        var port=new CompoundTag();for(String kind:CompatLoader.resources()){var config=new CompoundTag();config.putString("mode",mode(kind).name());config.putInt("sides",sideMask(kind));config.putLong("rate",rate(kind));port.put(kind,config);}tag.put("ports",port);
        tag.putString("filter",filterText());tag.putBoolean("whitelist",whitelist);tag.putLong("eu_voltage",euVoltage);tag.putLong("eu_amperage",euAmperage);
        tag.putBoolean("ae_enabled",aeEnabled);
        tag.putLong("settings_version",settingsVersion);
        tag.put("ae_node",aeNodeData.copy());
        // Balances, allocations and device authorizations never go into cloneable block item NBT.
    }
    @Override protected void loadAdditional(CompoundTag tag,HolderLookup.Provider registries) {
        super.loadAdditional(tag,registries);if(tag.hasUUID("instance"))id=tag.getUUID("instance");if(tag.hasUUID("device_owner"))owner=tag.getUUID("device_owner");
        savedCheckpoint=Math.max(0,tag.getLong("checkpoint"));channel=tag.hasUUID("channel")?tag.getUUID("channel"):null;chunkDesired=tag.getBoolean("chunk_desired");
        var port=tag.getCompound("ports");for(String kind:port.getAllKeys()){var c=port.getCompound(kind);modes.put(kind,Protocol.Mode.safe(c.getString("mode")));sides.put(kind,c.getInt("sides")&63);rates.put(kind,Math.max(1,Math.min(c.getLong("rate"),LocalBuffer.slotCapacity(kind)*LocalBuffer.slots(kind))));}
        try{filter(tag.getString("filter"),tag.getBoolean("whitelist"));}catch(DomainException ignored){filter=Set.of();}
        euVoltage=Math.max(1,Math.min(tag.contains("eu_voltage")?tag.getLong("eu_voltage"):32,LocalBuffer.slotCapacity(Protocol.EU)));euAmperage=Math.max(1,Math.min(tag.contains("eu_amperage")?tag.getLong("eu_amperage"):1,64));
        aeEnabled=tag.getBoolean("ae_enabled");
        aeNodeData=tag.getCompound("ae_node").copy();
        settingsVersion=Math.max(1,tag.getLong("settings_version"));
    }
}
