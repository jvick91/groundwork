"""
Celery application instance.

This module is imported by three separate processes:
  - FastAPI server: to publish tasks via .delay() / .apply_async()
  - Celery worker: to discover and execute task functions
  - Celery beat: to schedule periodic tasks on a cron

All three communicate through Redis as the message broker.
"""

from celery import Celery

from app.core.settings import settings

celery_app = Celery("groundwork")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover tasks in app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])
