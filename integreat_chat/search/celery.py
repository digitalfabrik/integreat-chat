"""
Celery worker
"""

import os

from celery import Celery
from celery.schedules import crontab


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "integreat_chat.core.settings")
app = Celery("celery_app")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'update-indexes': {
        'task': 'tasks.update_search_indexes',
        'schedule': crontab(hour=2, minute=30),
    },
}
