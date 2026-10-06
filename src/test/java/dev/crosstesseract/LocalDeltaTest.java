package dev.crosstesseract;

import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.core.BusinessIds;
import dev.crosstesseract.core.DomainException;
import dev.crosstesseract.core.LocalBuffer;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.LocalSnapshot.Credit;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.core.Resource;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

/** Exercises the real buffer and WAL at the boundaries between two asynchronous SQL phases. */
class LocalDeltaTest {
    @Test void capturedCompletionPreservesNewInputConsumptionAndUnconfirmedZeroCredits(
            @TempDir Path directory) throws Exception {
        var buffer = new LocalBuffer();
        UUID endpoint = BusinessIds.next(), world = BusinessIds.next(), channel = BusinessIds.next();
        var originalItem = new Resource(Protocol.ITEM, new byte[]{1});
        var laterItem = new Resource(Protocol.ITEM, new byte[]{2});
        var energy = new Resource(Protocol.FE, new byte[0]);
        var first = credit(channel, energy, 40);
        var lateZero = credit(channel, energy, 9);
        var confirmedZero = credit(channel, energy, 5);
        assertEquals(9, buffer.insert(originalItem, 0, 9, false));
        buffer.credit(first);
        buffer.credit(lateZero);
        buffer.credit(confirmedZero);
        assertEquals(5, buffer.extract(confirmedZero.transaction(), 5, false));
        var captured = buffer.snapshot(endpoint, world, 1, channel, true);
        var committed = Set.of(captured.deposits().getFirst().transaction());
        var journal = new LocalJournal(directory);
        journal.write(captured);

        assertEquals(7, buffer.insert(laterItem, 1, 7, false));
        assertEquals(17, buffer.extract(first.transaction(), 17, false));
        assertEquals(9, buffer.extract(lateZero.transaction(), 9, false));
        buffer.committed(committed);
        buffer.checkpointed(Set.of(confirmedZero.transaction()));
        buffer.credit(first);
        assertEquals(23, buffer.receiveAmount(Protocol.FE), "an old credit must not restore captured remaining");
        var incoming = credit(channel, energy, 4);
        long previewVersion = buffer.revision();
        assertEquals(List.of(incoming), buffer.admissible(List.of(incoming)));
        assertEquals(previewVersion, buffer.revision());
        assertEquals(0, buffer.extract(incoming.transaction(), 4, false), "preview does not make SQL credit usable");

        buffer.touch();
        var current = buffer.snapshot(endpoint, world, 1, channel, true);
        assertTrue(current.revision() > captured.revision());
        assertEquals(1, current.deposits().size());
        assertEquals(laterItem, current.deposits().getFirst().resource());
        assertEquals(7, current.deposits().getFirst().amount());
        assertFalse(committed.contains(current.deposits().getFirst().transaction()),
                "accepted input after capture needs a new stable business ID");
        assertEquals(0, current.credits().stream().filter(c -> c.transaction().equals(lateZero.transaction()))
                .findFirst().orElseThrow().remaining(), "a later zero was not in the confirmed SQL checkpoint");
        var durable = withCredits(current, List.of(incoming));

        // Further main-thread I/O while the immutable destination checkpoint is being fsynced.
        assertEquals(3, buffer.extract(first.transaction(), 3, false));
        assertEquals(2, buffer.insert(laterItem, 2, 2, false));
        journal.write(durable);
        assertEquals(20, buffer.receiveAmount(Protocol.FE));
        buffer.credit(incoming); // SQL publication succeeds only after the preceding fsync.
        assertEquals(2, buffer.extract(incoming.transaction(), 2, false));
        buffer.credit(incoming);
        buffer.committed(committed);
        buffer.checkpointed(Set.of(confirmedZero.transaction()));
        assertEquals(22, buffer.receiveAmount(Protocol.FE));
        assertEquals(9, buffer.sendAmount(Protocol.ITEM));
        buffer.touch();
        var closing = buffer.snapshot(endpoint, world, 1, channel, true);
        journal.write(closing);
        assertEquals(closing, journal.read(endpoint).orElseThrow());
        assertEquals(2, closing.deposits().size());
        assertEquals(2, closing.deposits().stream().map(d -> d.transaction()).distinct().count());
        assertEquals(40, captured.credits().getFirst().remaining(), "captured worker data is immutable");
        assertEquals(9, captured.deposits().getFirst().amount());
        assertEquals(58, 5 + 17 + 9 + 3 + 2 + buffer.receiveAmount(Protocol.FE));

        var restored = new LocalBuffer();
        restored.restore(journal.read(endpoint).orElseThrow());
        assertEquals(22, restored.receiveAmount(Protocol.FE));
        assertEquals(9, restored.sendAmount(Protocol.ITEM));
        assertTrue(restored.dirty(), "recovery must confirm the WAL's remaining values in SQL");
        assertTrue(restored.revision() > closing.revision());
    }

