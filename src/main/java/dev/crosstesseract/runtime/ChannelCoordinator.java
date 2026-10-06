package dev.crosstesseract.runtime;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Main-thread-owned, bounded round-robin work admission for one runtime session.
 * A channel has at most one active lease. Signals received during that lease are
 * retained, and remaining work rejoins the tail after completion.
 */
public final class ChannelCoordinator {
    private final int maxChannels;
    private final int maxEndpoints;
    private final Map<UUID, ChannelState> channels = new HashMap<>();
    private final Map<UUID, EndpointState> endpoints = new HashMap<>();
    private final LinkedHashSet<UUID> rotation = new LinkedHashSet<>();
    private int endpointCount;

    public ChannelCoordinator(int maxChannels, int maxEndpoints) {
        if (maxChannels <= 0 || maxEndpoints <= 0) {
            throw new IllegalArgumentException("channel and endpoint limits must be positive");
        }
        this.maxChannels = maxChannels;
        this.maxEndpoints = maxEndpoints;
    }

    /**
     * Marks a device ready, preserving duplicate signals without extra admission.
     * Returns false at capacity or if the device belongs to another channel;
     * a binding change requires remove before signalling the new channel.
     */
    public boolean signal(UUID channel, UUID endpoint) {
        Objects.requireNonNull(channel, "channel");
        Objects.requireNonNull(endpoint, "endpoint");
        EndpointState existing = endpoints.get(endpoint);
        if (existing != null && !existing.channel.id.equals(channel)) return false;

        ChannelState state = channels.get(channel);
        if (existing == null) {
            if (endpointCount >= maxEndpoints) return false;
            if (state == null) {
                if (channels.size() >= maxChannels) return false;
                state = new ChannelState(channel);
                channels.put(channel, state);
            }
            endpoints.put(endpoint, new EndpointState(endpoint, state));
            endpointCount++;
        }
        state.ready.add(endpoint);
        if (state.flight == null) rotation.add(channel);
        return true;
    }

    /** A recorded next-run signal, not a permission or asset authorization.
     * A lease alone is not ready: its first in-flight wake must still be retained. */
    public boolean hasPendingSignal(UUID channel,UUID endpoint) {
        Objects.requireNonNull(channel,"channel");Objects.requireNonNull(endpoint,"endpoint");
        EndpointState entry=endpoints.get(endpoint);
        return entry!=null && !entry.removed && entry.channel.id.equals(channel) && entry.channel.ready.contains(endpoint);
    }

    /** Takes up to maxDevices from the oldest ready channel, or returns null. */
    public Lease poll(int maxDevices) {
        if (maxDevices <= 0) throw new IllegalArgumentException("device limit must be positive");
        if (rotation.isEmpty()) return null;
        UUID channel = rotation.removeFirst();
        ChannelState state = channels.get(channel);
        int size = Math.min(maxDevices, state.ready.size());
        var ids = new ArrayList<UUID>(size);
        var selected = new ArrayList<EndpointState>(size);
        for (int i = 0; i < size; i++) {
            UUID endpoint = state.ready.removeFirst();
            EndpointState entry = endpoints.get(endpoint);
            entry.inFlight = true;
            ids.add(endpoint);
            selected.add(entry);
        }
        state.selected = List.copyOf(selected);
        state.flight = new Lease(channel, ids);
        return state.flight;
    }

    /**
     * Releases a matching lease and queues remaining or newly signalled work at
     * the tail. Stale, repeated, removed-session or foreign leases return false.
     */
    public boolean complete(Lease lease) {
        Objects.requireNonNull(lease, "lease");
        ChannelState state = channels.get(lease.channel());
        if (state == null || state.flight != lease) return false;
        for (EndpointState entry : state.selected) {
            entry.inFlight = false;
            if (entry.removed || !state.ready.contains(entry.id)) {
                endpoints.remove(entry.id, entry);
                endpointCount--;
            }
        }
        state.selected = List.of();
        state.flight = null;
        if (state.ready.isEmpty()) channels.remove(state.id);
        else rotation.add(state.id);
        return true;
    }

    /**
     * Revokes pending signals. An in-flight device retains one capacity slot
     * until its lease finishes; that finish cannot recreate the removed device.
     */
    public boolean remove(UUID endpoint) {
        Objects.requireNonNull(endpoint, "endpoint");
        EndpointState entry = endpoints.remove(endpoint);
        if (entry == null) return false;
        entry.removed = true;
        ChannelState state = entry.channel;
        state.ready.remove(endpoint);
        if (!entry.inFlight) endpointCount--;
        if (state.flight == null && state.ready.isEmpty()) {
            rotation.remove(state.id);
            channels.remove(state.id);
        }
        return true;
    }

    /** Discards this session's coordinator state and invalidates all old leases. */
    public void clear() {
        channels.clear();
        endpoints.clear();
        rotation.clear();
        endpointCount = 0;
    }

    public int maxChannels() { return maxChannels; }
    public int maxEndpoints() { return maxEndpoints; }
    public int channelCount() { return channels.size(); }

    /** Ready and leased admissions, including revoked work awaiting completion. */
    public int endpointCount() { return endpointCount; }

    public static final class Lease {
        private final UUID channel;
        private final List<UUID> endpoints;

        private Lease(UUID channel, List<UUID> endpoints) {
            this.channel = channel;
            this.endpoints = List.copyOf(endpoints);
        }

        public UUID channel() { return channel; }
        public List<UUID> endpoints() { return endpoints; }
    }

    private static final class ChannelState {
        private final UUID id;
        private final LinkedHashSet<UUID> ready = new LinkedHashSet<>();
        private List<EndpointState> selected = List.of();
        private Lease flight;

        private ChannelState(UUID id) { this.id = id; }
    }

    private static final class EndpointState {
        private final UUID id;
        private final ChannelState channel;
        private boolean inFlight;
        private boolean removed;

        private EndpointState(UUID id, ChannelState channel) {
            this.id = id;
            this.channel = channel;
        }
    }
}
