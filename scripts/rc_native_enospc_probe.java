import dev.crosstesseract.backend.LocalJournal;
import dev.crosstesseract.core.LocalSnapshot;
import dev.crosstesseract.core.LocalSnapshot.Deposit;
import dev.crosstesseract.core.Protocol;
import dev.crosstesseract.core.Resource;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Offline native-origin WAL COPY probe. The seed has no SQL authorization here.
 * No Minecraft or database runs, no fixture is funded and no copy is imported.
 * The only checkpoint change is revision+1 with the same32 original TX IDs/FE.
 * Run only inside rc_native_enospc_test.py's private, networkless tmpfs container.
 */
public final class rc_native_enospc_probe {
    private static void require(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }

    private static boolean noSpace(IOException error) {
        return error.getMessage() != null && error.getMessage().contains("No space left on device");
    }

    private static Map<String,Object> exception(IOException error) {
        return Map.of("class", error.getClass().getName(), "message", String.valueOf(error.getMessage()),
                "numeric_errno", "NOT_EXPOSED_BY_PUBLIC_JAVA_API", "ENOSPC_message_observed", noSpace(error));
    }

    private static void asset(LocalSnapshot snapshot) {
        require(snapshot.deposits().size() == 32, "exact32_original_TX_records_required");
        require(snapshot.deposits().stream().allMatch(d -> d.amount() == 1
                && d.resource().kind().equals(Protocol.FE) && d.resource().bytes().length == 0),
                "only_original32_native_FE_required");
        require(snapshot.deposits().stream().map(Deposit::transaction).distinct().count() == 32,
                "duplicate_original_business_ID");
        require(snapshot.deposits().stream().map(Deposit::channel).distinct().count() == 1,
                "one_original_channel_required");
        require(snapshot.credits().stream().allMatch(c -> c.remaining() == 0), "positive_RX_copy_not_allowed");
        require(snapshot.thermal().microjoules() == 0 && snapshot.thermal().residual() == 0
                && snapshot.thermal().pending() == null, "thermal_assets_not_allowed");
    }

