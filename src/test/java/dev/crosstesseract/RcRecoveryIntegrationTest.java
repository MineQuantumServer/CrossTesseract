package dev.crosstesseract;

import dev.crosstesseract.backend.Authority;
import dev.crosstesseract.backend.BackendConfig;
import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.backend.Sql;
import dev.crosstesseract.backend.TransferWork;
import dev.crosstesseract.core.BusinessIds;
import dev.crosstesseract.core.LocalBuffer;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.LocalSnapshot.Credit;
import dev.crosstesseract.core.Models.Endpoint;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.core.Resource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * Real MySQL COMMIT OK loss, real LocalJournal and actual production LocalBuffer.
 * No Minecraft JVM/capability, world rollback, historical fixture, injected SQL
 * exception or hardware power-loss claim. New fixtures and raw evidence are kept.
 */
@Execution(ExecutionMode.SAME_THREAD)
@ResourceLock("rc_mysql_ack_proxy_13307")
class RcRecoveryIntegrationTest {
    private static final Path ROOT = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
    private static final Resource FE = new Resource(Protocol.FE, new byte[0]);

    @BeforeAll static void isolatedRealBackendRequired() {
        assumeTrue(Boolean.getBoolean("ct.integration"), "requires the isolated real MySQL; -Dct.integration=true");
    }

    @Test void depositCommitOkIsLostOnWireAndOriginalWalBusinessIdCreditsOnlyOnce() throws Exception {
        try (var fixture = new Fixture("deposit")) {
            var sender = fixture.bound();
            var source = new LocalBuffer();
            assertEquals(128, source.insert(FE, 128, false));
            var prepared = source.snapshot(sender.id(), fixture.world, fixture.generation(), fixture.channel, true);
            assertEquals(1, prepared.deposits().size());
            var deposit = prepared.deposits().getFirst();
            fixture.journal.write(prepared);
            assertEquals(prepared, fixture.journal.read(sender.id()).orElseThrow());
            fixture.captureWal("before_commit", sender.id());
            fixture.authority.heartbeat();
            fixture.arm(deposit.transaction());

            var lost = assertThrows(SQLException.class, () -> fixture.authority.deposit(
                    deposit.transaction(), sender.id(), fixture.channel, FE, 128));
            fixture.assertRealDroppedOk(deposit.transaction(), lost);
            var committed = fixture.transfer(deposit.transaction()); // Separate direct :13306 connection.
            assertEquals("DEPOSIT", Sql.str(committed, "kind"));
            assertEquals("COMMITTED", Sql.str(committed, "state"));
            assertEquals(128, Sql.num(committed, "amount"));
            assertEquals(0, Sql.num(committed, "remaining"));
            assertEquals(128, fixture.balance());
            assertEquals(1, fixture.transferCount(sender.id(), "DEPOSIT"));
            assertEquals(prepared, fixture.journal.read(sender.id()).orElseThrow(),
                    "the unresolved WAL intent is not a second copy of SQL's 128 FE");
            fixture.evidence.put("post_lost_response", fixture.ledger());

            fixture.authority.heartbeat();
            fixture.authority.deposit(deposit.transaction(), sender.id(), fixture.channel, FE, 128);
            assertEquals(1, fixture.transferCount(sender.id(), "DEPOSIT"));
            assertEquals(128, fixture.balance(), "same-ID retry must not duplicate or refund committed input");
            source.committed(List.of(deposit.transaction()));
            var acknowledged = source.snapshot(sender.id(), fixture.world, fixture.generation(), fixture.channel, true);
            fixture.journal.write(acknowledged);
            fixture.authority.checkpoint(sender.id(), acknowledged.revision(), Map.of());
            assertEquals(0, source.sendAmount(Protocol.FE));
            assertTrue(fixture.journal.read(sender.id()).orElseThrow().deposits().isEmpty());
            fixture.captureWal("after_same_id_acknowledgement", sender.id());
            fixture.evidence.put("after_same_id_retry", fixture.ledger());
            fixture.complete(128, 0);
        }
    }

