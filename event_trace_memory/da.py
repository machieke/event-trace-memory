"""Filesystem-backed data availability store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from event_trace_memory.canonical import (
    canonical_json_bytes,
    cid_for_bytes,
    digest_from_cid,
    sha256_hex,
)


class FileDA:
    """Small content-addressed store used by the reference implementation."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.objects_dir = self.root / "objects"
        self.manifests_dir = self.root / "manifests"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, data: bytes, *, codec: str = "raw") -> str:
        cid = cid_for_bytes(data)
        digest = digest_from_cid(cid)
        object_path = self.objects_dir / digest
        if not object_path.exists():
            object_path.write_bytes(data)
        manifest = {
            "cid": cid,
            "codec": codec,
            "size": len(data),
            "digest": f"sha256:{digest}",
        }
        manifest_path = self.manifests_dir / f"{digest}.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        return cid

    def put_json(self, value: Any, *, codec: str = "dag-json") -> str:
        return self.put_bytes(canonical_json_bytes(value), codec=codec)

    def get_bytes(self, cid: str) -> bytes:
        digest = digest_from_cid(cid)
        object_path = self.objects_dir / digest
        if not object_path.exists():
            raise KeyError(cid)
        data = object_path.read_bytes()
        actual = sha256_hex(data)
        if actual != digest:
            raise ValueError(f"DA object digest mismatch for {cid}: {actual}")
        return data

    def get_json(self, cid: str) -> Any:
        return json.loads(self.get_bytes(cid).decode("utf-8"))

    def has(self, cid: str) -> bool:
        return (self.objects_dir / digest_from_cid(cid)).exists()

    def stat(self, cid: str) -> dict[str, Any]:
        digest = digest_from_cid(cid)
        manifest_path = self.manifests_dir / f"{digest}.json"
        if not manifest_path.exists():
            raise KeyError(cid)
        return json.loads(manifest_path.read_text(encoding="utf-8"))
