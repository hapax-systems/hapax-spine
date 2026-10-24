"""S07a offline Claude admission locator readers, Council cef55b52 parity.

REF and HASHED_IGNORED retain the committed test fixture bytes from
tests/shared/test_quota_spend_ledger.py:CLAUDE_ADMISSION_EVIDENCE_REF and
CLAUDE_SAFE_HASHED_IGNORED_EVIDENCE_REF at
cef55b5216574f7eb80fd42c887c58e83f7cace0. The writer's composition boundary is
scripts/hapax-quota-telemetry-writer:1902. Other locators are synthetic negatives.
These readers qualify evidence, not provider availability or a spend grant.
S07b owns the remaining consumer wiring; no credential or live receipt is read.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hapax.spine import quota_spend_ledger as q
from test_obs0b_s05_parity import snapshot

NOW = datetime(2026, 7, 8, 14, 5, tzinfo=UTC)
LABEL = "claude-subscription-quota-admission-20260708t140000z.yaml"
WITNESS = "claude-subscription-headroom-observed-20260708t1400z"
REF = (
    "relay-receipt:claude-subscription-quota-admission-20260708t140000z.yaml:"
    "witness:claude-subscription-headroom-observed-20260708t1400z:"
    "observation:subscription_quota_headroom_observed:"
    "route_id:claude.headless.full:"
    "observed_at:2026-07-08T14:00:00Z:"
    "fresh_until:2026-07-08T14:15:00Z:"
    "account-live-quota:observed"
)
HASH_LABEL = "unsafe-receipt-name-sha256:0123456789abcdef"
HASHED_IGNORED = (
    "relay-receipt:unsafe-receipt-name-sha256:0123456789abcdef:"
    "ignored:receipt-name-names-billing-or-account-identifier"
)
ROUTES = ["claude.headless.full", "claude.review.opus", "claude.interactive.full"]


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("locator reader attempted network, credential or subprocess action")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def quota(refs, *, route="claude.headless.full", state="fresh"):
    return q.QuotaSnapshot.model_validate(snapshot(
        route_id=route, provider="claude", captured_at=NOW,
        fresh_until=NOW + timedelta(minutes=5), subscription_quota_state=state,
        evidence_refs=refs,
    ))


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("operator", [False, True])
@pytest.mark.parametrize("seconds", [False, True])
def test_producer_shaped_admission(route, operator, seconds):
    ref = REF.replace("claude.headless.full", route)
    if operator:
        ref = ref.replace("subscription_quota_headroom_observed",
                          "operator_confirmed_subscription_headroom")
        ref = ref.replace("claude-subscription-headroom-observed-",
                          "claude-operator-confirmed-subscription-headroom-")
    if seconds:
        ref = ref.replace("20260708t1400z", "20260708t140000z")
    assert q._claude_evidence_receipt_label(ref) == LABEL
    assert q._has_safe_claude_admission_receipt_label(ref)
    assert q._has_safe_claude_admission_witness(ref)
    assert q._is_claude_admission_evidence_ref(ref, route_id=route, now=NOW)
    assert q._is_claude_admission_evidence_ref(ref)
    assert not q._is_untrusted_claude_admission_ref_for_evidence(ref)
    snap = quota([ref], route=route)
    before = snap.model_dump_json()
    assert not q._subscription_quota_missing_current_claude_receipt(snap, now=NOW)
    assert snap.model_dump_json() == before


@pytest.mark.parametrize("minutes,valid", [(-1, False), (0, True), (14, True), (15, False), (16, False)])
def test_live_interval(minutes, valid):
    now = datetime(2026, 7, 8, 14, tzinfo=UTC) + timedelta(minutes=minutes)
    assert q._is_claude_admission_evidence_ref(REF, now=now) is valid
    assert q._subscription_quota_missing_current_claude_receipt(quota([REF]), now=now) is not valid


@pytest.mark.parametrize("fresh", ["2026-07-08T14:00:00Z", "2026-07-08T13:59:59Z"])
def test_nonpositive_interval_refused_even_without_now(fresh):
    ref = REF.replace("2026-07-08T14:15:00Z", fresh)
    assert not q._is_claude_admission_evidence_ref(ref)


@pytest.mark.parametrize("old,new", [
    ("2026-07-08T14:00:00Z", "2026-02-30T14:00:00Z"),
    ("2026-07-08T14:15:00Z", "2026-07-08T24:15:00Z"),
    ("2026-07-08T14:00:00Z", "2026-07-08T14:00:00"),
    ("2026-07-08T14:15:00Z", "2026-07-08T14:15:00+00:00"),
    ("subscription_quota_headroom_observed", "native_execution_success_observed"),
    ("subscription_quota_headroom_observed", "session_present"),
    ("claude.headless.full", "codex.headless.full"),
    ("claude.headless.full", "claude.review.sonnet"),
    (":account-live-quota:observed", ""),
    (":account-live-quota:observed", ":account-live-quota:unobserved"),
    (":account-live-quota:observed", ":lane-present:observed"),
    ("route_id:", "billingcus123:route_id:"),
    ("route_id:", "route_id:claude.review.opus:route_id:"),
    ("observed_at:", "observed_at:2026-07-08T14:00:00Z:observed_at:"),
])
def test_composite_field_refusal(old, new):
    ref = REF.replace(old, new)
    assert not q._is_claude_admission_evidence_ref(ref, now=NOW)
    assert q._subscription_quota_missing_current_claude_receipt(quota([ref]), now=NOW)


@pytest.mark.parametrize("ref", ["prefix:" + REF, REF + ":suffix", REF + "\n", REF.upper()])
def test_entire_composite_must_match(ref):
    assert not q._is_claude_admission_evidence_ref(ref, now=NOW)


def test_route_binding_and_normalization():
    assert not q._is_claude_admission_evidence_ref(REF, route_id="claude.review.opus", now=NOW)
    assert q._subscription_quota_missing_current_claude_receipt(
        quota([REF], route="claude.review.opus"), now=NOW)
    assert not q._subscription_quota_missing_current_claude_receipt(
        quota([REF], route=" claude/headless/full "), now=NOW)
    assert q._subscription_quota_missing_current_claude_receipt(
        quota([HASHED_IGNORED], route=" claude/headless/full "), now=NOW)


UNSAFE_LABEL_PARTS = [
    "api-key", "bearer", "secret", "token", "sk-fixture", "a" * 32,
    "billing", "customer", "account", "invoice", "payment", "subscription-id-123",
    "cus_123", "acct123", "in.123", "ch-123", "sub+123",
    "hapax-claude-eta", "session-present", "lane-present", "lane-exists",
    "tmux", "sessions2", "dev25", "eta2", "cx-teal", "vbe-2",
]


@pytest.mark.parametrize("token", UNSAFE_LABEL_PARTS)
def test_unsafe_receipt_labels(token):
    ref = REF.replace(LABEL, "claude-subscription-quota-admission-" + token + ".yaml")
    assert not q._has_safe_claude_admission_receipt_label(ref)
    assert not q._is_claude_admission_evidence_ref(ref, now=NOW)
    assert q._is_untrusted_claude_admission_ref_for_evidence(ref)
    ignored = ref.split(":witness:", 1)[0] + ":ignored:expired"
    assert not q._is_safe_claude_ignored_evidence_ref(ignored)


@pytest.mark.parametrize("label", ["other.yaml", "/private/admission.yaml", "../" + LABEL,
                                  HASH_LABEL, LABEL.upper(), ""])
def test_receipt_label_shape_refused(label):
    ref = REF.replace(LABEL, label)
    assert not q._has_safe_claude_admission_receipt_label(ref)
    assert not q._is_claude_admission_evidence_ref(ref)


@pytest.mark.parametrize("witness", [
    "", "sk-fixture", "opaque-safe-but-unrecognized", "hapax-claude-eta-present-20260708",
    "eta", "session-present", "cus_123", "/private/path", "a" * 240,
    "claude-subscription-headroom-observed-20260708", WITNESS.upper(),
    WITNESS + ":observation:x:witness:" + WITNESS,
    ":observation:x:witness:" + WITNESS,
    WITNESS + ":observation:x:witness:",
])
def test_witness_refusal(witness):
    ref = REF.replace(WITNESS, witness)
    # The raw witness helper only counts nonempty witness/observation pairs.
    # Empty/extra pairs are refused by the full composite grammar as well.
    if witness not in {":observation:x:witness:" + WITNESS,
                       WITNESS + ":observation:x:witness:"}:
        assert not q._has_safe_claude_admission_witness(ref)
    assert not q._is_claude_admission_evidence_ref(ref, now=NOW)
    assert q._subscription_quota_missing_current_claude_receipt(quota([ref]), now=NOW)


@pytest.mark.parametrize("ref,label", [
    (REF, LABEL), (HASHED_IGNORED, HASH_LABEL),
    ("not-relay:" + LABEL + ":witness:x", None),
    ("foreign:witness:x", None),
    ("relay-receipt:" + LABEL, None),
    ("relay-receipt:" + LABEL + ":other:x", None),
    ("relay-receipt:unsafe-receipt-name-sha256:0123456789abcdef", None),
    ("relay-receipt:unsafe-receipt-name-sha256", None),
])
def test_label_extraction_is_separate_from_qualification(ref, label):
    assert q._claude_evidence_receipt_label(ref) == label


@pytest.mark.parametrize("label", [LABEL, HASH_LABEL])
@pytest.mark.parametrize("reason", [
    "expired", "receipt-name-names-billing-or-account-identifier", "missing-account-live-quota",
])
def test_sanitized_ignored_evidence_is_not_admission(label, reason):
    ref = f"relay-receipt:{label}:ignored:{reason}"
    assert q._is_safe_claude_ignored_reason(reason)
    assert q._is_safe_claude_ignored_evidence_ref(ref)
    assert not q._is_untrusted_claude_admission_ref_for_evidence(ref)
    assert not q._is_claude_admission_evidence_ref(ref)
    assert q._subscription_quota_missing_current_claude_receipt(quota([ref]), now=NOW)


@pytest.mark.parametrize("reason", [
    "", "X", "unsafe:detail", "a" * 121, "reason_with_underscore", "expired\n",
    "secret", "api-key", "customer-cus-123", "billingcus123", "subscriptionid123",
    "session-present", "lane-exists", "dev25", "eta", "cx-teal", "vbe-2",
])
def test_unsafe_ignored_reasons(reason):
    assert not q._is_safe_claude_ignored_reason(reason)
    for label in (LABEL, HASH_LABEL):
        ref = f"relay-receipt:{label}:ignored:{reason}"
        assert not q._is_safe_claude_ignored_evidence_ref(ref)
        assert q._is_untrusted_claude_admission_ref_for_evidence(ref)


@pytest.mark.parametrize("ref", [
    "relay-receipt:unsafe-receipt-name-sha256:0123456789abcde:ignored:expired",
    "relay-receipt:unsafe-receipt-name-sha256:0123456789abcdef0:ignored:expired",
    "relay-receipt:unsafe-receipt-name-sha256:0123456789abcdeF:ignored:expired",
    "relay-receipt:other.yaml:ignored:expired", "other:ignored:expired", REF,
])
def test_ignored_label_boundary(ref):
    assert not q._is_safe_claude_ignored_evidence_ref(ref)


@pytest.mark.parametrize("ref,untrusted", [
    ("fixture:unrelated-observation", False), ("relay-receipt:other.yaml:ignored:expired", False),
    ("outside:witness:unknown:observation:unknown", False),
    ("claude-billing-cus_123-lane-eta-observed", True), ("customer:cus_123", True),
    ("lane-present", True), ("relay-receipt:claude-subscription-quota-admission", True),
    ("relay-receipt:unsafe-receipt-name-sha256:bad", True),
    ("relay-receipt:other.yaml:witness:unknown:observation:unknown", True),
])
def test_untrusted_classification_preserves_unrelated_evidence(ref, untrusted):
    assert q._is_untrusted_claude_admission_ref_for_evidence(ref) is untrusted


@pytest.mark.parametrize("route", ROUTES + ["codex.headless.full"])
@pytest.mark.parametrize("state", ["fresh", "stale", "unknown", "exhausted"])
def test_receipt_requirement_scope(route, state):
    snap = quota([HASHED_IGNORED], route=route, state=state)
    before = snap.model_dump_json()
    assert q._subscription_quota_missing_current_claude_receipt(snap, now=NOW) is (
        state == "fresh" and route in ROUTES)
    assert snap.model_dump_json() == before


def test_missing_admission_and_mixed_evidence():
    assert q._subscription_quota_missing_current_claude_receipt(quota(["fixture:no-admission"]), now=NOW)
    refs = [HASHED_IGNORED, REF.replace("claude.headless.full", "claude.review.opus"), REF]
    assert not q._subscription_quota_missing_current_claude_receipt(quota(refs), now=NOW)


def _mutations():
    """Break observable reader contracts; restore exact bytes after each control.

    Redundant witness secret/billing/lane filters behind the strict allowlist
    are not claimed as independently necessary guards. Their label and ignored
    reason counterparts are independently exercised. Prefix anchoring is shared
    by two patterns, so its control removes both anchors. No provider action runs.
    """
    import ast
    import hashlib
    import json
    import os
    import subprocess
    import sys
    import tempfile

    path = Path(__file__).resolve().parents[1] / "src/hapax/spine/quota_spend_ledger.py"
    assert Path(q.__file__).resolve() == path
    original = path.read_bytes()
    source = original.decode()
    nodes = {}
    for node in ast.parse(source).body:
        name = node.name if isinstance(node, ast.FunctionDef) else (
            node.targets[0].id if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name) else None)
        if name:
            nodes[name] = node
    lines = source.splitlines(keepends=True)
    controls = []

    def replace(name, old, new, label, *, combine=False):
        node = nodes[name]
        block = "".join(lines[node.lineno - 1:node.end_lineno])
        assert block.count(old) == 1, (name, old)
        altered = block.replace(old, new)
        if combine:
            prior = controls.pop()[1]
            assert prior.count(block.encode()) == 1
            mutant = prior.replace(block.encode(), altered.encode(), 1)
        else:
            mutant = ("".join(lines[:node.lineno - 1]) + altered + "".join(lines[node.end_lineno:])).encode()
        controls.append((label, mutant))

    admission = "_is_claude_admission_evidence_ref"
    for old, new, label in [
        ('match.group("route_id") != route_id', "False", "route-binding"),
        ("except ValueError:\n        return False", "except ValueError:\n        return True", "invalid-calendar"),
        ("observed_at < fresh_until", "True", "positive-interval"),
        ("observed_at <= now < fresh_until", "now < fresh_until", "future-observation"),
        ("observed_at <= now < fresh_until", "observed_at <= now", "expiry-exclusive"),
        ("_has_safe_claude_admission_receipt_label(ref)", "True", "composite-label-check"),
    ]:
        replace(admission, old, new, label)
    composite = "CLAUDE_ADMISSION_COMPOSITE_REF_RE"
    replace(composite, r"\Arelay-receipt:", r".*relay-receipt:", "composite-prefix")
    replace("CLAUDE_ADMISSION_RECEIPT_LABEL_RE", r"\Arelay-receipt:", r".*relay-receipt:",
            "composite-prefix-both-anchors", combine=True)
    replace(composite, r"\Z", ".*", "composite-suffix")
    replace("CLAUDE_ADMISSION_ACCOUNT_LIVE_QUOTA_SUFFIX", '":account-live-quota:observed"',
            '""', "account-live-observation-required")
    replace("CLAUDE_ADMISSION_OBSERVATIONS", '"subscription_quota_headroom_observed",',
            '"subscription_quota_headroom_observed", "native_execution_success_observed",',
            "execution-is-not-quota")
    replace(composite, r"claude\.(?:headless\.full|review\.opus|interactive\.full)",
            r"[a-z.]+", "declared-claude-routes-only")

    label_reader = "_has_safe_claude_admission_receipt_label"
    replace(label_reader, "if label_match is None:\n        return False",
            "if label_match is None:\n        return True", "receipt-label-shape")
    for pattern in ("SECRETISH", "BILLINGISH", "LANE_PRESENCE"):
        guard = f"CLAUDE_ADMISSION_{pattern}_RE.search(label_stem) is None"
        replace(label_reader, guard, "True", "label-" + pattern)
        replace("_is_safe_claude_ignored_evidence_ref", guard, "True", "ignored-label-" + pattern)

    witness_reader = "_has_safe_claude_admission_witness"
    replace(witness_reader, "len(witness_matches) != 1", "not witness_matches", "duplicate-witness")
    replace(witness_reader, "CLAUDE_ADMISSION_WITNESS_ALLOWLIST_RE.fullmatch(witness) is not None",
            "True", "witness-allowlist")

    ignored = "_is_safe_claude_ignored_evidence_ref"
    for old, new, label in [
        ('if ":ignored:" not in ref:\n        return False',
         'if ":ignored:" not in ref:\n        return True', "ignored-marker"),
        ("if label is None:\n        return False", "if label is None:\n        return True", "ignored-label-present"),
        ("if not _is_safe_claude_ignored_reason(ignored_reason):", "if False:", "ignored-reason-required"),
        ('re.fullmatch(r"unsafe-receipt-name-sha256:[0-9a-f]{16}", label) is not None',
         "True", "sanitized-hash-shape"),
        ('CLAUDE_ADMISSION_RECEIPT_LABEL_RE.match(f"relay-receipt:{label}:witness:") is not None',
         "True", "ignored-receipt-shape"),
    ]:
        replace(ignored, old, new, label)
    for expr, label in [
        ("CLAUDE_ADMISSION_IGNORED_REASON_RE.fullmatch(reason) is not None", "ignored-reason-grammar"),
        ("CLAUDE_ADMISSION_SECRETISH_RE.search(reason) is None", "ignored-reason-secret"),
        ("CLAUDE_ADMISSION_IGNORED_UNSAFE_DETAIL_RE.search(reason) is None", "ignored-reason-detail"),
    ]:
        replace("_is_safe_claude_ignored_reason", expr, "True", label)

    untrusted = "_is_untrusted_claude_admission_ref_for_evidence"
    replace(untrusted, "_is_claude_admission_evidence_ref(ref) or _is_safe_claude_ignored_evidence_ref(ref)",
            "False", "safe-evidence-precedence")
    for expr, label in [
        ("CLAUDE_ADMISSION_BILLINGISH_RE.search(ref) is not None", "plain-billing"),
        ("CLAUDE_ADMISSION_LANE_PRESENCE_RE.search(ref) is not None", "plain-lane"),
        ('not ref.startswith("relay-receipt:")', "relay-prefix"),
        ('"claude-subscription-quota-admission" in ref', "malformed-admission"),
        ('"unsafe-receipt-name-sha256:" in ref', "malformed-hashed-label"),
        ("bool(CLAUDE_ADMISSION_WITNESS_REF_RE.search(ref))", "unknown-witness"),
    ]:
        replace(untrusted, expr, "False", label)
    extractor = "_claude_evidence_receipt_label"
    replace(extractor, 'not ref.startswith("relay-receipt:")', "False", "label-prefix")
    replace(extractor, 'remainder.startswith("witness:")', "False", "witness-label-extraction")
    replace(extractor, 'remainder.startswith("ignored:")', "False", "ignored-label-extraction")

    requirement = "_subscription_quota_missing_current_claude_receipt"
    replace(requirement, "snapshot.subscription_quota_state is SubscriptionQuotaState.FRESH",
            "True", "requirement-fresh-scope")
    replace(requirement, "route_id in CLAUDE_RECEIPT_BOUNDED_SUBSCRIPTION_ROUTES",
            "True", "requirement-route-scope")
    replace(requirement, "not any(", "any(", "requires-positive-current-receipt")
    replace(requirement, "_normalize_route_id(snapshot.route_id)", "snapshot.route_id", "normalized-route")
    for route in ROUTES:
        replace("CLAUDE_RECEIPT_BOUNDED_SUBSCRIPTION_ROUTES", '"' + route + '"',
                '"undeclared"', "bounded-" + route)

    def run(label):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="s07a-pycache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(Path(__file__).resolve())],
                                    cwd=path.parents[3], env=env, capture_output=True, text=True)
        output = result.stdout + result.stderr
        print(json.dumps({"phase": label, "exit": result.returncode}), flush=True)
        print(output, flush=True)
        if label.endswith(":red"):
            assert "AssertionError" in output, "control must produce a behavioral assertion failure"
        return result.returncode

    assert run("original-green") == 0
    for label, mutant in controls:
        try:
            assert path.read_bytes() == original and mutant != original
            print(json.dumps({"control": label, "mutant_sha256": hashlib.sha256(mutant).hexdigest()}), flush=True)
            path.write_bytes(mutant)
            assert run(label + ":red") == 1
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original and run(label + ":restored-green") == 0
    print(json.dumps({"controls": len(controls), "all_killed_and_restored": True,
                      "restored_sha256": hashlib.sha256(original).hexdigest(),
                      "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}), flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--mutation-controls"]:
        _mutations()
    else:
        raise SystemExit("use --mutation-controls")
