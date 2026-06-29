"""Data availability store backends."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from event_trace_memory.canonical import (
    canonical_json_bytes,
    cid_for_bytes,
    digest_from_cid,
    sha256_hex,
)


class DAStore(Protocol):
    def put_bytes(self, data: bytes, *, codec: str = "raw") -> str:
        ...

    def put_json(self, value: Any, *, codec: str = "dag-json") -> str:
        ...

    def get_bytes(self, cid: str) -> bytes:
        ...

    def get_json(self, cid: str) -> Any:
        ...

    def has(self, cid: str) -> bool:
        ...

    def stat(self, cid: str) -> dict[str, Any]:
        ...

    def verify(self, cid: str) -> dict[str, Any]:
        ...


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
        manifest = _manifest(cid, codec, data)
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

    def verify(self, cid: str) -> dict[str, Any]:
        try:
            manifest = self.stat(cid)
            data = self.get_bytes(cid)
        except Exception as exc:
            return {"ok": False, "cid": cid, "error": str(exc)}
        return _verify_manifest(cid, manifest, data)


class MemoryDA:
    """In-memory DA backend with the same CID and manifest semantics as FileDA."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.manifests: dict[str, dict[str, Any]] = {}

    def put_bytes(self, data: bytes, *, codec: str = "raw") -> str:
        cid = cid_for_bytes(data)
        digest = digest_from_cid(cid)
        self.objects.setdefault(digest, data)
        self.manifests.setdefault(digest, _manifest(cid, codec, data))
        return cid

    def put_json(self, value: Any, *, codec: str = "dag-json") -> str:
        return self.put_bytes(canonical_json_bytes(value), codec=codec)

    def get_bytes(self, cid: str) -> bytes:
        digest = digest_from_cid(cid)
        if digest not in self.objects:
            raise KeyError(cid)
        data = self.objects[digest]
        actual = sha256_hex(data)
        if actual != digest:
            raise ValueError(f"DA object digest mismatch for {cid}: {actual}")
        return data

    def get_json(self, cid: str) -> Any:
        return json.loads(self.get_bytes(cid).decode("utf-8"))

    def has(self, cid: str) -> bool:
        return digest_from_cid(cid) in self.objects

    def stat(self, cid: str) -> dict[str, Any]:
        digest = digest_from_cid(cid)
        if digest not in self.manifests:
            raise KeyError(cid)
        return dict(self.manifests[digest])

    def verify(self, cid: str) -> dict[str, Any]:
        try:
            manifest = self.stat(cid)
            data = self.get_bytes(cid)
        except Exception as exc:
            return {"ok": False, "cid": cid, "error": str(exc)}
        return _verify_manifest(cid, manifest, data)


def _manifest(cid: str, codec: str, data: bytes) -> dict[str, Any]:
    digest = digest_from_cid(cid)
    return {
        "cid": cid,
        "codec": codec,
        "size": len(data),
        "digest": f"sha256:{digest}",
    }


def _verify_manifest(cid: str, manifest: dict[str, Any], data: bytes) -> dict[str, Any]:
    digest = digest_from_cid(cid)
    actual_digest = sha256_hex(data)
    expected = _manifest(cid, manifest.get("codec", "unknown"), data)
    checks = {
        "cid": manifest.get("cid") == cid,
        "digest": actual_digest == digest and manifest.get("digest") == f"sha256:{digest}",
        "size": manifest.get("size") == len(data),
    }
    ok = all(checks.values())
    result = {
        "ok": ok,
        "cid": cid,
        "codec": manifest.get("codec"),
        "size": len(data),
        "digest": f"sha256:{actual_digest}",
        "checks": checks,
    }
    if not ok:
        result["expected"] = expected
        result["actualManifest"] = manifest
    return result
