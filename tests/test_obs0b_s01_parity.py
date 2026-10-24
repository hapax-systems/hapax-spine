"""S01 package tests; no Council import, host probe, credential or provider call.

Concrete catalog/quality cases project Council cef55b5216574f7eb80fd42c887c58e83f7cace0
config/platform-capability-registry.json (sha256
7d7518c484b90dbb16728993a4c9b5a69b0ad402bb541d254c447470f16d73ca).
The remaining cases are labeled adversarial constructions, not live observations.
Run this file with --mutation-controls for explicit source-break/restore controls.
"""
from __future__ import annotations

import copy
import importlib

import pytest
from pydantic import ValidationError

from hapax.spine import platform_capability_registry as registry

OBSERVATION = "local_compute.agentic_trust_evaluator_surface"
RECEIPT = "AgenticTrustEvidenceReceiptV1:retained-evidence"
WHEN = "2026-10-24T17:25:59Z"
QUALITY = {
    "eligible_quality_floors": ["frontier_required", "frontier_review_required", "deterministic_ok"],
    "explicit_equivalence_records": ["route-authority:cloud-burst-spike-dev-frontier-equivalence"],
    "excluded_task_classes": ["privacy_secret_sensitive", "private_repo", "write_heavy_source_mutation",
                              "runtime_mutation", "public_release_without_gate"],
}


@pytest.mark.parametrize("platform,profile,auth,model", [
    ("api", "openrouter", "api_key", "gpt-5.5"),
    ("kimi", "lane", "subscription", "kimi-code/k3"),
    ("codex", "full", "oauth", "gpt-6-astra"),
    ("agy", "direct", "operator_session", "gemini-4-argon"),
    ("glmcp", "direct", "subscription", "z_ai-glm-5.2"),
])
def test_current_registry_catalog(platform, profile, auth, model):
    assert registry.Platform(platform).value == platform
    assert registry.Profile(profile).value == profile
    assert registry.AuthSurface(auth).value == auth
    assert registry.ModelId(model).value == model


@pytest.mark.parametrize("model", ["claude-opus-4-6", "claude-sonnet-5", "gpt-oss-120b",
                                  "qwen3.5-9b", "gemini-3.5-flash", "z_ai-glm-5.3"])
def test_additional_pinned_catalog_members(model):
    # Source catalog members, not assertions that these models are currently served.
    assert registry.ModelId(model).value == model


@pytest.mark.parametrize("enum,value", [("Platform", "grok"), ("ModelId", "grok-build"),
    ("ModelId", "gemma3:4b"), ("ModelId", "invented-model"), ("Platform", "invented-platform"),
    ("Profile", "invented-profile"), ("AuthSurface", "invented-auth")])
def test_catalog_rejects_retired_and_unknown(enum, value):
    with pytest.raises(ValueError):
        getattr(registry, enum)(value)


def test_current_quality_record_and_task_class_scope():
    assert registry.QualityEnvelope.model_validate(QUALITY).model_dump(mode="json") == {
        **QUALITY, "allowed_task_classes": []}
    payload = {**QUALITY, "allowed_task_classes": [" Read_Only ", "read_only"]}
    assert registry.QualityEnvelope.model_validate(payload).allowed_task_classes == ["read_only"]
    authority = registry.SupplyAuthority(ceiling="read_only", allowed_task_classes=[" Read_Only ", "read_only"],
                                         excluded_task_classes=["runtime_mutation"])
    assert authority.allows_task_class("READ_ONLY")
    assert not authority.allows_task_class(None)
    assert not authority.allows_task_class("runtime_mutation")
    assert not authority.allows_task_class("unlisted")
    assert not authority.allows_task_class("read_only!")
    assert registry.SupplyAuthority(ceiling="unknown").allows_task_class(None)
    assert not registry.SupplyAuthority(ceiling="unknown").allows_task_class("bad!")


@pytest.mark.parametrize("field", ["allowed_task_classes", "excluded_task_classes"])
@pytest.mark.parametrize("value", ["", " ", "read only", "../grant", "bad!"])
def test_malformed_task_classes_refuse(field, value):
    with pytest.raises(ValidationError):
        registry.QualityEnvelope.model_validate({**QUALITY, field: [value]})
    with pytest.raises(ValidationError):
        registry.SupplyAuthority.model_validate({"ceiling": "unknown", field: [value]})


