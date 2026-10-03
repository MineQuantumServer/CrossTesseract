package dev.crosstesseract.network;

import com.google.gson.*;
import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.*;
import dev.crosstesseract.compat.CompatLoader;
import dev.crosstesseract.core.*;
import dev.crosstesseract.runtime.RuntimeService;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.chat.Component;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.server.level.ServerPlayer;
import net.neoforged.neoforge.network.PacketDistributor;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;
import net.neoforged.neoforge.network.handling.IPayloadContext;

public final class Packets {
    public record Request(int menu,BlockPos pos,UUID request,String action,String argument,long expected) implements CustomPacketPayload {
        public static final Type<Request> TYPE=new Type<>(CrossTesseract.id("request"));
        public static final StreamCodec<RegistryFriendlyByteBuf,Request> CODEC=new StreamCodec<>(){
            @Override public Request decode(RegistryFriendlyByteBuf b){return new Request(b.readVarInt(),b.readBlockPos(),b.readUUID(),b.readUtf(32),b.readUtf(512),b.readLong());}
            @Override public void encode(RegistryFriendlyByteBuf b,Request p){b.writeVarInt(p.menu());b.writeBlockPos(p.pos());b.writeUUID(p.request());b.writeUtf(p.action(),32);b.writeUtf(p.argument(),512);b.writeLong(p.expected());}
        };
        @Override public Type<Request> type(){return TYPE;}
    }
    public record View(int menu,UUID request,String json,String status) implements CustomPacketPayload {
        public static final Type<View> TYPE=new Type<>(CrossTesseract.id("view"));
        public static final StreamCodec<RegistryFriendlyByteBuf,View> CODEC=new StreamCodec<>(){
            @Override public View decode(RegistryFriendlyByteBuf b){return new View(b.readVarInt(),b.readUUID(),b.readUtf(60_000),b.readUtf(96));}
            @Override public void encode(RegistryFriendlyByteBuf b,View p){b.writeVarInt(p.menu());b.writeUUID(p.request());b.writeUtf(p.json(),60_000);b.writeUtf(p.status(),96);}
        };
        @Override public Type<View> type(){return TYPE;}
    }
    // Installed only from the client entrypoint. This field has no client class in its descriptor.
    public static java.util.function.Consumer<View> clientReceiver=view->{};
    public static void register(RegisterPayloadHandlersEvent e){var r=e.registrar("1");r.playToServer(Request.TYPE,Request.CODEC,Packets::handle);r.playToClient(View.TYPE,View.CODEC,(view,ctx)->ctx.enqueueWork(()->clientReceiver.accept(view)));}
    private static void handle(Request request,IPayloadContext context){context.enqueueWork(()->{
        if(!(context.player() instanceof ServerPlayer player))return;
        RuntimeService rt=RuntimeService.get(player.server);
        if(!(player.containerMenu instanceof TesseractMenu menu) || menu.containerId!=request.menu() || !menu.pos().equals(request.pos()) || !menu.stillValid(player)){reply(player,request,"forbidden",new JsonObject());return;}
        if(!ManagementLimiter.allow(player.getUUID())){reply(player,request,"rate_limited",new JsonObject());return;}
        if(!(player.level().getBlockEntity(request.pos()) instanceof TesseractBlockEntity be) || !player.getUUID().equals(be.owner())){reply(player,request,"device_owner_required",new JsonObject());return;}
        if(rt==null){reply(player,request,"backend_disabled",new JsonObject());return;}
        try { perform(rt,player,be,request); }catch(RuntimeException e){reply(player,request,RuntimeService.errorCode(e),new JsonObject());}
    });}
    private static void perform(RuntimeService rt,ServerPlayer player,TesseractBlockEntity be,Request req){
        UUID actor=player.getUUID();
        java.util.function.Consumer<String> finish=status->{reply(player,req,status,new JsonObject());if(status.equals("success"))refresh(rt,player,be,req);};
        if(req.action().equals("refresh")){refresh(rt,player,be,req);return;}
        if(Set.of("ae","mode","sides","rate","filter","whitelist","eu").contains(req.action()))DomainException.require(be.settingsVersion()==req.expected(),"stale_version");
        reply(player,req,"processing",new JsonObject());
        switch(req.action()){
            case "stock_view" -> {
                DomainException.require(CompatLoader.aeAvailable() && be.aeEnabled,"resource_unsupported");UUID endpoint=be.id(),channel=be.channel();DomainException.require(channel!=null,"unbound");UUID cursor=req.argument().isEmpty()?null:UUID.fromString(req.argument());
                rt.submit(a->a.stock(actor,endpoint,channel,cursor),view->{if(be.isRemoved() || !endpoint.equals(be.id()) || !channel.equals(be.channel())){finish.accept("binding_changed");return;}stockReply(player,be,req,view);},finish);
            }
            case "stock_fetch" -> {
                DomainException.require(CompatLoader.aeAvailable() && be.aeEnabled,"resource_unsupported");DomainException.require(be.endpointVersion()==req.expected(),"stale_version");String[] args=req.argument().split("\\|",2);DomainException.require(args.length==2,"invalid_action");UUID resource=UUID.fromString(args[0]),endpoint=be.id(),channel=be.channel();long amount=Long.parseLong(args[1]);DomainException.require(channel!=null,"unbound");
                rt.submit(a->a.stockResource(actor,endpoint,channel,resource),payload->{try{
                    DomainException.require(endpoint.equals(be.id()) && channel.equals(be.channel()) && be.endpointVersion()==req.expected(),"binding_changed");
                    rt.requestStock(be,actor,req.request(),payload,amount,false,result->{var data=new JsonObject();data.addProperty("stockRequest",result.id().toString());reply(player,req,"stock_queued",data);},finish);
                }catch(RuntimeException e){finish.accept(RuntimeService.errorCode(e));}},finish);
            }
            case "stock_cancel" -> {
                DomainException.require(CompatLoader.aeAvailable() && be.aeEnabled,"resource_unsupported");UUID endpoint=be.id(),channel=be.channel();DomainException.require(channel!=null,"unbound");UUID request=UUID.fromString(req.argument());rt.submit(a->{a.cancelStock(actor,endpoint,channel,request);return true;},x->finish.accept("success"),finish);
            }
            case "ae" -> {DomainException.require(CompatLoader.aeAvailable(),"resource_unsupported");DomainException.require(be.buffer().empty() && !be.inFlight(),"endpoint_not_empty");be.aeEnabled=!be.aeEnabled;be.settingsChanged();for(var m:CompatLoader.modules())m.changed(be);finish.accept("success");}
            case "mode" -> {String kind=req.argument();be.mode(kind,be.mode(kind).next());finish.accept("success");}
            case "sides" -> {String[] args=req.argument().split("=",2);DomainException.require(args.length==2 && CompatLoader.resources().contains(args[0]),"invalid_resource");be.sideMask(args[0],Integer.parseInt(args[1]));finish.accept("success");}
            case "rate" -> {String[] args=req.argument().split("=",2);DomainException.require(args.length==2 && CompatLoader.resources().contains(args[0]),"invalid_resource");be.rate(args[0],Long.parseLong(args[1]));finish.accept("success");}
            case "filter" -> {be.filter(req.argument(),false);finish.accept("success");}
            case "whitelist" -> {be.filter(req.argument(),true);finish.accept("success");}
            case "eu" -> {String[] values=req.argument().split(",",2);DomainException.require(CompatLoader.resources().contains(Protocol.EU)&&values.length==2,"resource_unsupported");long v=Long.parseLong(values[0]),a=Long.parseLong(values[1]);DomainException.require(v>=1 && v<=LocalBuffer.slotCapacity(Protocol.EU) && a>=1 && a<=64,"invalid_amount");DomainException.require(be.buffer().empty() && !be.inFlight(),"endpoint_not_empty");be.euVoltage=v;be.euAmperage=a;be.settingsChanged();finish.accept("success");}
            case "chunk_on" -> rt.chunkOn(be,actor,req.request(),false,finish);
            case "chunk_off" -> rt.chunkOff(actor,be.id(),false,finish);
            case "remote_off" -> rt.chunkOff(actor,UUID.fromString(req.argument()),false,finish);
            case "create" -> rt.submit(a->a.createChannel(actor,req.argument(),req.request()),x->finish.accept("success"),finish);
            case "bind","unbind" -> {
                DomainException.require(!be.inFlight() && be.buffer().empty() && be.thermal().energy()==0 && !be.thermal().frozen(),"endpoint_not_empty");UUID channel=req.action().equals("unbind")?null:UUID.fromString(req.argument());
                rt.bindEndpoint(be,actor,req.expected(),channel,endpoint->finish.accept("success"),finish);
            }
            case "accept","decline" -> rt.submit(a->{a.answerInvitation(actor,UUID.fromString(req.argument()),req.action().equals("accept"));return true;},x->finish.accept("success"),finish);
            case "rename","invite","transfer","remove","freeze","thaw","delete","leave","members","endpoints","revoke" -> {
                String[] args=req.argument().split("\\|",2);UUID channel=UUID.fromString(args[0]);String argument=args.length==2?args[1]:"";
                rt.submit(a->{
                    switch(req.action()){
                        case "rename"->a.rename(actor,channel,req.expected(),argument);
                        case "invite","transfer"->a.invite(actor,channel,req.expected(),UUID.fromString(argument),req.action().equals("transfer"),req.request());
                        case "remove"->a.removeMember(actor,channel,req.expected(),UUID.fromString(argument));
                        case "leave"->a.removeMember(actor,channel,req.expected(),actor);
                        case "freeze"->a.freeze(actor,channel,req.expected());
                        case "thaw"->a.thaw(actor,channel,req.expected());
                        case "delete"->a.deleteChannel(actor,channel,req.expected());
                        case "revoke"->a.revokeInvitation(actor,UUID.fromString(argument));
                        case "members"->{var out=new JsonObject();var list=new JsonArray();for(var id:a.members(actor,channel))list.add(id.toString());out.add("members",list);return out;}
                        case "endpoints"->{var out=new JsonObject();out.add("endpoints",GSON.toJsonTree(a.endpoints(actor,channel).stream().limit(64).toList()));return out;}
                        default->throw new DomainException("invalid_action");
                    }return new JsonObject();
                },data->{if(data.size()>0)reply(player,req,"success",data);else finish.accept("success");},finish);
            }
            default -> throw new DomainException("invalid_action");
        }
    }
    private static final Gson GSON=new Gson();
    private static void stockReply(ServerPlayer player,TesseractBlockEntity be,Request request,dev.crosstesseract.core.Models.StockPage page){
        var data=new JsonObject();var rows=new JsonArray();boolean nativeReady=Set.of("local_storage","ae_proxy_experimental").contains(be.aeState);
        for(var row:page.rows()){
            var object=new JsonObject();object.addProperty("id",row.resource().toString());object.addProperty("kind",row.payload().kind());object.addProperty("profile",row.payload().hash().substring(0,8));String reason="",name=row.resource().toString();
            try{DomainException.require(be.runtime()!=null && be.runtime().codecBudget(),"local_budget_exhausted");Component label;if(row.payload().kind().equals(Protocol.ITEM)){var stack=be.decodeItem(row.payload(),1);label=stack.getHoverName();if(!be.acceptsId(net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(stack.getItem()).toString()))reason="resource_restricted";}else{var stack=be.decodeFluid(row.payload(),1);label=stack.getHoverName();if(!be.acceptsId(net.minecraft.core.registries.BuiltInRegistries.FLUID.getKey(stack.getFluid()).toString()))reason="resource_restricted";}name=label.getString();if(label.getContents() instanceof net.minecraft.network.chat.contents.TranslatableContents translated && translated.getArgs().length==0 && translated.getKey().length()<=128)object.addProperty("nameKey",translated.getKey());}catch(DomainException e){reason=e.code();}
            long owned=be.buffer().received(row.payload().kind()).stream().filter(c->c.resource().equals(row.payload())).mapToLong(c->c.remaining()).sum();
            boolean ready=reason.isEmpty() && nativeReady && be.allowed(row.payload().kind(),null,false);
            if(!ready && reason.isEmpty())reason=!nativeReady?be.aeState:!be.mode(row.payload().kind()).receive?"receive_disabled":!be.pauseReason().isEmpty()?be.pauseReason():"forbidden";
            object.addProperty("name",name.substring(0,Math.min(name.length(),256)));object.addProperty("localReady",ready?owned:0);object.addProperty("remoteKnown",row.remoteAvailable());object.addProperty("reserved",row.reserved());object.addProperty("inFlight",Math.max(0,row.ledgerLocal()-owned));object.addProperty("unreachable",Math.addExact(row.quarantined(),ready?0:owned));object.addProperty("reason",reason);rows.add(object);
        }
        data.add("stock",rows);data.addProperty("stockChannel",Objects.toString(be.channel(),""));data.addProperty("stockEndpointVersion",be.endpointVersion());data.addProperty("stockNext",Objects.toString(page.next(),""));
        // Instant has no reflective Gson adapter. Serialize its text explicitly.
        var requests=new JsonArray();for(var r:page.requests()){var object=new JsonObject();object.addProperty("id",r.id().toString());object.addProperty("resource",r.resource().toString());object.addProperty("remaining",r.remaining());object.addProperty("state",r.state());object.addProperty("expires",r.expires().toString());requests.add(object);}data.add("stockRequests",requests);reply(player,request,"success",data);
    }
    private static void refresh(RuntimeService rt,ServerPlayer player,TesseractBlockEntity be,Request req){
        UUID actor=player.getUUID();
        JsonObject local=new JsonObject();
        local.addProperty("endpoint",be.id().toString());local.addProperty("owner",be.owner().toString());local.addProperty("channel",Objects.toString(be.channel(),""));local.addProperty("channelOwner",Objects.toString(be.channelOwner(),""));
        local.addProperty("aeAvailable",CompatLoader.aeAvailable());local.addProperty("aeEnabled",be.aeEnabled);local.addProperty("aeState",be.aeState);
        local.addProperty("settingsVersion",be.settingsVersion());
        local.addProperty("registered",be.registered());
        local.addProperty("endpointVersion",be.endpointVersion());local.addProperty("channelVersion",be.channelVersion());local.addProperty("server",rt.serverId());local.addProperty("backend",rt.status());local.addProperty("pause",be.pauseReason());local.addProperty("chunkDesired",be.chunkDesired());local.addProperty("inFlight",be.inFlight());local.addProperty("quotaLimit",rt.quotaLimit());local.addProperty("filter",be.filterText());local.addProperty("whitelist",be.whitelist());
        var resources=new JsonArray();for(String kind:new TreeSet<>(CompatLoader.resources())){var port=new JsonObject();port.addProperty("kind",kind);port.addProperty("mode",be.mode(kind).name());port.addProperty("sides",be.sideMask(kind));port.addProperty("rate",be.rate(kind));port.addProperty("send",kind.equals(Protocol.HEAT)?be.thermal().energy():be.buffer().sendAmount(kind));port.addProperty("receive",be.buffer().receiveAmount(kind));resources.add(port);}local.add("resources",resources);
        rt.submit(a->{local.add("channels",GSON.toJsonTree(a.channels(actor).stream().limit(64).toList()));
            var invites=new JsonArray();for(var invitation:a.invitations(actor)){var i=new JsonObject();i.addProperty("id",invitation.id().toString());i.addProperty("channel",invitation.channel().toString());i.addProperty("kind",invitation.kind());i.addProperty("target",invitation.target().toString());i.addProperty("expires",invitation.expires().toString());invites.add(i);}local.add("invites",invites);
            local.add("grants",GSON.toJsonTree(a.grants(actor).stream().limit(64).toList()));return local;
        },data->reply(player,req,"success",data),status->reply(player,req,status,local));
    }
    private static void reply(ServerPlayer player,Request request,String status,JsonObject data){
        if(player.hasDisconnected() || !(player.containerMenu instanceof TesseractMenu menu) || menu.containerId!=request.menu() || !menu.pos().equals(request.pos()))return;
        String json=GSON.toJson(data);if(json.length()>60_000){json="{}";status="list_too_large";}
        PacketDistributor.sendToPlayer(player,new View(request.menu(),request.request(),json,status));
    }
    private Packets(){}
}
