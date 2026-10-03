package dev.crosstesseract.core;

import java.time.Instant;
import java.util.UUID;

public final class Models {
    public record Session(String cluster, String server, UUID world, UUID boot, long epoch, long generation, boolean recoveryRequired) {}
    public record Channel(UUID id, UUID owner, String name, long version, String state, int permissions) {}
    public record Invitation(UUID id, UUID channel, UUID target, String kind, String state, Instant expires) {}
    public record Endpoint(UUID id, String server, UUID world, UUID owner, UUID channel, String dimension,
                           int x, int y, int z, long version, String state, long checkpoint, String reason) {}
    public record Grant(UUID endpoint, UUID player, int slot, String state, boolean desired, long policyVersion, String reason, Endpoint location) {}
    public record Allocation(UUID id, UUID endpoint, UUID channel, UUID resource, Resource payload, long amount, long remaining, String state) {}
    public record Event(long id, UUID event, String type, UUID subject, String target) {}
    public record PermissionSnapshot(UUID endpoint,UUID channel,UUID channelOwner,long channelVersion,long endpointVersion,int permissions,String endpointState,String reason) {}
    public record AeNetwork(String server,UUID network,int usedChannels,boolean active,String controller) {}
    public record StockRow(UUID resource,Resource payload,long remoteAvailable,long reserved,long ledgerLocal,long quarantined) {}
    public record StockRequest(UUID id,UUID resource,long amount,long remaining,String state,Instant expires) {}
    public record StockPage(java.util.List<StockRow> rows,UUID next,java.util.List<StockRequest> requests) {}
    private Models() {}
}