# Model-valid ordinary records plus the precise field an attacker substitutes.
CASES = [
    ("DescriptorVariant", {"variant_id": "long-context"}, "variant_id"),
    ("FreshnessSurfaceEvidence", {"evidence_refs": ["receipt:ordinary"]}, "evidence_refs"),
    ("HistoricalPerformance", {"evidence_refs": ["benchmark:ordinary"]}, "evidence_refs"),
    ("QualityEnvelope", QUALITY, "explicit_equivalence_records"),
    ("ScoreConfidence", {"score": 2, "confidence": 1, "evidence_refs": ["benchmark:ordinary"],
                         "observed_at": WHEN, "stale_after": "1h"}, "evidence_refs"),
    ("SupplyDescriptor", {"base_context_mode": "standard", "base_effort": "high",
        "reachable_context_modes": ["standard"], "reachable_efforts": ["high"],
        "context_mode_to_variant": {"standard": None}, "effort_to_variant": {"high": None}},
        "base_context_mode"),
    ("SupplyFreshness", {"observed_at": WHEN, "stale_after": "1h", "source_refs": ["receipt:ordinary"]}, "source_refs"),
    ("SupplyRoute", {"route_id": "codex.headless.full", "platform": "codex", "mode": "headless",
        "profile": "full", "sanctioned_wrapper": "scripts/wrapper", "approval_posture": "unknown",
        "capability_tier": "frontier_full", "worker_tier": "full_worker"}, "route_id"),
    ("ToolAccess", {"filesystem": "read_only", "shell": "none", "browser": False, "mcp": []}, "mcp"),
    ("ToolState", {"tool_id": "reader", "available": True, "observed_at": WHEN,
        "stale_after": "1h", "evidence_ref": "receipt:ordinary"}, "evidence_ref"),
]


@pytest.mark.parametrize("model,payload,field", CASES, ids=[c[0] for c in CASES])
def test_observation_cannot_be_supply(model, payload, field):
    cls = getattr(registry, model)
    cls.model_validate(copy.deepcopy(payload))  # The ordinary control is otherwise valid.
    for marker in (OBSERVATION, "route/" + OBSERVATION.upper(), RECEIPT):
        unsafe = copy.deepcopy(payload)
        unsafe[field] = [marker] if isinstance(unsafe[field], list) else marker
        with pytest.raises(ValidationError, match="agentic-trust"):
            cls.model_validate(unsafe)


@pytest.mark.parametrize("field,value", [
    ("reachable_efforts", [RECEIPT]), ("reachable_context_modes", [RECEIPT]),
    ("effort_to_variant", {"high": RECEIPT}), ("context_mode_to_variant", {RECEIPT: None}),
])
def test_descriptor_aliases_cannot_hide_observation(field, value):
    payload = copy.deepcopy(CASES[5][1])
    payload[field] = value
    with pytest.raises(ValidationError, match="agentic-trust"):
        registry.SupplyDescriptor.model_validate(payload)


@pytest.mark.parametrize("field", ["model_fingerprint", "launcher_contract", "sanctioned_wrapper"])
def test_route_aliases_cannot_hide_observation(field):
    payload = copy.deepcopy(CASES[7][1]); payload[field] = RECEIPT
    with pytest.raises(ValidationError, match="agentic-trust"):
        registry.SupplyRoute.model_validate(payload)


def test_tool_identity_and_nested_history_refuse():
    payload = copy.deepcopy(CASES[9][1]); payload["tool_id"] = OBSERVATION
    with pytest.raises(ValidationError, match="agentic-trust"):
        registry.ToolState.model_validate(payload)
    payload = {"class_posteriors": {"review": {**CASES[4][1], "evidence_refs": [RECEIPT]}}}
    with pytest.raises(ValidationError, match="agentic-trust"):
        registry.HistoricalPerformance.model_validate(payload)


def test_policy_reference_is_typed_not_authenticated():
    boundary = importlib.import_module("hapax.spine.agentic_trust_boundary")
    for value in ("sha256:abc", "digest:abc", "hash:abc", "run:abc", "bare", ":empty", "policy:",
                  "bad namespace:ref", OBSERVATION, RECEIPT, None):
        assert not boundary.is_syntactically_typed_policy_evidence_reference(value), value
    # Syntax alone does not authenticate arbitrary caller-supplied subjects.
    assert boundary.is_syntactically_typed_policy_evidence_reference("policy:unverified-claim")


def test_reserved_identity_exactness_and_nested_paths():
    b = importlib.import_module("hapax.spine.agentic_trust_boundary")
    assert b.normalize_supply_admission_identity(" ROUTE/" + OBSERVATION.upper() + " ") == OBSERVATION
    assert b.is_agentic_trust_evidence_surface_identity("surface/" + OBSERVATION)
    assert not b.is_agentic_trust_evidence_surface_identity(OBSERVATION + ".child")
    assert not b.is_agentic_trust_supply_evidence_reference(OBSERVATION + ".child")
    assert not b.is_agentic_trust_supply_evidence_reference("x" + OBSERVATION)
    with pytest.raises(TypeError):
        b.normalize_supply_admission_identity(None)
    payload = {"rows": [{"evidence_refs": [RECEIPT]}, {"nested": {"policy_ref": OBSERVATION}}],
               "description": OBSERVATION}
    assert b.agentic_trust_supply_evidence_paths(payload) == ("rows[0].evidence_refs", "rows[1].nested.policy_ref")


