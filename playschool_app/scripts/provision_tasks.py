from scripts.celery_app import celery_app
from scripts.provision_tenant import provision_tenant
from scripts.provision_jobs import update_job
from scripts.audit import log as audit_log, redact_error
import smtplib
from email.mime.text import MIMEText
from config import Config
from tenant_services.job_context import validate_tenant_job_ref, resolve_tenant_job_ref
from scripts.provision_tenant import get_control_school_by_subdomain


@celery_app.task(bind=True)
def provision_task(self, job_id, name, subdomain, address='', use_aws=False, tenant_ref=None):
    try:
        tenant_ref = validate_tenant_job_ref(
            tenant_ref, expected_subdomain=subdomain, expected_job_id=job_id
        )
        update_job(job_id, status='running')
        res = provision_tenant(name, subdomain, address=address, use_aws=use_aws)
        if res.get('success'):
            resolve_tenant_job_ref(tenant_ref, get_control_school_by_subdomain)
            update_job(job_id, status='completed', result=res)
            audit_log('tenant_provisioned', {'job_id': job_id, 'subdomain': subdomain, 'tenant_id': res.get('tenant_id')})
            # notify super admin if configured
            try:
                if Config.MAIL_USERNAME and Config.MAIL_PASSWORD:
                    body = f"Tenant {subdomain} provisioned successfully.\n\n{res}"
                    msg = MIMEText(body)
                    msg['Subject'] = f"Tenant provisioned: {subdomain}"
                    msg['From'] = Config.MAIL_USERNAME
                    msg['To'] = Config.MAIL_USERNAME
                    with smtplib.SMTP_SSL(Config.MAIL_SERVER, Config.MAIL_PORT) as s:
                        s.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                        s.sendmail(Config.MAIL_USERNAME, [Config.MAIL_USERNAME], msg.as_string())
            except Exception:
                pass
            return {'status': 'completed', 'result': res}
        else:
            update_job(job_id, status='failed', result=res, error=res.get('message'))
            audit_log('tenant_failed', {'job_id': job_id, 'subdomain': subdomain, 'message': res.get('message')})
            try:
                if Config.MAIL_USERNAME and Config.MAIL_PASSWORD:
                    body = f"Tenant {subdomain} provisioning failed.\n\n{res}"
                    msg = MIMEText(body)
                    msg['Subject'] = f"Tenant provisioning failed: {subdomain}"
                    msg['From'] = Config.MAIL_USERNAME
                    msg['To'] = Config.MAIL_USERNAME
                    with smtplib.SMTP_SSL(Config.MAIL_SERVER, Config.MAIL_PORT) as s:
                        s.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                        s.sendmail(Config.MAIL_USERNAME, [Config.MAIL_USERNAME], msg.as_string())
            except Exception:
                pass
            return {'status': 'failed', 'result': res}
    except Exception as e:
        safe_error = redact_error(e)
        update_job(job_id, status='error', error=safe_error)
        audit_log('tenant_error', {'job_id': job_id, 'subdomain': subdomain, 'message': safe_error})
        raise
