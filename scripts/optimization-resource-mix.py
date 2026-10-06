#!/usr/bin/env python3
"""Same-channel, bounded real-resource mix on fresh isolated A/B/C fixtures.

Default and --self-test only read files and evaluate Python: no live calls.
--execute requires empty world-opt-resource-mix-* worlds in dev_three_v1.
One SEND endpoint feeds same/cross/mixed RECEIVE endpoints, with real vanilla
chests for two stable CUSTOM_NAME stone variants and native water/FE ports.

Defaults: 30s warmup, 120s observation, three repeats, 0.5s scheduled rounds.
Every round requests 32000 FE and 1000 mB water. ITEM warmup is empty. Each
observation window injects exactly one pair of 32 named stones at its entry,
via sequential validated vanilla writes to empty source slots0/1; never refed.
Native FE/fluid partial acceptance remains explicit; accepted quantities are
never inferred from SQL balances. Per-resource inputs, outputs, rejections,
observer lateness, source/external-container intervals and drain tails are saved.
Old one-slot NeighborPump scans can take minutes: the 120s window is not extended
silently; the separately recorded post-window drain permits up to 1200s.

No trace component, push-item/pull-item, SQL writes, reset, lifecycle or build
command is used. Any uncertain mutation or failed guard leaves owned assets.
Run without concurrent RCON clients. Native validation has not been performed
by the offline self-test. Example (operator-prepared fresh worlds only):
  python3 scripts/optimization-resource-mix.py --execute --label original-mix \
    --operator-revision 87bf217 --warmup 30 --seconds 120 --repeats 3
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = ROOT / "scripts/optimization-container-benchmark.py"
PRIMARY = ROOT / "scripts/optimization-benchmark.py"
ITEM, FLUID, FE = ("cross_tesseract:" + kind for kind in ("item", "fluid", "fe"))
VARIANTS = {"A": "CT mixed A", "B": "CT mixed B"}
UNITS = {"FE": "FE", "water": "mB", "item_A": "items", "item_B": "items"}
KEYS = tuple(UNITS)
SNAPSHOT_COUNTERS = ("db_transactions", "db_deadlock_retries", "transactions",
    "errors", "queue_rejected", "quarantined", "db_transaction_attempts",
    "db_statements", "deferred_registry_decodes", "dropped_wake_hints",
    "local_exchange_calls", "local_input_units", "local_output_units",
    "batch_devices", "batch_records", "batch_payload_bytes", "local_wakes",
    "remote_hint_wakes", "poll_fallback", "empty_batches", "allocation_misses",
    "local_credit_publications", "wal_writes", "wal_bytes", "wal_identical_skipped")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def load_file_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON component key")
        result[key] = value
    return result


class SmallSNBT:
    """Only compounds, lists, quoted strings, keys and small integer literals."""

    def __init__(self, text):
        if len(text.encode("utf-8")) > 16384:
            raise ValueError("SNBT byte bound exceeded")
        self.text, self.index, self.nodes = text, 0, 0

    def ws(self):
        while self.index < len(self.text) and self.text[self.index].isspace():
            self.index += 1

    def token(self, expected):
        self.ws()
        if not self.text.startswith(expected, self.index):
            raise ValueError("Unexpected/truncated SNBT structure")
        self.index += len(expected)

    def string(self):
        quote = self.text[self.index]
        self.index += 1
        value = []
        while self.index < len(self.text):
            char = self.text[self.index]
            self.index += 1
            if char == quote:
                result = "".join(value)
                if len(result.encode("utf-8")) > 512:
                    raise ValueError("SNBT string bound exceeded")
                return result
            if char == "\\":
                if self.index == len(self.text) or self.text[self.index] not in (quote, "\\"):
                    raise ValueError("Unsupported SNBT string escape")
                char = self.text[self.index]
                self.index += 1
            if ord(char) < 32:
                raise ValueError("Control character in SNBT string")
            value.append(char)
        raise ValueError("Unterminated SNBT string")

    def value(self, depth=0):
        self.nodes += 1
        if depth > 4 or self.nodes > 512:
            raise ValueError("SNBT depth/node bound exceeded")
        self.ws()
        if self.index == len(self.text):
            raise ValueError("Truncated SNBT value")
        char = self.text[self.index]
        if char in "\"'":
            return self.string()
        if char == "{":
            self.token("{")
            result = {}
            self.ws()
            while self.index < len(self.text) and self.text[self.index] != "}":
                key = self.value(depth + 1)
                if not isinstance(key, str) or key in result:
                    raise ValueError("Non-string/duplicate SNBT key")
                self.token(":")
                result[key] = self.value(depth + 1)
                self.ws()
                if self.index < len(self.text) and self.text[self.index] == ",":
                    self.token(",")
                    self.ws()
                    if self.index < len(self.text) and self.text[self.index] == "}":
                        raise ValueError("Trailing SNBT compound comma")
                elif self.index < len(self.text) and self.text[self.index] != "}":
                    raise ValueError("SNBT compound separator missing")
            self.token("}")
            return result
        if char == "[":
            self.token("[")
            result = []
            self.ws()
            while self.index < len(self.text) and self.text[self.index] != "]":
                if len(result) >= 27:
                    raise ValueError("Single-chest slot bound exceeded")
                result.append(self.value(depth + 1))
                self.ws()
                if self.index < len(self.text) and self.text[self.index] == ",":
                    self.token(",")
                    self.ws()
                    if self.index < len(self.text) and self.text[self.index] == "]":
                        raise ValueError("Trailing SNBT list comma")
                elif self.index < len(self.text) and self.text[self.index] != "]":
                    raise ValueError("SNBT list separator missing")
            self.token("]")
            return result
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*|-?\d{1,4}[bBsS]?", self.text[self.index:])
        if not match:
            raise ValueError("Unsupported SNBT token")
        token = match[0]
        self.index += len(token)
        if re.fullmatch(r"-?\d+[bBsS]?", token):
            return int(token.rstrip("bBsS"))
        return token

    def parse(self):
        result = self.value()
        self.ws()
        if self.index != len(self.text):
            raise ValueError("Trailing SNBT content")
        return result


def parse_items(reply, position):
    if len(reply.encode("utf-8")) > 16384:
        raise ValueError("Chest reply byte bound exceeded")
    match = re.fullmatch(r"\s*(-?\d+),\s*(-?\d+),\s*(-?\d+) has the following block data:\s*(\[.*\])\s*", reply, re.S)
    if not match or tuple(int(match[i]) for i in (1, 2, 3)) != tuple(position):
        raise ValueError("Unrecognized or mismatched own chest-coordinate reply")
    entries = SmallSNBT(match[4]).parse()
    if not isinstance(entries, list):
        raise ValueError("Expected single-chest Items list")
    seen, stacks, totals = set(), [], {variant: 0 for variant in VARIANTS}
    for entry in entries:
        if not isinstance(entry, dict) or not set(entry) <= {"Slot", "id", "count", "Count", "components"}:
            raise ValueError("Unknown item field")
        if entry.get("id") != "minecraft:stone" or "Slot" not in entry or "components" not in entry or \
                ("count" in entry and "Count" in entry):
            raise ValueError("Only named stone with one count field is accepted")
        slot, count = entry["Slot"], entry.get("count", entry.get("Count", 1))
        if type(slot) is not int or type(count) is not int or not 0 <= slot < 27 or not 1 <= count <= 64 or slot in seen:
            raise ValueError("Invalid/duplicate single-chest slot or count")
        components = entry["components"]
        if not isinstance(components, dict) or set(components) != {"minecraft:custom_name"}:
            raise ValueError("Only the stable CUSTOM_NAME component is accepted")
        encoded = components["minecraft:custom_name"]
        if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > 256 or \
                (not encoded.lstrip().startswith(('"', "{"))):
            raise ValueError("Expected bounded FLAT_CODEC JSON component string")
        name = json.loads(encoded, object_pairs_hook=no_duplicate_keys)
        if isinstance(name, dict) and set(name) == {"text"}:
            name = name["text"]
        if not isinstance(name, str) or name not in VARIANTS.values():
            raise ValueError("Unexpected CUSTOM_NAME text/style/identity")
        variant = next(v for v, text in VARIANTS.items() if text == name)
        seen.add(slot)
        totals[variant] += count
        stacks.append({"slot": slot, "id": "minecraft:stone", "count": count,
            "variant": variant, "custom_name": name, "flat_component_JSON": encoded})
    return {"stacks": stacks, "by_variant": totals, "total": sum(totals.values()), "snbt": match[4]}


def item_argument(variant):
    if variant not in VARIANTS:
        raise ValueError("Unknown component variant")
    component = json.dumps({"text": VARIANTS[variant]}, separators=(",", ":"))
    return "minecraft:stone[minecraft:custom_name='" + component + "']"


def phase_plan(seconds, period, name):
    if not math.isfinite(seconds) or not math.isfinite(period) or seconds < 0 or period <= 0 or name not in ("warmup", "steady"):
        raise ValueError("Invalid bounded phase plan")
    rounds = math.ceil(seconds / period)
    return {"planned_rounds": rounds, "planned_FE_attempts": rounds,
        "planned_water_attempts": rounds, "planned_ITEM_pairs": 1 if name == "steady" else 0}


def new_ledger():
    return {key: {"unit": UNITS[key], "accepted": 0,
        "source_actual_decrement": 0 if key.startswith("item_") else None,
        "external_output": 0, "input_by_endpoint": {}, "output_by_endpoint": {}} for key in KEYS}


def ledger_change(first, last):
    result = {}
    for key in KEYS:
        result[key] = {"unit": UNITS[key]}
        for field in ("accepted", "source_actual_decrement", "external_output"):
            if first[key][field] is None and last[key][field] is None:
                result[key][field] = None  # Native FE/fluid input is capability acceptance, not a chest decrement.
                continue
            difference = last[key][field] - first[key][field]
            if difference < 0:
                raise AssertionError("Cumulative business ledger decreased")
            result[key][field] = difference
        for field in ("input_by_endpoint", "output_by_endpoint"):
            result[key][field] = {name: amount - first[key][field].get(name, 0)
                for name, amount in last[key][field].items()}
    return result


def ledger_add(ledger, key, field, amount, endpoint=None):
    if type(amount) is not int or amount < 0:
        raise AssertionError("Invalid external business amount")
    record = ledger[key]
    record[field] += amount
    if endpoint is not None:
        by_endpoint = "input_by_endpoint" if field == "accepted" else "output_by_endpoint"
        record[by_endpoint][endpoint] = record[by_endpoint].get(endpoint, 0) + amount
    if record["external_output"] > record["accepted"] or (key.startswith("item_") and record["source_actual_decrement"] > record["accepted"]):
        raise AssertionError("External output/source decrement exceeds accepted resource input")


def resource_statement(channel, kinds):
    channel = str(uuid.UUID(channel))
    if not kinds or any(kind not in (FE, FLUID, ITEM) for kind in kinds):
        raise ValueError("Invalid resource guard scope")
    prefix = "r.cluster_id='dev_three_v1' AND "
    balance = "b.cluster_id=r.cluster_id AND b.resource_id=r.resource_id AND b.channel_id='" + channel + "'"
    transfers = "t.cluster_id=r.cluster_id AND t.resource_id=r.resource_id AND t.channel_id='" + channel + "'"
    return ("SELECT r.kind,r.resource_id,r.format_version,r.payload_hash,"
        "(SELECT COALESCE(SUM(b.amount),0) FROM ct_balances b WHERE " + balance + "),"
        "(SELECT COALESCE(SUM(t.remaining),0) FROM ct_transfers t WHERE " + transfers + " AND t.kind='ALLOCATE') "
        "FROM ct_resources r WHERE " + prefix + "r.kind IN (" + ",".join("'" + kind + "'" for kind in kinds) + ") AND "
        "(EXISTS(SELECT 1 FROM ct_balances b WHERE " + balance + ") OR "
        "EXISTS(SELECT 1 FROM ct_transfers t WHERE " + transfers + ")) ORDER BY r.kind,r.resource_id")


def cost_difference(first, last):
    result, per_server, statuses = {}, {}, {}
    for server in first["servers"]:
        a, b = first["servers"][server]["metrics"], last["servers"][server]["metrics"]
        values = {}
        for key in SNAPSHOT_COUNTERS:
            value = b[key] - a[key] if key in a and key in b else None
            if value is not None and (type(value) is not int or value < 0):
                raise AssertionError("Non-integer/reset instrumented counter: " + server + "/" + key)
            values[key] = value
        per_server[server] = values
    for key in SNAPSHOT_COUNTERS:
        values = [point[key] for point in per_server.values()]
        result[key] = sum(values) if all(value is not None for value in values) else None
        statuses[key] = "MEASURED" if result[key] is not None else "UNMEASURED"
    statements = None
    if first["statements"] is not None and last["statements"] is not None:
        statements = {key: last["statements"][key] - first["statements"][key]
            for key in ("events", "timer_picoseconds", "errors")}
        if any(value < 0 for value in statements.values()):
            raise AssertionError("Account statement counters reset")
    return {"sum": result, "per_server": per_server, "measurement_status": statuses,
        "account_statement_events": statements,
        "scope": "Actual per-server cumulative status and root-observed ct_dev SQL attempts; missing counters UNMEASURED. End rings/avg100 are snapshots, not window percentiles. Credit publications include cross delivery. Native local_input/output_units may mix resource units and are diagnostics, not external throughput/asset totals."}


def make_driver(args, physical, y, evidence):
    # Reuse the existing immutable fixture/preflight/launch-manifest implementation.
    # Construction has no live effects; setup occurs only inside run after --execute.
    template = physical.make_driver(args, y, evidence)
    base = physical.load_helpers()

    class MixBenchmark(type(template)):
        def __init__(self):
            super().__init__()
            self.target = self.target.with_name(self.target.name.replace("optimization-container-", "optimization-resource-mix-", 1))
            self.pending, self.ledgers, self.sequences = {}, {}, {}
            self.report.update(report_kind="same_channel_real_resource_mix", RCON_trace=[],
                guard_SQL_trace=[], item_batches=[], drain_proofs=[],
                resource_units=UNITS, native_executed=False, native_validation="NOT_RUN",
                helper_sources={str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (Path(__file__).resolve(), CONTAINER, PRIMARY, ROOT / "scripts/rcon.py")})
            self.report["conditions"] = {"scenarios": args.scenarios, "warmup_seconds": args.warmup,
                "observation_seconds": args.seconds, "repeats": args.repeats,
                "feed_period_seconds": args.feed_period, "poll_seconds": args.poll,
                "fixed_attempts_per_round": {"FE": args.fe, "water_mB": args.water},
                "fixed_item_pair_per_observation_window": {"named_stone_A": args.items,
                    "named_stone_B": args.items, "warmup_items": 0,
                    "injection": "At observation entry, two sequential validated vanilla writes; no atomic pair claim or refeeding."},
                "item": "minecraft:stone", "CUSTOM_NAME": VARIANTS,
                "item_source_slots": {"A": 0, "B": 1},
                "maximum_inflight_item_batches": 1, "sources_per_channel": 1,
                "endpoint_spacing_blocks": 64, "be_y": y, "chest_side": "EAST",
                "quiet_seconds": args.quiet, "item_guard_interval_seconds": args.feed_period,
                "post_phase_drain_timeout_seconds": args.timeout,
                "world_prefix": args.world_prefix, "observer": "single Python/RCON"}
            self.report["measurement"] = {
                "scope": "Supplemental same-channel simultaneous ITEM(two stable CUSTOM_NAME variants)+water+FE; given-load fixed-attempt performance, not primary240-input target or factory capacity.",
                "attempts": "FE/water each haveceil(seconds/feed_period) rounds with raw actual acceptance and partial rejections. Every steady window injects one32+32 ITEM pair, warmup none; no refeeding. A failed/uncertain pair is not a valid fixed-input window. SQL balances never prove input equality.",
                "ITEM": "Actual vanilla source chest variant count decrement -> actual external vanilla destination variant count increase/full batch; NeighborPump only. Components identify two workload variants, never event traces.",
                "FE_FLUID": "Synchronous native capability acceptance and actual extraction; aggregate overlapped ledgers only, no per-input E2E latency. Water type derives from fixed push-fluid native API; no physical fluid-container claim.",
                "clock": "All event bounds use this Python time.monotonic request/reply/read intervals; no cross-JVM nanoTime subtraction or world-save claim.",
                "bounds": "First decreased source read falls back to that variant item-replace request start. Target bounds include preceding zero/non-full reads, read order, polls and RCON uncertainty. Batch identity is finite because no second ITEM batch exists before full output, independent ITEM quiet guard and confirmed clear.",
                "counter_window": "Main cost captures before120s drive and after drive, before separately recorded final drain. Lifecycle cost also recorded through drain/quiet guard. Warmup/drain/setup separate. Capture requests/statement observer ends retained.",
                "assets": "Independent variant/FE/mB ledgers, source counts, external outputs and zero local/SQL checks. SQL allocation/WAL/local mirrors never added as assets; different units never summed.",
                "observer": "No concurrent RCON clients. Shared Minecraft console reply buffer has no business nonce despite protocol IDs; every raw body retained, chest coordinates/strict components validated. RCON spans, guard SQL spans, polling lateness and actual phase duration recorded; driver-limited results are not capacity.",
                "native_validation": "Offline parser/math checks do not validate Minecraft/component command syntax or performance; --execute must produce real completed guarded windows.",
                "revision": "Inherited launch-selected class/resource/JAR manifests plus PID/world/session/epoch. Operator revision and checkout are labels, not loaded-code proof. Rehash at end.",
                "config": "Verified launch config path; start/end config-file hashes and only allowlisted observed transfer flags retained. Current file bytes/flags alone do not prove old runtime support or startup-loaded values.",
                "barriers": "One fixed ITEM pair per steady window drains and remains zero for2.2s before its confirmed external chest outputs are cleared. Warmup/final phases drain all three resources and all owned chests; timeout/failure keeps assets. Old324s scanner waiting stays visible, even when120s ITEM output is0.",
                "metrics": "Optional instrumented counter differences are actual counters; baseline WAL remains UNMEASURED. local_credit_publications includes cross delivery. Native local_input/output_units may mix resource units: not external business throughput/assets. Mod/MC end rings cannot establish phase-wide MSPT/TPS or p95."}

        def verify_isolation(self):
            super().verify_isolation()
            if self.report["other_live_backend_sessions"]:
                raise ValueError("Resource mix requires exclusive ct_dev workload sessions A/B/C")
            for server, info in self.report["identity"].items():
                rows = base.sql("SELECT COUNT(*) FROM ct_endpoints WHERE cluster_id='dev_three_v1' AND world_id='" +
                    info["world_id"] + "'")
                if rows != [["0"]]:
                    raise ValueError("Requires never-used endpoint world, not just currently unloaded: " + server)
                path = ROOT / ("run-" + server) / "cross-tesseract.properties"
                flags = {"transfer.channelBatches": None, "transfer.localFastPath": None}
                for line in path.read_text().splitlines():
                    if not line.lstrip().startswith(("#", "!")) and "=" in line:
                        key, value = (part.strip() for part in line.split("=", 1))
                        if key in flags:
                            if value not in ("true", "false"):
                                raise ValueError("Invalid observed transfer flag: " + server + "/" + key)
                            flags[key] = value
                info["config_file_start_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                info["config_transfer_flags_observed"] = flags
            self.report.update(native_executed=True, native_validation="EXECUTED_PENDING_COMPLETE_WINDOWS")

        def endpoint(self, server, name, channel):
            endpoint = super().endpoint(server, name, channel)
            self.issue(server, f"mode {endpoint.x} {endpoint.z} {FLUID} OFF")
            return endpoint

        def activate(self, lanes, active):
            for lane in lanes:
                for endpoint in lane.sources + lane.sinks:
                    mode = ("SEND" if endpoint in lane.sources else "RECEIVE") if active else "OFF"
                    for kind in (ITEM, FLUID, FE):
                        response = self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {kind} {mode}")
                        if response["reply"].strip() != "MODE " + mode:
                            raise AssertionError("Unconfirmed resource mode")

        def chest(self, endpoint):
            own = self.chests[endpoint.name]
            x, y, z = own["position"]
            result = self.vanilla(endpoint.server, f"data get block {x} {y} {z} Items")
            parsed = parse_items(result["reply"], (x, y, z))
            return dict(parsed, endpoint=endpoint.name, start=result["start"], end=result["end"],
                count=parsed["total"], RCON_trace_index=len(self.report["RCON_trace"]) - 1)

        def frame(self, lane, order=0):
            source = self.chest(lane.sources[0])
            if any(stack["slot"] != (0 if stack["variant"] == "A" else 1) for stack in source["stacks"]):
                raise AssertionError("Unexpected own source slot/component identity")
            sinks = lane.sinks[order % len(lane.sinks):] + lane.sinks[:order % len(lane.sinks)]
            targets = {endpoint.name: self.chest(endpoint) for endpoint in sinks}
            return {"source": source, "targets": targets,
                "totals": {v: sum(point["by_variant"][v] for point in targets.values()) for v in VARIANTS},
                "target_interval": {"start": min(point["start"] for point in targets.values()),
                    "end": max(point["end"] for point in targets.values())}}

        def residue_kinds(self, lane, kinds):
            statement = resource_statement(lane.channel, kinds)
            observed = {"start": time.monotonic() - self.started, "statement": statement,
                "observer_account": "isolated dev root"}
            self.report["guard_SQL_trace"].append(observed)
            try:
                observed["rows"] = base.sql(statement)
            except Exception as error:
                observed["failure"] = type(error).__name__ + ": " + str(error)
                raise
            finally:
                observed["end"] = time.monotonic() - self.started
            by_kind = {kind: {"pool": 0, "allocation_remaining": 0} for kind in kinds}
            resources = []
            for kind, resource_id, version, payload_hash, pool, remaining in observed["rows"]:
                point = {"kind": kind, "resource_id": str(uuid.UUID(resource_id)),
                    "format_version": int(version), "payload_hash": payload_hash,
                    "pool": int(pool), "allocation_remaining": int(remaining)}
                if kind not in by_kind or not re.fullmatch(r"[0-9a-f]{64}", payload_hash) or min(point["pool"], point["allocation_remaining"]) < 0:
                    raise AssertionError("Invalid resource identity/guard amount")
                resources.append(point)
                for field in ("pool", "allocation_remaining"):
                    by_kind[kind][field] += point[field]
            local = {e.name: self.inspect(e) for e in lane.sources + lane.sinks}
            return {"resources": resources, "by_kind": by_kind, "local_buffers": local,
                "guard_SQL_trace_index": len(self.report["guard_SQL_trace"]) - 1,
                "scope": "Separate zero tests; allocations/local/WAL may mirror the same asset."}

        def zero(self, residue, kinds):
            fields = {FE: ("txFE", "rxFE"), FLUID: ("txFluid", "rxFluid"), ITEM: ("txItem", "rxItem")}
            return all(residue["by_kind"][kind]["pool"] == residue["by_kind"][kind]["allocation_remaining"] == 0
                for kind in kinds) and all(
                point[field] == 0 for point in residue["local_buffers"].values()
                for kind in kinds for field in fields[kind])

        def cap(self, lane, endpoint, key, direction, amount, events):
            resource = "fe" if key == "FE" else "fluid"
            event = {"kind": "input" if direction == "push" else "output", "resource": key,
                "unit": UNITS[key], "endpoint": endpoint.name, "requested": amount,
                "amount": None, "result": "UNKNOWN_UNTIL_REPLY_VALIDATED",
                "RCON_trace_index": len(self.report["RCON_trace"])}
            events.append(event)  # Keep uncertain native mutations/extractions, never label them zero.
            result = self.issue(endpoint.server, f"{direction}-{resource} {endpoint.x} {endpoint.z} {amount}")
            marker = "ACCEPTED" if direction == "push" else "EXTRACTED"
            match = re.fullmatch(marker + r" (\d+)\s*", result["reply"])
            if not match:
                raise AssertionError("Missing/unattributed native resource amount")
            actual = int(match[1])
            if not 0 <= actual <= amount:
                raise AssertionError("Invalid native amount")
            event.update({k: result[k] for k in ("start", "end")})
            event.update(amount=actual, result="CONFIRMED_NATIVE_AMOUNT")
            ledger_add(self.ledgers[lane.name], key, "accepted" if direction == "push" else "external_output", actual, endpoint.name)
            return event

        def source_observation(self, lane, batch, source, events):
            batch["source_observations"].append(source)
            for variant, record in batch["variants"].items():
                injection = record.get("injection")
                if injection is None:
                    continue
                count = source["by_variant"][variant]
                previous = record.get("last_source")
                old = previous["by_variant"][variant] if previous else args.items
                if not 0 <= count <= old <= args.items:
                    raise AssertionError("Own source quantity increased/invalid during one batch")
                if count < old:
                    bound = physical.transition(previous or injection, source, injection["start"])
                    if "source_first_decrement" not in record:
                        record["source_first_decrement"] = dict(bound,
                            origin="last_source_read_to_first_decrement" if previous else "item_replace_request_start_fallback_first_read_already_decreased")
                        record["input_to_source_bounds"] = physical.e2e(injection, bound)
                    if count == 0:
                        record["source_empty_interval"] = bound
                    ledger_add(self.ledgers[lane.name], "item_" + variant, "source_actual_decrement", old - count)
                    events.append(dict(bound, kind="source_chest_decrement", resource="item_" + variant,
                        amount=old - count, endpoint=lane.sources[0].name,
                        RCON_trace_index=source["RCON_trace_index"]))
                record["last_source"] = source

        def attempt_items(self, lane, phase, round_index):
            attempts = [{"round": round_index, "variant": variant, "requested": args.items,
                "accepted": 0, "at": time.monotonic() - self.started} for variant in VARIANTS]
            phase["item_attempts"].extend(attempts)
            if lane.name in self.pending:
                raise AssertionError("Prior in-flight ITEM pair at steady entry; never overwrite/skip a mandated fixed pair")
            before = self.frame(lane, round_index)
            if before["source"]["count"] or any(before["totals"].values()):
                raise AssertionError("Nonempty own source/targets before new batch; never overwrite")
            sequence = self.sequences[lane.name] = self.sequences.get(lane.name, 0) + 1
            batch = {"lane": lane.name, "phase": phase["name"], "repeat": phase["repeat"],
                "sequence": sequence, "round": round_index, "passed": False,
                "variants": {variant: {} for variant in VARIANTS}, "frames": [],
                "source_observations": [], "item_quiet_checks": [], "clears": [], "before": before,
                "previous_targets": before}
            phase["item_batches"].append(sequence)
            self.report["item_batches"].append(batch)
            self.pending[lane.name] = batch  # Before any mutation, including uncertain/partial pair.
            source_endpoint = lane.sources[0]
            for slot, (variant, record) in enumerate(batch["variants"].items()):
                # The second read also captures A actually leaving while B is not yet injected.
                source = self.chest(source_endpoint)
                self.source_observation(lane, batch, source, phase["events"])
                if any(stack["slot"] == slot for stack in source["stacks"]) or source["by_variant"][variant]:
                    raise AssertionError("Input slot contains prior stock; refusing overwrite")
                x, y, z = self.chests[source_endpoint.name]["position"]
                attempts[slot].update(accepted=None, status="UNKNOWN_MUTATION_RESULT",
                    RCON_trace_index=len(self.report["RCON_trace"]))
                result = self.vanilla(source_endpoint.server,
                    f"item replace block {x} {y} {z} container.{slot} with {item_argument(variant)} {args.items}")
                record["injection"] = {key: result[key] for key in ("start", "end")}
                record["injection"]["RCON_trace_index"] = len(self.report["RCON_trace"]) - 1
                if "replaced" not in result["reply"].lower() or "slot" not in result["reply"].lower():
                    raise AssertionError("Unconfirmed item replace; uncertain mutation will not be replayed")
                attempts[slot].update(accepted=args.items, status="CONFIRMED_ITEM_REPLACE",
                    input_interval=record["injection"])
                ledger_add(self.ledgers[lane.name], "item_" + variant, "accepted", args.items, source_endpoint.name)
                phase["events"].append(dict(record["injection"], kind="input", resource="item_" + variant,
                    unit="items", endpoint=source_endpoint.name, requested=args.items, amount=args.items))

        def service_items(self, lane, phase, order):
            batch = self.pending.get(lane.name)
            if batch is None:
                return
            current = self.frame(lane, order)
            batch["frames"].append(current)
            self.source_observation(lane, batch, current["source"], phase["events"])
            previous = batch["previous_targets"]
            for variant, record in batch["variants"].items():
                if record.get("injection") is None:
                    raise AssertionError("Partially unconfirmed ITEM pair; retaining assets")
                total = current["totals"][variant]
                if not 0 <= previous["totals"][variant] <= total <= args.items:
                    raise AssertionError("External component total decreased/exceeded input")
                for name, point in current["targets"].items():
                    old = previous["targets"][name]
                    difference = point["by_variant"][variant] - old["by_variant"][variant]
                    if difference < 0:
                        raise AssertionError("External chest output disappeared before confirmed clear")
                    if difference:
                        bound = physical.transition(old, point, record["injection"]["start"])
                        phase["events"].append(dict(bound, kind="output", resource="item_" + variant,
                            unit="items", endpoint=name, amount=difference,
                            RCON_trace_index=point["RCON_trace_index"]))
                        ledger_add(self.ledgers[lane.name], "item_" + variant, "external_output", difference, name)
                for field, condition in (("first_output", total > 0), ("full_output", total == args.items)):
                    if field not in record and condition:
                        bound = physical.transition(previous["target_interval"], current["target_interval"],
                            record["injection"]["start"])
                        record[field] = bound
                        record["input_to_" + field + "_bounds"] = physical.e2e(record["injection"], bound)
                if "source_first_decrement" in record:
                    for field in ("first_output", "full_output"):
                        if field in record:
                            record["source_to_" + field + "_bounds"] = physical.e2e(record["source_first_decrement"], record[field])
                record["outputs_by_sink"] = {name: point["by_variant"][variant] for name, point in current["targets"].items()}
            batch["previous_targets"] = current
            if current["source"]["count"] or any(current["totals"][v] != args.items for v in VARIANTS):
                return
            now = time.monotonic()
            if now < batch.get("next_quiet_check", 0):
                return
            batch["next_quiet_check"] = now + args.feed_period
            residue = self.residue_kinds(lane, (ITEM,))
            at = time.monotonic() - self.started
            batch["item_quiet_checks"].append({"at": at, "residue": residue,
                "physical_frame": current, "zero": self.zero(residue, (ITEM,))})
            if not self.zero(residue, (ITEM,)):
                batch.pop("quiet_start", None)
                return
            batch.setdefault("quiet_start", at)
            if at - batch["quiet_start"] < args.quiet:
                return
            for endpoint in lane.sinks:
                # Fresh typed read immediately before own confirmed clear.
                point = self.chest(endpoint)
                if point["by_variant"] != current["targets"][endpoint.name]["by_variant"]:
                    raise AssertionError("Destination changed after ITEM quiet guard; refusing clear")
                if point["count"]:
                    x, y, z = self.chests[endpoint.name]["position"]
                    clear = {"endpoint": endpoint.name, "confirmed_by_variant": point["by_variant"],
                        "result": "UNKNOWN_MUTATION_RESULT",
                        "RCON_trace_index": len(self.report["RCON_trace"])}
                    batch["clears"].append(clear)
                    result = self.vanilla(endpoint.server, f"data modify block {x} {y} {z} Items set value []")
                    clear["interval"] = {key: result[key] for key in ("start", "end")}
                    if "modified" not in result["reply"].lower():
                        raise AssertionError("Unconfirmed clear; uncertain mutation will not be replayed")
                    clear["result"] = "CONFIRMED_CLEAR"
                    self.report["cleared_confirmed_stone"] += point["count"]
                if self.chest(endpoint)["count"]:
                    raise AssertionError("Confirmed own target clear left residue")
            if any("source_first_decrement" not in r or "full_output" not in r for r in batch["variants"].values()):
                raise AssertionError("Missing actual source/full-container observations")
            batch.update(passed=True, completed=time.monotonic() - self.started,
                item_quiet_seconds=at - batch["quiet_start"])
            del self.pending[lane.name]

        def service(self, lane, phase, order):
            self.service_items(lane, phase, order)
            sinks = lane.sinks[order % len(lane.sinks):] + lane.sinks[:order % len(lane.sinks)]
            for endpoint in sinks:
                for key in (("FE", "water") if order % 2 == 0 else ("water", "FE")):
                    self.cap(lane, endpoint, key, "pull", 2147483647, phase["events"])

        def observer_cost(self, trace_start, sql_start, start, end):
            spans = [point["end"] - point["start"] for point in self.report["RCON_trace"][trace_start:]]
            guard_spans = [point["end"] - point["start"] for point in self.report["guard_SQL_trace"][sql_start:]]
            return {"actual_seconds": end - start, "RCON_commands": len(spans),
                "RCON_request_reply_seconds_sum": sum(spans),
                "RCON_request_reply_seconds_max": max(spans, default=0),
                "guard_SQL_SELECTs": len(guard_spans), "guard_SQL_seconds_sum": sum(guard_spans),
                "scope": "Observer-side synchronous spans include waiting; not CPU. Only resource guard SQL individually timed. Inherited preflight/statement SQL included in total/capture spans, not these guard-only sums."}

        def drive_mix(self, lane, seconds, repeat, name):
            phase = {"name": name, "repeat": repeat, "events": [], "item_attempts": [],
                "item_batches": [], "rounds": [], "requested_seconds": seconds,
                **phase_plan(seconds, args.feed_period, name), "late_rounds": 0,
                "start": time.monotonic() - self.started}
            self.report["samples"][-1][name] = phase  # Preserve partial state on failure.
            initial = deepcopy(self.ledgers[lane.name])
            trace_start, sql_start = len(self.report["RCON_trace"]), len(self.report["guard_SQL_trace"])
            origin, next_poll, round_index, polls = time.monotonic(), time.monotonic(), 0, 0
            if phase["planned_ITEM_pairs"] == 1:
                phase["item_injection_entry"] = time.monotonic() - self.started
                self.attempt_items(lane, phase, 0)
            while round_index < phase["planned_rounds"] or time.monotonic() < origin + seconds:
                now = time.monotonic()
                due = origin + round_index * args.feed_period
                if round_index < phase["planned_rounds"] and now >= due:
                    lateness = now - due
                    phase["late_rounds"] += lateness > args.feed_period
                    row = {"index": round_index, "scheduled": due - self.started,
                        "actual_start": now - self.started, "lateness_seconds": lateness}
                    phase["rounds"].append(row)
                    for key, amount in (("FE", args.fe), ("water", args.water)):
                        self.cap(lane, lane.sources[0], key, "push", amount, phase["events"])
                    row["actual_end"] = time.monotonic() - self.started
                    round_index += 1
                if time.monotonic() >= next_poll:
                    self.service(lane, phase, polls)
                    polls += 1
                    # No replay/catch-up read burst; missed polling opportunity is explicit.
                    next_poll = time.monotonic() + args.poll
                deadlines = [next_poll, origin + round_index * args.feed_period] if round_index < phase["planned_rounds"] else [next_poll, origin + seconds]
                delay = min(deadlines) - time.monotonic()
                if delay > 0:
                    time.sleep(min(delay, args.poll))
            phase["end"] = time.monotonic() - self.started
            phase["scheduled_rounds"], phase["polls"] = round_index, polls
            phase["observer_saturated"] = bool(phase["late_rounds"] or phase["end"] - phase["start"] > seconds + args.feed_period)
            phase["ledger_change"] = ledger_change(initial, self.ledgers[lane.name])
            phase["input_completeness"] = {}
            for key in KEYS:
                events = [e for e in phase["events"] if e["kind"] == "input" and e["resource"] == key]
                phase["input_completeness"][key] = {"attempts": len(events),
                    "requested": sum(e["requested"] for e in events),
                    "actually_accepted": sum(e["amount"] for e in events),
                    "fully_accepted_attempts": sum(e["amount"] == e["requested"] for e in events),
                    "partial_or_zero_acceptance_attempts": sum(e["amount"] != e["requested"] for e in events),
                    "scope": "Validated native returns or validated vanilla writes; failed/unknown events abort, never replaced by SQL totals."}
            phase["throughput"] = {key: {"unit_per_second": UNITS[key] + "/s",
                "actual_external_output_per_second": point["external_output"] / (phase["end"] - phase["start"]) if phase["end"] > phase["start"] else None,
                "accepted_input": point["accepted"], "actual_external_output": point["external_output"]}
                for key, point in phase["ledger_change"].items()}
            phase["observer_cost"] = self.observer_cost(trace_start, sql_start, phase["start"], phase["end"])
            return phase

        def guard_empty(self, lane, purpose):
            proof = {"lane": lane.name, "purpose": purpose, "passed": False,
                "start": time.monotonic() - self.started, "snapshots": []}
            self.report["drain_proofs"].append(proof)
            deadline, quiet_start = time.monotonic() + args.timeout, None
            while time.monotonic() < deadline:
                frame = self.frame(lane, len(proof["snapshots"]))
                residue = self.residue_kinds(lane, (ITEM, FLUID, FE))
                now = time.monotonic() - self.started
                empty = not frame["source"]["count"] and not any(frame["totals"].values()) and self.zero(residue, (ITEM, FLUID, FE))
                proof["snapshots"].append({"frame": frame, "residue": residue, "at": now, "empty": empty})
                quiet_start = (quiet_start if quiet_start is not None else now) if empty else None
                if quiet_start is not None and now - quiet_start >= args.quiet:
                    proof.update(passed=True, end=now, quiet_seconds=now - quiet_start)
                    return proof
                time.sleep(max(args.poll, min(args.feed_period, .5)))
            raise AssertionError("Resource/chest static empty guard timeout; fixtures retained")

        def drain_mix(self, lane, repeat, name):
            phase = {"name": name, "repeat": repeat, "events": [], "start": time.monotonic() - self.started}
            self.report["samples"][-1][name] = phase
            deadline, order = time.monotonic() + args.timeout, 0
            while time.monotonic() < deadline:
                self.service(lane, phase, order)
                order += 1
                ledger = self.ledgers[lane.name]
                if lane.name not in self.pending and all(record["accepted"] == record["external_output"] and
                        (not key.startswith("item_") or record["source_actual_decrement"] == record["accepted"])
                        for key, record in ledger.items()):
                    phase["guard"] = self.guard_empty(lane, name)
                    phase.update(end=time.monotonic() - self.started, passed=True, ledger=deepcopy(ledger))
                    return phase
                time.sleep(args.poll)
            raise AssertionError("Post-phase drain timeout; assets retained, no replay/cleanup")

        def prove_drained(self, lane, total, probe=None, purpose="cleanup"):
            if total != 0 or lane.name in self.pending:
                raise AssertionError("Cleanup requires no in-flight batch and empty owned chests")
            return self.guard_empty(lane, purpose)

        def measure(self, name, repeat):
            lane = self.cases[name][0]
            self.ledgers.setdefault(lane.name, new_ledger())
            sample = {"scenario": name, "repeat": repeat, "passed": False}
            self.report["samples"].append(sample)
            self.activate([lane], True)
            sample["before_warmup"] = self.guard_empty(lane, "before_warmup")
            sample["warmup_counter_start"] = self.snapshot()
            self.drive_mix(lane, args.warmup, repeat, "warmup")
            self.drain_mix(lane, repeat, "warmup_drain")
            sample["warmup_counter_end"] = self.snapshot()
            sample["warmup_and_drain_counter_delta"] = cost_difference(sample["warmup_counter_start"], sample["warmup_counter_end"])
            sample["ledger_before_steady"] = deepcopy(self.ledgers[lane.name])
            sample["counter_start"] = self.snapshot()
            self.drive_mix(lane, args.seconds, repeat, "steady")
            sample["counter_end"] = self.snapshot()
            sample["counter_delta"] = cost_difference(sample["counter_start"], sample["counter_end"])
            self.drain_mix(lane, repeat, "conservation")
            sample["counter_after_drain"] = self.snapshot()
            sample["lifecycle_counter_delta"] = cost_difference(sample["counter_start"], sample["counter_after_drain"])
            sample["ledger_after_drain"] = deepcopy(self.ledgers[lane.name])
            sample["steady_and_tail_ledger_change"] = ledger_change(sample["ledger_before_steady"], sample["ledger_after_drain"])
            totals = sample["counter_delta"]["sum"]
            sample["recovered_SQL_failures"] = {
                "db_deadlock_retries": totals.get("db_deadlock_retries"),
                "account_statement_errors": (sample["counter_delta"]["account_statement_events"] or {}).get("errors"),
                "warmup_and_drain": {
                    "db_deadlock_retries": sample["warmup_and_drain_counter_delta"]["sum"].get("db_deadlock_retries"),
                    "account_statement_errors": (sample["warmup_and_drain_counter_delta"]["account_statement_events"] or {}).get("errors")},
                "steady_plus_tail": {
                    "db_deadlock_retries": sample["lifecycle_counter_delta"]["sum"].get("db_deadlock_retries"),
                    "account_statement_errors": (sample["lifecycle_counter_delta"]["account_statement_events"] or {}).get("errors")}}
            sample["passed"] = (sample["conservation"]["passed"] and
                all(delta["sum"][key] == 0 for delta in (sample["counter_delta"],
                    sample["warmup_and_drain_counter_delta"], sample["lifecycle_counter_delta"])
                    for key in ("errors", "queue_rejected", "quarantined")) and
                sample["steady"]["scheduled_rounds"] == sample["steady"]["planned_rounds"] and
                all(sample["steady"]["input_completeness"][key]["attempts"] == sample["steady"]["planned_" + key + "_attempts"]
                    for key in ("FE", "water")) and
                all(sample["steady"]["input_completeness"]["item_" + v]["attempts"] == 1 and
                    sample["steady"]["input_completeness"]["item_" + v]["actually_accepted"] == args.items for v in VARIANTS) and
                all(sample["warmup"]["input_completeness"]["item_" + v]["attempts"] == 0 for v in VARIANTS))
            if not sample["passed"]:
                raise AssertionError("Mixed-resource window failed validation; assets retained")
            self.activate([lane], False)
            self.save()

        def cleanup(self):
            expected = args.repeats * len(args.scenarios)
            if self.report["failures"] or len(self.report["samples"]) != expected or not all(s.get("passed") for s in self.report["samples"]):
                self.report["fixture_retained_for_diagnosis"] = True
                return
            super().cleanup()

        def run(self):
            self.save()
            try:
                self.verify_isolation()
                self.setup()
                for repeat in range(1, args.repeats + 1):
                    names = args.scenarios[(repeat - 1) % len(args.scenarios):] + args.scenarios[:(repeat - 1) % len(args.scenarios)]
                    for name in names:
                        self.measure(name, repeat)
                service = {}
                for name, cases in self.cases.items():
                    lane, ledger = cases[0], self.ledgers[cases[0].name]
                    endpoints = [e.name for e in lane.sinks]
                    service[name] = {"FE": {e: ledger["FE"]["output_by_endpoint"].get(e, 0) for e in endpoints},
                        "water": {e: ledger["water"]["output_by_endpoint"].get(e, 0) for e in endpoints},
                        "named_stone_total": {e: sum(ledger["item_" + v]["output_by_endpoint"].get(e, 0) for v in VARIANTS) for e in endpoints}}
                self.report["all_phase_actual_receiver_service"] = service
                steady_service, steady_and_tail_service = {}, {}
                for name, cases in self.cases.items():
                    endpoints = [e.name for e in cases[0].sinks]
                    for field, destination in (("steady", steady_service), ("steady_and_tail_ledger_change", steady_and_tail_service)):
                        selected = [s for s in self.report["samples"] if s["scenario"] == name]
                        records = [s[field]["ledger_change"] if field == "steady" else s[field] for s in selected]
                        destination[name] = {
                            "FE": {e: sum(r["FE"]["output_by_endpoint"].get(e, 0) for r in records) for e in endpoints},
                            "water": {e: sum(r["water"]["output_by_endpoint"].get(e, 0) for r in records) for e in endpoints},
                            "named_stone_total": {e: sum(r["item_" + v]["output_by_endpoint"].get(e, 0) for r in records for v in VARIANTS) for e in endpoints}}
                self.report["steady_window_actual_receiver_service"] = steady_service
                self.report["steady_plus_tail_actual_receiver_service"] = steady_and_tail_service
                self.report["receiver_service_scope"] = "Three distinct ledgers:within-window, steady+separate-tail, and all phases including warmup. No tail delivery relabeled as120s throughput."
                if any(amount <= 0 for case in steady_and_tail_service.values() for resource in case.values() for amount in resource.values()):
                    raise AssertionError("An intended receiver had no actual steady+tail service for a resource across repeats")
                self.verify_final_identity()
                for server, info in self.report["identity"].items():
                    path = ROOT / ("run-" + server) / "cross-tesseract.properties"
                    end_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                    info["config_file_end_sha256"] = end_hash
                    if end_hash != info["config_file_start_sha256"]:
                        raise AssertionError("Verified development config changed during run")
                for path, expected_hash in self.report["helper_sources"].items():
                    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_hash:
                        raise AssertionError("Python driver/helper source changed during run")
                self.report["native_validation"] = "COMPLETED_REAL_GUARDED_WINDOWS"
            except KeyboardInterrupt:
                self.report["failures"].append("Interrupted; uncertain operations not replayed and fixtures/assets retained")
            except Exception as error:
                self.report["failures"].append(type(error).__name__ + ": " + str(error))
            finally:
                self.report["resource_ledgers"] = deepcopy(self.ledgers)
                self.report["inflight_item_batch_sequences"] = {name: batch["sequence"] for name, batch in self.pending.items()}
                try:
                    self.cleanup()
                except Exception as error:
                    self.report["failures"].append("Cleanup: " + type(error).__name__ + ": " + str(error))
                    self.report["fixture_retained_for_diagnosis"] = True
                expected = args.repeats * len(args.scenarios)
                self.report.update(utc_end=utc_now(), elapsed_seconds=time.monotonic() - self.started,
                    passed=not self.report["failures"] and len(self.report["samples"]) == expected and all(s.get("passed") for s in self.report["samples"]),
                    devices=[vars(endpoint) for endpoint in self.devices], chests=self.chests)
                self.save()
            print("Saved " + str(self.target), flush=True)
            if self.report["failures"]:
                print(json.dumps(self.report["failures"], ensure_ascii=False), file=sys.stderr)
            return 0 if self.report["passed"] else 1

    return MixBenchmark()


def self_test(physical, y, args, evidence):
    prefix, position = "1000005, 64, 164 has the following block data: ", (1000005, 64, 164)

    def stack(variant, slot, count=32):
        encoded = json.dumps({"text": VARIANTS[variant]}, separators=(",", ":"))
        return "{Slot:" + str(slot) + 'b,id:"minecraft:stone",count:' + str(count) + \
            ',components:{"minecraft:custom_name":\'' + encoded + "'}}"

    good = "[" + stack("A", 0) + "," + stack("B", 1) + "]"
    assert parse_items(prefix + good, position)["by_variant"] == {"A": 32, "B": 32}
    assert parse_items(prefix + "[]", position)["total"] == 0
    shorthand = stack("A", 0).replace('{"text":"CT mixed A"}', '"CT mixed A"')
    assert parse_items(prefix + "[" + shorthand + "]", position)["by_variant"]["A"] == 32
    double_quoted = stack("A", 0).replace("""'{"text":"CT mixed A"}'""", '''"{\\"text\\":\\"CT mixed A\\"}"''')
    assert parse_items(prefix + "[" + double_quoted + "]", position)["total"] == 32
    for bad in (
        good.replace("minecraft:stone", "minecraft:dirt"), good.replace("CT mixed A", "CT mixed C"),
        good.replace('"minecraft:custom_name"', '"minecraft:custom_data"'),
        good.replace("count:32", "count:65"), good.replace("Slot:1b", "Slot:0b"),
        good.replace("count:32", "count:32,Count:32b"),
        good.replace('{"text":"CT mixed A"}', '{"text":"CT mixed A","italic":true}'),
        good.replace('{"text":"CT mixed A"}', '{"text":"CT mixed A","text":"CT mixed A"}'),
        good.replace("count:32", "count:32e1"), good[:-1] + ",]", good + " extra",
        "[" * 8 + "]" * 8, "[" + stack("A", 0) * 28 + "]", " " * 16385):
        try:
            parse_items(prefix + bad, position)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError("Unsafe/unknown SNBT accepted")
    try:
        parse_items(prefix + good, (1000006, 64, 164))
    except ValueError:
        pass
    else:
        raise AssertionError("Foreign chest-coordinate reply accepted")
    points = [physical.layout(1_000_000, index, y) for index in range(7)]
    assert y == 64 and all(p["be"][0] // 16 == p["chest"][0] // 16 for p in points)
    assert all(b["be"][0] - a["be"][0] >= 64 for a, b in zip(points, points[1:]))
    source = {"start": 1.0, "end": 1.1}
    target = {"start": 1.2, "end": 1.4}
    interval = physical.e2e(source, target)
    assert abs(interval["lower_ms"] - 100) < .0001 and abs(interval["upper_ms"] - 400) < .0001
    ledger = new_ledger()
    first = deepcopy(ledger)
    for variant in VARIANTS:
        ledger_add(ledger, "item_" + variant, "accepted", 32, "source")
        ledger_add(ledger, "item_" + variant, "source_actual_decrement", 32)
        ledger_add(ledger, "item_" + variant, "external_output", 32, "target")
    ledger_add(ledger, "FE", "accepted", 9007199254740993, "source")
    assert ledger_change(first, ledger)["FE"]["accepted"] == 9007199254740993
    assert ledger_change(first, ledger)["water"]["external_output"] == 0
    try:
        ledger_add(ledger, "item_A", "external_output", 1, "target")
    except AssertionError:
        pass
    else:
        raise AssertionError("Duplicate output accepted")
    statement = resource_statement(str(uuid.uuid4()), (FE, FLUID, ITEM))
    assert statement.startswith("SELECT ") and ";" not in statement and "t.kind='ALLOCATE'" in statement
    try:
        resource_statement("'; DROP TABLE", (ITEM,))
    except ValueError:
        pass
    else:
        raise AssertionError("Unbounded SQL identifier accepted")
    before = {"servers": {s: {"metrics": {"db_transactions": 9007199254740993, "errors": 0}} for s in "ABC"}, "statements": None}
    after = deepcopy(before)
    for point in after["servers"].values():
        point["metrics"]["db_transactions"] += 5
    assert cost_difference(before, after)["sum"]["db_transactions"] == 15
    assert cost_difference(before, after)["measurement_status"]["wal_writes"] == "UNMEASURED"
    assert "custom_name" in item_argument("A") and "CT mixed A" in item_argument("A")
    assert phase_plan(120, .5, "steady") == {"planned_rounds": 240, "planned_FE_attempts": 240,
        "planned_water_attempts": 240, "planned_ITEM_pairs": 1}
    assert phase_plan(30, .5, "warmup")["planned_ITEM_pairs"] == 0
    assert phase_plan(30, .5, "warmup")["planned_rounds"] == 60
    # Constructor compatibility only. No verify/setup/run/save/native method.
    driver = make_driver(args, physical, y, evidence)
    assert driver.report["native_validation"] == "NOT_RUN" and not driver.report["native_executed"]
    assert not driver.devices and not driver.report["RCON_trace"] and not driver.report["samples"]
    assert driver.report["conditions"]["fixed_item_pair_per_observation_window"]["warmup_items"] == 0
    print(json.dumps({"offline_self_test": "PASS", "native_validation": "NOT_RUN",
        "checks": ["bounded SNBT/component/slot/coordinate allowlist", "reject malformed/duplicate/style/depth/byte input",
            "fixed y64/64-block/chunk layout", "one-observer intervals", "per-resource exact-integer conservation ledger",
            "read-only bounded SQL guard", "optional counters remain UNMEASURED",
            "120s240 FE/water attempts, one32+32 ITEM pair; warmup noITEM",
            "lazy constructor compatibility; no live methods/run/report save"],
        "backend_JVM_RCON_SQL_access": False}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="resource-mix-supplement")
    parser.add_argument("--scenarios", default="mixed", help="same,cross,mixed; each case uses one channel for all resources")
    parser.add_argument("--warmup", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--feed-period", type=float, default=.5)
    parser.add_argument("--poll", type=float, default=.1)
    parser.add_argument("--quiet", type=float, default=2.2)
    parser.add_argument("--timeout", type=float, default=1200, help="Separate per-phase drain/quiet timeout; does not hide120s item waiting")
    parser.add_argument("--fe", type=int, default=32000)
    parser.add_argument("--water", type=int, default=1000, help="Native water input request in mB per round")
    parser.add_argument("--items", type=int, default=32, help="Fixed32 of each named stone variant once per steady window")
    parser.add_argument("--world-prefix", default="world-opt-resource-mix-")
    parser.add_argument("--operator-revision", default="unknown")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    args.scenarios = list(dict.fromkeys(args.scenarios.split(",")))
    numeric = (args.warmup, args.seconds, args.feed_period, args.poll, args.quiet, args.timeout)
    if not all(math.isfinite(value) for value in numeric) or \
            not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label) or not args.scenarios or \
            any(s not in ("same", "cross", "mixed") for s in args.scenarios) or \
            not 0 <= args.warmup <= 120 or not 1 <= args.seconds <= 600 or not 1 <= args.repeats <= 3 or \
            not .25 <= args.feed_period <= 10 or not .05 <= args.poll <= 1 or not 2.2 <= args.quiet <= 30 or \
            not 30 <= args.timeout <= 1800 or not 1 <= args.fe <= 32000 or not 1 <= args.water <= 16000 or \
            args.items != 32 or not re.fullmatch(r"world-opt-resource-mix-[A-Za-z0-9_-]{0,24}", args.world_prefix) or \
            (args.operator_revision != "unknown" and not re.fullmatch(r"[0-9a-f]{7,40}", args.operator_revision)):
        parser.error("Parameters outside bounded isolated-resource-mix scope")
    # Untouched container constructor compatibility, not its low-flow measurement.
    args.probes, args.probe_idle = 0, args.quiet
    physical = load_file_module("ct_resource_mix_physical_helpers", CONTAINER)
    y, evidence = physical.harness_height()
    if args.self_test:
        self_test(physical, y, args, evidence)
        return 0
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE_DESIGN_PREVIEW", "native_validation": "NOT_RUN",
            "JVM_backend_RCON_SQL_access": False, "scenarios": args.scenarios,
            "defaults": {"warmup_seconds": args.warmup, "observation_seconds": args.seconds,
                "repeats": args.repeats, "feed_period": args.feed_period, "poll": args.poll},
            "same_channel_resources": {"ITEM": {"id": "minecraft:stone", "CUSTOM_NAME": VARIANTS,
                "items_per_variant_attempt": args.items, "max_inflight_pair": 1},
                "FLUID": {"id": "minecraft:water", "mB_per_attempt": args.water},
                "FE": {"FE_per_attempt": args.fe}},
            "ITEM_policy": "Warmup0; fixed32+32 pair once at each steady entry; two sequential validated writes, no refeeding.",
            "harness_source_height_evidence": evidence,
            "example_mixed_geometry": [physical.layout(1_000_000, i, y) for i in range(3)],
            "limitations": ["Native command/component acceptance remains UNMEASURED until actual --execute.",
                "Fixed FE/fluid attempts, partial acceptance separately retained; valid ITEM windows each have64 identical input items.",
                "Old scanner wait/zero within-window item output/drain tail retained.",
                "FE/mB/items throughput separately; no primary target/capacity/tail/TPS claim."]}, indent=2))
        return 0
    return make_driver(args, physical, y, evidence).run()


if __name__ == "__main__":
    sys.exit(main())