    @Test void localCommitOkIsLostOnWireAndSamePublicationCannotRestoreConsumedRemaining() throws Exception {
        try (var fixture = new Fixture("local")) {
            var sender = fixture.bound();
            var receiver = fixture.bound();
            var source = new LocalBuffer();
            assertEquals(128, source.insert(FE, 128, false));
            var outgoing = source.snapshot(sender.id(), fixture.world, fixture.generation(), fixture.channel, true);
            fixture.journal.write(outgoing);
            var deposit = outgoing.deposits().getFirst();
            fixture.authority.deposit(deposit.transaction(), sender.id(), fixture.channel, FE, 128);
            source.committed(List.of(deposit.transaction()));
            var committed = source.snapshot(sender.id(), fixture.world, fixture.generation(), fixture.channel, true);
            fixture.journal.write(committed);
            fixture.authority.checkpoint(sender.id(), committed.revision(), Map.of());

            fixture.authority.demand(receiver.id(), fixture.channel, Protocol.FE, 128);
            var allocation = fixture.authority.allocate(BusinessIds.next(), receiver.id(), fixture.channel,
                    Protocol.FE, 128).orElseThrow();
            assertEquals("RESERVED", allocation.state());
            var credit = new Credit(allocation.id(), fixture.channel, allocation.payload(), 128, 128);
            var durable = new LocalSnapshot(receiver.id(), fixture.world, fixture.generation(), 1,
                    List.of(), List.of(credit));
            fixture.journal.write(durable);
            assertEquals(durable, fixture.journal.read(receiver.id()).orElseThrow());
            fixture.captureWal("before_LOCAL_commit", receiver.id());
            fixture.authority.heartbeat();
            fixture.arm(credit.transaction());
            var publication = new TransferWork.Publication(durable, fixture.channel, receiver.version(),
                    List.of(credit), Map.of());

            var lost = assertThrows(SQLException.class,
                    () -> fixture.authority.publishBatch(fixture.channel, List.of(publication)));
            fixture.assertRealDroppedOk(credit.transaction(), lost);
            var local = fixture.transfer(credit.transaction());
            assertEquals("LOCAL", Sql.str(local, "state"));
            assertEquals(128, Sql.num(local, "remaining"));
            assertEquals(1, fixture.endpointCheckpoint(receiver.id()));
            assertEquals(0, fixture.balance());
            assertEquals(1, fixture.transferCount(receiver.id(), "ALLOCATE"));
            assertEquals(durable, fixture.journal.read(receiver.id()).orElseThrow());
            fixture.evidence.put("post_lost_response", fixture.ledger());

            fixture.authority.heartbeat();
            assertTrue(fixture.authority.publishBatch(fixture.channel, List.of(publication)).isEmpty());
            assertEquals(1, fixture.transferCount(receiver.id(), "ALLOCATE"));
            var received = new LocalBuffer();
            received.restore(fixture.authority.restoreSnapshot(durable));
            assertEquals(23, received.extract(FE, 23, false));
            var consumed = received.snapshot(receiver.id(), fixture.world, fixture.generation(), fixture.channel, true);
            fixture.journal.write(consumed);
            fixture.authority.checkpoint(receiver.id(), consumed.revision(), remaining(consumed));
            assertEquals(105, Sql.num(fixture.transfer(credit.transaction()), "remaining"));
            assertEquals("stale_checkpoint", fixture.authority.publishBatch(fixture.channel,
                    List.of(publication)).get(receiver.id()), "an old positive snapshot cannot roll remaining back");
            assertEquals(105, Sql.num(fixture.transfer(credit.transaction()), "remaining"));
            assertEquals(105, received.extract(FE, 128, false));
            assertEquals(0, received.extract(FE, 128, false));
            var exhausted = received.snapshot(receiver.id(), fixture.world, fixture.generation(), fixture.channel, true);
            fixture.journal.write(exhausted); // Keep the zero tombstone until SQL also confirms consumption.
            fixture.authority.checkpoint(receiver.id(), exhausted.revision(), remaining(exhausted));
            assertEquals("CONSUMED", Sql.str(fixture.transfer(credit.transaction()), "state"));
            assertEquals(0, Sql.num(fixture.transfer(credit.transaction()), "remaining"));
            assertEquals(1, fixture.transferCount(receiver.id(), "ALLOCATE"));
            fixture.captureWal("after_monotone_consumption", receiver.id());
            fixture.evidence.put("after_same_id_retry_and_consumption", fixture.ledger());
            fixture.complete(128, 128);
        }
    }

    private static Map<UUID,Long> remaining(LocalSnapshot snapshot) {
        var values = new LinkedHashMap<UUID,Long>();
        for (var credit : snapshot.credits()) values.put(credit.transaction(), credit.remaining());
        return values;
    }

