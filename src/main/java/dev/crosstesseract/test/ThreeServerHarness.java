package dev.crosstesseract.test;

import com.mojang.brigadier.arguments.StringArgumentType;
import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.*;
import dev.crosstesseract.runtime.RuntimeService;
import java.util.*;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;
import net.neoforged.neoforge.event.tick.ServerTickEvent;
import net.minecraft.server.MinecraftServer;

/** Explicitly enabled, console-only dev harness using real world blocks and registered capabilities. */
public final class ThreeServerHarness {
    private static final Map<MinecraftServer,Bulk> BULKS=new WeakHashMap<>();
    private static final class Bulk {
        int x,z,count,spawned,cursor;UUID owner;List<UUID> channels;boolean active;
        long accepted,extracted,fixtureNanos,fixtureTicks;int binding;
        final List<TesseractBlockEntity> devices=new ArrayList<>();
        final Set<UUID> pending=new HashSet<>();
    }
    public static void register(RegisterCommandsEvent event){
        if(!Boolean.getBoolean("cross_tesseract.testHarness"))return;
        event.getDispatcher().register(net.minecraft.commands.Commands.literal("ct_test").requires(src->src.hasPermission(4) && src.getEntity()==null)
            .then(net.minecraft.commands.Commands.argument("args",StringArgumentType.greedyString()).executes(ctx->run(ctx.getSource(),StringArgumentType.getString(ctx,"args")))));
    }
    private static int run(CommandSourceStack source,String input){
        var rt=RuntimeService.get(source.getServer());String[] args=input.split(" +");
        try{
            if(rt==null)throw new DomainException("backend_disabled");
            DomainException.require(rt.clusterId().startsWith("dev_") || rt.clusterId().startsWith("test_"),"forbidden");
            if(args[0].equals("fault")){Faults.arm(rt.clusterId(),args[2],UUID.fromString(args[1]));out(source,"FAULT armed");return 1;}
            if(args[0].equals("status")){out(source,"STATUS "+rt.status()+" tickets="+rt.ticketCount()+" "+rt.metricSnapshot());return 1;}
            if(args[0].equals("reset-metrics")){rt.metrics().resetWindow();out(source,"WINDOW reset");return 1;}
            if(args[0].equals("pid")){out(source,"PID "+ProcessHandle.current().pid());return 1;}
            if(args[0].equals("bulk")){
                int x=Integer.parseInt(args[1]),z=Integer.parseInt(args[2]),count=Integer.parseInt(args[3]);UUID owner=UUID.fromString(args[4]);List<UUID> channels=Arrays.stream(args[5].split(",")).map(UUID::fromString).toList();
                DomainException.require(count>=1 && count<=1000 && channels.size()>=4 && channels.size()<=8,"invalid_amount");
                Bulk bulk=BULKS.computeIfAbsent(source.getServer(),s->new Bulk());
                DomainException.require(bulk.count==0 || (bulk.x==x&&bulk.z==z&&owner.equals(bulk.owner)&&channels.equals(bulk.channels)&&count>=bulk.count),"invalid_action");
                bulk.x=x;bulk.z=z;bulk.count=count;bulk.owner=owner;bulk.channels=channels;out(source,"BULK queued="+count);return 1;
            }
            if(args[0].equals("bulk-active")){Bulk bulk=Objects.requireNonNull(BULKS.get(source.getServer()));bulk.active=Boolean.parseBoolean(args[1]);for(int i=0;i<bulk.devices.size();i++){var be=bulk.devices.get(i);if(be.registered())be.mode(Protocol.FE,bulk.active?(i%2==0?Protocol.Mode.SEND:Protocol.Mode.RECEIVE):Protocol.Mode.OFF);}out(source,"BULK active="+bulk.active);return 1;}
            if(args[0].equals("bulk-status")){Bulk bulk=Objects.requireNonNull(BULKS.get(source.getServer()));out(source,"BULK count="+bulk.count+" spawned="+bulk.spawned+" registered="+bulk.devices.stream().filter(TesseractBlockEntity::registered).count()+" bound="+bulk.devices.stream().filter(be->be.channel()!=null).count()+" accepted="+bulk.accepted+" extracted="+bulk.extracted+" fixture_ms_total="+(bulk.fixtureNanos/1e6)+" fixture_ticks="+bulk.fixtureTicks);return 1;}
            if(args[0].equals("create")){UUID owner=UUID.fromString(args[1]);rt.submit(a->a.createChannel(owner,args[2],BusinessIds.next()),id->{CrossTesseract.LOG.info("CT_TEST_CHANNEL {}",id);out(source,"CHANNEL "+id);},code->out(source,"ERROR "+code));return 1;}
            if(args[0].equals("invite")){UUID owner=UUID.fromString(args[1]),channel=UUID.fromString(args[2]),target=UUID.fromString(args[3]);rt.submit(a->a.invite(owner,channel,a.authorize(owner,channel,Protocol.MEMBERS).version(),target,false,BusinessIds.next()),id->out(source,"INVITE "+id),code->out(source,"ERROR "+code));return 1;}
            if(args[0].equals("accept")){UUID player=UUID.fromString(args[1]),invitation=UUID.fromString(args[2]);rt.submit(a->{a.answerInvitation(player,invitation,true);return true;},x->out(source,"ACCEPTED"),code->out(source,"ERROR "+code));return 1;}
            if(args[0].equals("remove-member")){UUID owner=UUID.fromString(args[1]),channel=UUID.fromString(args[2]),target=UUID.fromString(args[3]);rt.submit(a->{a.removeMember(owner,channel,a.authorize(owner,channel,Protocol.MEMBERS).version(),target);return true;},x->out(source,"REMOVED"),code->out(source,"ERROR "+code));return 1;}
            int x=Integer.parseInt(args[1]),z=Integer.parseInt(args[2]);var level=source.getLevel();BlockPos pos=new BlockPos(x,64,z);
            if(args[0].equals("spawn")){
                DomainException.require(level.getBlockEntity(pos)==null,"location_sealed");level.setBlockAndUpdate(pos,CrossTesseract.TESSERACT.get().defaultBlockState());
                var be=(TesseractBlockEntity)level.getBlockEntity(pos);be.placed(UUID.fromString(args[3]));out(source,"SPAWN "+be.id());return 1;
            }
            if(args[0].equals("remove")){level.destroyBlock(pos,true);out(source,"REMOVED_BLOCK");return 1;}
            DomainException.require(level.getBlockEntity(pos) instanceof TesseractBlockEntity,"endpoint_not_found");var be=(TesseractBlockEntity)level.getBlockEntity(pos);
            switch(args[0]){
                case "inspect" -> out(source,"DEVICE "+be.id()+" registered="+be.registered()+" pause="+be.pauseReason()+" channel="+be.channel()+" txFE="+be.buffer().sendAmount(Protocol.FE)+" rxFE="+be.buffer().receiveAmount(Protocol.FE)+" txItem="+be.buffer().sendAmount(Protocol.ITEM)+" rxItem="+be.buffer().receiveAmount(Protocol.ITEM)+" txFluid="+be.buffer().sendAmount(Protocol.FLUID)+" rxFluid="+be.buffer().receiveAmount(Protocol.FLUID)+" checkpoint="+be.buffer().revision());
                case "bind" -> rt.bindEndpoint(be,be.owner(),be.endpointVersion(),UUID.fromString(args[3]),endpoint->out(source,"BOUND"),code->out(source,"ERROR "+code));
                case "mode" -> {be.mode(args[3],Protocol.Mode.valueOf(args[4]));out(source,"MODE "+be.mode(args[3]));}
                case "sides" -> {be.sideMask(args[3],Integer.parseInt(args[4]));out(source,"SIDES "+be.sideMask(args[3]));}
                case "push-fe" -> {var port=level.getCapability(Capabilities.EnergyStorage.BLOCK,pos,Direction.UP);out(source,"ACCEPTED "+Objects.requireNonNull(port).receiveEnergy(Integer.parseInt(args[3]),false));}
                case "pull-fe" -> {var port=level.getCapability(Capabilities.EnergyStorage.BLOCK,pos,Direction.DOWN);out(source,"EXTRACTED "+Objects.requireNonNull(port).extractEnergy(Integer.parseInt(args[3]),false));}
                case "push-item" -> {ItemStack stack=new ItemStack(BuiltInRegistries.ITEM.get(ResourceLocation.parse(args[3])),Integer.parseInt(args[4]));stack.set(net.minecraft.core.component.DataComponents.CUSTOM_NAME,Component.literal("CT real-process test"));var port=level.getCapability(Capabilities.ItemHandler.BLOCK,pos,Direction.UP);var rest=Objects.requireNonNull(port).insertItem(0,stack,false);out(source,"ACCEPTED "+(stack.getCount()-rest.getCount()));}
                case "pull-item" -> {var port=Objects.requireNonNull(level.getCapability(Capabilities.ItemHandler.BLOCK,pos,Direction.DOWN));int count=0;for(int slot=9;slot<port.getSlots();slot++)count+=port.extractItem(slot,Integer.parseInt(args[3]),false).getCount();out(source,"EXTRACTED "+count);}
                case "push-fluid" -> {var port=Objects.requireNonNull(level.getCapability(Capabilities.FluidHandler.BLOCK,pos,Direction.UP));out(source,"ACCEPTED "+port.fill(new FluidStack(Fluids.WATER,Integer.parseInt(args[3])),IFluidHandler.FluidAction.EXECUTE));}
                case "pull-fluid" -> {var port=Objects.requireNonNull(level.getCapability(Capabilities.FluidHandler.BLOCK,pos,Direction.DOWN));out(source,"EXTRACTED "+port.drain(Integer.parseInt(args[3]),IFluidHandler.FluidAction.EXECUTE).getAmount());}
                case "chunk-on" -> rt.chunkOn(be,be.owner(),BusinessIds.next(),false,code->out(source,"CHUNK "+code));
                case "chunk-off" -> rt.chunkOff(be.owner(),be.id(),false,code->out(source,"CHUNK "+code));
                case "ae" -> {be.aeEnabled=Boolean.parseBoolean(args[3]);for(var module:dev.crosstesseract.compat.CompatLoader.modules())module.changed(be);out(source,"AE "+be.aeState);}
                case "ae-test" -> {var module=dev.crosstesseract.compat.CompatLoader.modules().stream().filter(m->m.getClass().getName().contains(".ae2.")).findFirst().orElseThrow(()->new DomainException("resource_unsupported"));out(source,"AE_TEST "+module.testCommand(be,args[3],Arrays.copyOfRange(args,4,args.length)));}
                default -> throw new DomainException("invalid_action");
            }
            return 1;
        }catch(Exception e){out(source,"ERROR "+RuntimeService.errorCode(e));return 0;}
    }
    /** Test load generator only. Four setup steps and sixteen capability calls per tick, separate
     * from the mod's own measured tick work; no fake backend or production replacement. */
    public static void tick(ServerTickEvent.Post event){
        if(!Boolean.getBoolean("cross_tesseract.testHarness"))return;
        Bulk bulk=BULKS.get(event.getServer());var rt=RuntimeService.get(event.getServer());if(bulk==null || rt==null || !rt.online())return;
        long start=System.nanoTime();var level=event.getServer().overworld();
        for(int n=0;n<4 && bulk.spawned<bulk.count;n++){
            int index=bulk.spawned;BlockPos pos=new BlockPos(bulk.x+index%32,64,bulk.z+index/32);
            if(level.getBlockEntity(pos)!=null)throw new IllegalStateException("benchmark location occupied; choose fresh coordinates");
            level.setBlockAndUpdate(pos,CrossTesseract.TESSERACT.get().defaultBlockState());var be=(TesseractBlockEntity)level.getBlockEntity(pos);be.placed(bulk.owner);bulk.devices.add(be);bulk.spawned++;
        }
        for(int n=0;n<16 && !bulk.devices.isEmpty();n++){
            int index=bulk.cursor++%bulk.devices.size();var be=bulk.devices.get(index);
            if(!be.registered() || be.isRemoved())continue;
            if(be.channel()==null && !be.binding() && bulk.pending.size()<16 && bulk.pending.add(be.id())){
                UUID id=be.id(),channel=bulk.channels.get(index/256),owner=be.owner();long version=be.endpointVersion();
                rt.bindEndpoint(be,owner,version,channel,endpoint->{bulk.pending.remove(id);be.mode(Protocol.FE,bulk.active?(index%2==0?Protocol.Mode.SEND:Protocol.Mode.RECEIVE):Protocol.Mode.OFF);},code->{bulk.pending.remove(id);});continue;
            }
            if(!bulk.active || be.channel()==null)continue;
            var port=level.getCapability(Capabilities.EnergyStorage.BLOCK,be.getBlockPos(),Direction.UP);
            if(port==null)continue;
            if(index%2==0)bulk.accepted=Math.addExact(bulk.accepted,port.receiveEnergy(1000,false));else bulk.extracted=Math.addExact(bulk.extracted,port.extractEnergy(32_000,false));
        }
        bulk.fixtureNanos+=System.nanoTime()-start;bulk.fixtureTicks++;
    }
    private static void out(CommandSourceStack source,String message){source.sendSuccess(()->Component.literal(message),false);}
    private ThreeServerHarness(){}
}
