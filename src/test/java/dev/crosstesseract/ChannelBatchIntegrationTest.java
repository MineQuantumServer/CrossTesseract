package dev.crosstesseract;

import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.BackendConfig;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.backend.TransferWork;
import dev.crosstesseract.core.BusinessIds;
import dev.crosstesseract.core.DomainException;
import dev.crosstesseract.core.LocalBuffer;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.LocalSnapshot.Credit;
import dev.crosstesseract.core.LocalSnapshot.Deposit;
import dev.crosstesseract.core.Models.Allocation;
import dev.crosstesseract.core.Models.Endpoint;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.core.Resource;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Real MySQL tests with three independent Authority instances, without Minecraft JVMs. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ChannelBatchIntegrationTest {
    private final String cluster = "test_" + BusinessIds.next().toString().replace("-", "");
    private final UUID owner = BusinessIds.next();
    private final List<Authority> servers = new ArrayList<>();
    private final List<BackendConfig> configs = new ArrayList<>();
    private int deviceSequence;

    @BeforeAll void start() throws Exception {
        assumeTrue(Boolean.getBoolean("ct.integration"),
                "requires real isolated MySQL; run -Dct.integration=true");
        for (int i = 0; i < 3; i++) {
            var config = new BackendConfig(true, cluster, "batch-" + i,
                    "jdbc:mysql://127.0.0.1:13306/cross_tesseract?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectTimeout=1000&socketTimeout=3000",
                    "ct_dev", "ct_dev_only", "redis://127.0.0.1:16379", 2, 4, 200, 128, 32, 256);
            configs.add(config);
            var authority = new Authority(config);
            servers.add(authority);
            authority.join(BusinessIds.next(), BusinessIds.next(), Protocol.BASE);
        }
    }

    @BeforeEach void renew() throws Exception {
        for (var authority : servers) authority.heartbeat();
    }

    @AfterAll void finish() {
        for (var authority : servers) {
            try { authority.stopClean(); } catch (Exception ignored) {}
            authority.close();
        }
    }

    @Test void multipleDeviceSqlAndWalPublicationPhasesEachCommitOneTransaction(@TempDir Path directory)
            throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("phase-transactions");
        var firstSender = bound(0, owner, channel);
        var secondSender = bound(0, owner, channel);
        var firstReceiver = bound(0, owner, channel);
        var secondReceiver = bound(0, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        var firstDeposit = new Deposit(BusinessIds.next(), channel, resource, 56);
        var secondDeposit = new Deposit(BusinessIds.next(), channel, resource, 44);
        var firstDemand = demand(resource, 30);
        var secondDemand = demand(resource, 40);
        var requests = List.of(
                send(0, firstSender, channel, firstDeposit),
                send(0, secondSender, channel, secondDeposit),
                receive(0, firstReceiver, channel, List.of(), firstDemand),
                receive(0, secondReceiver, channel, List.of(), secondDemand));
        var journal = new LocalJournal(directory);
        for (var request : requests) journal.write(request.snapshot());

        long before = transactions(authority);
        long remoteBefore = transactions(servers.get(1)) + transactions(servers.get(2));
        var results = authority.channelBatch(channel, requests);
        assertEquals(1, transactions(authority) - before,
                "deposits, demand registration and allocations must share one SQL transaction");
        assertEquals(remoteBefore, transactions(servers.get(1)) + transactions(servers.get(2)));
        assertEquals(Set.of(firstDeposit.transaction()), result(results, firstSender.id()).committed());
        assertEquals(Set.of(secondDeposit.transaction()), result(results, secondSender.id()).committed());
        var firstCredit = singleCredit(result(results, firstReceiver.id()));
        var secondCredit = singleCredit(result(results, secondReceiver.id()));
        assertEquals(firstDemand.transaction(), firstCredit.transaction());
        assertEquals(secondDemand.transaction(), secondCredit.transaction());
        assertEquals(30, firstCredit.remaining());
        assertEquals(40, secondCredit.remaining());
        assertEquals("RESERVED", state(firstCredit.transaction()));
        assertEquals("RESERVED", state(secondCredit.transaction()));
        assertConserved(channel, resource, 100);

        var publications = new ArrayList<TransferWork.Publication>();
        for (var request : requests) {
            publications.add(durablePublication(journal, request, result(results, request.endpoint())));
        }
        assertTrue(journal.read(firstReceiver.id()).orElseThrow().credits().contains(firstCredit));
        assertTrue(journal.read(secondReceiver.id()).orElseThrow().credits().contains(secondCredit));
        assertEquals("RESERVED", state(firstCredit.transaction()), "WAL fsync is separate from publication");
        before = transactions(authority);
        assertTrue(authority.publishBatch(channel, publications).isEmpty());
        assertEquals(1, transactions(authority) - before,
                "the separately fenced publication phase must also commit one SQL transaction");
        assertEquals("LOCAL", state(firstCredit.transaction()));
        assertEquals("LOCAL", state(secondCredit.transaction()));
        assertEquals(30, balance(channel, resource));
        assertConserved(channel, resource, 100);
    }

    @Test void registeredRemoteDemandKeepsPriorityOverLocalBatchesAndAllThreeAuthoritiesConserve()
            throws Exception {
        UUID channel = channel("global-fairness");
        var sender = bound(0, owner, channel);
        var remoteFirst = bound(1, owner, channel);
        var local = bound(0, owner, channel);
        var remoteLast = bound(2, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        servers.get(0).deposit(BusinessIds.next(), sender.id(), channel, resource, 90);
        servers.get(1).demand(remoteFirst.id(), channel, Protocol.FE, 30);
        servers.get(2).demand(remoteLast.id(), channel, Protocol.FE, 30);
        var localDemand = demand(resource, 30);
        var localRequest = receive(0, local, channel, List.of(), localDemand);

        var deferred = singleResult(servers.get(0).channelBatch(channel, List.of(localRequest)));
        assertNull(deferred.error());
        assertTrue(deferred.received().isEmpty(), "a local batch must not bypass the oldest remote demand");
        assertEquals(90, balance(channel, resource));

        var first = singleCredit(singleResult(servers.get(1).channelBatch(channel,
                List.of(receive(1, remoteFirst, channel, List.of(), demand(resource, 30))))));
        var second = singleCredit(singleResult(servers.get(0).channelBatch(channel, List.of(localRequest))));
        var third = singleCredit(singleResult(servers.get(2).channelBatch(channel,
                List.of(receive(2, remoteLast, channel, List.of(), demand(resource, 30))))));
        assertEquals(localDemand.transaction(), second.transaction());
        assertEquals(3, new HashSet<>(List.of(first.transaction(), second.transaction(), third.transaction())).size());
        assertEquals(30, first.remaining());
        assertEquals(30, second.remaining());
        assertEquals(30, third.remaining());
        assertEquals(0, balance(channel, resource));
        assertEquals(1, lastGrant(remoteFirst.id(), channel, Protocol.FE));
        assertEquals(2, lastGrant(local.id(), channel, Protocol.FE));
        assertEquals(3, lastGrant(remoteLast.id(), channel, Protocol.FE));
        assertConserved(channel, resource, 90);
    }

    @Test void replayingCapturedBusinessIdsDoesNotDuplicateDepositsCreditsOrPublication(@TempDir Path directory)
            throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("batch-idempotency");
        var sender = bound(0, owner, channel);
        var receiver = bound(0, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        var deposit = new Deposit(BusinessIds.next(), channel, resource, 70);
        var wanted = demand(resource, 20);
        var requests = List.of(send(0, sender, channel, deposit), receive(0, receiver, channel, List.of(), wanted));
        var first = authority.channelBatch(channel, requests);
        var repeated = authority.channelBatch(channel, requests);
        var credit = singleCredit(result(first, receiver.id()));
        assertEquals(credit, singleCredit(result(repeated, receiver.id())));
        assertEquals(wanted.transaction(), credit.transaction());
        assertEquals(Set.of(deposit.transaction()), result(repeated, sender.id()).committed());
        assertEquals(1, transferCount(sender.id(), "DEPOSIT"));
        assertEquals(1, transferCount(receiver.id(), "ALLOCATE"));
        assertEquals(50, balance(channel, resource));
        assertConserved(channel, resource, 70);

        var journal = new LocalJournal(directory);
        var publication = durablePublication(journal, requests.get(1), result(first, receiver.id()));
        assertTrue(authority.publishBatch(channel, List.of(publication)).isEmpty());
        long before = transactions(authority);
        assertTrue(authority.publishBatch(channel, List.of(publication)).isEmpty());
        assertEquals(1, transactions(authority) - before);
        assertEquals("LOCAL", state(credit.transaction()));
        assertEquals(1, transferCount(receiver.id(), "ALLOCATE"));
        assertConserved(channel, resource, 70);
    }

    @Test void staleVersionAndRevokedEndpointRollBackTheirSavepointsWhileAnotherDeviceCommits()
            throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("endpoint-isolation");
        UUID member = BusinessIds.next();
        addMember(channel, member);
        var stale = bound(0, owner, channel);
        var revoked = bound(0, member, channel);
        var healthy = bound(0, owner, channel);
        authority.permissions(owner, channel, channelVersion(channel), member, Protocol.VIEW);
        var resource = new Resource(Protocol.FE, new byte[0]);
        var staleDeposit = new Deposit(BusinessIds.next(), channel, resource, 10);
        var revokedDeposit = new Deposit(BusinessIds.next(), channel, resource, 25);
        var goodDeposit = new Deposit(BusinessIds.next(), channel, resource, 40);
        var staleRequest = send(0, stale, channel, staleDeposit);
        staleRequest = new TransferWork.Request(staleRequest.snapshot(), channel, stale.version() - 1,
                staleRequest.checkpoint(), staleRequest.sending(), staleRequest.demands(), staleRequest.depositLimit());
        long before = transactions(authority);
        var results = authority.channelBatch(channel, List.of(staleRequest,
                send(0, revoked, channel, revokedDeposit), send(0, healthy, channel, goodDeposit)));
        assertEquals(1, transactions(authority) - before);
        assertEquals("stale_version", result(results, stale.id()).error());
        assertEquals("forbidden", result(results, revoked.id()).error());
        assertNull(result(results, healthy.id()).error());
        assertEquals(Set.of(goodDeposit.transaction()), result(results, healthy.id()).committed());
        assertEquals(0, transferCount(stale.id(), "DEPOSIT"));
        assertEquals(0, transferCount(revoked.id(), "DEPOSIT"));
        assertEquals(0, endpointCheckpoint(stale.id()));
        assertEquals(0, endpointCheckpoint(revoked.id()));
        assertEquals(1, endpointCheckpoint(healthy.id()));
        assertEquals(40, balance(channel, resource));
        assertConserved(channel, resource, 40);
    }

    @Test void fullOwnedItemAndFeCandidatesIncludingQuarantineCannotBlockOtherServers() throws Exception {
        for (String kind : List.of(Protocol.ITEM, Protocol.FE)) {
            int limit = kind.equals(Protocol.ITEM) ? 9 : 32;
            UUID channel = channel("full-owned-" + kind.substring(kind.indexOf(':') + 1));
            var sender = bound(0, owner, channel);
            var full = bound(1, owner, channel);
            var healthy = bound(2, owner, channel);
            var resource = new Resource(kind, kind.equals(Protocol.ITEM) ? new byte[]{1, 2, 3} : new byte[0]);
            servers.get(0).deposit(BusinessIds.next(), sender.id(), channel, resource, limit + 10L);
            var owned = new ArrayList<Allocation>();
            for (int i = 0; i < limit; i++) {
                servers.get(1).demand(full.id(), channel, kind, 1);
                owned.add(servers.get(1).allocate(BusinessIds.next(), full.id(), channel, kind, 1).orElseThrow());
            }
            for (var allocation : owned) {
                servers.get(1).quarantineAllocation(full.id(), allocation.id(), "test_owned_capacity");
            }
            renew();
            servers.get(1).demand(full.id(), channel, kind, 1);
            servers.get(2).demand(healthy.id(), channel, kind, 1);
            var initialHealthy = servers.get(2).allocate(BusinessIds.next(), healthy.id(), channel, kind, 1)
                    .orElseThrow();
            assertTrue(lastGrant(full.id(), channel, kind) < lastGrant(healthy.id(), channel, kind),
                    "the full candidate must be older, so this checks exclusion before choosing the head");
            var wanted = demand(resource, 1);
            var previous = credit(initialHealthy);
            var received = singleCredit(singleResult(servers.get(2).channelBatch(channel,
                    List.of(receive(2, healthy, channel, List.of(previous), wanted)))));
            assertEquals(wanted.transaction(), received.transaction(),
                    "a full quarantined candidate must not block a different server's fresh allocation");
            assertEquals(limit, ownedCount(full.id(), kind));
            for (var allocation : owned) assertEquals("QUARANTINED", state(allocation.id()));
            assertEquals(2, ownedCount(healthy.id(), kind));
            assertEquals(8, balance(channel, resource));
            assertConserved(channel, resource, limit + 10L);
        }
    }

    @Test void differentCompletePayloadBytesRemainSeparateInDepositsAndAllocations() throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("payload-identity");
        var firstSender = bound(0, owner, channel);
        var secondSender = bound(0, owner, channel);
        var firstReceiver = bound(0, owner, channel);
        var secondReceiver = bound(0, owner, channel);
        byte[] firstBytes = new byte[1024];
        Arrays.fill(firstBytes, (byte)7);
        byte[] secondBytes = firstBytes.clone();
        secondBytes[secondBytes.length - 1] = 8;
        var firstResource = new Resource(Protocol.ITEM, firstBytes);
        var secondResource = new Resource(Protocol.ITEM, secondBytes);
        var firstDeposit = new Deposit(BusinessIds.next(), channel, firstResource, 7);
        var secondDeposit = new Deposit(BusinessIds.next(), channel, secondResource, 11);
        var requests = List.of(send(0, firstSender, channel, firstDeposit),
                send(0, secondSender, channel, secondDeposit),
                receive(0, firstReceiver, channel, List.of(), demand(firstResource, 5)),
                receive(0, secondReceiver, channel, List.of(), demand(secondResource, 9)));
        var results = authority.channelBatch(channel, requests);
        var firstCredit = singleCredit(result(results, firstReceiver.id()));
        var secondCredit = singleCredit(result(results, secondReceiver.id()));
        assertArrayEquals(firstBytes, firstCredit.resource().bytes());
        assertArrayEquals(secondBytes, secondCredit.resource().bytes());
        assertNotEquals(firstCredit.resource(), secondCredit.resource());
        assertEquals(2, resourceCount(channel));
        assertConserved(channel, firstResource, 7);
        assertConserved(channel, secondResource, 11);

        var conflicting = send(0, firstSender, channel,
                new Deposit(firstDeposit.transaction(), channel, secondResource, firstDeposit.amount()));
        assertEquals("idempotency_conflict", singleResult(authority.channelBatch(channel, List.of(conflicting))).error());
        assertConserved(channel, firstResource, 7);
        assertConserved(channel, secondResource, 11);
    }

    @Test void longOverflowRollsBackOneDeviceIncludingItsNewResourceWhileOtherDevicesCommit()
            throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("long-and-savepoint");
        var failing = bound(0, owner, channel);
        var healthy = bound(0, owner, channel);
        var receiver = bound(1, owner, channel);
        var energy = new Resource(Protocol.FE, new byte[0]);
        var fluid = new Resource(Protocol.FLUID, new byte[]{9, 8, 7});
        long original = Long.MAX_VALUE - 4;
        authority.deposit(BusinessIds.next(), failing.id(), channel, energy, original);
        var rolledBackResource = new Deposit(BusinessIds.next(), channel, fluid, 100);
        var overflow = new Deposit(BusinessIds.next(), channel, energy, 10);
        var committed = new Deposit(BusinessIds.next(), channel, fluid, 123);
        long before = transactions(authority);
        var results = authority.channelBatch(channel, List.of(
                send(0, failing, channel, rolledBackResource, overflow), send(0, healthy, channel, committed)));
        assertEquals(1, transactions(authority) - before);
        assertEquals("quantity_overflow", result(results, failing.id()).error());
        assertTrue(result(results, failing.id()).committed().isEmpty());
        assertNull(result(results, healthy.id()).error());
        assertEquals(Set.of(committed.transaction()), result(results, healthy.id()).committed());
        assertEquals(0, transferExists(rolledBackResource.transaction()));
        assertEquals(0, transferExists(overflow.transaction()));
        assertEquals(original, balance(channel, energy));
        assertEquals(123, balance(channel, fluid), "rollback must invalidate a resource ID cached before commit");
        assertConserved(channel, energy, original);
        assertConserved(channel, fluid, 123);

        var received = singleCredit(singleResult(servers.get(1).channelBatch(channel,
                List.of(receive(1, receiver, channel, List.of(), demand(energy, 7))))));
        assertEquals(7, received.remaining());
        assertEquals(original - 7, balance(channel, energy));
        assertConserved(channel, energy, original);
    }

    @Test void freshPublicationAuthorizationRejectsRevokedCreditWithoutRefundAndKeepsOthersWorking(
            @TempDir Path directory) throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("publish-permission");
        UUID member = BusinessIds.next();
        addMember(channel, member);
        var sender = bound(0, owner, channel);
        var revoked = bound(0, member, channel);
        var healthy = bound(0, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        authority.deposit(BusinessIds.next(), sender.id(), channel, resource, 100);
        var requests = List.of(receive(0, revoked, channel, List.of(), demand(resource, 10)),
                receive(0, healthy, channel, List.of(), demand(resource, 10)));
        var results = authority.channelBatch(channel, requests);
        var revokedCredit = singleCredit(result(results, revoked.id()));
        var healthyCredit = singleCredit(result(results, healthy.id()));
        var journal = new LocalJournal(directory);
        var publications = new ArrayList<TransferWork.Publication>();
        for (var request : requests) {
            publications.add(durablePublication(journal, request, result(results, request.endpoint())));
        }
        authority.permissions(owner, channel, channelVersion(channel), member, Protocol.VIEW);
        long before = transactions(authority);
        var errors = authority.publishBatch(channel, publications);
        assertEquals(1, transactions(authority) - before);
        assertEquals(Map.of(revoked.id(), "forbidden"), errors);
        assertEquals("RESERVED", state(revokedCredit.transaction()));
        assertEquals("LOCAL", state(healthyCredit.transaction()));
        assertEquals(0, endpointCheckpoint(revoked.id()));
        assertEquals(2, endpointCheckpoint(healthy.id()));
        assertEquals(80, balance(channel, resource), "permission loss must not refund an owned credit");
        assertEquals(10, remaining(revokedCredit.transaction()));
        assertConserved(channel, resource, 100);
    }

    @Test void exhaustedWalCreditSurvivesRestoreUntilSqlCheckpointAndCannotBeRediscovered(
            @TempDir Path directory) throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("zero-wal-recovery");
        var sender = bound(0, owner, channel);
        var receiver = bound(0, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        authority.deposit(BusinessIds.next(), sender.id(), channel, resource, 35);
        authority.demand(receiver.id(), channel, Protocol.FE, 35);
        var allocated = credit(authority.allocate(BusinessIds.next(), receiver.id(), channel, Protocol.FE, 35)
                .orElseThrow());
        var session = authority.session();
        var journal = new LocalJournal(directory);
        var initial = new LocalSnapshot(receiver.id(), session.world(), session.generation(), 1,
                List.of(), List.of(allocated));
        journal.write(initial);
        assertTrue(authority.publishBatch(channel, List.of(new TransferWork.Publication(initial, channel,
                receiver.version(), List.of(allocated), Map.of()))).isEmpty());

        var local = new LocalBuffer();
        local.restore(initial);
        assertEquals(35, local.extract(allocated.transaction(), 35, false));
        var exhausted = local.snapshot(receiver.id(), session.world(), session.generation(), channel, true);
        journal.write(exhausted);
        assertEquals(35, remaining(allocated.transaction()),
                "simulate SQL failure after an exhausted local checkpoint was fsynced");
        assertEquals("LOCAL", state(allocated.transaction()));

        var restored = authority.restoreSnapshot(journal.read(receiver.id()).orElseThrow());
        assertEquals(1, restored.credits().size(), "zero is an unconfirmed consumption tombstone");
        assertEquals(allocated.transaction(), restored.credits().getFirst().transaction());
        assertEquals(0, restored.credits().getFirst().remaining());
        assertEquals(35, remaining(allocated.transaction()), "restore must not mutate SQL ownership");
        var recovering = new LocalBuffer();
        recovering.restore(restored);
        var checkpoint = recovering.snapshot(receiver.id(), session.world(), session.generation(), channel, true);
        journal.write(checkpoint);
        var request = new TransferWork.Request(checkpoint, channel, receiver.version(), true,
                Set.of(), List.of(), 8);
        long before = transactions(authority);
        var result = singleResult(authority.channelBatch(channel, List.of(request)));
        assertEquals(1, transactions(authority) - before);
        assertNull(result.error());
        assertEquals(Set.of(allocated.transaction()), result.consumed());
        assertTrue(result.received().isEmpty(), "an exhausted WAL credit must never become an unknown credit");
        assertEquals(0, remaining(allocated.transaction()));
        assertEquals("CONSUMED", state(allocated.transaction()));

        recovering.checkpointed(result.consumed());
        var confirmed = recovering.snapshot(receiver.id(), session.world(), session.generation(), channel, true);
        journal.write(confirmed);
        var repeated = singleResult(authority.channelBatch(channel, List.of(new TransferWork.Request(confirmed,
                channel, receiver.version(), true, Set.of(), List.of(), 8))));
        assertNull(repeated.error());
        assertTrue(repeated.received().isEmpty());
        assertTrue(authority.allocations(receiver.id()).isEmpty());
        assertEquals(1, transferCount(receiver.id(), "ALLOCATE"));
        assertEquals(0, recovering.receiveAmount(Protocol.FE));
        assertEquals(0, balance(channel, resource));
    }

    @Test void oneCorruptOutstandingPayloadIsQuarantinedWithoutRollingBackHealthyDeviceWork()
            throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("corrupt-outstanding-isolation");
        var sender = bound(0, owner, channel);
        var damaged = bound(0, owner, channel);
        var healthy = bound(0, owner, channel);
        // Corruption must belong to this scenario; other tests share the isolated cluster's
        // immutable resource catalogue and may legitimately reuse ordinary ITEM payloads.
        var damagedResource = new Resource(Protocol.ITEM,
                ("corrupt-outstanding-" + BusinessIds.next()).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        authority.deposit(BusinessIds.next(), sender.id(), channel, damagedResource, 40);
        authority.demand(damaged.id(), channel, Protocol.ITEM, 12, damagedResource.hash(), 1);
        var damagedAllocation = authority.allocate(BusinessIds.next(), damaged.id(), channel, Protocol.ITEM, 12)
                .orElseThrow();
        byte[] corruptedPayload = damagedResource.bytes();
        corruptedPayload[corruptedPayload.length - 1] ^= 1;
        authority.database().transaction(connection -> {
            assertEquals(1, Sql.update(connection,
                    "UPDATE ct_resources SET payload=? WHERE cluster_id=? AND resource_id=?",
                    corruptedPayload, cluster, damagedAllocation.resource()));
            return null;
        });
        var session = authority.session();
        var damagedRequest = new TransferWork.Request(new LocalSnapshot(damaged.id(), session.world(),
                session.generation(), 1, List.of(), List.of()), channel, damaged.version(), false,
                Set.of(), List.of(), 8);
        var energy = new Resource(Protocol.FE, new byte[0]);
        var deposit = new Deposit(BusinessIds.next(), channel, energy, 17);
        var source = send(0, healthy, channel, deposit);
        var wanted = demand(energy, 5);
        var healthyRequest = new TransferWork.Request(source.snapshot(), channel, healthy.version(), true,
                source.sending(), List.of(wanted), 8);

        long before = transactions(authority);
        var results = authority.channelBatch(channel, List.of(damagedRequest, healthyRequest));
        assertEquals(1, transactions(authority) - before);
        assertTrue(result(results, damaged.id()).received().isEmpty());
        assertNull(result(results, healthy.id()).error());
        assertEquals(Set.of(deposit.transaction()), result(results, healthy.id()).committed());
        var received = singleCredit(result(results, healthy.id()));
        assertEquals(wanted.transaction(), received.transaction());
        assertEquals(5, received.remaining());
        assertEquals("RESERVED", state(received.transaction()));
        assertEquals(1, endpointCheckpoint(healthy.id()));
        assertEquals("QUARANTINED", state(damagedAllocation.id()));
        assertEquals(12, remaining(damagedAllocation.id()), "corrupt payload remains exclusively owned");
        assertEquals(1, transferCount(damaged.id(), "ALLOCATE"));
        assertEquals(1, scalar("SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND transfer_id=? AND endpoint_id=?",
                cluster, damagedAllocation.id(), damaged.id()));
        assertEquals(1, scalar("SELECT COUNT(*) AS n FROM ct_quarantine WHERE cluster_id=? AND endpoint_id=? AND transfer_id=? AND state='OPEN'",
                cluster, damaged.id(), damagedAllocation.id()));
        assertEquals(28, balance(channel, damagedResource), "quarantine must not refund the allocation");
        assertConserved(channel, damagedResource, 40);
        assertConserved(channel, energy, 17);
    }

    @Test void walReservedCreditCannotOpenAfterReceivePermissionWasRevoked(@TempDir Path directory)
            throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("reserved-recovery-permission");
        UUID member = BusinessIds.next();
        addMember(channel, member);
        var sender = bound(0, owner, channel);
        var receiver = bound(0, member, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        authority.deposit(BusinessIds.next(), sender.id(), channel, resource, 55);
        var request = receive(0, receiver, channel, List.of(), demand(resource, 20));
        var result = singleResult(authority.channelBatch(channel, List.of(request)));
        var credit = singleCredit(result);
        var journal = new LocalJournal(directory);
        var publication = durablePublication(journal, request, result);
        assertEquals("RESERVED", state(credit.transaction()));
        authority.permissions(owner, channel, channelVersion(channel), member, Protocol.VIEW);

        try {
            var restored = authority.restoreSnapshot(journal.read(receiver.id()).orElseThrow());
            assertTrue(restored.credits().stream().noneMatch(c -> c.transaction().equals(credit.transaction())),
                    "a denied RESERVED credit must be rejected or excluded before local restoration");
            assertEquals("QUARANTINED", state(credit.transaction()),
                    "successful exclusion requires durable isolation of SQL ownership");
            var local = new LocalBuffer();
            local.restore(restored);
            assertEquals(0, local.receiveAmount(Protocol.FE));
        } catch (DomainException denied) {
            assertEquals("forbidden", denied.code());
            assertEquals("RESERVED", state(credit.transaction()));
        }
        assertEquals(publication.snapshot(), journal.read(receiver.id()).orElseThrow());
        assertEquals(20, remaining(credit.transaction()), "authorization failure is never a refund");
        assertEquals(35, balance(channel, resource));
        assertConserved(channel, resource, 55);
    }

    @Test void authorizedReservedWalRecoveryConfirmsFencedSqlPublicationBeforeReturningCredit(
            @TempDir Path directory) throws Exception {
        var authority = servers.getFirst();
        UUID channel = channel("reserved-recovery-publish");
        var sender = bound(0, owner, channel);
        var receiver = bound(0, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        authority.deposit(BusinessIds.next(), sender.id(), channel, resource, 31);
        var request = receive(0, receiver, channel, List.of(), demand(resource, 15));
        var result = singleResult(authority.channelBatch(channel, List.of(request)));
        var credit = singleCredit(result);
        var journal = new LocalJournal(directory);
        var publication = durablePublication(journal, request, result);
        assertEquals("RESERVED", state(credit.transaction()));

        long before = transactions(authority);
        var restored = authority.restoreSnapshot(journal.read(receiver.id()).orElseThrow());
        assertEquals(1, transactions(authority) - before);
        assertEquals("LOCAL", state(credit.transaction()),
                "restore must confirm fresh SQL publication before handing a credit to the local buffer");
        assertEquals(publication.snapshot(), restored);
        var local = new LocalBuffer();
        local.restore(restored);
        assertEquals(15, local.receiveAmount(Protocol.FE));
        assertEquals(1, transferCount(receiver.id(), "ALLOCATE"));
        assertEquals(16, balance(channel, resource));
        assertConserved(channel, resource, 31);
    }

    @Test void aNewBootFencesBothOldSqlAndOldPublicationPhases(@TempDir Path directory) throws Exception {
        var old = servers.getFirst();
        UUID channel = channel("boot-fencing");
        var sender = bound(0, owner, channel);
        var receiver = bound(0, owner, channel);
        var resource = new Resource(Protocol.FE, new byte[0]);
        var requests = List.of(send(0, sender, channel, new Deposit(BusinessIds.next(), channel, resource, 100)),
                receive(0, receiver, channel, List.of(), demand(resource, 10)));
        var results = old.channelBatch(channel, requests);
        var received = singleCredit(result(results, receiver.id()));
        var publication = durablePublication(new LocalJournal(directory), requests.get(1),
                result(results, receiver.id()));
        UUID world = old.session().world();
        old.stopClean();
        var replacement = new Authority(configs.getFirst());
        try {
            replacement.join(world, BusinessIds.next(), Protocol.BASE);
            servers.set(0, replacement);
            replacement.registerEndpoint(sender, 1);
            replacement.registerEndpoint(receiver, 0);
            assertTrue(replacement.session().epoch() > old.session().epoch());
            rejected("session_fenced", () -> old.channelBatch(channel, requests));
            rejected("session_fenced", () -> old.publishBatch(channel, List.of(publication)));
            rejected("session_fenced", () -> old.restoreSnapshot(publication.snapshot()));
            assertEquals("RESERVED", state(received.transaction()));
            assertEquals(90, balance(channel, resource));
            assertTrue(replacement.publishBatch(channel, List.of(publication)).isEmpty());
            assertEquals("LOCAL", state(received.transaction()));
            assertConserved(channel, resource, 100);
        } finally {
            old.close();
            if (servers.getFirst() != replacement) replacement.close();
        }
    }

    private UUID channel(String name) throws Exception {
        return servers.getFirst().createChannel(owner, name, BusinessIds.next());
    }

    private Endpoint bound(int server, UUID player, UUID channel) throws Exception {
        var authority = servers.get(server);
        var session = authority.session();
        int number = ++deviceSequence;
        // Stable ascending endpoint IDs make ties in the shared SQL fairness sequence deterministic.
        UUID endpoint = new UUID(0x1000_0000_0000_0000L, number);
        var registered = authority.registerEndpoint(new Endpoint(endpoint, session.server(), session.world(),
                player, null, "minecraft:overworld", number, 64, server * 16, 1, "ACTIVE", 0, ""), 0);
        return authority.bind(player, endpoint, registered.version(), channel);
    }

    private void addMember(UUID channel, UUID member) throws Exception {
        var authority = servers.getFirst();
        UUID invitation = authority.invite(owner, channel, channelVersion(channel), member, false, BusinessIds.next());
        servers.get(1).answerInvitation(member, invitation, true);
    }

    private long channelVersion(UUID channel) throws Exception {
        return servers.getFirst().authorize(owner, channel, Protocol.VIEW).version();
    }

    private TransferWork.Request send(int server, Endpoint endpoint, UUID channel, Deposit... deposits) {
        var session = servers.get(server).session();
        var sending = Arrays.stream(deposits).map(deposit -> deposit.resource().kind()).collect(Collectors.toSet());
        var snapshot = new LocalSnapshot(endpoint.id(), session.world(), session.generation(), 1,
                List.of(deposits), List.of());
        return new TransferWork.Request(snapshot, channel, endpoint.version(), true, sending, List.of(), 8);
    }

    private TransferWork.Request receive(int server, Endpoint endpoint, UUID channel, List<Credit> known,
                                         TransferWork.Demand demand) {
        var session = servers.get(server).session();
        var snapshot = new LocalSnapshot(endpoint.id(), session.world(), session.generation(), 1, List.of(), known);
        // Some tests deliberately inspect RESERVED credits without making them usable locally.
        return new TransferWork.Request(snapshot, channel, endpoint.version(), false, Set.of(), List.of(demand), 8);
    }

    private static TransferWork.Demand demand(Resource resource, long room) {
        return new TransferWork.Demand(BusinessIds.next(), resource.kind(), room, resource.hash(), 1);
    }

    private static TransferWork.Result result(List<TransferWork.Result> results, UUID endpoint) {
        assertEquals(1, results.stream().filter(result -> endpoint.equals(result.endpoint())).count());
        return results.stream().filter(result -> endpoint.equals(result.endpoint())).findFirst().orElseThrow();
    }

    private static TransferWork.Result singleResult(List<TransferWork.Result> results) {
        assertEquals(1, results.size());
        return results.getFirst();
    }

    private static Credit singleCredit(TransferWork.Result result) {
        assertNull(result.error());
        assertEquals(1, result.received().size());
        return result.received().getFirst();
    }

    private static Credit credit(Allocation allocation) {
        return new Credit(allocation.id(), allocation.channel(), allocation.payload(), allocation.amount(),
                allocation.remaining());
    }

    private static TransferWork.Publication durablePublication(LocalJournal journal, TransferWork.Request request,
                                                               TransferWork.Result result) throws Exception {
        assertNull(result.error());
        var source = request.snapshot();
        var credits = new ArrayList<>(source.credits());
        credits.addAll(result.received());
        var snapshot = new LocalSnapshot(source.endpoint(), source.world(), source.generation(),
                Math.addExact(source.revision(), 1),
                source.deposits().stream().filter(deposit -> !result.committed().contains(deposit.transaction())).toList(),
                credits, source.thermal());
        journal.write(snapshot);
        assertEquals(snapshot, journal.read(snapshot.endpoint()).orElseThrow());
        return new TransferWork.Publication(snapshot, request.channel(), request.endpointVersion(),
                result.received(), Map.of());
    }

    private static long transactions(Authority authority) {
        return authority.database().stats().get("db_transactions").longValue();
    }

    private long scalar(String sql, Object... args) throws SQLException {
        return servers.getFirst().database().connection(connection -> Sql.num(Sql.one(connection, sql, args), "n"));
    }

    private long balance(UUID channel, Resource resource) throws SQLException {
        return scalar("SELECT COALESCE(SUM(b.amount),0) AS n FROM ct_balances b JOIN ct_resources r ON r.cluster_id=b.cluster_id AND r.resource_id=b.resource_id WHERE b.cluster_id=? AND b.channel_id=? AND r.kind=? AND r.payload_hash=?",
                cluster, channel, resource.kind(), resource.hash());
    }

    private long owned(UUID channel, Resource resource) throws SQLException {
        return scalar("SELECT COALESCE(SUM(t.remaining),0) AS n FROM ct_transfers t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE t.cluster_id=? AND t.channel_id=? AND t.kind='ALLOCATE' AND r.kind=? AND r.payload_hash=?",
                cluster, channel, resource.kind(), resource.hash());
    }

    private void assertConserved(UUID channel, Resource resource, long expected) throws SQLException {
        assertEquals(expected, Math.addExact(balance(channel, resource), owned(channel, resource)));
    }

    private long transferCount(UUID endpoint, String kind) throws SQLException {
        return scalar("SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind=?",
                cluster, endpoint, kind);
    }

    private long transferExists(UUID transaction) throws SQLException {
        return scalar("SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND transfer_id=?", cluster, transaction);
    }

    private long ownedCount(UUID endpoint, String kind) throws SQLException {
        return scalar("SELECT COUNT(*) AS n FROM ct_transfers t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id WHERE t.cluster_id=? AND t.endpoint_id=? AND t.kind='ALLOCATE' AND t.remaining>0 AND r.kind=?",
                cluster, endpoint, kind);
    }

    private long resourceCount(UUID channel) throws SQLException {
        return scalar("SELECT COUNT(DISTINCT resource_id) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?",
                cluster, channel);
    }

    private long endpointCheckpoint(UUID endpoint) throws SQLException {
        return scalar("SELECT checkpoint AS n FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?", cluster, endpoint);
    }

    private long lastGrant(UUID endpoint, UUID channel, String kind) throws SQLException {
        return scalar("SELECT last_grant AS n FROM ct_demands WHERE cluster_id=? AND endpoint_id=? AND channel_id=? AND kind=?",
                cluster, endpoint, channel, kind);
    }

    private long remaining(UUID transaction) throws SQLException {
        return scalar("SELECT remaining AS n FROM ct_transfers WHERE cluster_id=? AND transfer_id=?", cluster, transaction);
    }

    private String state(UUID transaction) throws SQLException {
        return servers.getFirst().database().connection(connection -> Sql.str(Sql.one(connection,
                "SELECT state FROM ct_transfers WHERE cluster_id=? AND transfer_id=?", cluster, transaction), "state"));
    }

    private static void rejected(String code, org.junit.jupiter.api.function.Executable action) {
        assertEquals(code, assertThrows(DomainException.class, action).code());
    }
}
