"""Explicit Phase 5 billing migration for the control database.

Run this operator command after taking a database backup. It is intentionally
not called from Flask startup and never contains credentials or seed prices.
"""

import os
import argparse
import mysql.connector
from tenant_services.secrets_manager import get_tenant_db_credentials


def run():
    config = {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", ""),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": os.environ.get("MYSQL_DB", "playschool_db"),
    }
    if not config["user"] or not config["password"]:
        raise RuntimeError("MYSQL_USER and MYSQL_PASSWORD must be provided through the environment.")
    conn = mysql.connector.connect(**config)
    cur = conn.cursor()
    statements = [
        """CREATE TABLE IF NOT EXISTS platform_subscription_plans (
            id INT AUTO_INCREMENT PRIMARY KEY,
            code VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            amount DECIMAL(12,2) NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'INR',
            duration_days INT NOT NULL,
            grace_days INT NOT NULL DEFAULT 0,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS platform_subscription_payments (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            school_id INT NOT NULL,
            plan_id INT NULL,
            amount DECIMAL(12,2) NOT NULL,
            duration_days INT NOT NULL DEFAULT 30,
            currency CHAR(3) NOT NULL DEFAULT 'INR',
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'unreconciled',
            provider VARCHAR(32) NOT NULL DEFAULT 'manual_upi',
            provider_order_id VARCHAR(128) NULL,
            provider_payment_id VARCHAR(128) NULL,
            provider_refund_id VARCHAR(128) NULL,
            provider_dispute_id VARCHAR(128) NULL,
            idempotency_key VARCHAR(160) NOT NULL,
            invoice_no VARCHAR(96) NOT NULL,
            receipt_file VARCHAR(255) NULL,
            notes TEXT NULL,
            paid_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_platform_idempotency (idempotency_key),
            UNIQUE KEY uq_platform_order (provider_order_id),
            UNIQUE KEY uq_platform_payment (provider_payment_id),
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES platform_subscription_plans(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS platform_payment_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_id VARCHAR(200) NOT NULL UNIQUE,
            event_type VARCHAR(120) NOT NULL,
            payload_sha256 CHAR(64) NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'received',
            processed_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS school_payment_config (
            school_id INT PRIMARY KEY,
            provider VARCHAR(32) NOT NULL DEFAULT 'manual_upi',
            upi_id VARCHAR(160) NULL,
            display_name VARCHAR(160) NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        "ALTER TABLE platform_subscription_payments ADD COLUMN reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'unreconciled'",
        "ALTER TABLE platform_subscription_payments ADD COLUMN provider_refund_id VARCHAR(128) NULL",
        "ALTER TABLE platform_subscription_payments ADD COLUMN provider_dispute_id VARCHAR(128) NULL",
        """INSERT IGNORE INTO platform_subscription_payments
            (school_id, amount, duration_days, status, provider, idempotency_key, invoice_no, receipt_file, notes)
            SELECT school_id, amount, months * 30, status, 'manual_upi',
                   CONCAT('legacy:', id), CONCAT('LEGACY-PS-', id), screenshot, notes
            FROM payments""",
    ]
    try:
        for statement in statements:
            try:
                cur.execute(statement)
            except mysql.connector.Error as exc:
                # The column is allowed to already exist when this operator
                # migration is rerun; all CREATE statements are idempotent.
                if statement.startswith('ALTER TABLE') and getattr(exc, 'errno', None) == 1060:
                    continue
                raise
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def run_tenant_fee_migration(tenant_subdomain, tenant_database):
    """Add the school-fee domain marker inside one tenant database only."""
    credentials = get_tenant_db_credentials(tenant_subdomain)
    if credentials.get('database') != tenant_database:
        raise RuntimeError('Tenant database does not match the server-side credential mapping.')
    conn = mysql.connector.connect(
        host=credentials['host'], port=int(credentials.get('port', 3306)),
        user=credentials['username'], password=credentials['password'], database=tenant_database,
    )
    cur = conn.cursor()
    try:
        try:
            cur.execute("ALTER TABLE student_fee_payments ADD COLUMN payment_domain VARCHAR(32) NOT NULL DEFAULT 'school_fee'")
        except mysql.connector.Error as exc:
            if getattr(exc, 'errno', None) != 1060:
                raise
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--tenant-subdomain')
    parser.add_argument('--tenant-database')
    args = parser.parse_args()
    run()
    if bool(args.tenant_subdomain) != bool(args.tenant_database):
        raise SystemExit('--tenant-subdomain and --tenant-database must be supplied together.')
    if args.tenant_subdomain:
        run_tenant_fee_migration(args.tenant_subdomain, args.tenant_database)
