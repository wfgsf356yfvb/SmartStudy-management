import os
import json
import threading
from uuid import uuid4

JOBS_FILE = os.path.join(os.path.dirname(__file__), '.provision_jobs.json')
_lock = threading.Lock()


def _read_jobs():
    if not os.path.exists(JOBS_FILE):
        return {}
    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _write_jobs(jobs):
    with open(JOBS_FILE, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2)


def create_job(initial=None):
    job_id = str(uuid4())
    job = {'id': job_id, 'status': 'pending', 'result': initial}
    with _lock:
        jobs = _read_jobs()
        jobs[job_id] = job
        _write_jobs(jobs)
    return job_id


def update_job(job_id, status=None, result=None):
    with _lock:
        jobs = _read_jobs()
        job = jobs.get(job_id, {'id': job_id})
        if status:
            job['status'] = status
        if result is not None:
            job['result'] = result
        jobs[job_id] = job
        _write_jobs(jobs)


def get_job(job_id):
    jobs = _read_jobs()
    return jobs.get(job_id)
