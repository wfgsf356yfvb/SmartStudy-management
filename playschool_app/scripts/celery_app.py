import os
from celery import Celery

broker = os.environ.get('CELERY_BROKER_URL', os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
backend = os.environ.get('CELERY_RESULT_BACKEND', broker)

celery_app = Celery('playschool', broker=broker, backend=backend)

# Optional: configure Celery task settings here
celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
)

# Development helper: run tasks eagerly if CELERY_EAGER=1
if os.environ.get('CELERY_EAGER', '').lower() in ('1', 'true', 'yes'):
    celery_app.conf.task_always_eager = True
