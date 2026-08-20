# PlaySchool-app

## Local setup — Database credentials

Create a `.env` file in the project root with your MySQL and SMTP credentials:

MYSQL_HOST=localhost
MYSQL_USER=<non-root-application-user>
MYSQL_PASSWORD=your_mysql_password
MYSQL_DB=playschool_db
MYSQL_PORT=3306

MAIL_USERNAME=
MAIL_PASSWORD=

Then run:

```powershell
python mysql_setup.py   # creates DB and tables; does not seed accounts
python app.py           # start the Flask app
```

Note: `.env` is ignored by git (see `.gitignore`). For production, use secure secret management instead of `.env`.

Quick start (development)

1. Create and activate a virtualenv

	python -m venv venv
	venv\Scripts\Activate.ps1  # PowerShell on Windows

2. Install dependencies

	pip install -r requirements.txt

3. Configure environment (copy `.env.example` -> `.env` and edit values)

4. Start Redis (optional for background tasks) or run tasks eagerly for development:

	# run Redis in Docker (optional)
	docker run -d -p 6379:6379 --name redis redis:7

5. Run the app (dev)

	# development eager mode (no Redis required)
	set CELERY_EAGER=1
	python app.py

6. For production-like setup (Redis + Celery worker):

	# install dependencies
	pip install -r requirements.txt

	# start Redis (or configured broker)
	docker run -d -p 6379:6379 --name redis redis:7

	# start Celery worker
	celery -A scripts.celery_app.celery_app worker --loglevel=info

	# start web (gunicorn)
	gunicorn app:app

Provisioning tenants

- Super Admin provisioning requires a controlled operator workflow; no default account is seeded.
- CLI: `python scripts/provision_tenant.py --name "My School" --subdomain mysn`
- To store tenant DB credentials in AWS Secrets Manager, set `USE_AWS_SECRETS=1` or use `--use-aws` flag.

Security & production notes

- Set `USE_AWS_SECRETS=1` and provide AWS credentials/role for Secrets Manager in production.
- Configure `TENANT_DB_USER_HOST` to restrict tenant DB user to specific host (default: `localhost` for local MySQL, `%` otherwise).
- Avoid `CREATE USER ... '@%'` in production; use least-privileged hosts and minimal privileges.
- Rotate tenant DB passwords and enforce secret lifecycle policies in the secrets store.

Support

If you want me to:
- Wire Celery with a persistent results backend and admin UI
- Add audit logging + email notifications for tenant creation
- Harden DB privileges further and add migration auto-generation

Tell me and I will implement it.
