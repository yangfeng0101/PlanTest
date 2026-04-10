# Storage Service - MinIO Integration
import io
import os
from datetime import timedelta
from typing import Optional, List

from minio import Minio
from minio.error import S3Error

from app.config import settings


class StorageService:
    """MinIO storage service for reports and artifacts"""

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Ensure the bucket exists"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as e:
            print(f"Error ensuring bucket: {e}")

    def upload_file(
        self,
        object_name: str,
        file_path: str,
        content_type: str = "application/octet-stream"
    ) -> bool:
        """Upload a file to MinIO"""
        try:
            self.client.fput_object(
                self.bucket,
                object_name,
                file_path,
                content_type=content_type
            )
            return True
        except S3Error as e:
            print(f"Error uploading file: {e}")
            return False

    def upload_data(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream"
    ) -> bool:
        """Upload data to MinIO"""
        try:
            self.client.put_object(
                self.bucket,
                object_name,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type
            )
            return True
        except S3Error as e:
            print(f"Error uploading data: {e}")
            return False

    def download_file(self, object_name: str, file_path: str) -> bool:
        """Download a file from MinIO"""
        try:
            self.client.fget_object(
                self.bucket,
                object_name,
                file_path
            )
            return True
        except S3Error as e:
            print(f"Error downloading file: {e}")
            return False

    def download_data(self, object_name: str) -> Optional[bytes]:
        """Download data from MinIO"""
        try:
            response = self.client.get_object(
                self.bucket,
                object_name
            )
            return response.read()
        except S3Error as e:
            print(f"Error downloading data: {e}")
            return None

    def delete_file(self, object_name: str) -> bool:
        """Delete a file from MinIO"""
        try:
            self.client.remove_object(
                self.bucket,
                object_name
            )
            return True
        except S3Error as e:
            print(f"Error deleting file: {e}")
            return False

    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> Optional[str]:
        """Get a presigned URL for downloading"""
        try:
            url = self.client.presigned_get_object(
                self.bucket,
                object_name,
                expires=expires
            )
            return url
        except S3Error as e:
            print(f"Error getting presigned URL: {e}")
            return None

    def list_objects(self, prefix: str = "") -> List[dict]:
        """List objects in the bucket"""
        try:
            objects = self.client.list_objects(
                self.bucket,
                prefix=prefix
            )
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                }
                for obj in objects
            ]
        except S3Error as e:
            print(f"Error listing objects: {e}")
            return []

    def stat_object(self, object_name: str) -> Optional[dict]:
        """Get object metadata"""
        try:
            stat = self.client.stat_object(
                self.bucket,
                object_name
            )
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "etag": stat.etag
            }
        except S3Error as e:
            print(f"Error getting object stat: {e}")
            return None


# Global storage service instance
storage_service = StorageService()
