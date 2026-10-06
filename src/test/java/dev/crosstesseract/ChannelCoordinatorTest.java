package dev.crosstesseract;

import dev.crosstesseract.runtime.ChannelCoordinator;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.IntRange;
import net.jqwik.api.constraints.Size;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChannelCoordinatorTest {
    private static UUID channel(int id) { return new UUID(0, id + 1L); }
    private static UUID endpoint(int id) { return new UUID(1, id + 1L); }

    @Test void duplicateSignalsHaveOneAdmissionAndOneImmutableLeaseEntry() {
        var coordinator = new ChannelCoordinator(2, 3);
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertEquals(1, coordinator.channelCount());
        assertEquals(1, coordinator.endpointCount());
        var lease = coordinator.poll(3);
        assertNotNull(lease);
        assertEquals(channel(0), lease.channel());
        assertEquals(List.of(endpoint(0)), lease.endpoints());
        assertThrows(UnsupportedOperationException.class, () -> lease.endpoints().add(endpoint(1)));
        assertNull(coordinator.poll(3), "a channel must not have a second active lease");
        assertTrue(coordinator.complete(lease));
        assertFalse(coordinator.complete(lease));
        assertNull(coordinator.poll(3));
        assertEquals(0, coordinator.channelCount());
        assertEquals(0, coordinator.endpointCount());
    }

    @Test void partialBatchesAndSignalsDuringFlightSurviveInDeviceOrder() {
        var coordinator = new ChannelCoordinator(1, 4);
        for (int i = 0; i < 3; i++) assertTrue(coordinator.signal(channel(0), endpoint(i)));
        var first = coordinator.poll(1);
        assertNotNull(first);
        assertEquals(List.of(endpoint(0)), first.endpoints());
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.signal(channel(0), endpoint(3)));
        assertNull(coordinator.poll(4));
        assertTrue(coordinator.complete(first));
        assertEquals(4, coordinator.endpointCount());

        var second = coordinator.poll(2);
        assertNotNull(second);
        assertEquals(List.of(endpoint(1), endpoint(2)), second.endpoints());
        assertTrue(coordinator.complete(second));
        var third = coordinator.poll(4);
        assertNotNull(third);
        assertEquals(List.of(endpoint(0), endpoint(3)), third.endpoints());
        assertTrue(coordinator.complete(third));
        assertNull(coordinator.poll(4));
        assertEquals(0, coordinator.endpointCount());
    }

    @Test void hotChannelRejoinsTailAfterEachLease() {
        var coordinator = new ChannelCoordinator(3, 5);
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.signal(channel(0), endpoint(1)));
        assertTrue(coordinator.signal(channel(1), endpoint(2)));
        var hot = coordinator.poll(1);
        assertNotNull(hot);
        assertEquals(channel(0), hot.channel());
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.signal(channel(2), endpoint(3)));
        assertTrue(coordinator.complete(hot));

        var waiting = coordinator.poll(1);
        var newcomer = coordinator.poll(1);
        var hotAgain = coordinator.poll(1);
        assertNotNull(waiting);
        assertNotNull(newcomer);
        assertNotNull(hotAgain);
        assertEquals(channel(1), waiting.channel());
        assertEquals(channel(2), newcomer.channel());
        assertEquals(channel(0), hotAgain.channel());
        assertEquals(List.of(endpoint(1)), hotAgain.endpoints());
        assertTrue(coordinator.complete(waiting));
        assertTrue(coordinator.complete(newcomer));
        assertTrue(coordinator.complete(hotAgain));
        var last = coordinator.poll(1);
        assertNotNull(last);
        assertEquals(List.of(endpoint(0)), last.endpoints());
        assertTrue(coordinator.complete(last));
        assertNull(coordinator.poll(1));
    }

    @Test void removingReadyWorkAndRevokedFlightWorkNeverResurrectsDevices() {
        var coordinator = new ChannelCoordinator(1, 3);
        for (int i = 0; i < 3; i++) assertTrue(coordinator.signal(channel(0), endpoint(i)));
        var lease = coordinator.poll(2);
        assertNotNull(lease);
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.remove(endpoint(0)));
        assertTrue(coordinator.remove(endpoint(2)));
        assertFalse(coordinator.remove(endpoint(0)));
        assertEquals(2, coordinator.endpointCount(), "revoked in-flight work still occupies capacity");
        assertTrue(coordinator.complete(lease));
        assertFalse(coordinator.complete(lease));
        assertEquals(0, coordinator.endpointCount());
        assertEquals(0, coordinator.channelCount());
        assertNull(coordinator.poll(3));
    }

    @Test void oldFinishCannotEraseAnExplicitNewSignalAfterRemoval() {
        var coordinator = new ChannelCoordinator(1, 2);
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        var old = coordinator.poll(1);
        assertNotNull(old);
        assertTrue(coordinator.remove(endpoint(0)));
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertEquals(2, coordinator.endpointCount(), "the old work and new signal use separate admissions");
        assertTrue(coordinator.complete(old));
        assertEquals(1, coordinator.endpointCount());
        var fresh = coordinator.poll(1);
        assertNotNull(fresh);
        assertEquals(List.of(endpoint(0)), fresh.endpoints());
        assertFalse(coordinator.complete(old), "an old finish must not release a new lease");
        assertNull(coordinator.poll(1));
        assertTrue(coordinator.complete(fresh));
        assertEquals(0, coordinator.endpointCount());
    }

    @Test void channelAndEndpointBoundsIncludeFlightUntilCompletion() {
        var coordinator = new ChannelCoordinator(1, 1);
        assertEquals(1, coordinator.maxChannels());
        assertEquals(1, coordinator.maxEndpoints());
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        assertFalse(coordinator.signal(channel(0), endpoint(1)));
        assertFalse(coordinator.signal(channel(1), endpoint(0)), "rebinding requires explicit removal");
        var lease = coordinator.poll(1);
        assertNotNull(lease);
        assertTrue(coordinator.remove(endpoint(0)));
        assertEquals(1, coordinator.endpointCount());
        assertEquals(1, coordinator.channelCount());
        assertFalse(coordinator.signal(channel(0), endpoint(1)));
        assertFalse(coordinator.signal(channel(1), endpoint(1)));
        assertTrue(coordinator.complete(lease));
        assertTrue(coordinator.signal(channel(1), endpoint(1)));

        var channelsBound = new ChannelCoordinator(1, 3);
        assertTrue(channelsBound.signal(channel(0), endpoint(0)));
        assertFalse(channelsBound.signal(channel(1), endpoint(1)));
        assertEquals(1, channelsBound.endpointCount(), "rejection must not leak admission");
        assertTrue(channelsBound.remove(endpoint(0)));
        assertTrue(channelsBound.signal(channel(1), endpoint(1)));
    }

    @Test void clearAndForeignLeasesCannotFinishNewWork() {
        var coordinator = new ChannelCoordinator(1, 1);
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        var old = coordinator.poll(1);
        assertNotNull(old);
        coordinator.clear();
        assertEquals(0, coordinator.endpointCount());
        assertEquals(0, coordinator.channelCount());
        assertTrue(coordinator.signal(channel(0), endpoint(0)));
        var fresh = coordinator.poll(1);
        assertNotNull(fresh);
        assertFalse(coordinator.complete(old));
        assertEquals(1, coordinator.endpointCount());

        var other = new ChannelCoordinator(1, 1);
        assertTrue(other.signal(channel(0), endpoint(0)));
        var foreign = other.poll(1);
        assertNotNull(foreign);
        assertFalse(coordinator.complete(foreign));
        assertTrue(coordinator.complete(fresh));
        assertTrue(other.complete(foreign));
    }

    @Test void invalidLimitsAndNullArgumentsAreRejectedWithoutAdmission() {
        assertThrows(IllegalArgumentException.class, () -> new ChannelCoordinator(0, 1));
        assertThrows(IllegalArgumentException.class, () -> new ChannelCoordinator(1, 0));
        var coordinator = new ChannelCoordinator(1, 1);
        assertThrows(IllegalArgumentException.class, () -> coordinator.poll(0));
        assertThrows(NullPointerException.class, () -> coordinator.signal(null, endpoint(0)));
        assertThrows(NullPointerException.class, () -> coordinator.signal(channel(0), null));
        assertThrows(NullPointerException.class, () -> coordinator.remove(null));
        assertThrows(NullPointerException.class, () -> coordinator.complete(null));
        assertEquals(0, coordinator.endpointCount());
        assertEquals(0, coordinator.channelCount());
    }

    @Property(tries = 150)
    void boundedSignalsDrainExactlyOnceAcrossPartialChannelBatches(
            @ForAll @Size(max = 200) List<@IntRange(min = 0, max = 31) Integer> signals,
            @ForAll @IntRange(min = 1, max = 8) int maxDevices) {
        var coordinator = new ChannelCoordinator(3, 8);
        Set<UUID> accepted = new HashSet<>();
        for (int signal : signals) {
            int id = signal % 16;
            boolean admitted = coordinator.signal(channel(id % 3), endpoint(id));
            if (admitted) accepted.add(endpoint(id));
            else assertEquals(8, coordinator.endpointCount());
            assertEquals(accepted.size(), coordinator.endpointCount());
            assertTrue(coordinator.channelCount() <= 3);
        }
        Set<UUID> delivered = new HashSet<>();
        ChannelCoordinator.Lease lease;
        int batches = 0;
        while ((lease = coordinator.poll(maxDevices)) != null) {
            assertTrue(++batches <= accepted.size());
            assertFalse(lease.endpoints().isEmpty());
            assertTrue(lease.endpoints().size() <= maxDevices);
            for (UUID id : lease.endpoints()) {
                assertTrue(delivered.add(id), "duplicate signals must not duplicate completed work");
                assertEquals(channel((int)(id.getLeastSignificantBits() - 1) % 3), lease.channel());
            }
            assertTrue(coordinator.complete(lease));
            assertEquals(accepted.size() - delivered.size(), coordinator.endpointCount());
        }
        assertEquals(accepted, delivered);
        assertEquals(0, coordinator.channelCount());
        assertEquals(0, coordinator.endpointCount());
    }

    @Property(tries = 150)
    void stateChangesMatchPendingAndFlightAccounting(
            @ForAll @Size(max = 150) List<@IntRange(min = 0, max = 1023) Integer> actions) {
        var coordinator = new ChannelCoordinator(1, 6);
        var pending = new LinkedHashSet<UUID>();
        var flight = new ArrayList<UUID>();
        var revoked = new HashSet<UUID>();
        var issued = new ArrayList<ChannelCoordinator.Lease>();
        ChannelCoordinator.Lease active = null;
        for (int action : actions) {
            UUID id = endpoint((action / 6) % 8);
            switch (action % 6) {
                case 0 -> {
                    boolean known = pending.contains(id) || flight.contains(id) && !revoked.contains(id);
                    boolean expected = known || accounted(pending, flight, revoked) < 6;
                    assertEquals(expected, coordinator.signal(channel(0), id));
                    if (expected) pending.add(id);
                }
                case 1 -> {
                    boolean liveFlight = flight.contains(id) && !revoked.contains(id);
                    boolean expected = pending.contains(id) || liveFlight;
                    assertEquals(expected, coordinator.remove(id));
                    pending.remove(id);
                    if (liveFlight) revoked.add(id);
                }
                case 2 -> {
                    int maxDevices = (action / 48) % 3 + 1;
                    var lease = coordinator.poll(maxDevices);
                    if (active != null || pending.isEmpty()) assertNull(lease);
                    else {
                        assertNotNull(lease);
                        while (flight.size() < maxDevices && !pending.isEmpty()) flight.add(pending.removeFirst());
                        assertEquals(flight, lease.endpoints());
                        active = lease;
                        issued.add(lease);
                    }
                }
                case 3 -> {
                    if (active != null) {
                        assertTrue(coordinator.complete(active));
                        flight.clear();
                        revoked.clear();
                        active = null;
                    }
                }
                case 4 -> {
                    if (!issued.isEmpty()) {
                        var lease = issued.get((action / 6) % issued.size());
                        boolean expected = lease == active;
                        assertEquals(expected, coordinator.complete(lease));
                        if (expected) {
                            flight.clear();
                            revoked.clear();
                            active = null;
                        }
                    }
                }
                case 5 -> {
                    coordinator.clear();
                    pending.clear();
                    flight.clear();
                    revoked.clear();
                    active = null;
                }
                default -> throw new AssertionError();
            }
            int count = accounted(pending, flight, revoked);
            assertEquals(count, coordinator.endpointCount());
            assertTrue(count >= 0 && count <= 6);
            assertEquals(active != null || !pending.isEmpty() ? 1 : 0, coordinator.channelCount());
        }
    }

    private static int accounted(Set<UUID> pending, List<UUID> flight, Set<UUID> revoked) {
        int result = pending.size();
        for (UUID id : flight) if (revoked.contains(id) || !pending.contains(id)) result++;
        return result;
    }
}
