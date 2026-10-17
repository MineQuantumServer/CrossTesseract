#!/usr/bin/env python3
"""New smoke2/full2 continuation; never rewrite the failed original RC sequence.

Default is offline. Only closed, SHA-verified original FE/mix/ablation children
are reused as evidence. The first failed smoke remains failed; both new native
stages use fresh worlds, existing frozen3647/v2 bytes and normal stop.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meta(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def utc():
    return datetime.now(timezone.utc).isoformat()


def read_ref(ref):
    path = Path(ref["path"])
    if not path.is_absolute():
        path = ROOT / path
    if path.is_symlink():
        raise ValueError("Regular closed evidence only")
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or sha(path) != ref["sha256"]:
        raise ValueError("Closed evidence SHA/path mismatch")
    return path, json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--failed-sequence", type=Path)
    parser.add_argument("--failure-audit", type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"execution": "NOT_RUN", "order": ["fresh_smoke2_60s", "fresh_full2_3600s"],
                          "requires": "--execute --failed-sequence CLOSED_FAILED --failure-audit CLOSED_OFFLINE_AUDIT"}))
        return 0
    if args.failed_sequence is None or args.failure_audit is None:
        parser.error("Explicit closed failed evidence and its offline audit required")
    original_path = args.failed_sequence.resolve(strict=True)
    audit_path = args.failure_audit.resolve(strict=True)
    if not all(p.is_relative_to(ROOT) for p in (original_path, audit_path)):
        raise ValueError("Repository evidence only")
    original = json.loads(original_path.read_text())
    audit = json.loads(audit_path.read_text())
    if original.get("passed") is not False or original.get("state") != "FAILED_RETAINED" or not original.get("utc_end"):
        raise ValueError("Original sequence must remain closed and FAILED_RETAINED")
    runs = {run["name"]: run for run in original["runs"]}
    if runs["full3600"]["state"] != "NOT_RUN" or runs["smoke60"]["state"] != "FAILED_RETAINED":
        raise ValueError("Only the first failed smoke / unstarted full sequence is supported")
    failed_path, failed = read_ref(runs["smoke60"]["child_controller"])
    if (failed["passed"] is not False or failed.get("workload_exit") != 1
            or failed.get("all_own_launchers_exited_and_locks_free") is not True
            or any(v["exit_code"] != 0 for v in failed["own_launcher_exits"].values())
            or failed["failures"] != ["JSONDecodeError: Expecting value: line 115 column 3 (char 9693)"]):
        raise ValueError("Different failed native state; retain it for explicit review")
    prior_refs = {}
    for name in ("finalFE3", "f3Bmix", "finalBmix", "finalFastMix", "ablationDefault", "ablationNotification1000", "ablationActive200"):
        run = runs[name]
        path, data = read_ref(run["child_controller"])
        if (run["state"] != "PASS" or run["exit_code"] != 0 or not data.get("qualified_passed")
                or not data.get("functional_passed") or not data.get("all_own_launchers_exited_and_locks_free")):
            raise ValueError("Prior child incomplete: " + name)
        read_ref(data["raw_report"])
        prior_refs[name] = meta(path)
    # Audit contains the unchanged invalid raw bytes and the complete append-only
    # command journal. It does not repair JSON or claim a separate SQL asset audit.
    for key in ("raw_report_unchanged", "events"):
        ref = audit[key]; path = ROOT / ref["path"]
        if sha(path) != ref["sha256"]:
            raise ValueError("Failed raw evidence changed")
    if audit["recorded_asset_injection_or_extraction_or_component_mutation_commands"] != 0:
        raise ValueError("Unexpected old business commands; no automatic continuation")
    final_path, _ = read_ref(original["final_manifest"])
    read_ref(original["f3_manifest"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    target = ROOT / "reports/rc-20261017" / ("v2-soak-continuation-" + stamp + ".json")
    archive = ROOT / "reports/raw" / ("rc-soak-observer-fix-sources-" + stamp)
    archive.mkdir(parents=True, exist_ok=False)
    sources = []
    for source in (Path(__file__).resolve(), ROOT / "scripts/rc-soak.py", ROOT / "scripts/analysis/run-rc-v2-soak.py"):
        dest = archive / source.name
        with dest.open("xb") as output:
            output.write(source.read_bytes())
        sources.append({"source": meta(source), "archive": meta(dest)})
    helper = "scripts/analysis/run-rc-v2-soak.py"
    report = {"schema": 1, "utc_start": utc(), "passed": False, "state": "STARTING",
              "continuation_of_failed_sequence": meta(original_path), "failed_first_smoke_controller": meta(failed_path),
              "first_smoke_failure_audit": meta(audit_path), "prior_closed_children": prior_refs,
              "f3_manifest": original["f3_manifest"], "final_manifest": original["final_manifest"],
              "controller": meta(Path(__file__).resolve()), "archived_observer_sources": sources, "failures": [],
              "scope": "New smoke2/full2 after confirmed observer framing/JSON fixes. Original parent and first smoke remain FAILED; original full remains NOT_RUN. No original mutation replay/world reuse.",
              "runs": [{"name": name, "state": "NOT_RUN", "command": ["python3", helper, "--execute", "--manifest", str(final_path),
                          "--kind", kind, "--label", label]} for name, kind, label in (
                              ("smoke60", "smoke", "rc-soak-v2-3647-smoke2"),
                              ("full3600", "full", "rc-soak-v2-3647-full2"))]}

    def save():
        pending = target.with_suffix(".json.pending")
        pending.write_text(json.dumps(report, indent=2) + "\n"); pending.replace(target)

    try:
        if target.exists():
            raise ValueError("Never overwrite evidence")
        save()
        for run in report["runs"]:
            run.update(state="RUNNING", utc_start=utc(), observer_start=time.monotonic(), helper=meta(ROOT / helper))
            report["state"] = "RUNNING_" + run["name"]
            log = ROOT / "logs" / ("rc-v2-continuation-" + run["name"] + "-" + stamp + ".log")
            run["log"] = str(log.relative_to(ROOT)); save()
            print("RC_V2_CONTINUATION_STAGE_START " + run["name"], flush=True)
            with log.open("x") as output:
                child = subprocess.run(run["command"], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
            run.update(exit_code=child.returncode, utc_end=utc(), observer_end=time.monotonic())
            completion = json.loads(log.read_text().splitlines()[-1])
            run["completion"] = completion
            path, data = read_ref(completion["controller"])
            run["child_controller"] = meta(path)
            run["state"] = "PASS" if child.returncode == 0 and completion.get("passed") is True and data.get("passed") is True else "FAILED_RETAINED"
            save(); print("RC_V2_CONTINUATION_STAGE_END " + run["name"] + " " + run["state"], flush=True)
            if run["state"] != "PASS":
                raise ValueError("Fresh child failed; retain assets/configs and leave later stages NOT_RUN")
        report.update(state="COMPLETE", passed=True)
    except BaseException as error:
        report["failures"].append(type(error).__name__ + ": " + str(error)); report["state"] = "FAILED_RETAINED"
    finally:
        report["utc_end"] = utc(); save()
    print(json.dumps({"sequence": meta(target), "passed": report["passed"], "state": report["state"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
