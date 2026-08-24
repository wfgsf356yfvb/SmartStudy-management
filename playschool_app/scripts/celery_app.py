import os
from celery import Celery

_production = os.environ.get('FLASK_ENV', 'development').strip().lower() == 'production'
broker = os.environ.get('CELERY_BROKER_URL', '').strip()
if not broker and not _production:
    broker = os.environ.get('REDIS_URL', 'redis://localhost:6379/0').strip()
if _production:
    if not broker:
        raise RuntimeError('CELERY_BROKER_URL is required in production.')
    if not broker.lower().startswith(('redis://', 'rediss://')) or 'fakeredis' in broker.lower():
        raise RuntimeError('Production Celery requires a supervised Redis broker URL.')
backend = os.environ.get('CELERY_RESULT_BACKEND', broker)
if _production and (not backend.lower().startswith(('redis://', 'rediss://')) or 'fakeredis' in backend.lower()):
    raise RuntimeError('Production Celery requires a supervised Redis result backend.')

if _production and os.environ.get('CELERY_EAGER', '').strip().lower() in ('1', 'true', 'yes', 'on'):
    raise RuntimeError('CELERY_EAGER is forbidden in production.')

celery_app = Celery('playschool', broker=broker, backend=backend)

# Optional: configure Celery task settings here
celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
    beat_schedule={
        'phase4-file-maintenance': {
            'task': 'scripts.file_maintenance.run_configured_file_maintenance',
            'schedule': 86400.0,
        },
    },
)

# Development helper: run tasks eagerly if CELERY_EAGER=1
if os.environ.get('CELERY_EAGER', '').lower() in ('1', 'true', 'yes'):
    celery_app.conf.task_always_eager = True

# Register the scheduled Phase 4 maintenance tasks in worker and beat
# processes without relying on implicit filesystem discovery.
import scripts.file_maintenance  # noqa: E402,F401