def test_refusal_preserves_existing_duration_and_evidence_guards():
    with pytest.raises(ValidationError):
        registry.FreshnessSurfaceEvidence()
    with pytest.raises(ValidationError):
        registry.ScoreConfidence.model_validate({**CASES[4][1], "evidence_refs": []})
    for name, payload, _ in (CASES[4], CASES[6], CASES[9]):
        with pytest.raises(ValidationError):
            getattr(registry, name).model_validate({**payload, "stale_after": "forever"})


def _mutation_controls():
    """Opt-in controls: break the checkout, observe assertion red, restore exact bytes, green.

    Never invoked by pytest collection. Requires an explicit source checkout and no
    concurrent test/editor activity. Uses the same package tests in fresh processes;
    collection errors are not credited as killed mutants. stdout is the evidence log.
    """
    import ast
    import hashlib
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    import tempfile

    root = Path(__file__).resolve().parents[1]
    paths = {"registry": root / "src/hapax/spine/platform_capability_registry.py",
             "trust": root / "src/hapax/spine/agentic_trust_boundary.py"}
    original = {key: path.read_bytes() for key, path in paths.items()}
    # Refuse accidentally mutating a checkout while testing another installation.
    assert Path(registry.__file__).resolve() == paths["registry"].resolve()
    tests = [str(Path(__file__).resolve()), str(root / "tests/test_obs0b_package_boundary.py")]

    def replace_body(key, name, expression, owner=None):
        source = original[key].decode()
        tree = ast.parse(source)
        scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner).body if owner else tree.body
        node = next(n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name)
        lines = source.splitlines(keepends=True)
        lines[node.body[0].lineno - 1:node.end_lineno] = [" " * node.body[0].col_offset + "return " + expression + "\n"]
        return "".join(lines).encode()

    controls = []
    for node in ast.parse(original["registry"]).body:
        if not isinstance(node, ast.ClassDef) or node.name not in {case[0] for case in CASES} | {"SupplyAuthority"}:
            continue
        for member in node.body:
            if isinstance(member, ast.FunctionDef) and member.decorator_list:
                controls.append((node.name + "." + member.name, "registry",
                                 replace_body("registry", member.name, "self", node.name)))
    controls.append(("task-class-allow-all", "registry",
                     replace_body("registry", "allows_task_class", "True", "SupplyAuthority")))
    controls.append(("policy-reference-allow-all", "trust",
                     replace_body("trust", "is_syntactically_typed_policy_evidence_reference", "True")))
    controls.append(("observation-reference-blind", "trust",
                     replace_body("trust", "is_agentic_trust_supply_evidence_reference", "False")))
    controls.append(("recursive-evidence-blind", "trust",
                     replace_body("trust", "agentic_trust_supply_evidence_paths", "()")))
    controls.append(("child-namespace-overreach", "trust", replace_body(
        "trust", "is_agentic_trust_evidence_surface_identity",
        "isinstance(value, str) and normalize_supply_admission_identity(value).startswith(AGENTIC_TRUST_EVIDENCE_SURFACE_ID)")))
    old = b'TASK_CLASS_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"'
    assert original["registry"].count(old) == 1
    controls.append(("task-class-grammar-open", "registry", original["registry"].replace(old, b'TASK_CLASS_PATTERN = r".*"')))
    old = b'class Platform(StrEnum):\n'
    assert original["registry"].count(old) == 1
    controls.append(("retired-platform-reintroduced", "registry",
                     original["registry"].replace(old, old + b'    GROK = "grok"\n')))

    def run(label):
        env = os.environ.copy(); env.pop("PYTHONPATH", None)
        # A fresh cache prevents a same-second source restore reading a spent pyc.
        with tempfile.TemporaryDirectory(prefix="obs0b-s01-pycache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=root,
                                    env=env, text=True, capture_output=True)
        output = result.stdout + result.stderr
        print(json.dumps({"phase": label, "exit": result.returncode,
                          "output_sha256": hashlib.sha256(output.encode()).hexdigest()}), flush=True)
        print(output, flush=True)
        return result.returncode

    assert run("unmodified-green") == 0
    for label, key, broken in controls:
        try:
            assert all(path.read_bytes() == original[k] for k, path in paths.items())
            paths[key].write_bytes(broken)
            print(json.dumps({"mutation": label, "path": str(paths[key].relative_to(root)),
                              "before_sha256": hashlib.sha256(original[key]).hexdigest(),
                              "broken_sha256": hashlib.sha256(broken).hexdigest()}), flush=True)
            assert run(label + ":red") == 1, "control must fail assertions, not collection"
        finally:
            paths[key].write_bytes(original[key])
        assert all(path.read_bytes() == original[k] for k, path in paths.items())
        assert run(label + ":restored-green") == 0
    print(json.dumps({"controls": len(controls), "all_killed_and_restored": True,
                      "restored_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in original.items()}}), flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["--mutation-controls"]:
        raise SystemExit("usage: test_obs0b_s01_parity.py --mutation-controls")
    _mutation_controls()
