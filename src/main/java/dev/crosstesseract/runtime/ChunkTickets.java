package dev.crosstesseract.runtime;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.core.Models.Grant;
import dev.crosstesseract.block.TesseractBlockEntity;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.*;
import net.minecraft.core.registries.Registries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.neoforged.neoforge.common.world.chunk.TicketController;

public final class ChunkTickets {
    public static final TicketController CONTROLLER=new TicketController(CrossTesseract.id("loading"),(level,helper)->{
        // No DB call and no wait. Saved tickets are untrusted until the async authority list arrives.
        for(var owner:helper.getBlockTickets().keySet())helper.removeAllTickets(owner);
        for(var owner:helper.getEntityTickets().keySet())helper.removeAllTickets(owner);
    });
    private record Ticket(ServerLevel level,BlockPos pos) {}
    private final Map<UUID,Ticket> installed=new HashMap<>();
    private final MinecraftServer server;
    public ChunkTickets(MinecraftServer server){this.server=server;}
    public int count(){return installed.size();}
    public boolean contains(UUID id){return installed.containsKey(id);}
    public boolean install(Grant grant) {
        var endpoint=grant.location();
        if(!grant.desired() || !"ACTIVE".equals(endpoint.state()))return false;
        var key=ResourceKey.create(Registries.DIMENSION,ResourceLocation.parse(endpoint.dimension()));ServerLevel level=server.getLevel(key);if(level==null)return false;
        BlockPos pos=new BlockPos(endpoint.x(),endpoint.y(),endpoint.z());
        if(!Level.isInSpawnableBounds(pos) || level.isOutsideBuildHeight(pos))return false;
        boolean wasPresent=installed.containsKey(grant.endpoint());
        if(!wasPresent){boolean added=CONTROLLER.forceChunk(level,grant.endpoint(),pos.getX()>>4,pos.getZ()>>4,true,true);if(!added)return false;installed.put(grant.endpoint(),new Ticket(level,pos));}
        // Authorized temporary load resolves the startup deadlock. Validate saved instance before allowing IO.
        if(!(level.getBlockEntity(pos) instanceof TesseractBlockEntity be) || !be.id().equals(grant.endpoint()) || !be.owner().equals(grant.player())) {remove(grant.endpoint());return false;}
        be.chunkDesired(true);return true;
    }
    public void remove(UUID endpoint) {
        Ticket ticket=installed.remove(endpoint);if(ticket!=null)CONTROLLER.forceChunk(ticket.level(),endpoint,ticket.pos().getX()>>4,ticket.pos().getZ()>>4,false,true);
    }
    public void clear(){for(UUID id:List.copyOf(installed.keySet()))remove(id);}
    public Set<UUID> identities(){return Set.copyOf(installed.keySet());}
}
