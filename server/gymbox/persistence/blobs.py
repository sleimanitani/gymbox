"""Skeleton-blob storage (architecture.md §8, §13).

`local://` is fully implemented for the reference box. `s3://` and `gcs://` are
structured stubs the integrator wires to their own credentials/SDK.

The blob is immutable once first stored for a given session: a re-upload does
not replace it (architecture.md §8).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse


class BlobStore:
    """Base interface. `put` returns (storage_url, sha256, byte_size)."""

    async def put(self, key: str, data: bytes) -> tuple[str, str, int]:  # pragma: no cover
        raise NotImplementedError

    async def get(self, storage_url: str) -> bytes:  # pragma: no cover
        raise NotImplementedError


class LocalBlobStore(BlobStore):
    """Stores blobs on the local filesystem. Reference-box default."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, data: bytes) -> tuple[str, str, int]:
        sha = hashlib.sha256(data).hexdigest()
        dest = self.root / f"{key}.bin"
        dest.write_bytes(data)
        return (f"local://{dest}", sha, len(data))

    async def get(self, storage_url: str) -> bytes:
        path = storage_url.removeprefix("local://")
        return Path(path).read_bytes()


class S3BlobStore(BlobStore):
    """S3-compatible storage. ROADMAP Step 9 / integrator-configured.

    Stub: wire to boto3 / aioboto3 with the integrator's credentials.
    """

    def __init__(self, bucket: str, prefix: str) -> None:
        self.bucket = bucket
        self.prefix = prefix

    async def put(self, key: str, data: bytes) -> tuple[str, str, int]:
        raise NotImplementedError(
            "S3BlobStore.put — wire to aioboto3. ROADMAP: blob storage backends."
        )

    async def get(self, storage_url: str) -> bytes:
        raise NotImplementedError("S3BlobStore.get — wire to aioboto3.")


class GCSBlobStore(BlobStore):
    """GCS storage. ROADMAP Step 9 / integrator-configured. Stub."""

    def __init__(self, bucket: str, prefix: str) -> None:
        self.bucket = bucket
        self.prefix = prefix

    async def put(self, key: str, data: bytes) -> tuple[str, str, int]:
        raise NotImplementedError("GCSBlobStore.put — wire to google-cloud-storage.")

    async def get(self, storage_url: str) -> bytes:
        raise NotImplementedError("GCSBlobStore.get — wire to google-cloud-storage.")


def make_blob_store(blob_storage_url: str) -> BlobStore:
    """Construct a BlobStore from a Config.blob_storage_url scheme."""
    parsed = urlparse(blob_storage_url)
    scheme = parsed.scheme
    if scheme == "local":
        # local://./data/blobs  -> netloc="" path uses the rest
        root = blob_storage_url.removeprefix("local://")
        return LocalBlobStore(root or "./data/blobs")
    if scheme == "s3":
        return S3BlobStore(bucket=parsed.netloc, prefix=parsed.path.lstrip("/"))
    if scheme == "gcs":
        return GCSBlobStore(bucket=parsed.netloc, prefix=parsed.path.lstrip("/"))
    raise ValueError(f"unsupported blob_storage_url scheme: {scheme!r}")
