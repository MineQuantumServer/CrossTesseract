#!/usr/bin/env python3
"""Opt-in test-agent windows around the unchanged resource-mix workload.

Default is offline. The inherited mixed-resource driver owns every mutation,
input cadence, external ledger, static guard and cleanup decision. This wrapper
adds file controls and preserves raw, per-JVM ITEM pipeline events.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def clock_anchor():
    before = time.monotonic_ns()
    wall = time.time_ns()
    after = time.monotonic_ns()
    return {"observer_monotonic_before_ns": before, "observer_wall_ns": wall,
            "observer_monotonic_after_ns": after}


def item_payload_identity(payload, variants):
    """Restricted ASCII AnyTag reader for only this two-name stone workload.

    StackCodec writes an unnamed type byte followed by the sorted tag body.
    This is deliberately not a general NBT decoder or a Minecraft CODEC test.
    """
    if not 1 <= len(payload) <= 4096:
        raise ValueError("Bounded small component payload required")
    offset = 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(payload):
            raise ValueError("Truncated NBT")
        result = payload[offset:offset + size]
        offset += size
        return result

    def text():
        size = int.from_bytes(take(2), "big")
        if size > 512:
            raise ValueError("NBT text bound")
        return take(size).decode("ascii")

    def value(kind, depth):
        if depth > 4:
            raise ValueError("NBT depth bound")
        if kind == 3:
            return int.from_bytes(take(4), "big", signed=True)
        if kind == 8:
            return text()
        if kind != 10:
            raise ValueError("Only controlled compound/string/int tags allowed")
        result, keys = {}, []
        while True:
            child = take(1)[0]
            if child == 0:
                if keys != sorted(keys):
                    raise ValueError("Expected StackCodec sorted compound")
                return result
            key = text()
            if len(result) >= 8 or key in result:
                raise ValueError("Duplicate/oversized compound")
            keys.append(key)
            result[key] = value(child, depth + 1)

    tag = value(take(1)[0], 0)
    if offset != len(payload) or not isinstance(tag, dict) or not set(tag) <= {"id", "count", "components"}:
        raise ValueError("Unknown/trailing root payload")
    if tag.get("id") != "minecraft:stone" or type(tag.get("count", 1)) is not int or tag.get("count", 1) != 1:
        raise ValueError("Expected normalized single stone")
    components = tag.get("components")
    if not isinstance(components, dict) or set(components) != {"minecraft:custom_name"}:
        raise ValueError("Unexpected actual component patch")
    encoded = components["minecraft:custom_name"]
    if not isinstance(encoded, str):
        raise ValueError("Expected flat component string")
    name = encoded
    if encoded.lstrip().startswith(('"', '{')):
        def unique(pairs):
            result = {}
            for key, val in pairs:
                if key in result:
                    raise ValueError("Duplicate component JSON key")
                result[key] = val
            return result
        name = json.loads(encoded, object_pairs_hook=unique)
        if isinstance(name, dict) and set(name) == {"text"}:
            name = name["text"]
    if not isinstance(name, str) or name not in variants.values():
        raise ValueError("Actual CUSTOM_NAME/style is outside fixed workload")
    variant = next(key for key, val in variants.items() if val == name)
    return {"variant": variant, "item_id": tag["id"], "normalized_count": 1,
            "CUSTOM_NAME": name, "actual_payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(), "decoded_NBT": tag}


def make_driver(args, mix, physical, y, evidence, probe):
    template = mix.make_driver(args, physical, y, evidence)
    base = physical.load_helpers()

    class ProbedMix(type(template)):
        def __init__(self):
            super().__init__()
            self.target = self.target.with_name(self.target.name.replace(
                "optimization-resource-mix-", "optimization-rc-probe-mix-", 1))
            self.windows = probe.ProbeWindows(args.probe_manifest)
            self.report.update(probe_manifest=probe.file_meta(self.windows.path),
                probe_configuration=self.windows.manifest,
                probe_observer_clock_anchors=[clock_anchor()])
            for path in (Path(__file__).resolve(), ROOT / "scripts/rc-probe-benchmark.py"):
                self.report["helper_sources"][str(path)] = probe.file_meta(path)["sha256"]
            self.report["measurement"]["full_window_probe"] = (
                "One continuous opt-in session from before steady counter_start through "
                "conservation/quiet and counter_after_drain; counter_end has an unsealed "
                "daemon prefix. Whole tickServer samples include Neo Pre/Post. Input and "
                "service loops are inherited unchanged; no rolling-percentile substitution.")
            self.report["measurement"]["pipeline_trace"] = (
                "Raw ITEM local input/capture/source-WAL/SQL deposit confirmation/reservation/"
                "destination-WAL/LOCAL/RX-apply events retain endpoint and operation IDs where "
                "the hook provides them. wal_return is a successful LocalJournal.write return, "
                "including identical-snapshot skips; it is not an independent fsync or "
                "power-loss measurement. local_input is the localChanged notification hook, "
                "not a replacement for physical source-chest observation. Missing hooks or "
                "stages are UNMEASURED. The current "
                "agent records resource kind, not a variant fingerprint: A/B external ledgers "
                "stay independent, but ambiguous internal operations must not be assigned a "
                "variant by order. Never subtract nanoTime across JVMs. Same-JVM deltas are "
                "valid; wall/nano anchors allow approximate alignment only, with 1ms wall "
                "quantization, non-atomic anchor reads, drift and scheduling uncertainty. "
                "This supplies no rigorous cross-JVM latency bound. External container "
                "request/reply intervals remain the E2E evidence; no WorldSave claim.")
            self.report["measurement"]["post_seal_resource_identity"] = (
                "Only after the complete measure returns and all JVM windows are sealed, "
                "read this fresh owned channel's traced business IDs joined to actual SQL "
                "resource payloads. Strict bounded AnyTag parsing and payload SHA256 validate "
                "the two fixed component identities. Unknown/missing IDs stay UNKNOWN; "
                "ordering is never identity proof. Queries add no timed-window cost. "
                "Hooks without a business ID remain unassigned even if their amounts match.")

        def snapshot(self):
            sample = self.report["samples"][-1] if self.report["samples"] else None
            if sample is not None and "ledger_before_steady" in sample and "counter_start" not in sample:
                self.report["probe_observer_clock_anchors"].append(clock_anchor())
                sample["probe_start"] = self.windows.start(trace=True)
            result = super().snapshot()
            if sample is not None and "counter_start" in sample and "steady" in sample and "counter_end" not in sample:
                sample["probe_fixed_window"] = self.windows.fixed()
            if sample is not None and "counter_end" in sample and sample.get("conservation", {}).get("passed") and "counter_after_drain" not in sample:
                sample["probe_full_lifecycle"] = self.windows.stop()
                sample["probe_control_commands"] = list(self.windows.commands)
                sample["probe_ITEM_trace_phase_counts"] = {}
                for server, record in sample["probe_full_lifecycle"].items():
                    data = record["data"]
                    if data["trace_events_dropped"]:
                        raise AssertionError("Bounded ITEM trace overflow; raw retained")
                    counts = {}
                    for event in data["item_events"]:
                        counts[event["phase"]] = counts.get(event["phase"], 0) + 1
                    sample["probe_ITEM_trace_phase_counts"][server] = counts
                self.report["probe_observer_clock_anchors"].append(clock_anchor())
            return result

        def measure(self, name, repeat):
            try:
                result = super().measure(name, repeat)
                sample = self.report["samples"][-1]
                self.resource_identity_after_seal(sample)
                self.save()
                return result
            finally:
                if self.windows.token is not None:
                    try:
                        self.report["samples"][-1]["probe_incomplete_window"] = self.windows.stop()
                    except Exception as error:
                        self.report["failures"].append("Probe stop: " + repr(error))
                    self.save()

        def resource_identity_after_seal(self, sample):
            audit = {"scope": "Post-fixed-and-full-seal read-only identity audit; not timed cost",
                "status": "UNKNOWN", "queries": [], "operations": {},
                "hooks_without_business_ID": "UNKNOWN; never assigned by sequence/amount"}
            sample["trace_resource_identity_after_seal"] = audit
            try:
                if self.windows.token is not None or "counter_after_drain" not in sample or not sample.get("passed"):
                    raise AssertionError("Complete cost/window required before identity SQL")
                records = sample["probe_full_lifecycle"]
                if set(records) != {"A", "B", "C"} or not all(r["data"]["window_closed"] for r in records.values()):
                    raise AssertionError("All JVM probes must be sealed")
                operations = sorted({str(uuid.UUID(event["operation"]))
                    for record in records.values() for event in record["data"]["item_events"]
                    if event.get("operation")})
                if not operations or len(operations) > 128:
                    raise ValueError("No bounded traced business-ID set")
                channel = str(uuid.UUID(self.cases[sample["scenario"]][0].channel))
                ids = ",".join("'" + operation + "'" for operation in operations)
                statement = ("SELECT t.transfer_id,t.endpoint_id,t.channel_id,t.kind,t.state,t.amount,t.remaining,"
                    "r.resource_id,r.kind,r.format_version,r.payload_hash,CONCAT('hex:',HEX(r.payload)) "
                    "FROM ct_transfers t JOIN ct_resources r ON r.cluster_id=t.cluster_id AND r.resource_id=t.resource_id "
                    "WHERE t.cluster_id='dev_three_v1' AND t.channel_id='" + channel + "' AND t.transfer_id IN (" + ids + ") ORDER BY t.transfer_id")
                query = {"statement": statement, "observer_start": time.monotonic(),
                         "observer_account": "isolated dev root; after all counters/probes"}
                audit["queries"].append(query)
                try:
                    rows = base.sql(statement)
                    query["raw_rows"] = rows
                finally:
                    query["observer_end"] = time.monotonic()
                if len(rows) > len(operations):
                    raise ValueError("Duplicate/unexpected transfer rows")
                for row in rows:
                    if len(row) != 12 or row[0] not in operations or row[2] != channel or row[8] != mix.ITEM or row[9] != "1" or not row[11].startswith("hex:"):
                        raise ValueError("Unexpected actual transfer/resource row")
                    payload = bytes.fromhex(row[11][4:])
                    identity = item_payload_identity(payload, mix.VARIANTS)
                    if identity["payload_sha256"] != row[10].lower():
                        raise ValueError("Actual payload/hash mismatch")
                    audit["operations"][row[0]] = dict(identity, endpoint_id=row[1],
                        transfer_kind=row[3], state=row[4], amount=int(row[5]), remaining=int(row[6]),
                        resource_id=str(uuid.UUID(row[7])), resource_kind=row[8], format_version=1)
                audit["missing_business_IDs"] = [op for op in operations if op not in audit["operations"]]
                audit["status"] = "ALL_TRACED_BUSINESS_IDS_IDENTIFIED" if not audit["missing_business_IDs"] else "PARTIAL_UNKNOWN_IDS"
            except Exception as error:
                audit["failure"] = type(error).__name__ + ": " + str(error)

    return ProbedMix()


def self_test(args, mix, physical, y, evidence, probe):
    mix.self_test(physical, y, args, evidence)
    def text(value):
        encoded = value.encode("ascii")
        return len(encoded).to_bytes(2, "big") + encoded
    def string_entry(key, val):
        return b"\x08" + text(key) + text(val)
    for variant, name in mix.VARIANTS.items():
        payload = (b"\x0a\x0a" + text("components") + string_entry("minecraft:custom_name", json.dumps(name)) + b"\x00"
            + b"\x03" + text("count") + (1).to_bytes(4, "big") + string_entry("id", "minecraft:stone") + b"\x00")
        assert item_payload_identity(payload, mix.VARIANTS)["variant"] == variant
        for bad in (payload + b"\x00", payload[:-1], payload.replace(b"minecraft:stone", b"minecraft:dirt!"),
                payload.replace((1).to_bytes(4, "big"), (2).to_bytes(4, "big"))):
            try:
                item_payload_identity(bad, mix.VARIANTS)
            except (ValueError, UnicodeError):
                pass
            else:
                raise AssertionError("Unknown/corrupt component identity accepted")
    with tempfile.TemporaryDirectory(prefix="rc-mix-offline-", dir=ROOT / "scratch") as directory:
        manifest = Path(directory) / "manifest.json"
        manifest.write_text("{}\n")
        offline = argparse.Namespace(**vars(args))
        offline.probe_manifest = manifest
        d = make_driver(offline, mix, physical, y, evidence, probe)
        for name in ("drive_mix", "attempt_items", "cap", "service", "drain_mix", "guard_empty"):
            assert Path(getattr(d, name).__func__.__code__.co_filename).resolve() == ROOT / "scripts/optimization-resource-mix.py", name
        owner = next(cls for cls in type(d).__mro__[1:] if "snapshot" in cls.__dict__)
        original = owner.snapshot
        owner.snapshot = lambda self: {"offline_snapshot": True}
        calls = []

        class OfflineWindows:
            token = None
            commands = []
            def start(self, trace=False):
                assert trace
                self.token = "offline"
                calls.append("start")
                return {}
            def fixed(self):
                calls.append("fixed")
                return {}
            def stop(self):
                calls.append("stop")
                self.token = None
                return {"A": {"data": {"trace_events_dropped": 0, "item_events": []}}}

        d.windows = OfflineWindows()
        sample = {}
        d.report["samples"].append(sample)
        try:
            d.snapshot()
            assert calls == []
            sample["ledger_before_steady"] = {}
            d.snapshot()
            sample.update(counter_start={}, steady={})
            d.snapshot()
            sample.update(counter_end={}, conservation={"passed": True})
            d.snapshot()
            assert calls == ["start", "fixed", "stop"]
            assert all(key in sample for key in ("probe_start", "probe_fixed_window", "probe_full_lifecycle"))
        finally:
            owner.snapshot = original
    print("Probe mix offline real-subclass phase ordering PASS; no native calls")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--probe-manifest", type=Path)
    p.add_argument("--label", default="rc-candidate-batch")
    p.add_argument("--operator-revision", default="unknown")
    p.add_argument("--world-prefix", default="world-opt-resource-mix-")
    p.add_argument("--scenarios", default="mixed")
    p.add_argument("--warmup", type=float, default=30)
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--feed-period", type=float, default=.5)
    p.add_argument("--poll", type=float, default=.1)
    p.add_argument("--quiet", type=float, default=2.2)
    p.add_argument("--timeout", type=float, default=1200)
    p.add_argument("--fe", type=int, default=32000)
    p.add_argument("--water", type=int, default=1000)
    p.add_argument("--items", type=int, default=32)
    args = p.parse_args()
    args.scenarios = list(dict.fromkeys(args.scenarios.split(",")))
    if (not all(math.isfinite(v) for v in (args.warmup, args.seconds, args.feed_period, args.poll, args.quiet, args.timeout))
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label) or not args.scenarios
            or any(s not in ("same", "cross", "mixed") for s in args.scenarios)
            or not 0 <= args.warmup <= 120 or not 1 <= args.seconds <= 600 or not 1 <= args.repeats <= 3
            or not .25 <= args.feed_period <= 10 or not .05 <= args.poll <= 1 or not 2.2 <= args.quiet <= 30
            or not 30 <= args.timeout <= 1800 or not 1 <= args.fe <= 32000 or not 1 <= args.water <= 16000
            or args.items != 32 or not re.fullmatch(r"world-opt-resource-mix-[A-Za-z0-9_-]{0,24}", args.world_prefix)
            or (args.operator_revision != "unknown" and not re.fullmatch(r"[0-9a-f]{7,40}", args.operator_revision))):
        p.error("Parameters outside inherited bounded resource-mix scope")
    args.probes, args.probe_idle = 0, args.quiet
    mix = load("rc_probed_resource_mix", ROOT / "scripts/optimization-resource-mix.py")
    physical = mix.load_file_module("rc_probed_mix_physical", mix.CONTAINER)
    y, evidence = physical.harness_height()
    probe = load("rc_mix_probe_controls", ROOT / "scripts/rc-probe-benchmark.py")
    if args.self_test:
        self_test(args, mix, physical, y, evidence, probe)
        return 0
    if not args.execute:
        print(json.dumps({"execution": "NOT_RUN", "native_validation": "UNMEASURED",
            "requires": "--execute --probe-manifest with fresh isolated fixtures"}))
        return 0
    if args.probe_manifest is None:
        p.error("--probe-manifest is required for actual execution")
    return make_driver(args, mix, physical, y, evidence, probe).run()


if __name__ == "__main__":
    sys.exit(main())
