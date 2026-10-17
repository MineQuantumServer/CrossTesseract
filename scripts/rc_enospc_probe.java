import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.LocalSnapshot.Deposit;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.core.Resource;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Standalone production-WAL filesystem probe, compiled only by rc_enospc_test.py.
 * Its positive pending-TX fixture has no SQL or Minecraft asset provenance.
 * No synthetic IOException is thrown: both expected errors must come from actual
 * FileChannel/LocalJournal writes to the container's private, full tmpfs.
 */
public final class rc_enospc_probe {
    private static void require(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }

    private static boolean noSpace(IOException error) {
        // Public Java IOExceptions do not expose errno numerically. Preserve the
        // real class/message, private tmpfs type/size and usable=0 as evidence.
        return error.getMessage() != null && error.getMessage().contains("No space left on device");
    }

    private static Map<String,Object> exception(IOException error) {
        var result = new LinkedHashMap<String,Object>();
        result.put("class", error.getClass().getName());
        result.put("message", error.getMessage());
        result.put("numeric_errno", "NOT_EXPOSED_BY_PUBLIC_JAVA_API");
        result.put("ENOSPC_message_observed", noSpace(error));
        return result;
    }

    private static Map<String,Object> exercise(Path root) throws Exception {
        require(root.equals(Path.of("/wal")), "private_container_mount_required");
        var store = Files.getFileStore(root);
        require(store.type().equals("tmpfs"), "real_private_tmpfs_required");
        require(store.getTotalSpace() >= 65_536 && store.getTotalSpace() <= 2_097_152,
                "small_private_volume_required");
        var evidence = new LinkedHashMap<String,Object>();
        evidence.put("java_version", System.getProperty("java.version"));
        evidence.put("file_store_type", store.type());
        evidence.put("volume_total_bytes", store.getTotalSpace());
        evidence.put("scope", "actual private-container tmpfs ENOSPC; standalone positive WAL fixture only; no SQL/native/world/hardware power-loss test");
        evidence.put("controlled_IOException_injection", false);
        evidence.put("SQL_and_native_asset_lineage", "NOT_RUN");
        UUID endpoint = UUID.randomUUID(), world = UUID.randomUUID(), channel = UUID.randomUUID();
        var resource = new Resource(Protocol.FE, new byte[0]);
        var original = new Deposit(UUID.randomUUID(), channel, resource, 128);
        var additional = new Deposit(UUID.randomUUID(), channel, resource, 7);
        var before = new LocalSnapshot(endpoint, world, 1, 1, List.of(original), List.of());
        var next = new LocalSnapshot(endpoint, world, 1, 2, List.of(original, additional), List.of());
        var journal = new LocalJournal(root);
        journal.write(before);
        Path checkpoint = root.resolve(endpoint + ".ctj");
        byte[] initialBytes = Files.readAllBytes(checkpoint);
        evidence.put("endpoint", endpoint.toString());
        evidence.put("original_business_uuid", original.transaction().toString());
        evidence.put("additional_business_uuid", additional.transaction().toString());
        evidence.put("initial_WAL_sha256", Resource.hash(initialBytes));
        evidence.put("initial_durable_TX_FE", 128);
        evidence.put("attempted_additional_TX_FE", 7);
        Path filler = root.resolve("only-this-fixture.fill");
        long written = 0;
        IOException fillError = null;
        try (var output = FileChannel.open(filler, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            var buffer = ByteBuffer.allocate(65_536);
            while (written < 2_097_152) {
                buffer.clear();
                while (buffer.hasRemaining()) written += output.write(buffer);
            }
        } catch (IOException actual) { fillError = actual; }
        require(fillError != null && noSpace(fillError), "filler_must_receive_real_ENOSPC");
        require(store.getUsableSpace() == 0, "private_tmpfs_not_full");
        evidence.put("filler_bytes", written);
        evidence.put("filler_actual_exception", exception(fillError));
        evidence.put("usable_bytes_before_failed_WAL", store.getUsableSpace());
        IOException walError = null;
        try { journal.write(next); } catch (IOException actual) { walError = actual; }
        require(walError != null && noSpace(walError), "LocalJournal_must_receive_real_ENOSPC");
        evidence.put("WAL_actual_exception", exception(walError));
        require(Arrays.equals(initialBytes, Files.readAllBytes(checkpoint)), "old_positive_ctj_changed_on_failed_write");
        require(journal.read(endpoint).orElseThrow().equals(before), "failed_pending_became_authoritative");
        evidence.put("old_positive_ctj_preserved", true);
        evidence.put("durable_TX_after_failure_FE", 128);
        Path pending = root.resolve(endpoint + ".pending");
        evidence.put("pending_exists_after_failure", Files.exists(pending));
        evidence.put("pending_bytes_after_failure", Files.exists(pending) ? Files.size(pending) : 0);
        Files.delete(filler); // Never touch a host/shared mount or any other fixture file.
        require(store.getUsableSpace() > 0, "private_fixture_space_not_released");
        evidence.put("usable_bytes_after_own_filler_removal", store.getUsableSpace());
        journal.write(next);
        var restored = journal.read(endpoint).orElseThrow();
        require(restored.equals(next), "retry_did_not_persist_same_snapshot");
        require(restored.deposits().getFirst().equals(original), "original_128_business_identity_changed");
        require(restored.deposits().stream().mapToLong(Deposit::amount).sum() == 135, "retry_amount_mismatch");
        evidence.put("retry_original_business_identity_preserved", true);
        evidence.put("durable_TX_after_retry_FE", 135);
        evidence.put("retry_WAL_sha256", Resource.hash(Files.readAllBytes(checkpoint)));
        evidence.put("journal_stats", journal.stats());
        evidence.put("first_WAL_failure_new_input_boundary", "additional7 was not durable before retry; no hardware power-loss or automatic-refund guarantee");
        evidence.put("passed", true);
        return evidence;
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?,?> map) return "{" + map.entrySet().stream()
                .map(entry -> json(entry.getKey().toString()) + ":" + json(entry.getValue()))
                .collect(java.util.stream.Collectors.joining(",")) + "}";
        String text = value.toString().replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
        return "\"" + text + "\"";
    }

    public static void main(String[] arguments) {
        try {
            require(arguments.length == 1, "one_private_mount_argument_required");
            System.out.println(json(exercise(Path.of(arguments[0]))));
        } catch (Throwable failure) {
            System.out.println(json(Map.of("passed", false, "failure_class", failure.getClass().getName(),
                    "failure_message", String.valueOf(failure.getMessage()), "SQL_and_native_asset_lineage", "NOT_RUN")));
            System.exit(1);
        }
    }
}
