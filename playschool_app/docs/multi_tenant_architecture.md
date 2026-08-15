Overview

This document outlines a pragmatic multi-tenant architecture for PlaySchool SaaS. It focuses on tenant routing, isolation options, provisioning, security, and operational concerns.

Goals
- Support multiple schools (tenants) with logical isolation
- Secure tenant data and enable per-tenant backups
- Scale horizontally, keep operational overhead reasonable
- Support subscription / billing and Super Admin control

Tenant identification & routing
- Two supported approaches:
  1) Subdomain-per-tenant: `tenant1.example.com` (recommended UX)
  2) Path-per-tenant: `example.com/tenant1` (simpler DNS but worse isolation)
- Use subdomain routing. Configure web server (ALB / CloudFront) and Flask to read `Host` header and resolve tenant.
- Middleware: `before_request` reads tenant identifier from subdomain (or custom header `X-Tenant-ID` for API calls authenticated by Super Admin/service accounts).

Tenant isolation models
- Option A: DB-per-tenant (recommended for security/backup/PG scaling)
  - Each tenant gets its own database/schema on the RDS instance or a separate database instance.
  - Pros: clean data separation, easy per-tenant backup/restore, simpler query logic.
  - Cons: more databases to manage; need automation for provisioning and connection pooling.

- Option B: Shared DB with tenant_id in every table
  - Pros: lower operational overhead, cheaper at small scale.
  - Cons: harder to enforce data isolation, backup/restore per-tenant is complex, risk of accidental cross-tenant access if code bug.

Recommendation: Start with DB-per-tenant for production SaaS where tenant data separation and legal compliance matter.

App-layer responsibilities
- Tenant resolver middleware: maps hostname → tenant record (id, DB connection details, plan).
- Connection management: maintain a connection pool per tenant (or dynamic pool creation using a small LRU cache to avoid opening thousands of DB pools).
- Data models: keep tenant-agnostic models in code; the tenant resolver provides DB session/connection.
- Super Admin: separate admin app or prefixed area `superadmin.example.com` with elevated credentials and cross-tenant views (no tenant scoping).

Provisioning and onboarding
- Workflow:
  1) Super Admin creates tenant (metadata record in central `control` DB).
  2) Provision DB for tenant (create schema or new DB), run migrations, seed admin user, set S3 prefix for files.
  3) Provision subscription (Razorpay order creation) and mark tenant active after payment.
- Implement provisioning as idempotent Terraform + migration runner (e.g., Alembic or custom migration script).

Configuration & secrets
- Central control DB stores tenant metadata only (no tenant data). Tenant DB credentials are stored in Secrets Manager (rotate regularly).
- Use environment-specific config (dev/staging/prod). Never commit secrets.

Storage & static assets
- Use object storage (S3) with tenant-specific prefixes (e.g., `s3://playschool-uploads/{tenant_id}/...`).
- Front files via CDN (CloudFront) and signed URLs for private content.

Backups & restores
- RDS snapshots for each tenant DB (or logical dumps to S3 for schema-per-tenant strategy).
- Automate nightly snapshot retention and ad-hoc exports for tenant-level restore.

Security
- TLS everywhere, secure cookies, strong `SECRET_KEY` per environment; rotate keys.
- Enforce RBAC per tenant; use parameterized queries / ORM to avoid injection.
- No Flask debug in prod; lock down admin endpoints to IPs or VPN if needed.
- Rate-limiting, WAF rules, CSP, HSTS.

Scaling
- Stateless Flask app in containers; use autoscaling behind load balancer.
- Redis for sessions and caching (one cluster shared across tenants but with namespaced keys).

Monitoring & observability
- Central logging (structured logs) with tenant_id attached where applicable.
- Metrics (errors, latency, payments, signups) per tenant.

Next steps / checklist to implement (step 2 will be DB isolation implementation)
- Decide DB isolation strategy (db-per-tenant vs shared)
- Define tenant metadata schema in control DB
- Implement tenant resolver middleware in `app.py`
- Create provisioning script to create DB + run migrations + seed admin
- Add S3 tenant prefix logic for uploads

Files to add next:
- `docs/multi_tenant_architecture.md` (this file)
- `infra/terraform/*` for DB provisioning
- `scripts/provision_tenant.py` to automate provisioning
- `app/middleware/tenant_resolver.py` implementation

If you confirm the architecture choice (subdomain routing + DB-per-tenant), I'll proceed to implement the tenant resolver middleware and the provisioning script (step 2: Database isolation).