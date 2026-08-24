import contextlib
import io
import os
from pathlib import Path
import unittest
from unittest import mock


RUN = os.environ.get("RUN_CONTROL_SCHEMA_MIGRATION_TEST", "").lower() in {"1", "true", "yes"}
HAS_CONFIG = all(os.environ.get(name) for name in (
    "MIGRATION_TEST_MYSQL_USER",
    "MIGRATION_TEST_MYSQL_PASSWORD",
    "MIGRATION_TEST_MYSQL_DATABASE",
))


@unittest.skipUnless(RUN and HAS_CONFIG, "Disposable MySQL migration test requires explicit RUN_CONTROL_SCHEMA_MIGRATION_TEST=1 and test credentials")
class ControlSchemaMigrationMySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mysql.connector
        from migrate_control_schema_mysql import migrate

        cls.mysql = mysql.connector
        cls.database_prefix = os.environ["MIGRATION_TEST_MYSQL_DATABASE"]
        if not cls.database_prefix.startswith("smartstudy_migration_test_"):
            raise unittest.SkipTest("MIGRATION_TEST_MYSQL_DATABASE must use the disposable smartstudy_migration_test_ prefix")
        cls.base = {
            "host": os.environ.get("MIGRATION_TEST_MYSQL_HOST", "localhost"),
            "port": int(os.environ.get("MIGRATION_TEST_MYSQL_PORT", "3306")),
            "user": os.environ["MIGRATION_TEST_MYSQL_USER"],
            "password": os.environ["MIGRATION_TEST_MYSQL_PASSWORD"],
        }
        cls.migrate = migrate

    def setUp(self):
        self.database = f"{self.database_prefix}_{self._testMethodName.lower()}"
        conn = self.mysql.connect(**self.base)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE `{self.database}`")
        cur.execute(f"USE `{self.database}`")
        for statement in [
            "CREATE TABLE schools (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, address VARCHAR(255)) ENGINE=InnoDB",
            "CREATE TABLE payments (id INT AUTO_INCREMENT PRIMARY KEY, school_id INT NOT NULL, amount DECIMAL(10,2) NOT NULL, payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status VARCHAR(20), months INT, notes TEXT) ENGINE=InnoDB",
            "CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(150) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, role ENUM('admin','teacher','student') NOT NULL DEFAULT 'student', class_level ENUM('nursery','lkg','ukg') NULL, school_id INT, is_active TINYINT(1) DEFAULT 1) ENGINE=InnoDB",
            "CREATE TABLE homework (id INT AUTO_INCREMENT PRIMARY KEY, teacher_id INT NOT NULL, class_level ENUM('nursery','lkg','ukg','all') NOT NULL DEFAULT 'all', title VARCHAR(200), description TEXT, homework_type ENUM('drawing','writing','reading','coloring','activity','other') DEFAULT 'other', due_date DATE) ENGINE=InnoDB",
            "CREATE TABLE submissions (id INT AUTO_INCREMENT PRIMARY KEY, homework_id INT NOT NULL, student_id INT NOT NULL, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB",
            "CREATE TABLE weekly_progress (id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, teacher_id INT NOT NULL, week_number INT NOT NULL, year INT NOT NULL) ENGINE=InnoDB",
            "CREATE TABLE game_scores (id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, game_name VARCHAR(100), score INT, stars INT) ENGINE=InnoDB",
            "CREATE TABLE announcements (id INT AUTO_INCREMENT PRIMARY KEY, author_id INT NOT NULL, title VARCHAR(200), content TEXT, target_role ENUM('all','teacher','student') DEFAULT 'all', target_class ENUM('all','nursery','lkg','ukg') DEFAULT 'all', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB",
        ]:
            cur.execute(statement)
        cur.execute("INSERT INTO schools (id, name) VALUES (1, 'Existing School')")
        cur.execute("INSERT INTO users (id, name, email, password_hash, role, class_level, school_id) VALUES (1, 'Existing User', 'existing@example.test', 'fixture-hash', 'admin', NULL, 1)")
        conn.commit()
        cur.close()
        conn.close()
        self.env = mock.patch.dict(os.environ, {
            "MYSQL_HOST": self.base["host"],
            "MYSQL_PORT": str(self.base["port"]),
            "MYSQL_DB": self.database,
            "MYSQL_USER": self.base["user"],
            "MYSQL_PASSWORD": self.base["password"],
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        conn = self.mysql.connect(**self.base)
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{self.database}`")
        conn.commit()
        cur.close()
        conn.close()

    def _connect(self):
        return self.mysql.connect(**self.base, database=self.database)

    def test_dry_run_does_not_backfill_or_mutate(self):
        actions = self.migrate(apply=False)
        self.assertFalse(any("UPDATE `schools`" in str(action) for action in actions))
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, subdomain FROM schools WHERE id=1")
        self.assertEqual(cur.fetchone(), (1, None))
        cur.close()
        conn.close()

    def test_apply_preserves_school_and_creates_missing_tables(self):
        self.migrate(apply=True)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, name, subdomain FROM schools WHERE id=1")
        self.assertEqual(cur.fetchone(), (1, "Existing School", None))
        cur.execute("SHOW TABLES")
        tables = {row[0] for row in cur.fetchall()}
        for table in ("attendance", "game_progress", "fee_structures", "student_fee_payments"):
            self.assertIn(table, tables)
        for table in ("platform_subscription_plans", "platform_subscription_payments", "platform_payment_events", "school_payment_config"):
            self.assertNotIn(table, tables)
        for table, column in (("schools", "subdomain"), ("payments", "screenshot"), ("game_scores", "level"), ("announcements", "announcement_type"), ("student_fee_payments", "payment_domain")):
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s",
                (self.database, table, column),
            )
            self.assertEqual(cur.fetchone()[0], 1)
        for table, column in (("users", "role"), ("users", "class_level"), ("homework", "class_level"), ("homework", "homework_type"), ("announcements", "target_role"), ("announcements", "target_class")):
            cur.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s",
                (self.database, table, column),
            )
            self.assertEqual(cur.fetchone()[0], "varchar")
        cur.close()
        conn.close()

    def test_weekly_unique_index_and_required_foreign_keys(self):
        self.migrate(apply=True)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SHOW INDEX FROM weekly_progress WHERE Key_name='unique_weekly'")
        self.assertEqual(len(cur.fetchall()), 4)
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.referential_constraints "
            "WHERE constraint_schema=%s AND table_name='weekly_progress'",
            (self.database,),
        )
        self.assertEqual(cur.fetchone()[0], 2)
        cur.close()
        conn.close()

    def test_duplicate_weekly_groups_fail_before_apply(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("INSERT INTO weekly_progress (student_id, teacher_id, week_number, year) VALUES (1, 2, 1, 2026)")
        cur.execute("INSERT INTO weekly_progress (student_id, teacher_id, week_number, year) VALUES (1, 2, 1, 2026)")
        conn.commit()
        cur.close()
        conn.close()
        with self.assertRaisesRegex(Exception, "duplicate weekly_progress"):
            self.migrate(apply=True)

    def test_explicit_backfill_and_rerun_are_safe(self):
        self.migrate(apply=True, backfill_school_id=1, backfill_subdomain="existing-school")
        self.migrate(apply=True, backfill_school_id=1, backfill_subdomain="existing-school")
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, subdomain FROM schools WHERE id=1")
        self.assertEqual(cur.fetchone(), (1, "existing-school"))
        cur.close()
        conn.close()

    def test_duplicate_backfill_is_rejected(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("ALTER TABLE schools ADD COLUMN subdomain VARCHAR(100) NULL")
        cur.execute("INSERT INTO schools (name, subdomain) VALUES ('Other', 'other-school')")
        conn.commit()
        cur.close()
        conn.close()
        with self.assertRaisesRegex(Exception, "already assigned"):
            self.migrate(apply=True, backfill_school_id=1, backfill_subdomain="other-school")

    def test_unexpected_existing_type_fails_closed(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("ALTER TABLE users MODIFY role ENUM('admin', 'teacher', 'student', 'unexpected')")
        conn.commit()
        cur.close()
        conn.close()
        with self.assertRaises(Exception):
            self.migrate(apply=True)


class ControlSchemaMigrationStaticTests(unittest.TestCase):
    def test_operator_only_and_phase5_separate(self):
        from migrate_control_schema_mysql import migrate
        source = Path(__file__).with_name("migrate_control_schema_mysql.py").read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__":', source)
        self.assertNotIn("migrate_phase5_billing", source)
        for table in ("platform_subscription_plans", "platform_subscription_payments", "platform_payment_events", "school_payment_config"):
            self.assertNotIn(table, source)
        self.assertNotIn("PROVISIONING_MYSQL_PASSWORD", source)
        self.assertNotIn("print(password", source)
        self.assertTrue(callable(migrate))

    def test_dry_run_output_does_not_include_secret(self):
        from migrate_control_schema_mysql import main
        secret = "migration-test-secret-not-for-output"
        with mock.patch.dict(os.environ, {
            "MYSQL_DB": "smartstudy_migration_test_static",
            "MYSQL_USER": "operator",
            "MYSQL_PASSWORD": secret,
        }), mock.patch("migrate_control_schema_mysql.mysql.connector.connect", side_effect=RuntimeError("connection unavailable")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                with self.assertRaises(SystemExit):
                    main()
            self.assertNotIn(secret, output.getvalue())


if __name__ == "__main__":
    unittest.main()
