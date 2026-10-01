"""File storage. `local` serves files from FastAPI (/files/...), fine for a
single VM. `s3` works with AWS S3, Cloudflare R2 (recommended: free egress,
10 GB free), Backblaze B2 or MinIO - all speak the S3 API."""
from __future__ import annotations

import shutil
from pathlib import Path

from .config import get_settings


class LocalStorage:
    def __init__(self):
        s = get_settings()
        self.root = s.data_dir / "songs"
        self.base = s.public_base_url.rstrip("/") + "/files"

    def put(self, local: Path, key: str, content_type: str) -> str:
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        if local.resolve() != dest.resolve():
            shutil.copyfile(local, dest)
        return f"{self.base}/{key}"

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()


class S3Storage:
    def __init__(self):
        import boto3
        s = get_settings()
        self.s = s
        self.client = boto3.client(
            "s3", endpoint_url=s.s3_endpoint_url or None, region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key)

    def put(self, local: Path, key: str, content_type: str) -> str:
        self.client.upload_file(str(local), self.s.s3_bucket, key, ExtraArgs={
            "ContentType": content_type, "CacheControl": "public, max-age=31536000, immutable"})
        if self.s.s3_public_base_url:
            return f"{self.s.s3_public_base_url.rstrip('/')}/{key}"
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.s.s3_bucket, "Key": key}, ExpiresIn=self.s.signed_url_ttl_s)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.s.s3_bucket, Key=key)
            return True
        except Exception:
            return False


_STORAGE = None


def storage():
    global _STORAGE
    if _STORAGE is None:
        _STORAGE = S3Storage() if get_settings().storage_backend == "s3" else LocalStorage()
    return _STORAGE