    @Test void identicalWalVersionsMayRepeatButDifferentContentsAndOldVersionsAreRejected(
            @TempDir Path directory) throws Exception {
        var buffer = new LocalBuffer();
        UUID endpoint = BusinessIds.next(), world = BusinessIds.next(), channel = BusinessIds.next();
        var energy = new Resource(Protocol.FE, new byte[0]);
        var original = credit(channel, energy, 15);
        buffer.credit(original);
        var captured = buffer.snapshot(endpoint, world, 1, channel, true);
        var journal = new LocalJournal(directory);
        journal.write(captured);
        journal.write(captured);
        assertEquals(1, journal.stats().get("wal_writes").longValue());
        assertEquals(1, journal.stats().get("wal_identical_skipped").longValue());
        var changedContent = new LocalSnapshot(endpoint, world, 1, captured.revision(), List.of(),
                List.of(new Credit(original.transaction(), channel, energy, 15, 14)));
        assertEquals("checkpoint_version_conflict",
                assertThrows(DomainException.class, () -> journal.write(changedContent)).code());
        assertEquals(captured, journal.read(endpoint).orElseThrow());

        assertEquals(1, buffer.extract(original.transaction(), 1, false));
        var latest = buffer.snapshot(endpoint, world, 1, channel, true);
        journal.write(latest);
        assertEquals("stale_checkpoint", assertThrows(DomainException.class, () -> journal.write(captured)).code());
        assertEquals(latest, journal.read(endpoint).orElseThrow());
        assertEquals(2, journal.stats().get("wal_writes").longValue());
    }

    @Test void prospectiveAdmissionIsNonMutatingAndAccountsForAllIncomingCreditsTogether() {
        UUID channel = BusinessIds.next();
        var energy = new Resource(Protocol.FE, new byte[0]);
        long capacity = LocalBuffer.slotCapacity(Protocol.FE);
        var buffer = new LocalBuffer();
        var existing = credit(channel, energy, capacity - 1);
        buffer.credit(existing);
        var first = credit(channel, energy, 1);
        var second = credit(channel, energy, 1);
        long before = buffer.revision();
        boolean dirty = buffer.dirty();
        assertEquals(List.of(first), buffer.admissible(List.of(first, second)));
        assertEquals(before, buffer.revision());
        assertEquals(dirty, buffer.dirty());
        assertEquals(capacity - 1, buffer.receiveAmount(Protocol.FE));
        assertEquals(0, buffer.extract(first.transaction(), 1, false));
        buffer.credit(first);
        assertTrue(buffer.admissible(List.of(second)).isEmpty());
        assertEquals(1, buffer.extract(existing.transaction(), 1, false));
        assertEquals(List.of(second), buffer.admissible(List.of(second)));
        buffer.credit(second);
        assertEquals(capacity, buffer.receiveAmount(Protocol.FE));

        assertEquals(1, buffer.extract(first.transaction(), 1, false));
        before = buffer.revision();
        assertTrue(buffer.admissible(List.of(first)).isEmpty(), "a stale known credit is never admitted again");
        buffer.credit(first);
        assertEquals(before, buffer.revision());
        assertEquals(capacity - 1, buffer.receiveAmount(Protocol.FE));
        var conflict = new Credit(first.transaction(), BusinessIds.next(), energy, first.original(), 1);
        assertEquals("idempotency_conflict",
                assertThrows(DomainException.class, () -> buffer.admissible(List.of(conflict))).code());
        assertEquals(before, buffer.revision());
    }

