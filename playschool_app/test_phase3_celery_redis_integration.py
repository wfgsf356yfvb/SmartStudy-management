"""Deterministic Celery integration over an isolated Redis-protocol service."""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from itertools import count
from socketserver import ThreadingTCPServer
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

try:
    from fakeredis import FakeServer
    from fakeredis._tcp_server import TCPFakeRequestHandler, Resp2Writer
    from celery.contrib.testing.worker import start_worker
except ImportError:  # pragma: no cover - dependency/setup diagnostic
    FakeServer = None
    TCPFakeRequestHandler = None
    Resp2Writer = None
    start_worker = None


if TCPFakeRequestHandler:
    class Resp2RequestHandler(TCPFakeRequestHandler):
        def setup(self):
            super().setup()
            self.writer = Resp2Writer(self.client_address, self.wfile, self)
            self.current_client.writer = self.writer


    class Resp2TcpFakeServer(ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

        def __init__(self, address):
            self._shutdown_event = threading.Event()
            super().__init__(address, Resp2RequestHandler)
            self.fake_server = FakeServer(server_type='redis', version=(7, 2))
            self.client_ids = count(0)
            self.clients = {}

        def shutdown(self):
            self._shutdown_event.set()
            for client in list(self.clients.values()):
                try:
                    client.disconnect()
                except Exception:
                    pass
            super().shutdown()
else:  # pragma: no cover - import guard
    Resp2TcpFakeServer = None


@unittest.skipUnless(Resp2TcpFakeServer and start_worker, 'fakeredis/Celery integration dependencies are unavailable')
class CeleryRedisProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Resp2TcpFakeServer(('127.0.0.1', 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.broker = f'redis://127.0.0.1:{cls.server.server_address[1]}/0'
        # The Phase 1 surface tests intentionally leave a production environment
        # in place. Configure the real test broker before importing the guarded
        # Celery module; production still rejects missing broker configuration.
        os.environ['CELERY_BROKER_URL'] = cls.broker
        os.environ['CELERY_RESULT_BACKEND'] = cls.broker
        os.environ['CELERY_EAGER'] = '0'
        cls.jobs_dir = tempfile.TemporaryDirectory()
        from scripts import provision_jobs
        cls.jobs_patch = patch.object(
            provision_jobs, 'JOBS_FILE', os.path.join(cls.jobs_dir.name, 'jobs.json')
        )
        cls.jobs_patch.start()
        from scripts.celery_app import celery_app
        cls.app = celery_app
        cls.app.conf.update(
            broker_url=cls.broker,
            result_backend=cls.broker,
            task_always_eager=False,
            task_acks_late=False,
            broker_pool_limit=0,
        )
        from scripts.provision_tasks import provision_task
        cls.task = provision_task

    @classmethod
    def tearDownClass(cls):
        os.environ.pop('CELERY_BROKER_URL', None)
        os.environ.pop('CELERY_RESULT_BACKEND', None)
        os.environ.pop('CELERY_EAGER', None)
        cls.jobs_patch.stop()
        cls.jobs_dir.cleanup()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def _wait_for(self, job_id, status, timeout=15):
        from scripts.provision_jobs import get_job
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = get_job(job_id)
            if job and job.get('status') == status:
                return job
            time.sleep(0.1)
        self.fail(f'job {job_id} did not reach {status}: {get_job(job_id)}')

    def _enqueue(self, name, subdomain):
        from scripts.provision_jobs import create_job
        from tenant_services.job_context import make_tenant_job_ref
        job_id = create_job({'name': name, 'subdomain': subdomain})
        self.task.apply_async(
            args=(job_id, name, subdomain, '', False, make_tenant_job_ref(subdomain, job_id))
        )
        return job_id

    def test_enqueue_worker_success_failure_duplicate_and_retry(self):
        from scripts import provision_tasks
        successful = {'success': True, 'subdomain': 'celeryalpha', 'tenant_id': 1}
        duplicate = {'success': False, 'subdomain': 'celeryduplicate', 'message': 'Tenant subdomain already exists.'}
        with patch.object(provision_tasks, 'get_control_school_by_subdomain', return_value={'subdomain': 'celeryalpha'}), \
                patch.object(provision_tasks, 'provision_tenant', return_value=successful):
            with start_worker(self.app, concurrency=1, pool='solo', loglevel='error', perform_ping_check=False):
                job_id = self._enqueue('Celery Alpha', 'celeryalpha')
                job = self._wait_for(job_id, 'completed')
                self.assertEqual(job['attempts'], 1)

        with patch.object(provision_tasks, 'get_control_school_by_subdomain', return_value={'subdomain': 'celeryduplicate'}), \
                patch.object(provision_tasks, 'provision_tenant', return_value=duplicate):
            with start_worker(self.app, concurrency=1, pool='solo', loglevel='error', perform_ping_check=False):
                duplicate_id = self._enqueue('Duplicate', 'celeryduplicate')
                duplicate_job = self._wait_for(duplicate_id, 'failed')
                self.assertIn('already exists', duplicate_job['error'])

        calls = [
            {'success': False, 'subdomain': 'celeryretry', 'message': 'temporary failure'},
            {'success': True, 'subdomain': 'celeryretry', 'tenant_id': 2},
        ]
        with patch.object(provision_tasks, 'get_control_school_by_subdomain', return_value={'subdomain': 'celeryretry'}), \
                patch.object(provision_tasks, 'provision_tenant', side_effect=calls):
            with start_worker(self.app, concurrency=1, pool='solo', loglevel='error', perform_ping_check=False):
                failed_id = self._enqueue('Retry', 'celeryretry')
                self.assertEqual(self._wait_for(failed_id, 'failed')['attempts'], 1)
                retry_id = self._enqueue('Retry', 'celeryretry')
                self.assertEqual(self._wait_for(retry_id, 'completed')['attempts'], 1)

    def test_worker_restart_recovery(self):
        from scripts import provision_tasks
        result = {'success': True, 'subdomain': 'restarttenant', 'tenant_id': 3}
        with patch.object(provision_tasks, 'get_control_school_by_subdomain', return_value={'subdomain': 'restarttenant'}), \
                patch.object(provision_tasks, 'provision_tenant', return_value=result):
            with start_worker(self.app, concurrency=1, pool='solo', loglevel='error', perform_ping_check=False):
                pass
            with start_worker(self.app, concurrency=1, pool='solo', loglevel='error', perform_ping_check=False):
                job_id = self._enqueue('Restart', 'restarttenant')
                job = self._wait_for(job_id, 'completed')
            self.assertTrue(job['updated_at'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
