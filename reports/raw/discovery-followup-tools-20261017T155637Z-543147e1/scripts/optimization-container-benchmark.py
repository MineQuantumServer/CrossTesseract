#!/usr/bin/env python3
"""Supplemental low-flow vanilla chest -> Tesseracts -> chest benchmark.

Default/--self-test are offline. --execute uses only isolated dev_three_v1
fixtures in new world-opt-container-* worlds; never starts/stops a process.
Every probe inserts 32 ordinary stone into a vanilla chest with item replace.
NeighborPump performs all transfers. No push-item/pull-item or trace components.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "src/main/java/dev/crosstesseract/test/ThreeServerHarness.java"
DRIVER = ROOT / "scripts/optimization-benchmark.py"
ITEM = "cross_tesseract:item"
STONE = "minecraft:stone"
AMOUNT = 32
SCENARIOS = ("same", "cross", "mixed")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def harness_height():
    raw = HARNESS.read_bytes()
    matches = list(re.finditer(r"BlockPos pos=new BlockPos\(x,(-?\d+),z\)", raw.decode()))
    if len(matches) != 1 or not -64 <= int(matches[0][1]) < 320:
        raise ValueError("Unrecognized ordinary ct_test endpoint height; inspect actual harness source")
    return int(matches[0][1]), {"path": str(HARNESS), "sha256": hashlib.sha256(raw).hexdigest(),
        "ordinary_endpoint_y": int(matches[0][1]), "source_expression": matches[0][0]}


def layout(base_x, index, y):
    x, z = base_x // 16 * 16 + 4 + index * 64, 164
    if not 1_000_000 <= x < 28_000_000:
        raise ValueError("Fresh test coordinate outside bounded development range")
    return {"be": (x, y, z), "chest": (x + 1, y, z), "side": "EAST", "item_side_mask": 32,
        "chunk": (x // 16, z // 16)}


def parse_items(reply, position=None):
    """Strict small SNBT grammar: Items list, stone/id, Slot, count or Count only."""
    if len(reply) > 16384:
        raise ValueError("Unexpectedly large chest reply")
    match = re.fullmatch(r"\s*(-?\d+),\s*(-?\d+),\s*(-?\d+) has the following block data:\s*(\[.*\])\s*", reply, re.S)
    if not match:
        raise ValueError("Unrecognized vanilla data-get Items reply; raw reply retained")
    coordinates = tuple(int(match[i]) for i in (1, 2, 3))
    if position is not None and coordinates != tuple(position):
        raise ValueError("Chest response coordinates differ")
    body, offset, tokens = match[4], 0, []
    pattern = re.compile(r'\s*("[^"\\]*"|[A-Za-z_][A-Za-z_0-9]*|\d+[bBsS]?|[\[\]{},:])')
    while offset < len(body):
        token = pattern.match(body, offset)
        if not token:
            if not body[offset:].strip():
                break
            raise ValueError("Unsupported SNBT token/component")
        tokens.append(token[1])
        offset = token.end()
    cursor = 0

    def take(expected=None):
        nonlocal cursor
        if cursor == len(tokens):
            raise ValueError("Truncated SNBT")
        value = tokens[cursor]
        cursor += 1
        if expected is not None and value != expected:
            raise ValueError("Unexpected SNBT structure")
        return value

    take("[")
    stacks, slots = [], set()
    while cursor < len(tokens) and tokens[cursor] != "]":
        take("{")
        fields = {}
        while cursor < len(tokens) and tokens[cursor] != "}":
            key = take().strip('"')
            if key not in ("id", "Slot", "count", "Count") or key in fields:
                raise ValueError("Unknown/duplicate SNBT key or item components")
            take(":")
            fields[key] = take()
            if cursor < len(tokens) and tokens[cursor] == ",":
                take(",")
            elif cursor < len(tokens) and tokens[cursor] != "}":
                raise ValueError("SNBT field separator missing")
        take("}")
        if fields.get("id") != '"minecraft:stone"' or "Slot" not in fields or ("count" in fields and "Count" in fields):
            raise ValueError("Only ordinary stone chest entries accepted")
        count_text = fields.get("count", fields.get("Count", "1"))
        # Minecraft 1.21.1 ItemStack.CODEC decoder defaults a missing count to 1.
        if not re.fullmatch(r"\d+[bBsS]?", count_text) or not re.fullmatch(r"\d+[bBsS]?", fields["Slot"]):
            raise ValueError("Invalid integer chest count/Slot")
        count, slot = int(count_text.rstrip("bBsS")), int(fields["Slot"].rstrip("bBsS"))
        if not 1 <= count <= 64 or not 0 <= slot < 27 or slot in slots:
            raise ValueError("Invalid/duplicate single-chest slot or stone stack count")
        slots.add(slot)
        stacks.append({"slot": slot, "id": STONE, "count": count})
        if cursor < len(tokens) and tokens[cursor] == ",":
            take(",")
        elif cursor < len(tokens) and tokens[cursor] != "]":
            raise ValueError("SNBT stack separator missing")
    take("]")
    if cursor != len(tokens):
        raise ValueError("Trailing SNBT data")
    return {"position": coordinates, "total": sum(s["count"] for s in stacks), "stacks": stacks, "snbt": body}


def transition(previous, current, earliest):
    return {"start": max(earliest, previous["start"]), "end": current["end"],
        "observation_span_ms": (current["end"] - max(earliest, previous["start"])) * 1000}


def e2e(source, target):
    if source["end"] < source["start"] or target["end"] < target["start"]:
        raise ValueError("Invalid observation interval")
    return {"lower_ms": max(0.0, (target["start"] - source["end"]) * 1000),
        "upper_ms": max(0.0, (target["end"] - source["start"]) * 1000),
        "source_observation_span_ms": (source["end"] - source["start"]) * 1000,
        "target_observation_span_ms": (target["end"] - target["start"]) * 1000}


def command_observation(trace, started, server, command, send):
    """Retain the original body even when inherited helpers pop their reply."""
    record = {"server": server, "command": command, "start": time.monotonic() - started,
        "utc_request_start": utc_now()}
    trace.append(record)
    try:
        record["reply"] = send(server, command)
        if "ERROR " in record["reply"]:
            raise AssertionError(server + ": " + record["reply"])
    except Exception as error:
        record["failure"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        record.update(end=time.monotonic() - started, utc_reply_end=utc_now())
    return dict(record)


def class_manifest(folder):
    folder = folder.resolve()
    allowed = ((ROOT / "scratch/dev-launch").resolve(), (ROOT / "build/classes").resolve(),
        (ROOT / "build/resources").resolve())
    if not any(folder.is_relative_to(root) for root in allowed) or not folder.is_dir():
        raise ValueError("Refusing unrelated launch mod folder")
    files, total = [], 0
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            actual = path.resolve()
            if not actual.is_relative_to(folder):
                raise ValueError("Launch mod-folder file escapes via symlink")
            raw = path.read_bytes()
            total += len(raw)
            if len(files) >= 4096 or total > 32 * 1024 * 1024:
                raise ValueError("Launch mod folder exceeds bounded hash collection")
            files.append({"relative_path": path.relative_to(folder).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)})
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"source_type": "launch_fml_mod_folder", "path": str(folder), "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "manifest_format": "sorted compact JSON array of relative_path/sha256/size_bytes objects",
        "files": files, "total_bytes": total}


def jar_manifest(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or path.suffix != ".jar" or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Unexpected/oversized isolated mod JAR")
    raw, files, total = path.read_bytes(), [], 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
        if "dev/crosstesseract/test/ThreeServerHarness.class" not in names or "META-INF/neoforge.mods.toml" not in names:
            raise ValueError("Not the cross_tesseract native harness JAR")
        if not re.search(r'modId\s*=\s*"cross_tesseract"', archive.read("META-INF/neoforge.mods.toml").decode()):
            raise ValueError("JAR mod identity differs")
        for name in sorted(names):
            if name.endswith("/"):
                continue
            if len(files) >= 4096 or archive.getinfo(name).file_size + total > 32 * 1024 * 1024:
                raise ValueError("Mod JAR content exceeds bounded hash collection")
            content = archive.read(name)
            total += len(content)
            files.append({"relative_path": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)})
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"source_type": "single_native_mod_jar_in_live_launch_mods_directory", "path": str(path),
        "jar_sha256": hashlib.sha256(raw).hexdigest(), "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "manifest_format": "sorted compact JSON array of relative_path/sha256/size_bytes objects",
        "files": files, "total_bytes": total,
        "resolution_scope": "Single cross_tesseract JAR in actual process working-directory mods folder; NeoForge standard discovery. Old harness has no class-loader CodeSource API, so retain operator launch evidence separately."}


def load_helpers():
    spec = importlib.util.spec_from_file_location("ct_container_frozen_helpers", DRIVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_driver(args, y, source_evidence):
    base = load_helpers()

    class ContainerBenchmark(base.Benchmark):
        def __init__(self):
            super().__init__(args)
            self.y, self.chests, self.launch_manifests = y, {}, {}
            self.target = self.target.with_name(self.target.name.replace("optimization-", "optimization-container-", 1))
            self.report.update(report_kind="real_vanilla_container_low_flow", utc_start=utc_now(),
                observer_monotonic_start=self.started, operator_runtime_revision=args.operator_revision,
                source_evidence=source_evidence, helper_sha256=hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
                RCON_trace=[], attempted_endpoints=[], cleared_confirmed_stone=0, drain_proofs=[])
            self.report["conditions"] = {"scenarios": args.scenarios, "repeats": args.repeats,
                "probes_per_layout_per_repeat": args.probes, "stone_per_probe": AMOUNT,
                "probe_idle_seconds": args.probe_idle, "poll_seconds": args.poll,
                "timeout_seconds": args.timeout, "quiet_seconds": args.quiet,
                "endpoint_minimum_spacing_blocks": 64, "be_y": y, "chest_side": "EAST", "item_side_mask": 32,
                "expected_new_world_prefix": args.world_prefix, "resource": ITEM, "item_id": STONE,
                "warmup_seconds": 0, "steady_seconds": 0}
            self.report["measurement"] = {
                "scope": "Supplemental 32-stone low-flow external vanilla containers only. No 30s warmup/120s steady run or factory capacity claim.",
                "source": "Physical source chest Items decreases. Source extraction interval spans last full source read to first decrease read; if first read is decreased, earliest bound is item-replace request start, not exact source acceptance.",
                "target": "Physical destination chest Items increases; full completion is observed combined destination count 32, then independently proven zero buffers/SQL residue.",
                "clock": "Single Python monotonic clock for all RCON request/reply and observation intervals. No cross-JVM nanoTime subtraction or world-save claim.",
                "polling": "0.1s default read-only chest observation; conservative event intervals include polling, read order and RCON uncertainty.",
                "conservation": "Exactly 32 source items become 32 physical destination items. Local item buffers, SQL balances and allocation remaining must each independently be zero; SQL/WAL copies never summed.",
                "cleanup": "Only confirmed outputs in script-created chests are cleared once. Any failure/timeout leaves fixtures/assets/tickets for diagnosis; uncertain mutations are never replayed.",
                "revision": "Actual launch -Dfml.modFolders paths or single native mod JAR in live launch mods directory, with embedded class/resource hashes. Checkout/source hash is not loaded JVM revision proof; operator revision retained separately. Old harness lacks a class-loader CodeSource API.",
                "RCON": "Run without concurrent RCON sidecars. Minecraft has a shared console reply buffer and no request-specific body nonce; all raw bodies and intervals are retained and chest-coordinate replies must match. A protocol request ID alone is not body attribution proof.",
                "numeric_fields": "This run's helper accepts bounded scientific-notation fields and exact plain integer counters. Historical excluded tiny exponent fields remain unmeasured, not retroactively relabeled.",
                "percentiles": "Nearest-rank summaries of this small low-flow sample set; p95/p99 with 10 probes are the observed maximum, not high-volume tail or phase-wide tick metrics."}

        def issue(self, server, value, harness=True):
            if "push-item" in value or "pull-item" in value:
                raise ValueError("Capability injection/extraction is forbidden in this container benchmark")
            return command_observation(self.report["RCON_trace"], self.started, server,
                ("ct_test " if harness else "") + value,
                lambda name, command: base.command(base.PORTS[name], command))

        def vanilla(self, server, command):
            return self.issue(server, "execute in minecraft:overworld run " + command, False)

        def verify_isolation(self):
            super().verify_isolation()
            if any(s["metrics"].get("registered_loaded_endpoints") != 0 for s in self.report["ambient_status"].values()):
                raise ValueError("Requires new empty development worlds with no loaded test endpoints")
            for server, info in self.report["identity"].items():
                if not info["level_name"].startswith(args.world_prefix):
                    raise ValueError("Use fresh container worlds, not an earlier baseline/B/C world: " + server)
                proc = Path(f"/proc/{info['pid']}")
                argv = [a.decode() for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
                expanded, _ = base.expanded_vm_args(argv, server, (proc / "cwd").resolve())
                props = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in expanded if a.startswith("-D") and "=" in a}
                selected = []
                for entry in props.get("fml.modFolders", "").split(":"):
                    if entry.startswith("cross_tesseract%%"):
                        selected.append(class_manifest(Path(entry.split("%%", 1)[1])))
                if not selected:
                    cwd = (proc / "cwd").resolve()
                    if cwd != (ROOT / ("run-" + server)).resolve():
                        raise ValueError("Unexpected packaged launch working directory")
                    candidates = []
                    for path in sorted((cwd / "mods").glob("*.jar")):
                        with zipfile.ZipFile(path) as archive:
                            if "dev/crosstesseract/test/ThreeServerHarness.class" in archive.namelist():
                                candidates.append(path)
                    if len(candidates) != 1:
                        raise ValueError("Requires one unambiguous native cross_tesseract JAR in launch mods folder")
                    selected = [jar_manifest(candidates[0])]
                    info["launch_native_mods_directory"] = str(cwd / "mods")
                if not any(any(f["relative_path"] == "dev/crosstesseract/test/ThreeServerHarness.class"
                        for f in manifest["files"]) for manifest in selected):
                    raise ValueError("Launch-selected mod classes do not contain the real harness")
                info["launch_selected_fml_modFolders"] = props.get("fml.modFolders")
                info["launch_mod_artifact_manifests"] = selected
                bytecode_files = sorted((f for manifest in selected for f in manifest["files"]
                    if f["relative_path"].startswith("dev/crosstesseract/") and f["relative_path"].endswith(".class")),
                    key=lambda f: f["relative_path"])
                info["launch_crosstesseract_bytecode_sha256"] = hashlib.sha256(json.dumps(
                    bytecode_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.launch_manifests[server] = selected
                argfiles = []
                for value in argv:
                    if not value.startswith("@"):
                        continue
                    path = Path(value[1:])
                    if not path.is_absolute():
                        path = (proc / "cwd").resolve() / path
                    path = path.resolve()
                    roots = ((ROOT / "scratch/dev-launch").resolve(), (ROOT / "build/moddev").resolve())
                    development = path.name in ("server" + server + "RunClasspath.txt", "server" + server + "RunVmArgs.txt",
                        "server" + server + "RunProgramArgs.txt") and any(path.is_relative_to(root) for root in roots)
                    cwd = (proc / "cwd").resolve()
                    official_paths = ((cwd / "user_jvm_args.txt").resolve(),
                        (cwd / "libraries/net/neoforged/neoforge/21.1.252/unix_args.txt").resolve(),
                        (ROOT / "scratch/packaged/server/user_jvm_args.txt").resolve(),
                        (ROOT / "scratch/packaged/server/libraries/net/neoforged/neoforge/21.1.252/unix_args.txt").resolve())
                    official = cwd == (ROOT / ("run-" + server)).resolve() and path in official_paths and path.is_relative_to(ROOT)
                    if not (development or official) or path.stat().st_size > 1048576:
                        raise ValueError("Unexpected launch argfile provenance")
                    raw = path.read_bytes()
                    argfiles.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)})
                info["all_launch_argfiles"] = argfiles
            if len({i["launch_crosstesseract_bytecode_sha256"] for i in self.report["identity"].values()}) != 1:
                raise ValueError("A/B/C launch-selected mod bytecode differs; do not mix code revisions in a cohort")
            self.save()

        def endpoint(self, server, name, channel):
            position = layout(self.base_x, len(self.devices), self.y)
            x, _, z = position["be"]
            endpoint = base.Endpoint(name, server, x, z)
            endpoint.y = self.y
            self.devices.append(endpoint)
            self.report["attempted_endpoints"].append(vars(endpoint))
            chunk = (server, *position["chunk"])
            if chunk not in self.loaded_chunks:
                query = self.issue(server, f"forceload query {x} {z}", False)["reply"]
                if "marked for force loading" in query and "not" not in query.lower():
                    raise AssertionError("Fresh test chunk already force loaded")
                reply = self.issue(server, f"forceload add {x} {z}", False)["reply"]
                if "No chunks" in reply or "already" in reply.lower():
                    raise AssertionError("Fresh test forceload failed")
                self.loaded_chunks.append(chunk)
            cx, cy, cz = position["chest"]
            self.wait(lambda: self.vanilla(server, f"execute if block {x} {self.y} {z} minecraft:air")["reply"],
                lambda reply: "Test passed" in reply)
            self.wait(lambda: self.vanilla(server, f"execute if block {cx} {cy} {cz} minecraft:air")["reply"],
                lambda reply: "Test passed" in reply)
            self.issue(server, f"spawn {x} {z} {self.owner}")
            if "Test passed" not in self.vanilla(server,
                    f"execute if block {x} {self.y} {z} cross_tesseract:tesseract")["reply"]:
                raise AssertionError("Live harness spawn height/block does not match the declared y64 geometry")
            endpoint.id = self.wait(lambda: self.inspect(endpoint), lambda d: d["registered"])["id"]
            self.issue(server, f"bind {x} {z} {channel}")
            self.wait(lambda: self.inspect(endpoint), lambda d: d["channel"] == channel and not d["pause"])
            self.issue(server, f"mode {x} {z} {base.FE} OFF")
            self.issue(server, f"mode {x} {z} {ITEM} OFF")
            self.issue(server, f"sides {x} {z} {ITEM} 32")
            for nx, nz in ((cx - 1, cz), (cx + 1, cz), (cx, cz - 1), (cx, cz + 1)):
                reply = self.vanilla(server, f"execute unless block {nx} {cy} {nz} minecraft:chest")["reply"]
                if "Test passed" not in reply:
                    raise AssertionError("Unexpected neighboring chest; no inventory inspected or overwritten")
            created = self.vanilla(server, f"setblock {cx} {cy} {cz} minecraft:chest[facing=north,type=single,waterlogged=false] keep")
            if "changed" not in created["reply"].lower():
                raise AssertionError("Chest keep placement did not report success")
            self.chests[name] = {"server": server, "position": position["chest"], "endpoint_id": endpoint.id,
                "creation_trace_index": self.report["RCON_trace"].index(created), "layout": position}
            if self.chest(endpoint)["count"] != 0:
                raise AssertionError("New own chest is not empty")
            return endpoint

        def setup(self):
            super().setup()
            self.report["chests"] = self.chests
            self.save()

        def activate(self, lanes, active):
            for lane in lanes:
                for endpoint in lane.sources + lane.sinks:
                    mode = ("SEND" if endpoint in lane.sources else "RECEIVE") if active else "OFF"
                    self.issue(endpoint.server, f"mode {endpoint.x} {endpoint.z} {ITEM} {mode}")

        def chest(self, endpoint):
            own = self.chests[endpoint.name]
            x, y, z = own["position"]
            result = self.vanilla(endpoint.server, f"data get block {x} {y} {z} Items")
            parsed = parse_items(result["reply"], (x, y, z))
            return {"endpoint": endpoint.name, "start": result["start"], "end": result["end"],
                "count": parsed["total"], "stacks": parsed["stacks"],
                "RCON_trace_index": self.report["RCON_trace"].index(result)}

        def frame(self, lane, order=0):
            source = self.chest(lane.sources[0])
            sinks = lane.sinks[order % len(lane.sinks):] + lane.sinks[:order % len(lane.sinks)]
            targets = {endpoint.name: self.chest(endpoint) for endpoint in sinks}
            return {"source": source, "targets": targets, "target_total": sum(r["count"] for r in targets.values()),
                "target_interval": {"start": min(r["start"] for r in targets.values()),
                    "end": max(r["end"] for r in targets.values())}}

        def residue(self, lanes):
            observed = super().residue(lanes)
            return {"sql_pool_items": observed["sql_pool_FE"],
                "sql_allocation_remaining_items": observed["sql_allocation_remaining_FE"],
                "local_buffers": observed["local_buffers"],
                "units": "This benchmark's fresh channels contain ordinary stone only; separate zero checks, never added together."}

        def is_empty(self, residue):
            return residue["sql_pool_items"] == residue["sql_allocation_remaining_items"] == 0 and all(
                d["registered"] and not d["pause"] and all(d.get(k, -1) == 0 for k in
                    ("txItem", "rxItem", "txFE", "rxFE", "txFluid", "rxFluid")) for d in residue["local_buffers"].values())

        def prove_drained(self, lane, total, probe=None, purpose="drain"):
            deadline = time.monotonic() + args.timeout
            quiet_start, snapshots = None, []
            proof = {"lane": lane.name, "purpose": purpose, "physical_destination_stone": total,
                "started": time.monotonic() - self.started, "passed": False, "snapshots": snapshots}
            self.report["drain_proofs"].append(proof)
            if probe is not None:
                probe.setdefault("drain_proof_refs", []).append(len(self.report["drain_proofs"]) - 1)
            while time.monotonic() < deadline:
                frame = self.frame(lane, len(snapshots))
                residue = self.residue([lane])
                snapshot = {"frame": frame, "residue": residue, "at": time.monotonic() - self.started}
                snapshots.append(snapshot)
                if probe is not None:
                    probe["quiescence_snapshots"] = snapshots
                if frame["source"]["count"] != 0 or frame["target_total"] != total:
                    raise AssertionError("Chest conservation changed during drain proof")
                if self.is_empty(residue):
                    quiet_start = quiet_start or time.monotonic()
                    if time.monotonic() - quiet_start >= args.quiet:
                        proof.update(quiet_seconds=time.monotonic() - quiet_start,
                            independent_zero_checks=True, passed=True, end=time.monotonic() - self.started)
                        return proof
                else:
                    quiet_start = None
                time.sleep(max(args.poll, .25))
            raise AssertionError("Independent buffer/SQL drain proof timeout; all assets retained")

        def probe(self, lane, index, result):
            result.update(index=index, passed=False, frames=[], ordinary_stone_requested=AMOUNT)
            before = self.prove_drained(lane, 0, result, "before_input")
            result["before_input_empty_proof"] = before
            time.sleep(args.probe_idle)
            previous = self.frame(lane, index)
            if previous["source"]["count"] or previous["target_total"]:
                raise AssertionError("Chest is not empty immediately before injection")
            x, y, z = self.chests[lane.sources[0].name]["position"]
            injection = self.vanilla(lane.sources[0].server,
                f"item replace block {x} {y} {z} container.0 with minecraft:stone 32")
            result["item_replace_trace_index"] = self.report["RCON_trace"].index(injection)
            result["item_replace_interval"] = {k: injection[k] for k in ("start", "end")}
            if "replaced" not in injection["reply"].lower() or "slot" not in injection["reply"].lower():
                raise AssertionError("Unconfirmed item-replace result; mutation will not be replayed")
            lane.accepted += AMOUNT
            source_event, first_output, full_output = None, None, None
            last_source, first_read = None, True
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                frame = self.frame(lane, index + len(result["frames"]))
                result["frames"].append(frame)
                source = frame["source"]
                if not 0 <= source["count"] <= AMOUNT or (last_source and source["count"] > last_source["count"]) or \
                        frame["target_total"] > AMOUNT or any(frame["targets"][name]["count"] < old["count"]
                            for name, old in previous["targets"].items()):
                    raise AssertionError("Unexpected source/target quantity or conservation decrease/duplication")
                if source_event is None and source["count"] < AMOUNT:
                    source_event = transition(last_source or injection, source, injection["start"])
                    source_event["origin"] = "item_replace_request_start_fallback_first_read_already_decreased" if first_read else "last_full_source_chest_read_to_first_decrease_read"
                    result["source_first_decrease_interval"] = source_event
                if first_output is None and frame["target_total"] > 0:
                    first_output = transition(previous["target_interval"], frame["target_interval"], injection["start"])
                    result["destination_first_increase_interval"] = first_output
                if full_output is None and frame["target_total"] == AMOUNT:
                    full_output = transition(previous["target_interval"], frame["target_interval"], injection["start"])
                    result["destination_full_32_interval"] = full_output
                    result["destination_totals"] = {name: r["count"] for name, r in frame["targets"].items()}
                # Source and destination reads are sequential. A fast transfer may
                # finish after a full source read but before the destination read;
                # retain that first destination interval and observe source decrease.
                if full_output is not None and source_event is not None:
                    break
                previous, last_source, first_read = frame, source, False
                time.sleep(args.poll)
            if source_event is None or first_output is None or full_output is None:
                raise AssertionError("Physical chest E2E timeout; fixtures/assets retained")
            result["first_output_E2E"] = e2e(source_event, first_output)
            result["full_32_E2E"] = e2e(source_event, full_output)
            result["after_output_drained_proof"] = self.prove_drained(lane, AMOUNT, result, "after_full_output")
            lane.extracted += AMOUNT
            for name, count in result["destination_totals"].items():
                lane.sink_totals[name] = lane.sink_totals.get(name, 0) + count
            result["clears"] = []
            for endpoint in lane.sinks:
                count = result["destination_totals"][endpoint.name]
                if not count:
                    continue
                x, y, z = self.chests[endpoint.name]["position"]
                clear = self.vanilla(endpoint.server, f"data remove block {x} {y} {z} Items")
                result["clears"].append({"endpoint": endpoint.name, "confirmed_items_before_clear": count,
                    "trace_index": self.report["RCON_trace"].index(clear)})
                if "modified" not in clear["reply"].lower():
                    raise AssertionError("Unconfirmed output clear; never replayed")
                if self.chest(endpoint)["count"]:
                    raise AssertionError("Confirmed output chest failed to clear")
                self.report["cleared_confirmed_stone"] += count
            result["ready_for_next_probe_proof"] = self.prove_drained(lane, 0, result, "after_confirmed_clear")
            result["passed"] = True
            return result

        def measure(self, name, repetition):
            lane = self.cases[name][0]
            sample = {"scenario": name, "repeat": repetition, "passed": False, "probes": []}
            self.report["samples"].append(sample)
            self.activate([lane], True)
            sample["counter_start"] = self.snapshot()
            before = dict(lane.sink_totals)
            for index in range(args.probes):
                # Append before issuing any mutation so failures retain the in-flight probe.
                probe = {"index": index, "passed": False}
                sample["probes"].append(probe)
                try:
                    self.probe(lane, index, probe)
                except Exception as error:
                    probe["failure"] = type(error).__name__ + ": " + str(error)
                    raise
                self.save()
                print(f"{args.label}: {name} repeat {repetition} real-chest {index + 1}/{args.probes}", flush=True)
            sample["counter_end"] = self.snapshot()
            sample["counter_delta"] = self.deltas(sample["counter_start"], sample["counter_end"])
            sample["actual_chest_items_by_sink"] = {e.name: lane.sink_totals.get(e.name, 0) - before.get(e.name, 0) for e in lane.sinks}
            for event in ("first_output_E2E", "full_32_E2E"):
                sample[event] = {bound: base.quantiles([p[event][bound] for p in sample["probes"]])
                    for bound in ("lower_ms", "upper_ms", "source_observation_span_ms", "target_observation_span_ms")}
            sample["passed"] = (all(value > 0 for value in sample["actual_chest_items_by_sink"].values()) and
                sample["counter_delta"]["errors"] == sample["counter_delta"]["queue_rejected"] == sample["counter_delta"]["quarantined"] == 0)
            if not sample["passed"]:
                raise AssertionError("Missing cumulative service to a destination or runtime error/rejection/quarantine")
            self.activate([lane], False)

        def verify_final_identity(self):
            for server, info in self.report["identity"].items():
                if self.issue(server, "pid")["reply"].strip() != "PID " + str(info["pid"]):
                    raise AssertionError("JVM PID changed during container run")
                rows = base.sql("SELECT world_id,session_id,fencing_epoch FROM ct_servers WHERE cluster_id='dev_three_v1' "
                    "AND server_id='" + info["server_id"] + "' AND lease_until>CURRENT_TIMESTAMP(6)")
                if rows != [[info["world_id"], info["session_id"], str(info["fencing_epoch"])]]:
                    raise AssertionError("World/session/epoch changed during container run")
                for manifest in self.launch_manifests[server]:
                    current = jar_manifest(Path(manifest["path"])) if "jar_sha256" in manifest else class_manifest(Path(manifest["path"]))
                    if current["manifest_sha256"] != manifest["manifest_sha256"] or current.get("jar_sha256") != manifest.get("jar_sha256"):
                        raise AssertionError("Launch-selected class/resource files changed during run")

        def cleanup(self):
            if self.report["failures"] or not self.report["samples"] or not all(s.get("passed") for s in self.report["samples"]):
                self.report["fixture_retained_for_diagnosis"] = True
                return
            # Every output was already confirmed and cleared. Validate before removing empty own fixtures.
            for lane in (lane for case in self.cases.values() for lane in case):
                self.prove_drained(lane, 0, purpose="final_cleanup_empty_proof")
                self.activate([lane], False)
            for endpoint in self.devices:
                if self.chest(endpoint)["count"]:
                    raise AssertionError("Unexpected chest residue during cleanup; retaining remaining fixtures")
                x, y, z = self.chests[endpoint.name]["position"]
                if "changed" not in self.vanilla(endpoint.server,
                        f"setblock {x} {y} {z} minecraft:air replace")["reply"].lower():
                    raise AssertionError("Empty own chest removal did not report success")
                self.issue(endpoint.server, f"remove {endpoint.x} {endpoint.z}")
                self.report["cleanup"].append({"endpoint": endpoint.name, "empty_chest_removed": True, "device_removed": True})
            for server, cx, cz in self.loaded_chunks:
                self.issue(server, f"forceload remove {cx * 16} {cz * 16}", False)
            self.report["fixture_retained_for_diagnosis"] = False

        def run(self):
            self.save()
            try:
                self.verify_isolation()
                self.setup()
                for repeat in range(1, args.repeats + 1):
                    names = args.scenarios[(repeat - 1) % len(args.scenarios):] + args.scenarios[:(repeat - 1) % len(args.scenarios)]
                    for name in names:
                        self.measure(name, repeat)
                self.verify_final_identity()
            except KeyboardInterrupt:
                self.report["failures"].append("Interrupted; uncertain operations not replayed and fixtures/assets retained")
            except Exception as error:
                self.report["failures"].append(type(error).__name__ + ": " + str(error))
            finally:
                try:
                    self.cleanup()
                except Exception as error:
                    self.report["failures"].append("Cleanup: " + type(error).__name__ + ": " + str(error))
                    self.report["fixture_retained_for_diagnosis"] = True
                self.report.update(utc_end=utc_now(), elapsed_seconds=time.monotonic() - self.started,
                    passed=not self.report["failures"] and all(s.get("passed") for s in self.report["samples"]))
                self.report["devices"] = [vars(e) for e in self.devices]
                self.report["chests"] = self.chests
                self.save()
            print("Saved " + str(self.target), flush=True)
            if self.report["failures"]:
                print(json.dumps(self.report["failures"], ensure_ascii=False), file=sys.stderr)
            return 0 if self.report["passed"] else 1

    return ContainerBenchmark()


def self_test(y):
    prefix = "1000004, 64, 164 has the following block data: "
    assert parse_items(prefix + "[]")["total"] == 0
    assert parse_items(prefix + '[{Slot: 0b, id: "minecraft:stone", count: 32}]')["total"] == 32
    assert parse_items(prefix + '[{Slot: 0b, id: "minecraft:stone"}]')["total"] == 1
    assert parse_items(prefix + '[{Slot: 0b, id: "minecraft:stone", Count: 16b}, {Slot: 1b, id: "minecraft:stone", count: 16}]')["total"] == 32
    for body in ('[{Slot: 0b, id: "minecraft:dirt", count: 32}]',
            '[{Slot: 0b, id: "minecraft:stone", count: 32, components: {}}]',
            '[{Slot: 0b, id: "minecraft:stone", count: 32, Count: 32b}]',
            '[{Slot: 0b, id: "minecraft:stone", count: 65}]',
            '[{Slot: 0b, id: "minecraft:stone", count: 16}, {Slot: 0b, id: "minecraft:stone", count: 16}]'):
        try:
            parse_items(prefix + body)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsupported/non-stone SNBT accepted")
    positions = [layout(1_000_000, index, y) for index in range(7)]
    assert all(p["be"][0] // 16 == p["chest"][0] // 16 and p["be"][2] // 16 == p["chest"][2] // 16 for p in positions)
    assert all(b["be"][0] - a["be"][0] >= 64 for a, b in zip(positions, positions[1:]))
    s = transition({"start": 1.0, "end": 1.01}, {"start": 1.1, "end": 1.11}, .5)
    t = transition({"start": 1.2, "end": 1.21}, {"start": 1.3, "end": 1.31}, .5)
    assert abs(e2e(s, t)["lower_ms"] - 90) < .001 and abs(e2e(s, t)["upper_ms"] - 310) < .001
    fallback = transition({"start": .5, "end": .51}, {"start": .52, "end": .53}, .5)
    assert fallback["start"] == .5
    trace, calls = [], []
    def fake_reply(server, command):
        calls.append((server, command))
        return "STATUS online {db_transactions=9007199254740993}\n"
    observed = command_observation(trace, time.monotonic(), "A", "ct_test status", fake_reply)
    observed.pop("reply")  # The untouched superclass snapshot performs this pop.
    assert trace[0]["reply"].startswith("STATUS online") and len(calls) == 1
    def uncertain_reply(server, command):
        calls.append((server, command))
        raise RuntimeError("uncertain command result")
    try:
        command_observation(trace, time.monotonic(), "A", "item replace block ...", uncertain_reply)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Uncertain mutation did not fail")
    assert len(calls) == 2 and "failure" in trace[-1] and "end" in trace[-1]
    print(f"Offline strict-SNBT/layout/interval checks passed; harness y={y}; no JVM/backend contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="container-supplement")
    parser.add_argument("--scenarios", default="same,cross,mixed")
    parser.add_argument("--probes", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--idle", type=float, default=2.2)
    parser.add_argument("--poll", type=float, default=.1)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--quiet", type=float, default=2.2)
    parser.add_argument("--world-prefix", default="world-opt-container-", help="Required new isolated world-name prefix; do not reuse main benchmark worlds")
    parser.add_argument("--operator-revision", default="unknown", help="Operator-declared loaded revision; actual mod folder hashes collected separately")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    args.scenarios = list(dict.fromkeys(args.scenarios.split(",")))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label) or not args.scenarios or any(s not in SCENARIOS for s in args.scenarios) or \
            not 1 <= args.probes <= 40 or not 1 <= args.repeats <= 3 or not 2.2 <= args.idle <= 30 or \
            not .05 <= args.poll <= 1 or not 30 <= args.timeout <= 600 or not 2.2 <= args.quiet <= 30 or \
            not re.fullmatch(r"world-opt-[A-Za-z0-9_-]{1,40}", args.world_prefix) or \
            (args.operator_revision != "unknown" and not re.fullmatch(r"[0-9a-f]{7,40}", args.operator_revision)):
        parser.error("Parameters outside bounded isolated-container benchmark range")
    # Compatibility values for the untouched helper constructor; never drive FE.
    args.warmup, args.seconds, args.probe_idle, args.feed_period = 0, 0, args.idle, .5
    y, evidence = harness_height()
    if args.self_test:
        self_test(y)
        return 0
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE_DESIGN_PREVIEW_NO_BACKEND_ACCESS", "harness": evidence,
            "layouts": list(SCENARIOS), "item": STONE, "items_per_probe": AMOUNT,
            "example_layouts": [layout(1_000_000, i, y) for i in range(7)],
            "note": "Run --execute only after FE measurements on newly prepared empty isolated worlds."}, indent=2))
        return 0
    return make_driver(args, y, evidence).run()


if __name__ == "__main__":
    sys.exit(main())