    @Test void prospectiveAdmissionHonorsPerKindCountsAndGlobalUnconfirmedTombstones() {
        UUID channel = BusinessIds.next();
        for (String kind : List.of(Protocol.ITEM, Protocol.FLUID, Protocol.CHEMICAL, Protocol.FE, Protocol.EU)) {
            var buffer = new LocalBuffer();
            var resource = new Resource(kind, new byte[]{1});
            int limit = LocalBuffer.creditLimit(kind);
            for (int i = 1; i < limit; i++) buffer.credit(credit(channel, resource, 1));
            var first = credit(channel, resource, 1);
            var second = credit(channel, resource, 1);
            long version = buffer.revision();
            assertEquals(List.of(first), buffer.admissible(List.of(first, second)), kind);
            assertEquals(version, buffer.revision(), kind);
            assertEquals(limit - 1, buffer.received(kind).size(), kind);
            buffer.credit(first);
            assertEquals(limit, buffer.received(kind).size(), kind);
            assertTrue(buffer.admissible(List.of(second)).isEmpty(), kind);
        }

        var tombstones = new ArrayList<Credit>();
        var energy = new Resource(Protocol.FE, new byte[0]);
        for (int i = 0; i < 64; i++) tombstones.add(new Credit(BusinessIds.next(), channel, energy, 1, 0));
        var full = new LocalBuffer();
        full.restore(new LocalSnapshot(BusinessIds.next(), BusinessIds.next(), 1, 3, List.of(), tombstones));
        var incoming = credit(channel, new Resource(Protocol.ITEM, new byte[]{1}), 1);
        long version = full.revision();
        assertTrue(full.admissible(List.of(incoming)).isEmpty());
        assertEquals(version, full.revision());
        full.checkpointed(tombstones.stream().map(Credit::transaction).collect(Collectors.toSet()));
        assertEquals(List.of(incoming), full.admissible(List.of(incoming)));
    }

