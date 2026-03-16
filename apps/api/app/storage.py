import boto3
from botocore.client import Config

from app.config import get_settings


def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.minio_secure else ''}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket_exists() -> None:
    settings = get_settings()
    s3 = get_s3_client()
    buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if settings.minio_bucket not in buckets:
        s3.create_bucket(Bucket=settings.minio_bucket)


def create_presigned_get_url(object_key: str, expires_seconds: int = 3600) -> str:
    settings = get_settings()
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": object_key},
        ExpiresIn=expires_seconds,
    )
