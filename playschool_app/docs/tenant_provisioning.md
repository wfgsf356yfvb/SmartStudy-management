Tenant provisioning

Quick steps to provision a new tenant locally (uses env vars in .env):

1. Ensure `.env` has MySQL access values: `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `MYSQL_PORT`.
2. Run the provisioning script:

```bash
python scripts/provision_tenant.py --name "Acme Playschool" --subdomain acme
```

This will:
- insert a control record in your control DB (`MYSQL_DB`) with `subdomain=acme`
- create a new database `playschool_tenant_acme`
- run the schema creation on the tenant DB

After provisioning, point DNS or /etc/hosts: `acme.localhost` -> `127.0.0.1` and visit `http://acme.localhost:5000` to access the tenant.

Notes
- For production, use Terraform or cloud provider APIs to create RDS instances or schema and store tenant DB credentials in Secrets Manager.
- The `scripts/provision_tenant.py` is intentionally simple; use it only for bootstrapping and testing.
