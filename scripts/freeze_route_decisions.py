#!/usr/bin/env python3
"""Freeze the allowed route-decision projection without retaining source paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SELECTED_SOURCE_FIELDS = (
    "created_at",
    "task_id",
    "authority_allowed",
    "quota_freshness_green",
    "registry_freshness_green",
    "resource_freshness_green",
    "quota_evidence_refs",
    "resource_state_refs",
    "candidate_snapshot_ref",
    "demand_vector_ref",
    "stale_metadata",
)
TRANSFORM_VERSION = "route-decision-freeze-v1"
SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:+-]+$")


def _canonical_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


class _OpaqueTokens:
    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, str]] = {}

    def one(self, namespace: str, raw: str) -> str:
        values = self._tokens.setdefault(namespace, {})
        if raw not in values:
            values[raw] = f"{namespace}-{len(values) + 1:04d}"
        return values[raw]

    def many(self, namespace: str, raw: Iterable[str]) -> list[str]:
        return [self.one(namespace, value) for value in raw]

    def counts(self) -> dict[str, int]:
        return {key: len(value) for key, value in sorted(self._tokens.items())}


def _safe_code(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SAFE_CODE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a non-path code")
    return value


def freeze_rows(source: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return a canonical selected-field projection; perform no writes."""

    tokens = _OpaqueTokens()
    frozen: list[dict[str, Any]] = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            missing = sorted(set(SELECTED_SOURCE_FIELDS) - row.keys())
            if missing:
                raise ValueError(
                    f"row {line_number} missing selected fields: {missing}"
                )
            candidate = row["candidate_snapshot_ref"]
            demand = row["demand_vector_ref"]
            stale = []
            for item in row["stale_metadata"]:
                stale.append(
                    {
                        "effect": _safe_code(
                            item["effect"], field="stale_metadata.effect"
                        ),
                        "field": _safe_code(
                            item["field"], field="stale_metadata.field"
                        ),
                        "observed_at": (
                            _canonical_timestamp(item["observed_at"])
                            if item["observed_at"] is not None
                            else None
                        ),
                        "source_token": tokens.one("source", item["source_id"]),
                        "stale_after": item["stale_after"],
                    }
                )
            frozen.append(
                {
                    "authority_allowed": bool(row["authority_allowed"]),
                    "candidate_snapshot_ref": {"hash": candidate["hash"]},
                    "created_at": _canonical_timestamp(row["created_at"]),
                    "demand_vector_ref": {
                        "freshness_state": _safe_code(
                            demand["freshness_state"],
                            field="demand_vector_ref.freshness_state",
                        ),
                        "hash": demand["hash"],
                    },
                    "quota_evidence_refs": tokens.many(
                        "quota-ref", row["quota_evidence_refs"]
                    ),
                    "quota_freshness_green": bool(row["quota_freshness_green"]),
                    "registry_freshness_green": bool(row["registry_freshness_green"]),
                    "resource_freshness_green": bool(row["resource_freshness_green"]),
                    "resource_state_refs": tokens.many(
                        "resource-ref", row["resource_state_refs"]
                    ),
                    "stale_metadata": stale,
                    "task_token": tokens.one("task", row["task_id"]),
                }
            )
    return frozen, tokens.counts()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    rows, token_counts = freeze_rows(args.source)
    fixture_bytes = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )
    if b"/home/" in fixture_bytes:
        raise ValueError(
            "selected projection retained a path under /home; refusing to freeze"
        )
    source_bytes = args.source.read_bytes()
    projected_field_names = {
        "task_id": "task_token",
        **{field: field for field in SELECTED_SOURCE_FIELDS if field != "task_id"},
    }
    distinct_counts = {
        source_field: len(
            {
                json.dumps(row[projected_field], sort_keys=True, separators=(",", ":"))
                for row in rows
            }
        )
        for source_field, projected_field in projected_field_names.items()
    }
    manifest = {
        "adapter_version": "route-decision-cc-task-v1",
        "created_at_max": max(row["created_at"] for row in rows),
        "created_at_min": min(row["created_at"] for row in rows),
        "derived_sha256": _sha256(fixture_bytes),
        "fixture_kind": "historical_selected_field_projection",
        "parameters": {"duplicate_saturation": 5},
        "row_count": len(rows),
        "selected_source_fields": list(SELECTED_SOURCE_FIELDS),
        "selected_projection_distinct_counts": distinct_counts,
        "source_frontier": "complete frozen ledger through source_sha256",
        "source_sha256": _sha256(source_bytes),
        "token_counts": token_counts,
        "transform_version": TRANSFORM_VERSION,
    }
    args.fixture.parent.mkdir(parents=True, exist_ok=True)
    args.fixture.write_bytes(fixture_bytes)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