    private static Map<String,Object> exercise(Path root, Path seed, String expectedHash) throws Exception {
        require(root.equals(Path.of("/wal")), "private_container_mount_required");
        require(seed.getParent().equals(Path.of("/source/seed"))
                && seed.getFileName().toString().endsWith(".ctj")
                && Files.isRegularFile(seed, LinkOption.NOFOLLOW_LINKS), "private_readonly_seed_required");
        require(expectedHash.matches("[0-9a-f]{64}"), "exact_seed_hash_required");
        byte[] original = Files.readAllBytes(seed);
        require(Resource.hash(original).equals(expectedHash), "readonly_seed_hash_mismatch");
        var before = LocalJournal.decode(original);
        require(ByteBuffer.wrap(original).getInt(4) == 2, "revision_only_native_v2_copy_required");
        require(seed.getFileName().toString().equals(before.endpoint() + ".ctj"), "seed_endpoint_mismatch");
        asset(before);
        var next = new LocalSnapshot(before.endpoint(), before.world(), before.generation(),
                Math.addExact(before.revision(), 1), before.deposits(), before.credits(), before.thermal());
        var store = Files.getFileStore(root);
        require(store.type().equals("tmpfs") && store.getTotalSpace() >= 65_536
                && store.getTotalSpace() <= 2_097_152, "small_private_tmpfs_required");
        Path checkpoint = root.resolve(before.endpoint() + ".ctj");
        Files.copy(seed, checkpoint); // Seed directory and the real world are never writable mounts.
        var journal = new LocalJournal(root);
        journal.write(before); // Reprove the copied file/directory barriers with the production implementation.
        require(Arrays.equals(original, Files.readAllBytes(checkpoint)), "initial_copy_changed");
        var evidence = new LinkedHashMap<String,Object>();
        evidence.put("scope", "Native-origin retained32FE WAL copy; production LocalJournal on private networkless tmpfs only. No Minecraft Runtime ENOSPC, SQL authorization, replay/import, hardware fault or power loss.");
        evidence.put("java_version", System.getProperty("java.version"));
        evidence.put("file_store_type", store.type());
        evidence.put("volume_total_bytes", store.getTotalSpace());
        evidence.put("controlled_IOException_injection", false);
        evidence.put("seed_sha256", expectedHash);
        evidence.put("endpoint", before.endpoint().toString());
        evidence.put("world", before.world().toString());
        evidence.put("generation", before.generation());
        evidence.put("original_revision", before.revision());
        evidence.put("attempted_revision", next.revision());
        evidence.put("original_business_IDs", before.deposits().stream().map(d -> d.transaction().toString()).toList());
        evidence.put("original_TX_FE", 32);
        evidence.put("new_input_added_FE", 0);
        evidence.put("SQL_authorization_present", false);
        evidence.put("copy_ever_imported_or_consumed", false);
        Path filler = root.resolve("only-this-private-copy.fill");
        long written = 0;
        IOException fillError = null;
        try (var output = FileChannel.open(filler, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            var buffer = ByteBuffer.allocate(65_536);
            while (written < 2_097_152) {
                buffer.clear();
                while (buffer.hasRemaining()) written += output.write(buffer);
            }
        } catch (IOException actual) { fillError = actual; }
        require(fillError != null && noSpace(fillError) && store.getUsableSpace() == 0, "actual_private_ENOSPC_required");
        evidence.put("filler_bytes", written);
        evidence.put("filler_actual_exception", exception(fillError));
        evidence.put("usable_bytes_before_failed_checkpoint", store.getUsableSpace());
        IOException walError = null;
        try { journal.write(next); } catch (IOException actual) { walError = actual; }
        require(walError != null && noSpace(walError), "production_checkpoint_must_receive_real_ENOSPC");
        evidence.put("WAL_actual_exception", exception(walError));
        require(Arrays.equals(original, Files.readAllBytes(checkpoint)), "failed_write_changed_original_copy");
        require(journal.read(before.endpoint()).orElseThrow().equals(before), "failed_checkpoint_became_authoritative");
        evidence.put("old32FE_copy_and_business_IDs_preserved_after_failure", true);
        evidence.put("durable_TX_after_failure_FE", 32);
        evidence.put("pending_exists_after_failure", Files.exists(root.resolve(before.endpoint() + ".pending")));
        Files.delete(filler); // The only deletion in this probe, within its private disposable tmpfs.
        require(store.getUsableSpace() > 0, "private_fixture_space_not_released");
        journal.write(next);
        var restored = journal.read(before.endpoint()).orElseThrow();
        asset(restored);
        require(restored.equals(next) && restored.deposits().equals(before.deposits())
                && restored.credits().equals(before.credits()), "same_ID_quantity_checkpoint_retry_failed");
        require(Arrays.equals(original, Files.readAllBytes(seed)), "readonly_seed_changed");
        evidence.put("retry_same_IDs_and_quantities", true);
        evidence.put("durable_TX_after_retry_FE", 32);
        evidence.put("retry_revision", restored.revision());
        evidence.put("retry_copy_sha256", Resource.hash(Files.readAllBytes(checkpoint)));
        evidence.put("readonly_seed_after_sha256", Resource.hash(Files.readAllBytes(seed)));
        evidence.put("journal_stats", journal.stats());
        evidence.put("passed", true);
        return evidence;
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?,?> map) return "{" + map.entrySet().stream()
                .map(entry -> json(entry.getKey().toString()) + ":" + json(entry.getValue()))
                .collect(java.util.stream.Collectors.joining(",")) + "}";
        if (value instanceof Iterable<?> items) {
            var parts = new java.util.ArrayList<String>();
            for (Object item : items) parts.add(json(item));
            return "[" + String.join(",", parts) + "]";
        }
        return "\"" + value.toString().replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    public static void main(String[] arguments) {
        try {
            require(arguments.length == 3, "private_mount_seed_and_hash_arguments_required");
            System.out.println(json(exercise(Path.of(arguments[0]), Path.of(arguments[1]), arguments[2])));
        } catch (Throwable failure) {
            System.out.println(json(Map.of("passed", false, "failure_class", failure.getClass().getName(),
                    "failure_message", String.valueOf(failure.getMessage()),
                    "SQL_native_Runtime_hardware_tests", "NOT_RUN")));
            System.exit(1);
        }
    }
}
