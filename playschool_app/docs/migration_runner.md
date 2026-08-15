Migration runner

Use `scripts/run_migrations.py` to apply SQL migrations to a tenant database.

Example:

```bash
# Run migrations for tenant 'acme' using files in migrations/
python scripts/run_migrations.py --subdomain acme --migrations migrations
```

The runner tracks applied files in `schema_migrations` table to avoid reapplying.

For production, use Alembic or a managed migration system. This runner is intentionally lightweight for bootstrapping and controlled upgrades.
