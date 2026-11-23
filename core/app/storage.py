"""Private file storage: local directory or any S3-compatible bucket (Hetzner, Backblaze...)."""
from pathlib import Path

from .config import get_settings


def _s3():
    import boto3  # optional dependency (extra "s3")
    s = get_settings()
    return boto3.client("s3", endpoint_url=s.s3_endpoint or None, region_name=s.s3_region,
                        aws_access_key_id=s.s3_access_key, aws_secret_access_key=s.s3_secret_key)


def _path(key: str) -> Path:
    root = Path(get_settings().storage_dir).resolve()
    p = (root / key).resolve()
    if root not in p.parents:
        raise ValueError("invalid storage key")
    return p


def put(key: str, data: bytes) -> None:
    s = get_settings()
    if s.storage_backend == "s3":
        _s3().put_object(Bucket=s.s3_bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        return
    p = _path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def get(key: str) -> bytes:
    s = get_settings()
    if s.storage_backend == "s3":
        return _s3().get_object(Bucket=s.s3_bucket, Key=key)["Body"].read()
    return _path(key).read_bytes()


def delete(key: str) -> None:
    s = get_settings()
    if s.storage_backend == "s3":
        _s3().delete_object(Bucket=s.s3_bucket, Key=key)
        return
    _path(key).unlink(missing_ok=True)
