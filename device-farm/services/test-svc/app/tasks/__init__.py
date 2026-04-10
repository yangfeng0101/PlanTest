# Celery Configuration
from celery import Celery
from app.config import settings

# Create Celery application
celery_app = Celery(
    "test_svc",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.APPIUM_TIMEOUT,
    task_soft_time_limit=settings.APPIUM_TIMEOUT - 30,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    result_expires=3600,  # 1 hour
    broker_connection_retry_on_startup=True,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
