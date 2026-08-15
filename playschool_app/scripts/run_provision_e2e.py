import os
os.environ['CELERY_EAGER'] = '1'

from scripts.provision_jobs import create_job, get_job
from scripts.provision_tasks import provision_task

if __name__ == '__main__':
    job_id = create_job({'name': 'E2E School', 'subdomain': 'e2eschool'})
    print('Created job', job_id)
    res = provision_task.apply_async(args=(job_id, 'E2E School', 'e2eschool', '', False))
    print('Task dispatched (eager); result id:', getattr(res, 'id', None))
    job = get_job(job_id)
    print('Job record:', job)
