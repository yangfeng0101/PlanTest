# MinIO Storage Service
import asyncio
import io
import logging
from datetime import timedelta
from typing import Optional, BinaryIO
import httpx
from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """MinIO storage service for screenshots and videos"""

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Ensure the bucket exists"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created bucket: {self.bucket}")
        except S3Error as e:
            logger.error(f"Failed to create bucket: {e}")

    def _get_object_name(self, task_id: str, filename: str, folder: str) -> str:
        """Generate object name for storage"""
        return f"{folder}/{task_id}/{filename}"

    async def upload_screenshot(
        self,
        task_id: str,
        data: BinaryIO,
        index: int,
        content_type: str = "image/png",
    ) -> tuple[str, str]:
        """Upload screenshot to MinIO

        Args:
            task_id: Task ID
            data: Binary data of the screenshot
            index: Screenshot index in the task
            content_type: MIME type

        Returns:
            Tuple of (object_name, presigned_url)
        """
        filename = f"screenshot_{index:04d}.png"
        object_name = self._get_object_name(task_id, filename, "screenshots")

        try:
            # Get data length
            data.seek(0, 2)  # Seek to end
            length = data.tell()
            data.seek(0)  # Seek to beginning

            # Upload using run_in_executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    self.bucket,
                    object_name,
                    data,
                    length,
                    content_type=content_type,
                )
            )

            logger.debug(f"Uploaded screenshot: {object_name}")

            # Generate presigned URL (valid for 7 days)
            url = await loop.run_in_executor(
                None,
                lambda: self.client.presigned_get_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(days=7),
                )
            )

            return object_name, url

        except S3Error as e:
            logger.error(f"Failed to upload screenshot: {e}")
            raise

    async def upload_screenshot_bytes(
        self,
        task_id: str,
        data: bytes,
        index: int,
        content_type: str = "image/png",
    ) -> tuple[str, str]:
        """Upload screenshot bytes to MinIO

        Args:
            task_id: Task ID
            data: Bytes of the screenshot
            index: Screenshot index in the task
            content_type: MIME type

        Returns:
            Tuple of (object_name, presigned_url)
        """
        filename = f"screenshot_{index:04d}.png"
        object_name = self._get_object_name(task_id, filename, "screenshots")

        try:
            # Upload using run_in_executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    self.bucket,
                    object_name,
                    io.BytesIO(data),
                    len(data),
                    content_type=content_type,
                )
            )

            logger.debug(f"Uploaded screenshot: {object_name}")

            # Generate presigned URL (valid for 7 days)
            url = await loop.run_in_executor(
                None,
                lambda: self.client.presigned_get_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(days=7),
                )
            )

            return object_name, url

        except S3Error as e:
            logger.error(f"Failed to upload screenshot: {e}")
            raise

    async def upload_video(
        self,
        task_id: str,
        data: BinaryIO,
        filename: str = "recording.mp4",
        content_type: str = "video/mp4",
    ) -> tuple[str, str]:
        """Upload video to MinIO

        Args:
            task_id: Task ID
            data: Binary data of the video
            filename: Video filename
            content_type: MIME type

        Returns:
            Tuple of (object_name, presigned_url)
        """
        object_name = self._get_object_name(task_id, filename, "videos")

        try:
            # Get data length
            data.seek(0, 2)
            length = data.tell()
            data.seek(0)

            # Upload using run_in_executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    self.bucket,
                    object_name,
                    data,
                    length,
                    content_type=content_type,
                )
            )

            logger.debug(f"Uploaded video: {object_name}")

            # Generate presigned URL
            url = await loop.run_in_executor(
                None,
                lambda: self.client.presigned_get_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(days=7),
                )
            )

            return object_name, url

        except S3Error as e:
            logger.error(f"Failed to upload video: {e}")
            raise

    async def upload_log(
        self,
        task_id: str,
        data: bytes,
        filename: str = "execution.log",
    ) -> tuple[str, str]:
        """Upload execution log to MinIO

        Args:
            task_id: Task ID
            data: Log content bytes
            filename: Log filename

        Returns:
            Tuple of (object_name, presigned_url)
        """
        object_name = self._get_object_name(task_id, filename, "logs")

        try:
            # Upload using run_in_executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    self.bucket,
                    object_name,
                    io.BytesIO(data),
                    len(data),
                    content_type="text/plain",
                )
            )

            logger.debug(f"Uploaded log: {object_name}")

            url = await loop.run_in_executor(
                None,
                lambda: self.client.presigned_get_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(days=7),
                )
            )

            return object_name, url

        except S3Error as e:
            logger.error(f"Failed to upload log: {e}")
            raise

    def get_presigned_url(self, object_name: str, expires_days: int = 7) -> str:
        """Get presigned URL for an object

        Args:
            object_name: Object name in storage
            expires_days: URL expiration in days

        Returns:
            Presigned URL
        """
        try:
            return self.client.presigned_get_object(
                self.bucket,
                object_name,
                expires=timedelta(days=expires_days),
            )
        except S3Error as e:
            logger.error(f"Failed to get presigned URL: {e}")
            raise

    async def download_object(self, object_name: str) -> bytes:
        """Download object from MinIO

        Args:
            object_name: Object name in storage

        Returns:
            Object content as bytes
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.get_object(self.bucket, object_name)
            )
            return response.read()
        except S3Error as e:
            logger.error(f"Failed to download object: {e}")
            raise
        finally:
            response.close()
            response.release_conn()

    async def delete_object(self, object_name: str) -> bool:
        """Delete object from MinIO

        Args:
            object_name: Object name in storage

        Returns:
            True if deleted successfully
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.remove_object(self.bucket, object_name)
            )
            logger.debug(f"Deleted object: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete object: {e}")
            return False

    async def delete_task_files(self, task_id: str) -> bool:
        """Delete all files for a task

        Args:
            task_id: Task ID

        Returns:
            True if deleted successfully
        """
        try:
            loop = asyncio.get_event_loop()
            # Delete all objects with task_id prefix
            for folder in ["screenshots", "videos", "logs"]:
                prefix = f"{folder}/{task_id}/"
                objects = await loop.run_in_executor(
                    None,
                    lambda p=prefix: list(self.client.list_objects(
                        self.bucket,
                        prefix=p,
                        recursive=True,
                    ))
                )
                for obj in objects:
                    await loop.run_in_executor(
                        None,
                        lambda o=obj: self.client.remove_object(self.bucket, o.object_name)
                    )

            logger.debug(f"Deleted all files for task: {task_id}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete task files: {e}")
            return False


# Global storage service instance
storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get or create storage service instance"""
    global storage_service
    if storage_service is None:
        storage_service = StorageService()
    return storage_service