    @Test void randomizedCapturedDeltasAndWalRestorationConserveWithFixedSeed(@TempDir Path directory)
            throws Exception {
        final long seed = 2026100601L;
        final int scenarios = 64;
        System.out.println("LocalDeltaTest seed=" + seed + " scenarios=" + scenarios);
        var random = new Random(seed);
        var journal = new LocalJournal(directory);
        var energy = new Resource(Protocol.FE, new byte[0]);
        for (int scenario = 0; scenario < scenarios; scenario++) {
            String context = "seed=" + seed + " scenario=" + scenario;
            UUID endpoint = uuid(random), world = uuid(random), channel = uuid(random);
            var buffer = new LocalBuffer();
            var originalItem = new Resource(Protocol.ITEM, new byte[]{1, (byte)scenario});
            var laterItem = new Resource(Protocol.ITEM, new byte[]{2, (byte)scenario});
            long sent = 1 + random.nextInt(32);
            assertEquals(sent, buffer.insert(originalItem, 0, sent, false), context);
            var first = new Credit(uuid(random), channel, energy, 1 + random.nextInt(5000), 0);
            first = new Credit(first.transaction(), channel, energy, first.original(), first.original());
            var second = new Credit(uuid(random), channel, energy, 1 + random.nextInt(1000), 0);
            second = new Credit(second.transaction(), channel, energy, second.original(), second.original());
            buffer.credit(first);
            buffer.credit(second);
            long firstRemaining = first.remaining(), secondRemaining = second.remaining(), extracted = 0;
            long initialAsk = random.nextInt((int)firstRemaining + 1);
            assertEquals(initialAsk, buffer.extract(first.transaction(), initialAsk, false), context);
            firstRemaining -= initialAsk;
            extracted += initialAsk;
            if (random.nextBoolean()) {
                assertEquals(secondRemaining, buffer.extract(second.transaction(), secondRemaining, false), context);
                extracted += secondRemaining;
                secondRemaining = 0;
            }
            var captured = buffer.snapshot(endpoint, world, 1, channel, true);
            journal.write(captured);
            Set<UUID> committed = captured.deposits().stream().map(d -> d.transaction()).collect(Collectors.toSet());
            Set<UUID> consumed = captured.credits().stream().filter(c -> c.remaining() == 0)
                    .map(Credit::transaction).collect(Collectors.toSet());
            long laterInput = 0;
            for (int step = 0; step < 8; step++) {
                long ask = random.nextInt(2001);
                boolean useFirst = random.nextBoolean();
                UUID id = useFirst ? first.transaction() : second.transaction();
                long expected = Math.min(ask, useFirst ? firstRemaining : secondRemaining);
                long version = buffer.revision();
                assertEquals(expected, buffer.extract(id, ask, true), context);
                assertEquals(version, buffer.revision(), context);
                assertEquals(expected, buffer.extract(id, ask, false), context);
                if (useFirst) firstRemaining -= expected; else secondRemaining -= expected;
                extracted += expected;
                buffer.credit(useFirst ? first : second);
                assertEquals(firstRemaining + secondRemaining, buffer.receiveAmount(Protocol.FE), context);
                laterInput += buffer.insert(laterItem, 1, random.nextInt(17), false);
            }
            buffer.committed(committed);
            buffer.checkpointed(consumed);
            var incoming = new Credit(uuid(random), channel, energy, 1 + random.nextInt(2000), 0);
            incoming = new Credit(incoming.transaction(), channel, energy, incoming.original(), incoming.original());
            long previewVersion = buffer.revision();
            assertEquals(List.of(incoming), buffer.admissible(List.of(incoming)), context);
            assertEquals(previewVersion, buffer.revision(), context);
            assertEquals(firstRemaining + secondRemaining, buffer.receiveAmount(Protocol.FE), context);
            buffer.touch();
            var current = buffer.snapshot(endpoint, world, 1, channel, true);
            assertEquals(laterInput, current.deposits().stream().mapToLong(d -> d.amount()).sum(), context);
            assertTrue(current.deposits().stream().noneMatch(d -> committed.contains(d.transaction())), context);
            var durable = withCredits(current, List.of(incoming));

            long lateAsk = random.nextInt(2001), lateExtracted = Math.min(firstRemaining, lateAsk);
            assertEquals(lateExtracted, buffer.extract(first.transaction(), lateAsk, false), context);
            firstRemaining -= lateExtracted;
            extracted += lateExtracted;
            laterInput += buffer.insert(laterItem, 2, 1 + random.nextInt(20), false);
            assertEquals(0, buffer.extract(incoming.transaction(), incoming.remaining(), false), context);
            journal.write(durable);
            buffer.credit(incoming);
            long incomingAsk = random.nextInt((int)incoming.remaining() + 1);
            assertEquals(incomingAsk, buffer.extract(incoming.transaction(), incomingAsk, false), context);
            extracted += incomingAsk;
            buffer.credit(incoming);
            buffer.committed(committed);
            buffer.checkpointed(consumed);
            buffer.touch();
            var closing = buffer.snapshot(endpoint, world, 1, channel, true);
            journal.write(closing);
            assertEquals(closing, journal.read(endpoint).orElseThrow(), context);
            var restored = new LocalBuffer();
            restored.restore(journal.read(endpoint).orElseThrow());
            assertEquals(laterInput, restored.sendAmount(Protocol.ITEM), context);
            assertEquals(firstRemaining + secondRemaining + incoming.remaining() - incomingAsk,
                    restored.receiveAmount(Protocol.FE), context);
            assertEquals(first.original() + second.original() + incoming.original(),
                    extracted + restored.receiveAmount(Protocol.FE), context);
            assertEquals(sent + laterInput, sent + closing.deposits().stream().mapToLong(d -> d.amount()).sum(), context);
            assertTrue(restored.dirty(), context);
            assertTrue(restored.revision() > closing.revision(), context);
        }
    }

    private static Credit credit(UUID channel, Resource resource, long amount) {
        return new Credit(BusinessIds.next(), channel, resource, amount, amount);
    }

    private static LocalSnapshot withCredits(LocalSnapshot snapshot, List<Credit> incoming) {
        var credits = new ArrayList<>(snapshot.credits());
        credits.addAll(incoming);
        return new LocalSnapshot(snapshot.endpoint(), snapshot.world(), snapshot.generation(), snapshot.revision(),
                snapshot.deposits(), credits, snapshot.thermal());
    }

    private static UUID uuid(Random random) {
        return new UUID(random.nextLong(), random.nextLong());
    }
}
