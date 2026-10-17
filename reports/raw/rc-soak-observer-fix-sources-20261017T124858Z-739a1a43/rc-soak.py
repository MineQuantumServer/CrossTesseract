#!/usr/bin/env python3
"""Bounded 3600-second native RC soak on NEW isolated development fixtures.

Default/--self-test opens no sockets and runs no Docker, JDK or Minecraft
commands. --execute requires already-running, otherwise unused A/B/C worlds,
the existing dev_three_v1 guards and a new rc-soak-* label. This driver never
starts/stops servers or containers and never writes SQL or rewrites the WAL.

One serial RCON observer serves concurrent hot/cold channels, mixed same-server
and remote recipients, repeated FE backpressure/recovery, water and two small
CUSTOM_NAME variants with fixed4KiB CUSTOM_DATA through real vanilla chests. /proc, jstat, SQL,
instrumented queue/WAL counters and owned WAL file hashes are sampled every
30 seconds. Setup, warmup and the bounded final drain are outside the full
3600-second observation. No cross-JVM nanoTime subtraction. Optional
--probe-manifest reuses the existing test agent for complete Runtime/whole
tickServer-call histograms and actual tick-start TPS. Its control/daemon-copy
and completed-call edges are preserved, rather than an exact3600s cutoff.
Explicit --smoke permits30..60sec tool validation only (60min_gate=false),
with5sec monitoring and operator-prepared buffers.fe<=64000 for a short full
hold/recovery. Smoke and full soak both require their own fresh worlds.

Example, AFTER an operator prepares fresh worlds and stops other observers:
  python3 scripts/rc-soak.py --execute --label rc-soak-candidate-1 \
    --world-prefix world-opt-rc-soak-candidate1 \
    --operator-revision <40-hex-frozen-source-revision>

Failure keeps remaining/uncertain isolated assets. Success leaves drained, OFF
fixtures and their tickets for operator inspection; no automatic block removal.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import struct
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION_SECONDS = 3600
SAMPLE_SECONDS = 30
MAX_TRACE_BYTES = 256 * 1024 * 1024
MAX_TRACE_RECORDS = 500_000
MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 128 * 1024
LARGE_NAMES = {v: "CT rc soak variant " + v + " " + "x" * 200 for v in ("A", "B")}
CUSTOM_DATA = {"r" + str(index): "x" * 512 for index in range(8)}
CUSTOM_DATA_CANONICAL = json.dumps(CUSTOM_DATA, sort_keys=True, separators=(",", ":"))
CUSTOM_DATA_SHA256 = hashlib.sha256(CUSTOM_DATA_CANONICAL.encode()).hexdigest()


class SoakSNBT:
    """Only a bounded compound/list/string/integer grammar, not arbitrary NBT."""
    def __init__(self, text):
        if len(text.encode()) > 32768:
            raise ValueError("soak SNBT32KiB bound exceeded")
        self.text, self.index, self.nodes = text, 0, 0

    def ws(self):
        while self.index < len(self.text) and self.text[self.index].isspace():
            self.index += 1

    def take(self, token):
        self.ws()
        if not self.text.startswith(token, self.index):
            raise ValueError("truncated/unrecognized soak SNBT")
        self.index += len(token)

    def value(self, depth=0):
        self.nodes += 1
        self.ws()
        if depth > 8 or self.nodes > 1024 or self.index == len(self.text):
            raise ValueError("soak SNBT depth/node/truncation bound")
        char = self.text[self.index]
        if char in ("'", '"'):
            self.index += 1
            result = []
            while self.index < len(self.text):
                current = self.text[self.index]
                self.index += 1
                if current == char:
                    text = "".join(result)
                    if len(text.encode()) > 512:
                        raise ValueError("soak string512-byte bound")
                    return text
                if current == "\\":
                    if self.index == len(self.text) or self.text[self.index] not in (char, "\\"):
                        raise ValueError("unsupported soak SNBT escape")
                    current = self.text[self.index]
                    self.index += 1
                if ord(current) < 32:
                    raise ValueError("soak SNBT control character")
                result.append(current)
            raise ValueError("unterminated soak SNBT string")
        if char in ("{", "["):
            compound, end = char == "{", "}" if char == "{" else "]"
            self.take(char)
            result = {} if compound else []
            self.ws()
            while self.index < len(self.text) and self.text[self.index] != end:
                if len(result) >= (64 if compound else 27):
                    raise ValueError("soak compound/list bound")
                if compound:
                    key = self.value(depth + 1)
                    if not isinstance(key, str) or key in result:
                        raise ValueError("nonstring/duplicate soak SNBT key")
                    self.take(":")
                    result[key] = self.value(depth + 1)
                else:
                    result.append(self.value(depth + 1))
                self.ws()
                if self.index < len(self.text) and self.text[self.index] == ",":
                    self.take(",")
                    self.ws()
                    if self.index == len(self.text) or self.text[self.index] == end:
                        raise ValueError("trailing soak SNBT separator")
                elif self.index < len(self.text) and self.text[self.index] != end:
                    raise ValueError("missing soak SNBT separator")
            self.take(end)
            return result
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*|-?\d{1,4}[bBsS]?", self.text[self.index:])
        if not match:
            raise ValueError("unsupported soak SNBT token")
        self.index += len(match[0])
        return int(match[0].rstrip("bBsS")) if re.fullmatch(r"-?\d+[bBsS]?", match[0]) else match[0]

    def parse(self):
        result = self.value(1)
        self.ws()
        if self.index != len(self.text):
            raise ValueError("trailing soak SNBT content")
        return result


def unique_json(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("duplicate component JSON key")
        values[key] = value
    return values


def parse_large_items(reply, position):
    if len(reply.encode()) > 32768:
        raise ValueError("soak chest reply32KiB bound")
    match = re.fullmatch(r"\s*(-?\d+),\s*(-?\d+),\s*(-?\d+) has the following block data:\s*(\[.*\])\s*", reply, re.S)
    if not match or tuple(int(match[index]) for index in (1, 2, 3)) != tuple(position):
        raise ValueError("unrecognized/mismatched own soak chest reply")
    rows = SoakSNBT(match[4]).parse()
    if not isinstance(rows, list):
        raise ValueError("soak chest must be an Items list")
    seen, stacks, totals = set(), [], {variant: 0 for variant in LARGE_NAMES}
    for row in rows:
        if not isinstance(row, dict) or not set(row) <= {"Slot", "id", "count", "Count", "components"}:
            raise ValueError("unexpected soak item fields")
        if row.get("id") != "minecraft:stone" or "Slot" not in row or "components" not in row or ("count" in row and "Count" in row):
            raise ValueError("only fixed component stone accepted")
        slot, count = row["Slot"], row.get("count", row.get("Count", 1))
        if type(slot) is not int or type(count) is not int or not 0 <= slot < 27 or not 1 <= count <= 64 or slot in seen:
            raise ValueError("invalid/duplicate soak chest slot/count")
        components = row["components"]
        if not isinstance(components, dict) or set(components) != {"minecraft:custom_name", "minecraft:custom_data"}:
            raise ValueError("fixed complete CUSTOM_NAME+CUSTOM_DATA required")
        name_json, custom = components["minecraft:custom_name"], components["minecraft:custom_data"]
        if not isinstance(name_json, str) or len(name_json.encode()) > 256:
            raise ValueError("small CUSTOM_NAME256-byte bound")
        name = json.loads(name_json, object_pairs_hook=unique_json)
        if isinstance(name, dict) and set(name) == {"text"}:
            name = name["text"]
        if not isinstance(name, str) or name not in LARGE_NAMES.values() or custom != CUSTOM_DATA:
            raise ValueError("unexpected component identity/value; no arbitrary custom data accepted")
        digest = hashlib.sha256(json.dumps(custom, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != CUSTOM_DATA_SHA256:
            raise ValueError("fixed CUSTOM_DATA digest mismatch")
        variant = next(variant for variant, text in LARGE_NAMES.items() if text == name)
        seen.add(slot)
        totals[variant] += count
        stacks.append({"slot": slot, "id": "minecraft:stone", "count": count, "variant": variant,
            "custom_name": name, "flat_component_JSON": name_json,
            "custom_data_canonical_JSON_bytes": len(CUSTOM_DATA_CANONICAL.encode()), "custom_data_sha256": digest})
    return {"stacks": stacks, "by_variant": totals, "total": sum(totals.values()), "snbt": match[4]}


def rcon_frame(identifier, kind, text):
    payload = struct.pack("<ii", identifier, kind) + text.encode() + b"\0\0"
    return struct.pack("<i", len(payload)) + payload


def read_exact(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("soak RCON closed before barrier")
        data.extend(chunk)
    return bytes(data)


def read_rcon_frame(sock):
    size = struct.unpack("<i", read_exact(sock, 4))[0]
    if not 10 <= size <= 32778:
        raise ValueError("soak RCON frame size bound")
    payload = read_exact(sock, size)
    if payload[-2:] != b"\0\0":
        raise ValueError("soak RCON terminator mismatch")
    identifier, kind = struct.unpack("<ii", payload[:8])
    return identifier, kind, payload[8:-2]


def collect_rcon_items(read_frame, expected_pid):
    chunks, total, packets = [], 0, 0
    for _ in range(16):
        identifier, kind, payload = read_frame()
        if kind != 0:
            raise ValueError("unexpected soak RCON reply type")
        if identifier == 103:
            if payload.decode().strip() != "PID " + str(expected_pid) or not chunks:
                raise ValueError("soak same-connection PID barrier mismatch")
            return b"".join(chunks).decode(), {"query_packets": packets, "query_bytes": total,
                "barrier_request_id": 103, "barrier_reply": payload.decode(), "complete_at_matching_barrier": True}
        if identifier != 102:
            raise ValueError("soak RCON reply requestID mismatch")
        total += len(payload)
        if total > 32768:
            raise ValueError("soak RCON Items total32KiB bound")
        chunks.append(payload)
        packets += 1
    raise ValueError("soak RCON packet count bound")


def query_rcon_items(sock, command, expected_pid):
    # Minecraft 1.21.1 RconClient validates one read as exactly one request
    # (declared length == read length - 4). Do not concatenate two frames.
    # The first response establishes that query102 has been processed before
    # sending barrier103. Any remaining102 chunks precede103 on this socket.
    sock.sendall(rcon_frame(102, 2, command))
    first = read_rcon_frame(sock)
    if first[0] != 102 or first[1] != 0:
        raise ValueError("soak first Items query reply requestID/type mismatch")
    sock.sendall(rcon_frame(103, 2, "ct_test pid"))
    pending = [first]
    reply, proof = collect_rcon_items(
        lambda: pending.pop() if pending else read_rcon_frame(sock), expected_pid)
    proof["barrier_sent_after_first_query_response"] = True
    return reply, proof


def component_field_command(position, slot, field):
    if slot not in (0, 1) or field not in CUSTOM_DATA or len(position) != 3 or any(type(value) is not int for value in position):
        raise ValueError("fixed own component staging target required")
    x, y, z = position
    command = f'data modify block {x} {y} {z} Items[{{Slot:{slot}b}}].components."minecraft:custom_data".{field} set value "{CUSTOM_DATA[field]}"'
    if len(("execute in minecraft:overworld run " + command).encode()) > 1024:
        raise ValueError("component staging command1KiB bound")
    return command


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def hold_cycle(offset, smoke=False):
    """Four 120s hold periods; all timing uses this observer's monotonic clock."""
    if smoke:
        return 0 if 3 <= offset < 18 else None
    cycle = int(offset // 900)
    return cycle if 0 <= cycle < 4 and 60 <= offset % 900 < 180 else None


def validate_args(args):
    if not re.fullmatch(r"rc-soak-[A-Za-z0-9_-]{1,32}", args.label or ""):
        raise ValueError("new --label rc-soak-<1..32 safe characters> required")
    if not re.fullmatch(r"world-opt-rc-soak-[A-Za-z0-9_-]{1,24}", args.world_prefix or ""):
        raise ValueError("fresh --world-prefix world-opt-rc-soak-<1..24 safe characters> required")
    if not re.fullmatch(r"[a-fA-F0-9]{40}", args.operator_revision or ""):
        raise ValueError("explicit 40-hex operator revision required; not classloader attestation")
    if args.smoke and not 30 <= args.seconds <= 60:
        raise ValueError("explicit tool smoke must be30..60sec; never a60-minute gate")
    if not args.smoke and args.seconds != OBSERVATION_SECONDS:
        raise ValueError("shortened observations cannot be labeled a 60-minute soak")
    if not .5 <= args.poll <= 2 or not .5 <= args.feed_period <= 2:
        raise ValueError("poll/feed period must be between .5 and 2 seconds")
    if not 120 <= args.timeout <= 1200 or not .1 <= args.jstat_timeout <= 3:
        raise ValueError("drain timeout 120..1200s and jstat timeout .1..3s required")
    if not 1 <= args.fe <= 32000 or not 1 <= args.water <= 1000 or args.items != 32:
        raise ValueError("bounded FE/water input and exactly32 items per variant required")


class EvidenceLog:
    """One exclusive, bounded append-only journal; no command replay on failure."""
    def __init__(self, path):
        self.path = path
        self.file = path.open("x", encoding="utf-8")
        os.chmod(path, 0o600)
        self.bytes = self.records = 0
        self.digest = hashlib.sha256()

    def append(self, stream, index, record):
        data = (json.dumps({"stream": stream, "index": index, "record": record},
            ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(data) > MAX_RECORD_BYTES or self.bytes + len(data) > MAX_TRACE_BYTES or self.records >= MAX_TRACE_RECORDS:
            raise ValueError("soak evidence size bound reached; retain assets, do not replay")
        self.file.write(data.decode())
        self.bytes += len(data)
        self.records += 1
        self.digest.update(data)

    def sync(self):
        self.file.flush()
        os.fsync(self.file.fileno())

    def close(self):
        self.sync()
        self.file.close()

    def summary(self):
        return {"path": str(self.path.relative_to(ROOT)), "records": self.records,
            "bytes": self.bytes, "sha256": self.digest.hexdigest(),
            "max_bytes": MAX_TRACE_BYTES, "max_records": MAX_TRACE_RECORDS}


class StreamRing(list):
    """List-compatible recent records with stable absolute indexes and disk spill.

    Existing fixture helpers append a mutable record before a synchronous call.
    Spill only OLD records, retaining32, so current in-progress records never
    reach disk as a misleading completed response. The final flush keeps any
    unknown mutation result exactly as recorded.
    """
    def __init__(self, log, name):
        super().__init__()
        self.log, self.name, self.offset = log, name, 0

    def __len__(self):
        return self.offset + list.__len__(self)

    def index(self, value, *bounds):
        if bounds:
            raise ValueError("bounded absolute trace index search unsupported")
        return self.offset + list.index(self, value)

    def append(self, record):
        if list.__len__(self) >= 256:
            self.spill(32)
        list.append(self, record)

    def spill(self, retain=0):
        count = max(0, list.__len__(self) - retain)
        # Advance once per successful write, so an output failure is never
        # retried as a duplicate evidence record by finally/another spill.
        for _ in range(count):
            self.log.append(self.name, self.offset, list.__getitem__(self, 0))
            list.__delitem__(self, 0)
            self.offset += 1


def report_snapshot(value):
    """Serialize resident data, not a StreamRing's absolute logical length.

    A fully spilled ring has logical len>0 but an empty list iterator. Encoding
    that list subclass directly produces malformed JSON in Python's encoder.
    Keep the live ring/absolute indexes intact and recursively copy plain lists.
    """
    if isinstance(value, StreamRing):
        return [report_snapshot(item) for item in list.__iter__(value)]
    if isinstance(value, dict):
        return {key: report_snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [report_snapshot(item) for item in value]
    return value


def safe_directory(label):
    scratch = ROOT / "scratch"
    if scratch.is_symlink() or not scratch.is_dir():
        raise ValueError("scratch must already be a real repository directory")
    for parent in scratch.parents:
        if parent.is_symlink():
            raise ValueError("scratch parent symlink rejected")
    if next(scratch.glob("rc-soak-" + label + "-*"), None) is not None:
        raise ValueError("label already has a retained soak manifest; choose a NEW label")
    path = scratch / ("rc-soak-" + label + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:10])
    path.mkdir(mode=0o700)
    return path


def probe_scope(path, kind):
    if path.is_relative_to(ROOT / "scratch"):
        return True
    archived = ROOT / "reports/rc-20261017"
    if path.parent != archived:
        return False
    if kind == "file":
        return bool(re.fullmatch(r"probe-launches-[A-Za-z0-9_-]{1,128}\.json", path.name))
    if kind == "directory":
        return bool(re.fullmatch(r"probe-[A-Za-z0-9_-]{1,128}-(?:A|B|C|Perf)", path.name))
    return False  # Control files may only live below scratch.


def probe_path(value, kind, max_bytes=None):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if ".." in path.parts or not probe_scope(path, kind):
        raise ValueError("probe path outside scratch or explicit frozen RC probe report scope")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("probe path symlink rejected")
    if kind == "file" and not path.is_file() or kind == "directory" and not path.is_dir():
        raise ValueError("probe path type mismatch")
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise ValueError("probe file size bound")
    return path.resolve()


def make_soak(args, directory):
    mix = load_module("rc_soak_mix", ROOT / "scripts/optimization-resource-mix.py")
    mix.VARIANTS = dict(LARGE_NAMES)
    physical = load_module("rc_soak_physical", ROOT / "scripts/optimization-container-benchmark.py")
    monitor = load_module("rc_soak_process", ROOT / "scripts/optimization-monitor.py")
    probe = None
    if args.probe_manifest is not None:
        manifest_path = probe_path(args.probe_manifest, "file", 262144)
        parsed = json.loads(manifest_path.read_text(), object_pairs_hook=unique_json)
        if not isinstance(parsed.get("launches"), dict) or not set(("A", "B", "C")) <= set(parsed["launches"]):
            raise ValueError("probe manifest must declare all three launches")
        for server in ("A", "B", "C"):
            launch = parsed["launches"][server]
            control = probe_path(launch["control"], "optional_file")
            probe_path(control.parent, "directory")
            if control.exists():
                probe_path(control, "file", 4096)
            probe_path(launch["output"], "directory")
        probe = load_module("rc_soak_probe_windows", ROOT / "scripts/rc-probe-benchmark.py")
    y, evidence = physical.harness_height()
    template = mix.make_driver(args, physical, y, evidence)
    base = physical.load_helpers()

    class Soak(type(template)):
        def __init__(self):
            super().__init__()
            self.target = directory / "report.json"
            self.evidence = EvidenceLog(directory / "events.jsonl")
            self.rings = []
            for field in ("RCON_trace", "guard_SQL_trace"):
                self.report[field] = self.ring(field)
            self.process = monitor.Monitor(SimpleNamespace(label=args.label, seconds=args.seconds,
                interval=5 if args.smoke else SAMPLE_SECONDS, jstat_timeout=args.jstat_timeout))
            self.process.start = self.started
            self.report.update(report_kind="native_soak_tool_smoke" if args.smoke else "rc_real_native_3600_second_soak",
                native_validation="NOT_RUN", smoke=args.smoke, **{"60min_gate": False},
                utc_start=utc(), scratch_manifest=str((directory / "manifest.json").relative_to(ROOT)),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                holds=[], cold_probes=[], cold_missed_opportunities=[], monitor_samples=[],
                fixture_retained=True, assets_of_prior_runs_accessed=False)
            self.report["helper_sources"][str(ROOT / "scripts/optimization-monitor.py")] = hashlib.sha256(
                (ROOT / "scripts/optimization-monitor.py").read_bytes()).hexdigest()
            self.windows = probe.ProbeWindows(manifest_path) if probe is not None else None
            self.report.update(probe_window_measurement_status="CONFIGURED_NOT_RUN" if self.windows else "NOT_CONFIGURED_UNMEASURED")
            if self.windows is not None:
                self.report.update(probe_manifest=probe.file_meta(manifest_path), probe_configuration=deepcopy(self.windows.manifest))
                for server in ("A", "B", "C"):
                    launch = self.windows.manifest["launches"][server]
                    launch["control"] = str(probe_path(launch["control"], "optional_file"))
                    launch["output"] = str(probe_path(launch["output"], "directory"))
                for path in (ROOT / "scripts/rc-probe-benchmark.py", ROOT / "scripts/rcprobe/WindowStats.java",
                        ROOT / "scripts/rcprobe/ProbeAgent.java", manifest_path):
                    self.report["helper_sources"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.sample_period, self.cold_period = (5, 10) if args.smoke else (SAMPLE_SECONDS, 30)
            self.cold_entry, self.item_period = (2, 30) if args.smoke else (5, 120)
            self.report["conditions"].update(observation_seconds=args.seconds,
                sample_interval_seconds=self.sample_period, observer="one serial RCON issuer; no sidecar RCON",
                scenarios=args.scenarios, hot_sources=4, cold_channels=3,
                cold_input_FE=1024, cold_period_seconds=self.cold_period, item_period_seconds=self.item_period,
                backpressure_period_seconds=None if args.smoke else 900,
                backpressure_hold_seconds=15 if args.smoke else 120,
                backpressure_feed_multiplier=2, warmup_seconds=args.warmup,
                small_CUSTOM_NAME_JSON_bytes={v: len(json.dumps({"text": name}, separators=(",", ":")).encode()) for v, name in LARGE_NAMES.items()},
                CUSTOM_DATA_fields=8, ASCII_bytes_per_field=512,
                CUSTOM_DATA_canonical_JSON_bytes=len(CUSTOM_DATA_CANONICAL.encode()), CUSTOM_DATA_sha256=CUSTOM_DATA_SHA256,
                actual_codec_payload_bytes="MEASURE_ONLY_FROM_NATIVE_SQL_RESOURCE_AFTER_COMPLETE_INPUT")
            self.report["measurement"].update(
                scope="Explicit short native tool smoke,60min_gate=false." if args.smoke else "Concurrent given-load3600s soak, excluding setup/warmup/drain. Not a capacity or primary benchmark target.",
                schedule="No catch-up mutation bursts: late/skipped feed opportunities retained. Duration cannot be shortened for pass.",
                item_scope="Small stable CUSTOM_NAME distinguishes A/B; identical fixed8x512ASCII CUSTOM_DATA is representative4KiB component content, not maximum payload. No per-event component changes. ITEM OFF until both staged stacks validate completely; unknown/failed staging retains stock and requests OFF.",
                item_input_clock="Initial real32-item chest write starts the saved input bound;16 subsequent component field writes and source validation happen while ITEM OFF. These setup costs are included in initial-stock-to-output bounds. Source-decrement bounds begin after complete component staging.",
                trace="All raw RCON and guarded SQL records spill to bounded events.jsonl with absolute stream indexes; report holds only a recent ring.",
                WAL_files="Only this run's endpoint ctj/pending paths read. Atomic replacement may occur between independent SQL/WAL reads; hashes are observations, never additional assets or proof of disk power-loss durability.",
                process="Serial /proc and short jstat -gc/-gcutil observations every30s. Their request spans and overhead are saved. Heap samples and cumulative GC deltas are not a pause distribution.",
                process_boundaries="Regular scheduled samples plus explicitly post-feed terminal read. Per-process GC/CPU deltas use actual first/last read spans, which can exceed the input window slightly.",
                main_thread="With --probe-manifest, verified agent exports measure every completed instrumented Runtime.tick/tickServer call and actual tick-start TPS, with complete sparse histograms. tickServer body includes hooks; waits outside that method are represented by separate tick-start intervals. Without it these whole-window values remain UNMEASURED; mod/MC rolling timing snapshots alone are diagnostic.",
                probe_boundaries="After warmup/drain, start(trace=False) controls take effect at the next tick entry, before initial counters. Fixed export follows fixed counter_end and is copied by the daemon from completed calls; it includes the actual recorded control/counter edge delay. Stop follows real drain/quiet and final counters, sealing at a completed tick boundary. Fixed prefixes have millisecond-scale edge observations, not a promised exact3600s cutoff; use retained command spans/each JVM's own anchors. Never subtract raw nanoTime across JVMs.",
                low_flow="One outstanding1024FE probe per cold channel. Acceptance-to-observed extraction bounds use this observer's monotonic clock; a missed scheduled probe remains a coverage failure.",
                large_RCON="Only this driver gathers bounded multipart Items replies using a same-connection requestID103 ct_test pid barrier after requestID102. Barrier traffic and raw replies are recorded; historical readers/parsers unchanged.",
                backpressure="Extraction withheld only for fresh owned FE endpoints; actual RX capacity or positive-owned-credit bound recorded distinctly, then real extraction must resume.",
                cleanup="No block/ticket/SQL/WAL cleanup. Successful fully drained endpoints set OFF; failures leave current fixture state for review.")

        def ring(self, name):
            value = StreamRing(self.evidence, name)
            self.rings.append(value)
            return value

        def save(self):
            # Construction of the inherited helper is offline and never saves.
            if not hasattr(self, "evidence"):
                return
            for ring in self.rings:
                ring.spill(32)
            self.evidence.sync()
            self.report["streamed_evidence"] = self.evidence.summary()
            self.report["streamed_resident_ranges"] = {ring.name: {
                "first_absolute_index": ring.offset, "resident_records": list.__len__(ring),
                "logical_total_records": len(ring)} for ring in self.rings}
            raw = (json.dumps(report_snapshot(self.report), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
            if len(raw) > MAX_REPORT_BYTES:
                raise ValueError("soak summary size bound; retain fixtures")
            temporary = self.target.with_suffix(".json.pending")
            with temporary.open("w") as output:
                output.write(raw.decode())
            temporary.replace(self.target)

        def prepare_process(self):
            for server, info in self.report["identity"].items():
                pid = info["pid"]
                java = Path(info["java_executable"])
                jstat = java.parent / "jstat"
                if not jstat.is_file() or not os.access(jstat, os.X_OK):
                    raise ValueError("jstat required for actual heap/GC evidence: " + server)
                initial = monitor.parse_stat(Path(f"/proc/{pid}/stat").read_text())
                self.process.identity[server] = {"pid": pid, "server_id": info["server_id"],
                    "starttime_ticks": initial["starttime_ticks"], "java_executable": str(java), "jstat": str(jstat)}
                if not 0 < info["buffer_capacity_FE"] <= 2_000_000:
                    raise ValueError("FE capacity above bounded backpressure fixture limit")
                if args.smoke and info["buffer_capacity_FE"] > 64_000:
                    raise ValueError("smoke requires operator-prepared buffers.fe<=64000 to prove actual short full/recovery")
                if self.windows is not None:
                    launch = self.windows.manifest["launches"][server]
                    proc = Path(f"/proc/{pid}")
                    argv = [part.decode() for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
                    expanded, _ = base.expanded_vm_args(argv, server, (proc / "cwd").resolve())
                    configured = str(probe_path(launch["control"], "optional_file")) + ";" + str(probe_path(launch["output"], "directory"))
                    agents = [arg for arg in expanded if arg.startswith("-javaagent:") and arg.partition("=")[2] == configured]
                    if len(agents) != 1:
                        raise ValueError("probe manifest control/output not bound to verified live JVM: " + server)
                    self.report.setdefault("probe_launch_binding", {})[server] = {
                        "pid": pid, "matched_javaagent_argument": agents[0], "world_id": info["world_id"],
                        "session_id": info["session_id"], "fencing_epoch": info["fencing_epoch"]}
            self.process.report["identity"] = deepcopy(self.process.identity)

        def probe_window(self, operation, field):
            if self.windows is None:
                return None
            started = time.monotonic()
            record = {"observer_start": started, "offset_start": started - self.started,
                "trace": False, "completed": False}
            self.report.setdefault("probe_window_operations", {})[field] = record
            try:
                data = self.windows.start(trace=False) if operation == "start" else getattr(self.windows, operation)()
                if operation == "stop" and any(not point["data"].get("window_closed") for point in data.values()):
                    raise AssertionError("probe stop did not produce sealed full windows")
                self.report[field] = data  # Complete A/B/C JSONs, including every histogram bin.
                record["completed"] = True
                if operation == "fixed":
                    self.report["probe_window_measurement_status"] = "MEASURED_FIXED_PREFIX_FULL_LIFECYCLE_PENDING"
                elif operation == "stop":
                    self.report["probe_window_measurement_status"] = "MEASURED_FIXED_AND_FULL" if field == "probe_full_lifecycle" and "probe_fixed_window" in self.report else "MEASURED_INCOMPLETE_LIFECYCLE_ONLY"
                return data
            except Exception as error:
                record["failure"] = type(error).__name__ + ": " + str(error)[:1000]
                raise
            finally:
                record.update(observer_end=time.monotonic(), offset_end=time.monotonic() - self.started)
                self.report["probe_control_commands"] = deepcopy(self.windows.commands)

        def issue(self, server, value, harness=True):
            if not harness and re.search(r"\bdata get block -?\d+ -?\d+ -?\d+ Items$", value):
                transport = {}
                def send(name, command):
                    if len(command.encode()) > 1024:
                        raise ValueError("soak RCON command1KiB bound")
                    started = time.monotonic() - self.started
                    with socket.create_connection(("127.0.0.1", base.PORTS[name]), 10) as sock:
                        sock.settimeout(10)
                        password = os.environ.get("CT_TEST_RCON_PASSWORD", "ct_dev_rcon_only")
                        sock.sendall(rcon_frame(101, 3, password))
                        auth_id, auth_type, body = read_rcon_frame(sock)
                        if auth_id != 101 or auth_type != 2 or body:
                            raise ValueError("soak RCON authentication failed")
                        reply, details = query_rcon_items(sock, command, self.report["identity"][name]["pid"])
                    transport.update(details, observer_start=started, observer_end=time.monotonic() - self.started,
                        barrier_command="ct_test pid", server=name)
                    return reply
                result = physical.command_observation(self.report["RCON_trace"], self.started, server, value, send)
                self.report["RCON_trace"][-1]["multipart_transport"] = dict(transport)
                result["multipart_transport"] = dict(transport)
                return result
            return super().issue(server, value, harness)

        def chest(self, endpoint):
            own = self.chests[endpoint.name]
            x, y, z = own["position"]
            result = self.vanilla(endpoint.server, f"data get block {x} {y} {z} Items")
            parsed = parse_large_items(result["reply"], (x, y, z))
            if result.get("multipart_transport", {}).get("query_packets", 0) > 1:
                for batch in self.pending.values():
                    proofs = batch.setdefault("large_reply_transport_proofs", [])
                    if len(proofs) < 8:
                        proofs.append({"endpoint": endpoint.name, "start": result["start"], "end": result["end"],
                            "reply_sha256": hashlib.sha256(result["reply"].encode()).hexdigest(),
                            "RCON_trace_index": len(self.report["RCON_trace"]) - 1,
                            "multipart_transport": result["multipart_transport"]})
            return dict(parsed, endpoint=endpoint.name, start=result["start"], end=result["end"],
                count=parsed["total"], RCON_trace_index=len(self.report["RCON_trace"]) - 1)

        def attempt_items(self, lane, phase, round_index):
            if lane.name in self.pending:
                raise AssertionError("prior ITEM batch pending; never overwrite")
            endpoint = lane.sources[0]
            attempts = [{"round": round_index, "variant": variant, "requested": args.items,
                "accepted": 0, "at": time.monotonic() - self.started} for variant in LARGE_NAMES]
            phase["item_attempts"].extend(attempts)
            batch = None
            try:
                reply = self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {mix.ITEM} OFF")
                if reply["reply"].strip() != "MODE OFF":
                    raise AssertionError("source ITEM OFF not confirmed; no staging attempted")
                before = self.frame(lane, round_index)
                if before["source"]["count"] or any(before["totals"].values()):
                    raise AssertionError("owned chest nonempty at new component staging; do not overwrite")
                sequence = self.sequences[lane.name] = self.sequences.get(lane.name, 0) + 1
                batch = {"lane": lane.name, "phase": phase["name"], "repeat": phase["repeat"],
                    "sequence": sequence, "round": round_index, "passed": False,
                    "variants": {variant: {} for variant in LARGE_NAMES}, "clears": [], "before": before,
                    "previous_targets": before, "staging_commands": [], "staging_complete": False,
                    "CUSTOM_DATA_sha256": CUSTOM_DATA_SHA256, "source_ITEM_OFF_confirmed": reply}
                for field in ("frames", "source_observations", "item_quiet_checks"):
                    batch[field] = self.ring("ITEM:" + str(sequence) + ":" + field)
                    batch[field + "_stream"] = batch[field].name
                phase["item_batches"].append(sequence)
                self.report["item_batches"].append(batch)
                self.pending[lane.name] = batch
                x, y, z = self.chests[endpoint.name]["position"]
                for slot, (variant, record) in enumerate(batch["variants"].items()):
                    attempts[slot].update(accepted=None, status="UNKNOWN_INITIAL_STOCK_WRITE")
                    injection = self.vanilla(endpoint.server,
                        f"item replace block {x} {y} {z} container.{slot} with {mix.item_argument(variant)} {args.items}")
                    if "replaced" not in injection["reply"].lower() or "slot" not in injection["reply"].lower():
                        raise AssertionError("unconfirmed initial component stock write; no replay")
                    attempts[slot].update(accepted=args.items, status="STOCK_CREATED_COMPONENTS_STILL_STAGING")
                    mix.ledger_add(self.ledgers[lane.name], "item_" + variant, "accepted", args.items, endpoint.name)
                    record["injection"] = {key: injection[key] for key in ("start", "end")}
                    record["injection"]["RCON_trace_index"] = len(self.report["RCON_trace"]) - 1
                    phase["events"].append(dict(record["injection"], kind="input", resource="item_" + variant,
                        unit="items", endpoint=endpoint.name, requested=args.items, amount=args.items,
                        result="CONFIRMED_STOCK_CREATED_WITH_ITEM_OFF_COMPONENT_STAGING_PENDING"))
                    for field, value in CUSTOM_DATA.items():
                        command = component_field_command((x, y, z), slot, field)
                        result = self.vanilla(endpoint.server, command)
                        batch["staging_commands"].append({"slot": slot, "field": field,
                            "value_bytes": len(value), "value_sha256": hashlib.sha256(value.encode()).hexdigest(),
                            "trace_index": len(self.report["RCON_trace"]) - 1, "reply": result["reply"],
                            "start": result["start"], "end": result["end"]})
                        if "modified" not in result["reply"].lower():
                            raise AssertionError("component staging mutation not confirmed; source remains OFF")
                staged = self.chest(endpoint)
                if staged["by_variant"] != {variant: args.items for variant in LARGE_NAMES} or {point["slot"] for point in staged["stacks"]} != {0, 1}:
                    raise AssertionError("staged complete fixed component source mismatch")
                batch.update(staging_complete=True, validated_staged_source=staged)
                self.source_observation(lane, batch, staged, phase["events"])
                for attempt in attempts:
                    attempt["status"] = "CONFIRMED_COMPLETE_FIXED_COMPONENT_STOCK"
                enabled = self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {mix.ITEM} SEND")
                if enabled["reply"].strip() != "MODE SEND":
                    raise AssertionError("source ITEM SEND unconfirmed after valid component staging")
                batch["source_ITEM_SEND_confirmed"] = enabled
            except Exception as error:
                if batch is not None:
                    batch["staging_failure"] = type(error).__name__ + ": " + str(error)[:1000]
                try:
                    off = self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {mix.ITEM} OFF")
                    if batch is not None:
                        batch["failure_ITEM_OFF_confirmation"] = off
                        batch["failure_ITEM_OFF_confirmed"] = off["reply"].strip() == "MODE OFF"
                except Exception as off_error:
                    if batch is not None:
                        batch["failure_ITEM_OFF_unconfirmed"] = type(off_error).__name__
                raise

        def service_items(self, lane, phase, order):
            batch = self.pending.get(lane.name)
            super().service_items(lane, phase, order)
            if batch is not None and batch["passed"]:
                for field in ("frames", "source_observations", "item_quiet_checks"):
                    batch[field + "_records"] = len(batch[field])
                    batch[field].spill()

        def wal_files(self):
            observations, total = [], 0
            for endpoint in self.devices:
                info = self.report["identity"][endpoint.server]
                parent = ROOT / ("run-" + endpoint.server) / info["level_name"] / "cross_tesseract/journal"
                for suffix in (".ctj", ".pending"):
                    path = parent / (str(uuid.UUID(endpoint.id)) + suffix)
                    record = {"endpoint": endpoint.name, "path": str(path.relative_to(ROOT)),
                        "start": time.monotonic() - self.started}
                    if path.is_symlink() or parent.is_symlink():
                        raise ValueError("owned WAL symlink rejected")
                    try:
                        with path.open("rb") as source:
                            metadata = os.fstat(source.fileno())
                            if metadata.st_size > 2 * 1024 * 1024:
                                raise ValueError("owned WAL file bound exceeded")
                            data = source.read(2 * 1024 * 1024 + 1) if suffix == ".ctj" else b""
                            total += len(data)
                            if total > 16 * 1024 * 1024:
                                raise ValueError("WAL sample total bound exceeded")
                            record.update(present=True, bytes=metadata.st_size, inode=metadata.st_ino,
                                observed_open_mtime_ns=metadata.st_mtime_ns,
                                sha256=hashlib.sha256(data).hexdigest() if suffix == ".ctj" else None)
                    except FileNotFoundError:
                        record["present"] = False
                    record["end"] = time.monotonic() - self.started
                    observations.append(record)
            return observations

        def monitor_sample(self, phase, scheduled, backpressure, current_hold):
            record = {"scheduled": scheduled, "utc": utc(), "start": time.monotonic() - self.started,
                "runtime_SQL_counters": self.snapshot(), "process": [], "resources": {}}
            phase.setdefault("monitor_samples", []).append(record)
            for server in base.PORTS:
                point = self.process.sample(server)
                self.process.report["samples"].append(point)
                record["process"].append(point)
                if point.get("error") or not point.get("jstat_gc", {}).get("values") or not point.get("jstat_gcutil", {}).get("values"):
                    self.report["failures"].append("process/heapGC sample failed: " + server)
            record["WAL_files"] = self.wal_files()
            for lanes in self.cases.values():
                for lane in lanes:
                    record["resources"][lane.name] = self.residue_kinds(lane, (mix.ITEM, mix.FLUID, mix.FE))
            if current_hold is not None:
                rows = base.sql("SELECT endpoint_id,COUNT(*),COALESCE(SUM(remaining),0) FROM ct_transfers "
                    "WHERE cluster_id='dev_three_v1' AND channel_id='" + backpressure.channel + "' "
                    "AND kind='ALLOCATE' AND remaining>0 GROUP BY endpoint_id")
                counts = {row[0]: {"positive_owned_credits": int(row[1]), "remaining": int(row[2])} for row in rows}
                local = record["resources"][backpressure.name]["local_buffers"]
                full = []
                for endpoint in backpressure.sinks:
                    rx = local[endpoint.name]["rxFE"]
                    capacity = self.report["identity"][endpoint.server]["buffer_capacity_FE"]
                    owned = counts.get(endpoint.id, {"positive_owned_credits": 0, "remaining": 0})
                    reason = "local_FE_capacity" if rx == capacity else "positive_owned_credit_limit" if owned["positive_owned_credits"] >= 32 else None
                    full.append({"endpoint": endpoint.name, "rxFE": rx, "configured_capacity": capacity, **owned, "bound_reached": reason})
                proof = {"at": time.monotonic() - self.started, "endpoints": full,
                    "all_sinks_reached_a_recorded_bound": all(point["bound_reached"] for point in full)}
                current_hold["full_observations"].append(proof)
            record["end"] = time.monotonic() - self.started
            self.save()
            return record

        def service_fe(self, lane, events, order):
            endpoints = lane.sinks[order % len(lane.sinks):] + lane.sinks[:order % len(lane.sinks)]
            return [self.cap(lane, endpoint, "FE", "pull", 2_147_483_647, events) for endpoint in endpoints]

        def conserved(self):
            return not self.pending and all(record["accepted"] == record["external_output"] and
                (not key.startswith("item_") or record["source_actual_decrement"] == record["accepted"])
                for ledger in self.ledgers.values() for key, record in ledger.items())

        def drive_concurrent(self, seconds, name, items):
            phase = {"name": name, "repeat": 1, "requested_seconds": seconds,
                "events": self.ring(name + ":business"), "item_attempts": [], "item_batches": [],
                "rounds": 0, "missed_feed_opportunities": 0, "monitor_samples": [],
                "cold_missed_opportunities": [], "start": time.monotonic() - self.started}
            self.report[name] = phase
            mixed, hot = self.cases["mixed"][0], self.cases["hotspot"][0]
            cold, back = self.cases["hotspot"][1:], self.cases["backpressure"][0]
            origin, last_round, last_poll, next_monitor = time.monotonic(), -1, -1, 0
            next_cold, next_item, probes = float(self.cold_entry), 0.0, {}
            current_hold, previous_hold = None, None
            while time.monotonic() < origin + seconds:
                now = time.monotonic()
                offset = now - origin
                cycle = hold_cycle(offset, args.smoke) if items else None
                if cycle != previous_hold:
                    if current_hold is not None:
                        current_hold.update(release_at=now - self.started,
                            actual_hold_seconds=now - self.started - current_hold["start"],
                            output_before_release=self.ledgers[back.name]["FE"]["external_output"])
                        current_hold = None
                    if cycle is not None:
                        current_hold = {"cycle": cycle, "start": now - self.started, "full_observations": []}
                        self.report["holds"].append(current_hold)
                    previous_hold = cycle
                round_index = int(offset // args.feed_period)
                if round_index > last_round:
                    phase["missed_feed_opportunities"] += round_index - last_round - 1
                    phase["rounds"] += 1
                    for lane in (mixed, hot, back):
                        for endpoint in lane.sources:
                            for _ in range(2 if lane is back else 1):
                                if time.monotonic() >= origin + seconds:
                                    break
                                self.cap(lane, endpoint, "FE", "push", args.fe, phase["events"])
                    if time.monotonic() < origin + seconds:
                        self.cap(mixed, mixed.sources[0], "water", "push", args.water, phase["events"])
                    last_round = round_index
                if offset >= next_cold:
                    skipped = int((offset - next_cold) // self.cold_period)
                    if skipped:
                        phase["cold_missed_opportunities"].append({"scheduled": next_cold,
                            "count_per_channel": skipped, "reason": "observer_missed_fixed_cold_slots"})
                    scheduled_cold = next_cold + skipped * self.cold_period
                    for lane in cold:
                        if lane.name in probes:
                            phase["cold_missed_opportunities"].append({"lane": lane.name, "at": offset, "reason": "previous_probe_still_outstanding"})
                            continue
                        event = self.cap(lane, lane.sources[0], "FE", "push", 1024, phase["events"])
                        probe = {"lane": lane.name, "phase": name, "scheduled": scheduled_cold, "input": dict(event),
                            "baseline_external_output": self.ledgers[lane.name]["FE"]["external_output"],
                            "last_output_read": {"start": event["start"], "end": event["end"]}, "passed": False}
                        self.report["cold_probes"].append(probe)
                        probes[lane.name] = probe
                    next_cold = scheduled_cold + self.cold_period  # Fixed slots; no catch-up mutation burst.
                if items and offset >= next_item:
                    if mixed.name in self.pending:
                        phase.setdefault("deferred_item_opportunities", []).append({"scheduled": next_item, "at": offset})
                    else:
                        before = self.frame(mixed, int(offset // self.item_period))
                        if before["source"]["count"] or any(before["totals"].values()):
                            phase.setdefault("deferred_item_opportunities", []).append({"scheduled": next_item,
                                "at": offset, "reason": "own_chest_not_empty_no_overwrite"})
                        else:
                            self.attempt_items(mixed, phase, int(offset // self.item_period))
                    next_item = (int(offset // self.item_period) + 1) * self.item_period
                poll_index = int((time.monotonic() - origin) // args.poll)
                if poll_index > last_poll:
                    self.service(mixed, phase, poll_index)
                    self.service_fe(hot, phase["events"], poll_index)
                    for lane in cold:
                        event = self.service_fe(lane, phase["events"], poll_index)[0]
                        probe = probes.get(lane.name)
                        if probe:
                            output = self.ledgers[lane.name]["FE"]["external_output"] - probe["baseline_external_output"]
                            if output > probe["input"]["amount"]:
                                raise AssertionError("cold output exceeds its single outstanding input")
                            if output == probe["input"]["amount"]:
                                bound = {"start": probe["last_output_read"]["start"], "end": event["end"]}
                                probe.update(output_interval=bound, input_to_full_output_bounds=physical.e2e(probe["input"], bound),
                                    passed=probe["input"]["amount"] == 1024, completed_at=event["end"])
                                del probes[lane.name]
                            else:
                                probe["last_output_read"] = {"start": event["start"], "end": event["end"]}
                    if current_hold is None:
                        output_events = self.service_fe(back, phase["events"], poll_index)
                        for hold in self.report["holds"]:
                            if "release_at" in hold and "first_resumed_output" not in hold:
                                positive = next((event for event in output_events if event["amount"] > 0), None)
                                if positive:
                                    hold["first_resumed_output"] = dict(positive)
                    last_poll = poll_index
                if items and time.monotonic() - origin >= next_monitor:
                    self.monitor_sample(phase, next_monitor, back, current_hold)
                    next_monitor = (int((time.monotonic() - origin) // self.sample_period) + 1) * self.sample_period
                delay = min(origin + seconds, origin + (last_round + 1) * args.feed_period,
                    origin + (last_poll + 1) * args.poll) - time.monotonic()
                if delay > 0:
                    time.sleep(min(delay, .25))
            phase.update(end=time.monotonic() - self.started, actual_observation_seconds=time.monotonic() - origin,
                ledger_at_end=deepcopy(self.ledgers), unfinished_cold_probes=list(probes.values()))
            return phase

        def drain_all(self, name):
            phase = {"name": name, "events": self.ring(name + ":business"),
                "start": time.monotonic() - self.started, "quiet_checks": [], "passed": False}
            self.report[name] = phase
            deadline, order, quiet_start = time.monotonic() + args.timeout, 0, None
            while time.monotonic() < deadline:
                for case, lanes in self.cases.items():
                    for lane in lanes:
                        self.service(lane, phase, order) if case == "mixed" else self.service_fe(lane, phase["events"], order)
                if self.conserved():
                    check = {"at": time.monotonic() - self.started, "lanes": {}, "empty": True}
                    for lanes in self.cases.values():
                        for lane in lanes:
                            frame = self.frame(lane, order)
                            residue = self.residue_kinds(lane, (mix.ITEM, mix.FLUID, mix.FE))
                            empty = frame["source"]["count"] == 0 and not any(frame["totals"].values()) and self.zero(residue, (mix.ITEM, mix.FLUID, mix.FE))
                            check["lanes"][lane.name] = {"frame": frame, "residue": residue, "empty": empty}
                            check["empty"] &= empty
                    phase["quiet_checks"].append(check)
                    quiet_start = (quiet_start if quiet_start is not None else time.monotonic()) if check["empty"] else None
                    if quiet_start is not None and time.monotonic() - quiet_start >= args.quiet:
                        phase.update(end=time.monotonic() - self.started, passed=True,
                            final_ledger=deepcopy(self.ledgers), quiet_seconds=time.monotonic() - quiet_start)
                        return phase
                order += 1
                time.sleep(args.poll)
            raise AssertionError("bounded final drain/quiet failed; isolated assets retained")

        def run(self):
            self.save()
            try:
                self.verify_isolation()
                self.prepare_process()
                self.setup()
                for lanes in self.cases.values():
                    for lane in lanes:
                        self.ledgers[lane.name] = mix.new_ledger()
                    self.activate(lanes, True)
                self.report["counter_before_warmup"] = self.snapshot()
                self.drive_concurrent(args.warmup, "warmup", False)
                self.drain_all("warmup_drain")
                self.probe_window("start", "probe_start")
                self.report["counter_before_observation"] = self.snapshot()
                self.report["ledger_before_observation"] = deepcopy(self.ledgers)
                phase = self.drive_concurrent(args.seconds, "observation", True)
                # Counter end precedes final drain; tail costs remain separate.
                self.report["counter_after_observation"] = self.snapshot()
                self.probe_window("fixed", "probe_fixed_window")
                terminal = self.monitor_sample(phase, args.seconds, self.cases["backpressure"][0], None)
                terminal["boundary"] = "post_fixed_prefix_terminal_read_before_final_drain"
                self.drain_all("final_drain")
                self.report["counter_after_drain"] = self.snapshot()
                self.probe_window("stop", "probe_full_lifecycle")
                self.report["observation_counter_delta"] = mix.cost_difference(
                    self.report["counter_before_observation"], self.report["counter_after_observation"])
                self.report["observation_and_tail_counter_delta"] = mix.cost_difference(
                    self.report["counter_before_observation"], self.report["counter_after_drain"])
                self.report["warmup_observation_and_tail_counter_delta"] = mix.cost_difference(
                    self.report["counter_before_warmup"], self.report["counter_after_drain"])
                self.report["business_ledger"] = deepcopy(self.ledgers)
                self.report["observation_and_tail_business_delta"] = {lane: mix.ledger_change(
                    self.report["ledger_before_observation"][lane], ledger) for lane, ledger in self.ledgers.items()}
                payload_rows = base.sql("SELECT r.resource_id,r.payload_hash,OCTET_LENGTH(r.payload) FROM ct_resources r "
                    "WHERE r.cluster_id='dev_three_v1' AND r.kind='" + mix.ITEM + "' AND EXISTS(SELECT 1 FROM ct_transfers t "
                    "WHERE t.cluster_id=r.cluster_id AND t.resource_id=r.resource_id AND t.channel_id='" + self.cases["mixed"][0].channel + "') ORDER BY r.resource_id")
                self.report["actual_native_ITEM_codec_payloads"] = [{"resource_id": str(uuid.UUID(row[0])),
                    "payload_sha256": row[1], "actual_payload_bytes": int(row[2])} for row in payload_rows]
                self.verify_final_identity()
                helper_end = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    for path in self.report["helper_sources"]}
                self.report["helper_sources_at_end"] = helper_end
                if helper_end != self.report["helper_sources"] or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != self.report["source_sha256"]:
                    raise AssertionError("Python helper/source files changed during soak")
                for lanes in self.cases.values():
                    self.activate(lanes, False)
                self.process.summarize()
                self.report["process_summary"] = self.process.report["summary"]
                metrics = self.report["observation_and_tail_counter_delta"]["sum"]
                planned_samples = (args.seconds + self.sample_period - 1) // self.sample_period + 1
                planned_probes = ((args.seconds - self.cold_entry + self.cold_period - 1) // self.cold_period) * 3
                planned_item_batches = (args.seconds + self.item_period - 1) // self.item_period
                self.report["coverage_checks"] = {
                    "full_declared_observation_seconds": phase["actual_observation_seconds"] >= args.seconds,
                    "expected_monitor_samples_including_post_feed_terminal": len(phase["monitor_samples"]) == planned_samples,
                    "monitor_scheduling_lateness_below_period": all(
                        sample["start"] - phase["start"] - sample["scheduled"] < self.sample_period for sample in phase["monitor_samples"]),
                    "all_cold_probes_complete": all(probe["passed"] for probe in self.report["cold_probes"]),
                    "all_planned_observation_cold_probes_attempted": len([probe for probe in self.report["cold_probes"] if probe["phase"] == "observation"]) == planned_probes,
                    "no_cold_opportunity_lost": not phase["cold_missed_opportunities"],
                    "all_planned_holds_full_then_resumed": len(self.report["holds"]) == (1 if args.smoke else 4) and all(
                        any(proof["all_sinks_reached_a_recorded_bound"] for proof in hold["full_observations"])
                        and "first_resumed_output" in hold for hold in self.report["holds"]),
                    "all_planned_component_batches_complete": len(phase["item_batches"]) == planned_item_batches and all(batch["passed"] for batch in self.report["item_batches"]),
                    "two_stable_native_ITEM_payloads_at_least4KiB": len(payload_rows) == 2 and all(int(row[2]) >= 4096 for row in payload_rows),
                    "multipart_large_chest_reply_observed": any(record.get("multipart_transport", {}).get("query_packets", 0) > 1
                        for batch in self.report["item_batches"] for record in batch.get("large_reply_transport_proofs", [])),
                    "all_hot_and_mixed_FE_recipients_served": all(
                        self.report["observation_and_tail_business_delta"][lane.name]["FE"]["output_by_endpoint"].get(endpoint.name, 0) > 0
                        for lane in (self.cases["mixed"][0], self.cases["hotspot"][0]) for endpoint in lane.sinks),
                    "no_worker_error_rejection_quarantine": all(metrics[key] == 0 for key in ("errors", "queue_rejected", "quarantined")),
                    "no_warmup_worker_error_rejection_quarantine": all(
                        self.report["warmup_observation_and_tail_counter_delta"]["sum"][key] == 0
                        for key in ("errors", "queue_rejected", "quarantined")),
                    "optional_full_window_probe_complete": self.windows is None or self.report["probe_window_measurement_status"] == "MEASURED_FIXED_AND_FULL",
                    "final_conservation_and_zero_guard": self.report["final_drain"]["passed"] and self.conserved()}
                self.report["passed"] = all(self.report["coverage_checks"].values()) and not self.report["failures"]
                self.report["completed_component_variant_samples"] = sum(2 for batch in self.report["item_batches"] if batch["passed"])
                self.report["planned_component_variant_samples"] = planned_item_batches * 2
                self.report["60min_gate"] = not args.smoke and self.report["passed"]
                if not self.report["passed"]:
                    self.report["failures"].append("coverage/function checks failed; inspect individual recorded checks")
            except KeyboardInterrupt:
                self.report["failures"].append("operator interrupted; full soak NOT completed")
            except Exception as error:
                self.report["failures"].append(type(error).__name__ + ": " + str(error)[:2000])
            finally:
                if self.windows is not None and self.windows.token is not None:
                    try:
                        self.probe_window("stop", "probe_incomplete_window")
                    except Exception as error:
                        self.report["failures"].append("Probe finally stop: " + type(error).__name__ + ": " + str(error)[:1000])
                        self.report.update(passed=False, **{"60min_gate": False})
                self.report.update(utc_end=utc(), elapsed_seconds=time.monotonic() - self.started,
                    native_validation="EXECUTED_FUNCTIONAL_PASS" if self.report["passed"] else "NOT_COMPLETED_OR_FAILED")
                try:
                    self.save()
                    for ring in self.rings:
                        ring.spill()
                    self.report["streamed_evidence"] = self.evidence.summary()
                    self.save()
                    with self.target.with_name("completion.json").open("x") as output:
                        json.dump({"passed": self.report["passed"], "procedure_completed": True,
                            "60min_gate": self.report["60min_gate"], "utc_end": self.report["utc_end"],
                            "report": str(self.target.relative_to(ROOT)),
                            "report_sha256": hashlib.sha256(self.target.read_bytes()).hexdigest()}, output, indent=2)
                        output.write("\n")
                except Exception as error:
                    self.report.update(passed=False, native_validation="FAILED_EVIDENCE_FINALIZATION", **{"60min_gate": False})
                    # A reached output bound cannot silently turn an old saved
                    # report into a completed pass. Keep fresh ledger/identity
                    # and recent unknown mutations in a separate bounded file.
                    failure = {"passed": False, "procedure_completed": False, "60min_gate": False,
                        "utc_end": utc(), "failure": type(error).__name__ + ": " + str(error)[:2000],
                        "fixture_retained": True, "identity": self.report.get("identity"),
                        "fixtures": self.report.get("fixtures"), "ledger": self.ledgers,
                        "streamed_evidence": self.evidence.summary(),
                        "recent_stream_records": {ring.name: list(ring)[-32:] for ring in self.rings}}
                    with self.target.with_name("finalization-failure.json").open("x") as output:
                        json.dump(failure, output, indent=2)
                        output.write("\n")
                finally:
                    self.evidence.close()
            print(json.dumps({"passed": self.report["passed"], "report": str(self.target.relative_to(ROOT)),
                "native_validation": self.report["native_validation"]}), flush=True)
            return 0 if self.report["passed"] else 1

    return Soak()


def self_test():
    class Tests(unittest.TestCase):
        def test_hold_plan_has_four_finite_full_recovery_periods(self):
            self.assertEqual([index for index in range(3600) if hold_cycle(index) is not None].__len__(), 480)
            for cycle in range(4):
                self.assertIsNone(hold_cycle(cycle * 900 + 59.99))
                self.assertEqual(hold_cycle(cycle * 900 + 60), cycle)
                self.assertIsNone(hold_cycle(cycle * 900 + 180))
        def test_streamed_absolute_indexes_remain_stable_and_bounded(self):
            with tempfile.TemporaryDirectory() as tmp:
                log = EvidenceLog(Path(tmp) / "events.jsonl")
                ring = StreamRing(log, "offline")
                for index in range(1000):
                    record = {"value": index}
                    ring.append(record)
                    self.assertEqual(index, ring.index(dict(record)))
                    record["complete"] = True
                self.assertEqual(len(ring), 1000)
                self.assertLessEqual(list.__len__(ring), 256)
                ring.spill()
                log.close()
                data = [json.loads(line) for line in (Path(tmp) / "events.jsonl").read_text().splitlines()]
                self.assertEqual([point["index"] for point in data], list(range(1000)))
                self.assertTrue(all(point["record"]["complete"] for point in data))
        def test_spilled_ring_plain_snapshot_is_valid_json_without_changing_indexes(self):
            with tempfile.TemporaryDirectory() as tmp:
                log = EvidenceLog(Path(tmp) / "events.jsonl")
                ring = StreamRing(log, "offline")
                ring.append({"value": 0}); ring.append({"value": 1})
                ring.spill()
                self.assertEqual(len(ring), 2)
                self.assertEqual(list.__len__(ring), 0)
                with self.assertRaises(json.JSONDecodeError):
                    json.loads(json.dumps({"nested": {"trace": ring}}, indent=2))
                self.assertEqual(json.loads(json.dumps(report_snapshot({"nested": {"trace": ring}}))), {"nested": {"trace": []}})
                ring.append({"value": 2})
                self.assertEqual(ring.index({"value": 2}), 2)
                self.assertEqual(report_snapshot({"trace": ring})["trace"], [{"value": 2}])
                self.assertEqual(len(ring), 3)
                log.close()
        def test_default_mode_cannot_open_sockets_or_run_processes(self):
            with patch("socket.socket", side_effect=AssertionError("offline socket")), patch("subprocess.run", side_effect=AssertionError("offline process")):
                self.assertEqual(main([]), 0)
        def test_short_or_unsafe_soak_rejected_offline(self):
            args = parse_args(["--label", "rc-soak-unit", "--world-prefix", "world-opt-rc-soak-unit", "--operator-revision", "a" * 40])
            validate_args(args)
            for field, value in (("seconds", 3599), ("label", "old-assets"), ("world_prefix", "world"), ("operator_revision", "75392af")):
                changed = deepcopy(args)
                setattr(changed, field, value)
                with self.assertRaises(ValueError): validate_args(changed)
        def large_reply(self, variant="A", custom=None):
            fields = CUSTOM_DATA if custom is None else custom
            custom_snbt = "{" + ",".join(key + ":" + json.dumps(value) for key, value in fields.items()) + "}"
            component = json.dumps({"text": LARGE_NAMES[variant]}, separators=(",", ":"))
            return "0, 64, 0 has the following block data: [{Slot:0b,id:\"minecraft:stone\",count:32,components:{\"minecraft:custom_name\":'" + component + "',\"minecraft:custom_data\":" + custom_snbt + "}}]"
        def test_fixed4KiB_custom_data_and_small_name_parse_strictly(self):
            for variant, name in LARGE_NAMES.items():
                component = json.dumps({"text": name}, separators=(",", ":"))
                self.assertGreater(len(component.encode()), 200)
                self.assertLessEqual(len(component.encode()), 256)
                parsed = parse_large_items(self.large_reply(variant), (0, 64, 0))
                self.assertEqual(parsed["by_variant"][variant], 32)
                self.assertEqual(parsed["stacks"][0]["custom_data_sha256"], CUSTOM_DATA_SHA256)
                self.assertGreaterEqual(parsed["stacks"][0]["custom_data_canonical_JSON_bytes"], 4096)
                self.assertEqual(parse_large_items(self.large_reply(variant).replace('"' + 'x' * 512 + '"', 'x' * 512), (0, 64, 0))["by_variant"][variant], 32)
        def test_large_parser_rejects_partial_foreign_duplicate_and_oversize(self):
            cases = [self.large_reply(custom={"r0": "x" * 512}),
                self.large_reply(custom=dict(CUSTOM_DATA, r7="y" * 512)),
                self.large_reply(custom=dict(CUSTOM_DATA, r8="x" * 512)),
                self.large_reply().replace("Slot:0b", "Slot:0b,Slot:1b"),
                self.large_reply().replace('"minecraft:custom_data"', '"minecraft:arbitrary"'),
                "x" * 32769]
            for reply in cases:
                with self.assertRaises(ValueError): parse_large_items(reply, (0, 64, 0))
            with self.assertRaises(ValueError): parse_large_items(self.large_reply(), (1, 64, 0))
            with self.assertRaises(ValueError): SoakSNBT("[" * 9 + "]" * 9).parse()
        def test_multiframe_read_requires_same_connection_pid_barrier(self):
            body = self.large_reply().encode()
            self.assertGreater(len(body), 4096)
            frames = iter([(102, 0, body[:4096]), (102, 0, body[4096:]), (103, 0, b"PID 41")])
            reply, proof = collect_rcon_items(lambda: next(frames), 41)
            self.assertEqual(reply.encode(), body)
            self.assertEqual(proof["query_packets"], 2)
            for bad in ([(102, 0, body), (103, 0, b"PID 42")], [(104, 0, body)], [(103, 0, b"PID 41")], [(102, 2, body)], [(102, 0, b"x" * 32769)]):
                frames = iter(bad)
                with self.assertRaises(ValueError): collect_rcon_items(lambda: next(frames), 41)
        def test_native_single_read_request_boundary_and_sequential_pid_barrier(self):
            body = self.large_reply().encode()
            first_reply = rcon_frame(102, 0, body[:4096].decode())
            rest_reply = rcon_frame(102, 0, body[4096:].decode())
            class NativeSocketModel:
                def __init__(self):
                    self.pending = bytearray(); self.requests = []; self.read_bytes = 0
                def sendall(self, data):
                    # The actual1.21.1 length gate rejects coalesced requests.
                    if struct.unpack("<i", data[:4])[0] != len(data) - 4:
                        raise ValueError("native RconClient single-read length rejection")
                    identifier, kind = struct.unpack("<ii", data[4:12])
                    self.requests.append(identifier)
                    if identifier == 102:
                        self.pending.extend(first_reply + rest_reply)
                    elif identifier == 103:
                        if self.read_bytes < len(first_reply):
                            raise AssertionError("barrier sent before first query response")
                        self.pending.extend(rcon_frame(103, 0, "PID 41"))
                def recv(self, size):
                    data = bytes(self.pending[:size]); del self.pending[:size]
                    self.read_bytes += len(data); return data
            bad = NativeSocketModel()
            with self.assertRaises(ValueError):
                bad.sendall(rcon_frame(102, 2, "query") + rcon_frame(103, 2, "ct_test pid"))
            sock = NativeSocketModel()
            reply, proof = query_rcon_items(sock, "query", 41)
            self.assertEqual(reply.encode(), body)
            self.assertEqual(sock.requests, [102, 103])
            self.assertEqual(proof["query_packets"], 2)
            self.assertTrue(proof["barrier_sent_after_first_query_response"])
        def test_staging_commands_are_fixed_fields_and_below1KiB(self):
            for slot in (0, 1):
                for field in CUSTOM_DATA:
                    command = component_field_command((27_999_940, 64, -27_999_940), slot, field)
                    self.assertLessEqual(len(("execute in minecraft:overworld run " + command).encode()), 1024)
                    self.assertIn('"minecraft:custom_data".' + field, command)
            with self.assertRaises(ValueError): component_field_command((0, 64, 0), 2, "r0")
            with self.assertRaises(ValueError): component_field_command((0, 64, 0), 0, "foreign")
        def test_smoke_is_explicit_and_never_shortens_normal_gate(self):
            smoke = parse_args(["--smoke", "--label", "rc-soak-smoke-unit", "--world-prefix", "world-opt-rc-soak-unit", "--operator-revision", "a" * 40])
            validate_args(smoke)
            self.assertEqual(smoke.seconds, 60)
            self.assertEqual(hold_cycle(3, True), 0)
            self.assertIsNone(hold_cycle(18, True))
            with tempfile.TemporaryDirectory(prefix="rc-soak-offline-smoke-", dir=ROOT / "scratch") as tmp:
                soak = make_soak(smoke, Path(tmp))
                self.assertEqual(soak.report["report_kind"], "native_soak_tool_smoke")
                self.assertFalse(soak.report["60min_gate"])
                soak.evidence.close()
        def test_helper_construction_and_failed_preflight_finalize_without_live_calls(self):
            args = parse_args(["--label", "rc-soak-offline-unit", "--world-prefix", "world-opt-rc-soak-unit", "--operator-revision", "a" * 40])
            with tempfile.TemporaryDirectory(prefix="rc-soak-offline-unit-", dir=ROOT / "scratch") as tmp:
                with patch("socket.socket", side_effect=AssertionError("offline socket")), patch("subprocess.run", side_effect=AssertionError("offline process")):
                    soak = make_soak(args, Path(tmp))
                    soak.verify_isolation = lambda: (_ for _ in ()).throw(ValueError("offline intentional preflight rejection"))
                    self.assertEqual(soak.run(), 1)
                report = json.loads((Path(tmp) / "report.json").read_text())
                self.assertFalse(report["passed"])
                self.assertFalse(report["native_executed"])
                self.assertIn("offline intentional preflight rejection", report["failures"][0])
                self.assertTrue((Path(tmp) / "completion.json").is_file())
        def test_optional_probe_preserves_full_histograms_and_stops_on_failure(self):
            with tempfile.TemporaryDirectory(prefix="rc-soak-offline-probe-", dir=ROOT / "scratch") as tmp:
                path = Path(tmp)
                launches = {}
                for server in ("A", "B", "C"):
                    directory = path / server
                    directory.mkdir()
                    launches[server] = {"control": str(directory / "control.txt"), "output": str(directory)}
                manifest = path / "probe-manifest.json"
                manifest.write_text(json.dumps({"launches": launches}))
                args = parse_args(["--label", "rc-soak-probe-unit", "--world-prefix", "world-opt-rc-soak-unit",
                    "--operator-revision", "a" * 40, "--probe-manifest", str(manifest)])
                calls = []
                bins = [[32, 7], [1023, 3]]
                class OfflineWindows:
                    token = None
                    commands = []
                    def start(self, trace):
                        self.token = "offline-test-token"
                        calls.append(("start", trace))
                        return self.values(False)
                    def fixed(self):
                        calls.append(("fixed", None))
                        return self.values(False)
                    def stop(self):
                        calls.append(("stop", None))
                        self.token = None
                        return self.values(True)
                    def values(self, closed):
                        return {server: {"data": {"window_closed": closed,
                            "spans": {"server_tick": {"inclusive": {"histogram_upper_ns_count": deepcopy(bins)}}}}}
                            for server in ("A", "B", "C")}
                with patch("socket.socket", side_effect=AssertionError("offline socket")), patch("subprocess.run", side_effect=AssertionError("offline process")):
                    soak = make_soak(args, path)
                    self.assertEqual(type(soak.windows).__name__, "ProbeWindows")
                    soak.windows = OfflineWindows()
                    soak.probe_window("start", "probe_start")
                    soak.probe_window("fixed", "probe_fixed_window")
                    soak.probe_window("stop", "probe_full_lifecycle")
                    self.assertEqual(calls, [("start", False), ("fixed", None), ("stop", None)])
                    self.assertEqual(soak.report["probe_full_lifecycle"]["C"]["data"]["spans"]["server_tick"]["inclusive"]["histogram_upper_ns_count"], bins)
                    self.assertEqual(soak.report["probe_window_measurement_status"], "MEASURED_FIXED_AND_FULL")
                    soak.probe_window("start", "probe_start")
                    soak.verify_isolation = lambda: (_ for _ in ()).throw(ValueError("offline intentional active-probe failure"))
                    self.assertEqual(soak.run(), 1)
                self.assertIsNone(soak.windows.token)
                self.assertEqual(calls[-1], ("stop", None))
                self.assertIn("probe_incomplete_window", soak.report)
                self.assertFalse(soak.report["60min_gate"])
                self.assertIn(str(ROOT / "scripts/rc-probe-benchmark.py"), soak.report["helper_sources"])
        def test_probe_scope_accepts_frozen_report_manifest_and_outputs_only(self):
            archived = ROOT / "reports/rc-20261017"
            self.assertTrue(probe_scope(archived / "probe-launches-candidate-20261017T105444Z-bc18ae27.json", "file"))
            self.assertTrue(probe_scope(archived / "probe-20261017T105444Z-bc18ae27-A", "directory"))
            self.assertTrue(probe_scope(archived / "probe-c9d5c83c81b64594be7db1261a84c16c-A", "directory"))
            self.assertTrue(probe_scope(ROOT / "scratch/dev-launch/unit/probe-control.txt", "optional_file"))
            for path, kind in ((archived / "control.txt", "optional_file"),
                    (archived / "unrelated.json", "file"), (archived / "probe-output", "directory"),
                    (ROOT / "reports/elsewhere/probe-launches-unit.json", "file"),
                    (Path("/tmp/probe-launches-unit.json"), "file")):
                self.assertFalse(probe_scope(path, kind))
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    print(json.dumps({"mode": "OFFLINE_SELF_TEST", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "native_3600s_SQL_RCON_Docker_JDK_tests": "NOT_RUN"}))
    return 0 if result.wasSuccessful() else 1


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Explicit30..60s native tool smoke; never satisfies60min_gate.")
    parser.add_argument("--label")
    parser.add_argument("--world-prefix")
    parser.add_argument("--operator-revision")
    parser.add_argument("--seconds", type=int, help="3600 normal;30..60 only with explicit --smoke.")
    parser.add_argument("--poll", type=float, default=1)
    parser.add_argument("--feed-period", type=float, default=1)
    parser.add_argument("--timeout", type=float, default=1200)
    parser.add_argument("--jstat-timeout", type=float, default=2)
    parser.add_argument("--fe", type=int, default=32000)
    parser.add_argument("--water", type=int, default=1000)
    parser.add_argument("--items", type=int, default=32)
    parser.add_argument("--probe-manifest", type=Path, help="Existing same-JVM agent manifest: scratch or reports/rc-20261017/probe-launches-*.json; controls stay in scratch, outputs in scratch or named RC probe directories. No new process.")
    args = parser.parse_args(argv)
    if args.seconds is None:
        args.seconds = 60 if args.smoke else OBSERVATION_SECONDS
    args.scenarios, args.warmup, args.repeats = ["mixed", "hotspot", "backpressure"], 5 if args.smoke else 30, 1
    args.quiet, args.probes, args.probe_idle = 2.2, 0, 2.2
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        return self_test()
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE", "native_3600s_SQL_RCON_Docker_JDK_tests": "NOT_RUN",
            "configured_observation_seconds": args.seconds, "smoke": args.smoke, "60min_gate": False}))
        return 0
    try:
        validate_args(args)
        directory = safe_directory(args.label)
        manifest = {"schema_version": 1, "utc_created": utc(), "state": "PREPARED_NOT_RUN",
            "label": args.label, "cluster": "dev_three_v1", "world_prefix": args.world_prefix,
            "operator_runtime_revision_declared": args.operator_revision,
            "scope": "operator declaration; actual launch manifests/PID/world/session verified separately",
            "required_observation_seconds": args.seconds, "smoke": args.smoke, "60min_gate": False,
            "source_path": str(Path(__file__).relative_to(ROOT)),
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "no_server_or_container_lifecycle": True, "historical_fixtures_reused": False}
        with (directory / "manifest.json").open("x") as output:
            json.dump(manifest, output, indent=2)
            output.write("\n")
        return make_soak(args, directory).run()
    except Exception as error:
        print(json.dumps({"passed": False, "failure_class": type(error).__name__, "failure": str(error)[:2000]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
