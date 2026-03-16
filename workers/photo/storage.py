import boto3
from botocore.client import Config

from config import get_settings


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


def upload_image(object_key: str, image_bytes: bytes) -> None:
    settings = get_settings()
    s3 = get_s3_client()
    s3.put_object(
        Bucket=settings.minio_bucket,
        Key=object_key,
        Body=image_bytes,
        ContentType="image/png",
    )
