"""Validate explicitly selected, completed original benchmark evidence offline.

This checks file identity and completeness, not the scientific interpretation of
latency or the loaded Minecraft classes. It never contacts a backend or process.
"""
from pathlib import Path
import hashlib
import json
import re


def _read_report(root, name, maximum):
    root = Path(root).resolve()
    path = Path(name)
    if not path.is_absolute():
        path = root / path
    if path.is_symlink() or not path.resolve().is_relative_to(root / "reports"):
        raise ValueError("Benchmark input must be a regular file within reports")
    if any(parent.is_symlink() for parent in path.parents if parent != root):
        raise ValueError("Symlinked benchmark report path")
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("Missing or oversized benchmark input")
    raw = path.read_bytes()
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("Benchmark report must be an object")
    return path.resolve(), raw, body


def select_original(root, sequence_path, original_revision):
    path, raw, sequence = _read_report(root, sequence_path, 262144)
    if (sequence.get("stage") != "original" or
            sequence.get("loaded_source_revision_declared") != original_revision or
            sequence.get("passed") is not True or
            sequence.get("procedure_completed", True) is not True or
            not isinstance(sequence.get("utc_end"), str) or
            sequence.get("stop_failure") or sequence.get("failure")):
        raise ValueError("Original sequence is incomplete, failed or another revision")
    runs = sequence.get("runs")
    if not isinstance(runs, list) or not 2 <= len(runs) <= 8:
        raise ValueError("Original sequence has invalid run list")
    selected = {}
    for entry in runs:
        if not isinstance(entry, dict):
            raise ValueError("Malformed original run")
        command = entry.get("command")
        if not isinstance(command, list) or not all(isinstance(v, str) for v in command):
            raise ValueError("Malformed original command")
        if not any(Path(v).name == "optimization-benchmark.py" for v in command[:2]):
            continue
        if entry.get("loaded_source_revision_declared") != original_revision or entry.get("exit_code") != 0:
            raise ValueError("Original benchmark run failed or has another revision")
        try:
            scenario = command[command.index("--scenarios") + 1]
            label = command[command.index("--label") + 1]
        except (ValueError, IndexError) as error:
            raise ValueError("Original benchmark has no explicit scenarios/label") from error
        kind = {"backpressure,hotspot": "pressure", "same,cross,mixed": "primary"}.get(scenario)
        if kind is None or kind in selected:
            raise ValueError("Ambiguous original benchmark stages")
        declared_hash = entry.get("report_sha256")
        if not isinstance(declared_hash, str) or re.fullmatch("[0-9a-f]{64}", declared_hash) is None:
            raise ValueError("Original report SHA-256 is required")
        name = entry.get("report")
        if not isinstance(name, str):
            raise ValueError("Original report path is required")
        child_path, child_raw, child = _read_report(root, name, 134217728)
        if hashlib.sha256(child_raw).hexdigest() != declared_hash:
            raise ValueError("Original child report checksum differs")
        conditions = child.get("conditions", {})
        scenarios = scenario.split(",")
        samples = child.get("samples", [])
        if (child.get("passed") is not True or child.get("failures") or
                child.get("label") != label or conditions.get("scenarios") != scenarios or
                conditions.get("repeats") != 3 or conditions.get("warmup_seconds") != 30 or
                conditions.get("steady_seconds") != 120 or
                len(samples) != 3 * len(scenarios) or
                any(not isinstance(s, dict) or s.get("passed") is not True for s in samples) or
                {(s.get("scenario"), s.get("repeat")) for s in samples} !=
                {(scenario, repeat) for scenario in scenarios for repeat in (1, 2, 3)}):
            raise ValueError("Original stage is not a complete matched 30/120/3 run")
        if conditions.get("low_flow_probes_per_path_per_repeat") != (40 if kind == "primary" else 0):
            raise ValueError("Original stage probe workload differs")
        selected[kind] = {"report": str(child_path.relative_to(Path(root).resolve())),
                          "sha256": declared_hash, "label": label}
    if set(selected) != {"pressure", "primary"}:
        raise ValueError("Both unique original benchmark stages are required")
    return {"sequence": str(path.relative_to(Path(root).resolve())),
            "sha256": hashlib.sha256(raw).hexdigest(), "stages": selected}


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ct-evidence-selection-") as directory:
        root = Path(directory)
        (root / "reports").mkdir()
        original = "1" * 40
        runs = []
        for kind, scenarios in (("pressure", ["backpressure", "hotspot"]),
                                ("primary", ["same", "cross", "mixed"])):
            child = {"label": kind, "passed": True, "failures": [], "conditions": {
                "scenarios": scenarios, "repeats": 3, "warmup_seconds": 30,
                "steady_seconds": 120, "low_flow_probes_per_path_per_repeat": 40 if kind == "primary" else 0},
                "samples": [{"scenario": s, "repeat": r, "passed": True}
                            for s in scenarios for r in (1, 2, 3)]}
            raw = json.dumps(child).encode()
            (root / "reports" / (kind + ".json")).write_bytes(raw)
            runs.append({"command": ["python3", "scripts/optimization-benchmark.py", "--label", kind,
                "--scenarios", ",".join(scenarios)], "loaded_source_revision_declared": original,
                "exit_code": 0, "report": "reports/" + kind + ".json",
                "report_sha256": hashlib.sha256(raw).hexdigest()})
        sequence = {"stage": "original", "loaded_source_revision_declared": original,
            "passed": True, "procedure_completed": True, "utc_end": "2026-10-06T00:00:00Z", "runs": runs}
        path = root / "reports" / "sequence.json"
        def save(body):
            path.write_text(json.dumps(body))
        def rejected(body):
            save(body)
            try:
                select_original(root, path, original)
            except (ValueError, TypeError):
                return
            raise AssertionError("Invalid original evidence accepted")
        save(sequence)
        assert set(select_original(root, path, original)["stages"]) == {"pressure", "primary"}
        rejected({**sequence, "procedure_completed": False})
        rejected({**sequence, "loaded_source_revision_declared": "2" * 40})
        rejected({**sequence, "runs": [runs[0], runs[0]]})
        rejected({**sequence, "runs": [runs[0], {**runs[1], "report_sha256": "0" * 64}]})
        rejected({**sequence, "runs": [runs[0], {**runs[1], "report": "../outside.json"}]})
        (root / "reports" / "primary.json").write_text("{}")
        rejected(sequence)
    print("Offline completed-evidence selection checks passed; no game/backend contacted.")


if __name__ == "__main__":
    self_test()