    private static String sha256(byte[] data) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
    }

    private static final class Fixture implements AutoCloseable {
        final String phase;
        final String suffix = BusinessIds.next().toString().replace("-", "");
        final String cluster = "test_rc_" + suffix;
        final UUID owner = BusinessIds.next(), world = BusinessIds.next();
        final Path directory, control, events, processLog;
        final Map<String,Object> evidence = new LinkedHashMap<>();
        final List<Map<String,Object>> walCopies = new ArrayList<>();
        Authority authority;
        Sql direct;
        LocalJournal journal;
        UUID channel;
        Process proxy;
        int device;
        boolean passed, closed;

        Fixture(String phase) throws Exception {
            this.phase = phase;
            assertTrue(Boolean.getBoolean("ct.integration"));
            assertTrue(cluster.matches("test_rc_[a-f0-9]{32}"));
            Path scratch = ROOT.resolve("scratch");
            assertFalse(Files.isSymbolicLink(scratch), "scratch must be a real repository directory");
            Files.createDirectories(scratch);
            directory = Files.createDirectory(scratch.resolve("rc-recovery-" + phase + "-" + suffix));
            control = directory.resolve("control.json");
            events = directory.resolve("proxy-events.jsonl");
            processLog = directory.resolve("proxy-process.log");
            evidence.put("utc_start", Instant.now().toString());
            evidence.put("cluster", cluster);
            evidence.put("phase", phase);
            evidence.put("world", world.toString());
            evidence.put("scope", "real MySQL COMMIT OK dropped on loopback; independent direct SQL; production LocalJournal/LocalBuffer; no Minecraft/native/world rollback or hardware power-loss claim");
            evidence.put("historical_assets_accessed", false);
            try {
                Files.writeString(control, new JSONObject().put("schema_version", 1).put("armed", false).toString(),
                        StandardOpenOption.CREATE_NEW);
                Files.createFile(processLog);
                Path script = ROOT.resolve("scripts/rc_mysql_ack_proxy.py");
                evidence.put("proxy_script_sha256", sha256(Files.readAllBytes(script)));
                var sourceHashes = new LinkedHashMap<String,String>();
                for (String source : List.of("backend/Sql.java", "backend/Authority.java", "backend/LocalJournal.java",
                        "backend/TransferWork.java", "core/LocalBuffer.java")) {
                    sourceHashes.put(source, sha256(Files.readAllBytes(ROOT.resolve("src/main/java/dev/crosstesseract/" + source))));
                }
                evidence.put("source_files_at_test_start_sha256", sourceHashes);
                proxy = new ProcessBuilder("python3", script.toString(), "--execute", "--control", control.toString(),
                        "--events", events.toString(), "--seconds", "120", "--idle-timeout", "60")
                        .directory(ROOT.toFile()).redirectErrorStream(true)
                        .redirectOutput(ProcessBuilder.Redirect.appendTo(processLog.toFile())).start();
                evidence.put("owned_proxy_pid", proxy.pid());
                awaitProxyReady();
                var config = config(13307);
                authority = new Authority(config);
                authority.join(world, BusinessIds.next(), Protocol.BASE);
                direct = new Sql(config(13306)); // Never routed through the fault proxy.
                journal = new LocalJournal(directory.resolve("journal"));
                channel = authority.createChannel(owner, "rc_" + phase + "_" + suffix.substring(24), BusinessIds.next());
                evidence.put("channel", channel.toString());
                evidence.put("generation", generation());
            } catch (Exception | Error error) {
                try { close(); } catch (Exception cleanup) { error.addSuppressed(cleanup); }
                throw error;
            }
        }

        private BackendConfig config(int port) {
            // Same isolated credentials/ports as existing ct.integration tests; never
            // inherit CT_MYSQL_URL and accidentally select a production database.
            return new BackendConfig(true, cluster, "rc_ack_" + suffix,
                    "jdbc:mysql://127.0.0.1:" + port + "/cross_tesseract?sslMode=DISABLED&allowPublicKeyRetrieval=true&useCompression=false&useServerPrepStmts=false&autoReconnect=false&connectTimeout=1000&socketTimeout=3000",
                    "ct_dev", "ct_dev_only", "redis://127.0.0.1:16379", 2, 2, 200, 128, 32, 256);
        }

        private void awaitProxyReady() throws Exception {
            long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            while (System.nanoTime() < until) {
                assertTrue(proxy.isAlive(), "owned proxy failed; raw evidence retained in " + directory);
                String output = readBounded(processLog, 131072);
                if (output.contains("\"mode\": \"EXECUTING\"")) return;
                TimeUnit.MILLISECONDS.sleep(20); // JUnit IO thread, never Minecraft's main thread.
            }
            fail("owned loopback proxy readiness timeout; evidence retained in " + directory);
        }

        long generation() { return authority.session().generation(); }

        Endpoint bound() throws Exception {
            int position = ++device;
            UUID id = BusinessIds.next();
            var registered = authority.registerEndpoint(new Endpoint(id, authority.session().server(), world, owner,
                    null, "minecraft:overworld", position * 16, 64, 0, 1, "ACTIVE", 0, ""), 0);
            return authority.bind(owner, id, registered.version(), channel);
        }

        void arm(UUID business) throws IOException {
            var value = new JSONObject().put("schema_version", 1).put("cluster", cluster)
                    .put("business_uuid", business.toString()).put("phase", phase);
            Path replacement = directory.resolve("arm-" + business + ".json");
            Files.writeString(replacement, value.toString(), StandardOpenOption.CREATE_NEW);
            Files.move(replacement, control, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            evidence.put("target_business_uuid", business.toString());
        }

        void assertRealDroppedOk(UUID business, SQLException error) throws Exception {
            assertNotNull(error.getSQLState());
            assertTrue(error.getSQLState().startsWith("08"), "JDBC must observe the real proxy disconnect");
            evidence.put("caller_sql_state", error.getSQLState());
            evidence.put("caller_sql_error_code", error.getErrorCode());
            evidence.put("caller_exception_class", error.getClass().getName());
            var selected = new ArrayList<JSONObject>();
            for (JSONObject event : events()) if (business.toString().equals(event.optString("business_uuid"))) selected.add(event);
            var forwarded = selected.stream().filter(event -> "commit_forwarded".equals(event.optString("event"))).toList();
            var acknowledged = selected.stream().filter(event -> "real_commit_OK_received".equals(event.optString("event"))).toList();
            var dropped = selected.stream().filter(event -> "commit_OK_dropped".equals(event.optString("event"))).toList();
            assertEquals(1, forwarded.size()); assertEquals(1, acknowledged.size()); assertEquals(1, dropped.size());
            assertEquals(1, acknowledged.getFirst().getInt("sequence"));
            assertEquals(0, acknowledged.getFirst().getLong("client_OK_bytes_forwarded"));
            assertEquals(acknowledged.getFirst().getString("packet_sha256"), dropped.getFirst().getString("packet_sha256"));
            assertTrue(dropped.getFirst().getBoolean("fault_executed"));
            assertFalse(dropped.getFirst().getBoolean("actual_database_outage"));
            assertTrue(forwarded.getFirst().getLong("monotonic_ns") <= acknowledged.getFirst().getLong("monotonic_ns"));
            assertTrue(acknowledged.getFirst().getLong("monotonic_ns") <= dropped.getFirst().getLong("monotonic_ns"));
            evidence.put("real_commit_OK_observed_and_not_forwarded", true);
            evidence.put("actual_database_outage", false);
        }

        List<JSONObject> events() throws IOException {
            var result = new ArrayList<JSONObject>();
            String text = readBounded(events, 4 * 1024 * 1024);
            int complete = text.lastIndexOf('\n');
            if (complete < 0) return result;
            for (String line : text.substring(0, complete).split("\n")) if (!line.isBlank()) result.add(new JSONObject(line));
            return result;
        }

        Map<String,Object> transfer(UUID transaction) throws SQLException {
            return direct.connection(connection -> {
                var row = Sql.one(connection, "SELECT * FROM ct_transfers WHERE cluster_id=? AND transfer_id=?", cluster, transaction);
                assertNotNull(row, "independent real MySQL must confirm the committed exact UUID");
                return row;
            });
        }

        long balance() throws SQLException {
            return direct.connection(connection -> Sql.num(Sql.one(connection,
                    "SELECT COALESCE(SUM(amount),0) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?", cluster, channel), "n"));
        }

        long transferCount(UUID endpoint, String kind) throws SQLException {
            return direct.connection(connection -> Sql.num(Sql.one(connection,
                    "SELECT COUNT(*) AS n FROM ct_transfers WHERE cluster_id=? AND endpoint_id=? AND kind=?", cluster, endpoint, kind), "n"));
        }

        long endpointCheckpoint(UUID endpoint) throws SQLException {
            return direct.connection(connection -> Sql.num(Sql.one(connection,
                    "SELECT checkpoint AS n FROM ct_endpoints WHERE cluster_id=? AND endpoint_id=?", cluster, endpoint), "n"));
        }

        Map<String,Long> ledger() throws SQLException {
            return direct.connection(connection -> {
                long pool = Sql.num(Sql.one(connection, "SELECT COALESCE(SUM(amount),0) AS n FROM ct_balances WHERE cluster_id=? AND channel_id=?", cluster, channel), "n");
                var rows = Sql.one(connection, "SELECT COUNT(*) AS n,COALESCE(SUM(IF(kind='DEPOSIT',amount,0)),0) AS deposited,COALESCE(SUM(IF(kind='ALLOCATE',remaining,0)),0) AS owned FROM ct_transfers WHERE cluster_id=? AND channel_id=?", cluster, channel);
                return Map.of("pool_FE", pool, "owned_remaining_FE", Sql.num(rows, "owned"), "deposited_FE", Sql.num(rows, "deposited"), "transfer_rows", Sql.num(rows, "n"));
            });
        }

        void captureWal(String label, UUID endpoint) throws Exception {
            Path original = directory.resolve("journal/" + endpoint + ".ctj");
            Path copy = directory.resolve(label + "-" + endpoint + ".ctj");
            Files.copy(original, copy);
            byte[] data = Files.readAllBytes(copy);
            var decoded = LocalJournal.decode(data);
            walCopies.add(Map.of("label", label, "endpoint", endpoint.toString(), "path", ROOT.relativize(copy).toString(),
                    "sha256", sha256(data), "revision", decoded.revision(), "pending_TX_FE", decoded.deposits().stream().mapToLong(LocalSnapshot.Deposit::amount).sum(),
                    "RX_mirror_remaining_FE", decoded.credits().stream().mapToLong(Credit::remaining).sum()));
        }

        void complete(long input, long extracted) throws Exception {
            var finalLedger = ledger();
            assertEquals(input, finalLedger.get("deposited_FE").longValue());
            assertEquals(input, Math.addExact(Math.addExact(finalLedger.get("pool_FE"), finalLedger.get("owned_remaining_FE")), extracted));
            assertEquals(1, events().stream().filter(event -> "commit_OK_dropped".equals(event.optString("event"))).count());
            evidence.put("confirmed_domain_input_FE", input);
            evidence.put("confirmed_LocalBuffer_extraction_FE", extracted);
            evidence.put("native_capability_input_or_output", "NOT_RUN");
            evidence.put("final_ledger", finalLedger);
            evidence.put("WAL_and_SQL_mirrors_not_added", true);
            passed = true;
        }

        @Override public void close() throws Exception {
            if (closed) return;
            closed = true;
            Exception cleanupFailure = null;
            try {
                if (authority != null) {
                    if (passed) authority.stopClean();
                    authority.close();
                }
            } catch (Exception failure) { cleanupFailure = failure; passed = false; }
            if (direct != null) direct.close();
            if (proxy != null) {
                proxy.destroy(); // Only this fixture's own proxy; never a MySQL/Minecraft process.
                if (!proxy.waitFor(8, TimeUnit.SECONDS)) {
                    proxy.destroyForcibly();
                    proxy.waitFor(2, TimeUnit.SECONDS);
                    passed = false;
                    evidence.put("proxy_stop_timeout", true);
                }
                if (!proxy.isAlive()) {
                    evidence.put("proxy_exit_code", proxy.exitValue());
                    if (passed && proxy.exitValue() != 0) {
                        passed = false;
                        cleanupFailure = new IOException("owned fault proxy did not confirm one real ACK drop");
                    }
                }
            }
            evidence.put("passed", passed);
            evidence.put("utc_end", Instant.now().toString());
            evidence.put("wal_snapshots", new JSONArray(walCopies));
            evidence.put("proxy_events", ROOT.relativize(events).toString());
            evidence.put("proxy_process_log", ROOT.relativize(processLog).toString());
            Files.writeString(directory.resolve("result.json"), new JSONObject(evidence).toString(2), StandardOpenOption.CREATE_NEW);
            System.out.println("RC_RECOVERY_EVIDENCE " + ROOT.relativize(directory.resolve("result.json")));
            if (cleanupFailure != null) throw cleanupFailure;
        }

        private static String readBounded(Path path, int maximum) throws IOException {
            if (Files.size(path) > maximum) throw new IOException("bounded fixture evidence exceeded size limit");
            byte[] data = Files.readAllBytes(path);
            if (data.length > maximum) throw new IOException("bounded fixture evidence grew beyond size limit");
            return new String(data, StandardCharsets.UTF_8);
        }
    }
}
