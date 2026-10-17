"""Small, explicit operator allowlist for RC test runtime identities.

No discovery, file writes, subprocesses or backend access. Add a candidate only
after the operator supplies its complete revision and actually built JAR SHA.
"""
import re

ORIGINAL_FINAL_REVISION = "3647dede64cfc23e054dfa962fd127787cae14ec"
ORIGINAL_FINAL_JAR = "1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f"
F3_REVISION = "f3c59b772dcbd343596174c73093b2fef536f19c"
F3_JAR = "7924ab808667c69aabbbe71c2c92f1294437a7cc8bb19e409c366af1f682553a"

# ROOT-supplied0113 pair, after its actual build/integration success. Native
# matrix/source qualification is an additional freeze gate, not implied here.
APPROVED = {
    ORIGINAL_FINAL_REVISION: {"jar_sha256": ORIGINAL_FINAL_JAR, "role": "candidate"},
    F3_REVISION: {"jar_sha256": F3_JAR, "role": "baseline"},
    "0113ef30f2269f9ea51e7c15e585792828fd2a51": {
        "jar_sha256": "70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c", "role": "candidate"},
}


def approved_pair(revision, jar_sha256, *, allow_baseline=False):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Explicit full source revision required")
    if not isinstance(jar_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", jar_sha256):
        raise ValueError("Explicit complete JAR SHA256 required")
    known = APPROVED.get(revision)
    if known is None or known["jar_sha256"] != jar_sha256:
        raise ValueError("Runtime revision/JAR pair is not explicitly approved")
    if known["role"] == "baseline" and not allow_baseline:
        raise ValueError("Baseline identity is not a candidate qualification")
    return {"source_revision": revision, "JAR_sha256": jar_sha256, "role": known["role"]}


def manifest_identity(seal, revision, jar_sha256, *, allow_baseline=False):
    expected = approved_pair(revision, jar_sha256, allow_baseline=allow_baseline)
    if seal.get("source_revision") != revision or seal.get("artifacts", {}).get("JAR", {}).get("sha256") != jar_sha256:
        raise ValueError("Frozen manifest differs from explicit expected revision/JAR")
    return expected


def legacy_stage_pair(seal):
    """Preserve only the two historical CLI defaults, never a new candidate."""
    pair = (seal.get("source_revision"), seal.get("artifacts", {}).get("JAR", {}).get("sha256"))
    if pair not in ((ORIGINAL_FINAL_REVISION, ORIGINAL_FINAL_JAR), (F3_REVISION, F3_JAR)):
        raise ValueError("New candidate requires both explicit expected-identity arguments")
    return pair
