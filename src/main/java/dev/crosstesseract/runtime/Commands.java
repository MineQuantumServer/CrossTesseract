package dev.crosstesseract.runtime;

import com.mojang.brigadier.arguments.StringArgumentType;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.*;
import java.util.*;
import net.minecraft.commands.*;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.phys.BlockHitResult;
import net.neoforged.neoforge.event.RegisterCommandsEvent;

public final class Commands {
    public static void register(RegisterCommandsEvent event){
        event.getDispatcher().register(net.minecraft.commands.Commands.literal("ct")
            .executes(ctx->{ctx.getSource().sendSuccess(()->Component.translatable("ct.command.help"),false);return 1;})
            .then(net.minecraft.commands.Commands.argument("arguments",StringArgumentType.greedyString()).executes(ctx->execute(ctx.getSource(),StringArgumentType.getString(ctx,"arguments")))));
    }
    private static int execute(CommandSourceStack source,String input){
        if(input.length()>1024){source.sendFailure(Component.translatable("ct.error.invalid_action"));return 0;}
        var rt=RuntimeService.get(source.getServer());if(rt==null){source.sendFailure(Component.translatable("ct.error.backend_disabled"));return 0;}
        String[] args=input.split(" +",8);
        try {
            if(args[0].equals("admin")){DomainException.require(source.hasPermission(2),"forbidden");admin(source,rt,args);return 1;}
            ServerPlayer player=source.getPlayerOrException();UUID actor=player.getUUID();
            DomainException.require(ManagementLimiter.allow(actor),"rate_limited");
            java.util.function.Consumer<String> failure=code->source.sendFailure(Component.translatable("ct.error."+code));
            java.util.function.Consumer<Object> done=x->source.sendSuccess(()->Component.translatable("ct.status.success"),false);
            source.sendSuccess(()->Component.translatable("ct.status.processing"),false);
            switch(args[0]){
                case "status" -> {source.sendSuccess(()->Component.translatable("ct.command.status",rt.serverId(),rt.status(),rt.ticketCount()),false);}
                case "channels" -> rt.submit(a->a.channels(actor),list->{for(var c:list)source.sendSuccess(()->Component.translatable("ct.command.channel",c.id(),c.name(),c.owner(),c.version(),c.state()),false);},failure);
                case "create" -> {DomainException.require(args.length>=2,"invalid_action");String name=input.substring(input.indexOf(' ')+1);rt.submit(a->a.createChannel(actor,name,BusinessIds.next()),id->source.sendSuccess(()->Component.translatable("ct.command.created",id),false),failure);}
                case "invites" -> rt.submit(a->a.invitations(actor),list->{for(var invitation:list)source.sendSuccess(()->Component.translatable("ct.command.invite",invitation.id(),invitation.channel(),invitation.kind(),invitation.expires().toString()),false);},failure);
                case "accept","decline" -> {UUID invite=UUID.fromString(args[1]);rt.submit(a->{a.answerInvitation(actor,invite,args[0].equals("accept"));return true;},done,failure);}
                case "quota" -> rt.submit(a->a.grants(actor),list->{source.sendSuccess(()->Component.translatable("ct.command.quota",list.size(),rt.quotaLimit()),false);for(var g:list){var e=g.location();source.sendSuccess(()->Component.translatable("ct.command.device",e.id(),e.server(),e.dimension(),e.x(),e.y(),e.z(),g.state(),g.reason()),false);}},failure);
                case "off" -> rt.chunkOff(actor,UUID.fromString(args[1]),false,code->{if(code.equals("success"))done.accept(true);else failure.accept(code);});
                case "load" -> {var be=target(player);rt.chunkOn(be,actor,BusinessIds.next(),false,code->{if(code.equals("success"))done.accept(true);else failure.accept(code);});}
                case "bind","unbind" -> {var be=target(player);UUID channel=args[0].equals("unbind")?null:UUID.fromString(args[1]);rt.bindEndpoint(be,actor,be.endpointVersion(),channel,done::accept,failure);}
                case "mode" -> {var be=target(player);be.mode(args[1],Protocol.Mode.valueOf(args[2]));done.accept(true);}
                case "invite","transfer","remove","leave","rename","freeze","thaw","delete","members","endpoints","permissions" -> {
                    UUID channel=UUID.fromString(args[1]);
                    rt.submit(a->{var c=a.channels(actor).stream().filter(ch->ch.id().equals(channel)).findFirst().orElseThrow(()->new DomainException("forbidden"));
                        switch(args[0]){
                            case "invite","transfer" -> a.invite(actor,channel,c.version(),UUID.fromString(args[2]),args[0].equals("transfer"),BusinessIds.next());
                            case "remove" -> a.removeMember(actor,channel,c.version(),UUID.fromString(args[2]));
                            case "leave" -> a.removeMember(actor,channel,c.version(),actor);
                            case "rename" -> a.rename(actor,channel,c.version(),String.join(" ",Arrays.copyOfRange(args,2,args.length)));
                            case "freeze" -> a.freeze(actor,channel,c.version());
                            case "thaw" -> a.thaw(actor,channel,c.version());
                            case "delete" -> a.deleteChannel(actor,channel,c.version());
                            case "members" -> {return a.members(actor,channel).toString();}
                            case "endpoints" -> {return a.endpoints(actor,channel).toString();}
                            case "permissions" -> a.permissions(actor,channel,c.version(),UUID.fromString(args[2]),Integer.parseInt(args[3]));
                            default -> throw new DomainException("invalid_action");
                        }return "";
                    },text->{if(!text.isEmpty())source.sendSuccess(()->Component.literal(text),false);else done.accept(true);},failure);
                }
                case "revoke" -> {UUID invite=UUID.fromString(args[1]);rt.submit(a->{a.revokeInvitation(actor,invite);return true;},done,failure);}
                default -> failure.accept("invalid_action");
            }
            return 1;
        }catch(Exception e){source.sendFailure(Component.translatable("ct.error."+(e instanceof IllegalArgumentException || e instanceof ArrayIndexOutOfBoundsException?"invalid_action":RuntimeService.errorCode(e))));return 0;}
    }
    private static TesseractBlockEntity target(ServerPlayer player){
        var hit=player.pick(8,0,false);DomainException.require(hit instanceof BlockHitResult,"endpoint_not_found");
        var be=player.level().getBlockEntity(((BlockHitResult)hit).getBlockPos());DomainException.require(be instanceof TesseractBlockEntity,"endpoint_not_found");
        var tess=(TesseractBlockEntity)be;DomainException.require(player.getUUID().equals(tess.owner()),"device_owner_required");return tess;
    }
    private static void admin(CommandSourceStack source,RuntimeService rt,String[] args){
        UUID actor=source.getEntity() instanceof ServerPlayer p?p.getUUID():new UUID(0,0);
        java.util.function.Consumer<String> failure=code->source.sendFailure(Component.translatable("ct.error."+code));
        java.util.function.Consumer<Object> done=out->source.sendSuccess(()->Component.literal(out.toString()),false);
        DomainException.require(args.length>=2,"invalid_action");
        switch(args[1]){
            case "health" -> rt.submit(a->a.health(),done,failure);
            case "policy" -> rt.submit(a->a.policy(),done,failure);
            case "quota-plan" -> rt.submit(a->a.quotaReductionPlan(Integer.parseInt(args[2])),done,failure);
            case "history-policy" -> {DomainException.require(source.hasPermission(4)&&args.length>=5&&args[4].equals("CONFIRM_HISTORY_CAPACITY"),"recovery_confirmation_required");rt.submit(a->{a.historyPolicy(actor,Integer.parseInt(args[2]),Long.parseLong(args[3]));return "success";},done,failure);}
            case "metrics" -> done.accept(rt.metricSnapshot());
            case "trace" -> {DomainException.require(args.length>=4,"invalid_action");rt.submit(a->a.trace(actor,UUID.fromString(args[3]),args[2]),done,failure);}
            case "quota" -> rt.submit(a->a.grants(UUID.fromString(args[2])),done,failure);
            case "off" -> rt.chunkOff(actor,UUID.fromString(args[2]),true,code->{if(code.equals("success"))done.accept(code);else failure.accept(code);});
            case "release-offline" -> {UUID id=UUID.fromString(args[2]);DomainException.require(args.length>=4 && args[3].equals("CONFIRM_EXPIRED_LEASES"),"recovery_confirmation_required");rt.submit(a->{a.releaseOfflineRevocation(actor,id);return "success";},done,failure);}
            case "reclaim-sealed" -> {DomainException.require(args.length>=5,"recovery_confirmation_required");rt.reclaimSealed(actor,UUID.fromString(args[2]),Long.parseLong(args[3]),args[4],done::accept,failure);}
            case "recover" -> {DomainException.require(args.length>=5,"recovery_confirmation_required");UUID id=UUID.fromString(args[2]);long version=Long.parseLong(args[3]);rt.submit(a->{a.recoverEndpoint(actor,id,version,args[4]);return "success";},done,failure);}
            case "quota-policy" -> {DomainException.require(source.hasPermission(4)&&args.length>=5&&args[4].equals("CONFIRM_SAFE_REVOCATION"),"recovery_confirmation_required");int max=Integer.parseInt(args[2]);long version=Long.parseLong(args[3]);rt.submit(a->{a.lowerQuota(actor,max,version);return "success";},done,failure);}
            default -> throw new DomainException("invalid_action");
        }
    }
    private Commands(){}
}
