"""Synthetic receipt parsing only; metadata never grants route authority."""

import json
from datetime import timedelta

import pytest
from pydantic import ValidationError
from test_obs0b_s04_parity import NOW, payload

from hapax.spine import platform_capability_receipts as r

E, D = "entitlement_metadata", "delta_resolution"
LATER = NOW + timedelta(hours=1)


def fields():
    return {
        E: {
            "provider": "synthetic", "product": "included", "auth_origin": "owner-export",
            "tenant_ref": "tenant:" + "a" * 64, "cohort": "test", "pool_id": "included",
            "policy_digest": "b" * 64, "observed_at": NOW, "fresh_until": LATER,
            "supported_knobs": {"model": ["synthetic"]}, "included_only": True,
            "payg_fallback_allowed": False, "evidence_refs": ["test:policy"],
        },
        D: {
            "delta_id": "delta-test", "surface_id": "surface-test", "route_id": "agy.review.direct",
            "descriptor_signature": "c" * 64, "configuration_digest": "d" * 64,
            "disposition": "admitted", "admission_refs": ["test:admission"],
            "observed_at": NOW, "fresh_until": LATER, "revoked": False,
        },
    }


def receipt(**extra):
    value = payload()
    value.update(platform="agy", routes=["agy.review.direct"], **extra)
    return value


def parse(value):
    return r.PlatformCapabilityReceipt.model_validate(value, context={"now": NOW})


@pytest.mark.parametrize("keys", [(E,), (D,), (E, D)])
def test_new_fields_and_loader(keys, tmp_path):
    value = receipt(**{k: fields()[k] for k in keys})
    parsed = parse(value)
    for key in keys:
        assert getattr(parsed, key).model_dump(mode="json", exclude_unset=True) == json.loads(
            json.dumps(value[key], default=lambda t: t.isoformat().replace("+00:00", "Z"))
        )
    path = tmp_path / "agy.json"
    path.write_text(parsed.model_dump_json())
    assert r.load_platform_capability_receipt(path) == parsed
    assert r.load_platform_capability_receipts(tmp_path, now=NOW) == {"agy": parsed}
    assert parsed.capability.status.value == "blocked"
    assert parsed.quota.reason_codes == ["quota_telemetry_unknown"]


def test_legacy_defaults():
    assert parse(receipt()).model_dump() == parse(receipt(**{E: None, D: None})).model_dump()


@pytest.mark.parametrize("level", [None, E, D])
def test_unknown_fields_refused(level):
    value = receipt(**fields())
    (value if level is None else value[level])["unrecognized"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        parse(value)


@pytest.mark.parametrize("key,field,bad", [
    (E, "provider", "UPPER"), (E, "tenant_ref", "tenant:short"),
    (E, "policy_digest", "bad"), (E, "supported_knobs", {"bad key": ["x"]}),
    (E, "included_only", 1), (E, "payg_fallback_allowed", 0),
    (E, "observed_at", LATER), (E, "fresh_until", NOW),
    (E, "observed_at", NOW.replace(tzinfo=None)),
    (E, "credit_expires_at", NOW.replace(tzinfo=None)),
    (E, "evidence_refs", ["plain"]), (E, "evidence_refs", []),
    (E, "evidence_refs", ["test:x@y"]), (E, "evidence_refs", ["/private"]),
    (D, "delta_id", " "), (D, "surface_id", " surface"),
    (D, "route_id", "route "), (D, "descriptor_signature", "bad"),
    (D, "configuration_digest", "bad"), (D, "disposition", "unknown"),
    (D, "revoked", 0), (D, "fresh_until", NOW),
    (D, "observed_at", NOW.replace(tzinfo=None)),
    (D, "admission_refs", ["plain"]), (D, "admission_refs", []),
])
def test_invalid_metadata_refused(key, field, bad):
    value = fields()
    value[key][field] = bad
    with pytest.raises(ValidationError):
        parse(receipt(**value))


@pytest.mark.parametrize("revoked,clock,current", [
    (False, NOW - timedelta(microseconds=1), False), (False, NOW, True),
    (False, LATER - timedelta(microseconds=1), True), (False, LATER, False),
    (True, NOW, False),
])
def test_resolution_currency_and_immutability(revoked, clock, current):
    value = fields()
    value[D]["revoked"] = revoked
    resolution = parse(receipt(**value)).delta_resolution
    assert resolution.is_current(clock) is current
    with pytest.raises(ValidationError, match="frozen_instance"):
        resolution.revoked = not revoked


@pytest.mark.parametrize("ref", ["/private", "test:x@y"])
def test_private_ref_remediation(ref):
    from hapax.spine.quota_spend_ledger import _reject_private_or_identity_refs

    with pytest.raises(ValueError, match="next action: supply a repo-relative or symbolic reference"):
        _reject_private_or_identity_refs([ref], "entitlement")


def test_future_entitlement_refused_with_ordered_expiry():
    value = fields()
    value[E].update(observed_at=LATER, fresh_until=LATER + timedelta(hours=1))
    with pytest.raises(ValidationError, match="entitlement clock invalid"):
        parse(receipt(**value))
