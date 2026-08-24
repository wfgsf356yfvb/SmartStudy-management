"""Small durable job journal used by the existing super-admin UI."""

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from uuid import uuid4

JOBS_FILE = os.environ.get(
    'PROVISION_JOBS_FILE',
    os.path.join(os.path.dirname(__file__), '.provision_jobs.json'),
).strip()
_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_jobs():
    if not os.path.exists(JOBS_FILE):
        return {}
    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_jobs(jobs):
    parent = os.path.dirname(os.path.abspath(JOBS_FILE))
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.provision-jobs-', dir=parent, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(jobs, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, JOBS_FILE)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def create_job(initial=None):
    job_id = str(uuid4())
    now = _now()
    job = {'id': job_id, 'status': 'pending', 'input': initial or {},
           'result': None, 'error': None, 'attempts': 0,
           'created_at': now, 'updated_at': now}
    with _lock:
        jobs = _read_jobs()
        jobs[job_id] = job
        _write_jobs(jobs)
    return job_id


def update_job(job_id, status=None, result=None, error=None):
    with _lock:
        jobs = _read_jobs()
        job = jobs.get(job_id, {'id': job_id, 'input': {}})
        if status:
            job['status'] = status
            if status == 'running':
                job['attempts'] = int(job.get('attempts', 0)) + 1
        if result is not None:
            job['result'] = result
        if error is not None:
            job['error'] = re.sub(r'(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[^,; ]+', r'\1=[redacted]', str(error))
        job['updated_at'] = _now()
        jobs[job_id] = job
        _write_jobs(jobs)


def get_job(job_id):
    with _lock:
        return _read_jobs().get(job_id)
