"""Canonical serialization and content-address helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CID_PREFIX = "cidv0-local-sha256:"


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value deterministically."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cid_for_bytes(data: bytes) -> str:
    return f"{CID_PREFIX}{sha256_hex(data)}"


def digest_json(value: Any) -> str:
    return sha256_hex(canonical_json_bytes(value))


def content_id(kind: str, value: Any) -> str:
    return f"{kind}:{digest_json(value)}"


def digest_from_cid(cid: str) -> str:
    if not cid.startswith(CID_PREFIX):
        raise ValueError(f"unsupported CID format: {cid}")
    digest = cid[len(CID_PREFIX) :]
    if len(digest) != 64:
        raise ValueError(f"invalid sha256 digest length in CID: {cid}")
    return digest
