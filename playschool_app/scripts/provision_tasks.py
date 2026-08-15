from scripts.celery_app import celery_app
from scripts.provision_tenant import provision_tenant
from scripts.provision_jobs import update_job
from scripts.audit import log as audit_log
import smtplib
from email.mime.text import MIMEText
from config import Config


@celery_app.task(bind=True)
def provision_task(self, job_id, name, subdomain, address='', use_aws=False):
    try:
        update_job(job_id, status='running')
        res = provision_tenant(name, subdomain, address=address, use_aws=use_aws)
        if res.get('success'):
            update_job(job_id, status='completed', result=res)
            audit_log('tenant_provisioned', {'subdomain': subdomain, 'result': res})
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
            update_job(job_id, status='failed', result=res)
            audit_log('tenant_failed', {'subdomain': subdomain, 'result': res})
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
        update_job(job_id, status='error', result={'message': str(e)})
        raise
