"""Operator-run, additive MySQL control-database migration.

This module is deliberately not imported by Flask, Gunicorn, Celery, or
Compose startup.  It defaults to a read-only inventory; ``--apply`` is
required before any DDL or data backfill is attempted.
"""

import argparse
import os
import re
import sys

import mysql.connector


class MigrationError(RuntimeError):
    """The existing schema is not safe to change automatically."""


SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_SUBDOMAINS = {"www", "api", "app", "admin", "control"}


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise MigrationError(f"Invalid {label}.")
    return value


def _subdomain(value):
    value = (value or "").strip().lower()
    if not SUBDOMAIN_RE.fullmatch(value) or value in RESERVED_SUBDOMAINS:
        raise MigrationError("Invalid approved subdomain.")
    return value


def _config():
    database = os.environ.get("MYSQL_DB", "").strip()
    user = os.environ.get("MYSQL_USER", "").strip()
    password = os.environ.get("MYSQL_PASSWORD", "")
    if not database or not user or not password:
        raise MigrationError("MYSQL_DB, MYSQL_USER, and MYSQL_PASSWORD are required.")
    if user.lower() == "root":
        raise MigrationError("Use a protected operator account, not MySQL root runtime credentials.")
    return {
        "host": os.environ.get("MYSQL_HOST", "localhost").strip(),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": user,
        "password": password,
        "database": _identifier(database, "MYSQL_DB"),
    }


def _q(value):
    return f"`{_identifier(value, 'identifier')}`"


def _tables():
    # These definitions match the current mysql_setup.py runtime schema.
    return [
        ("game_progress", """
            CREATE TABLE IF NOT EXISTS `game_progress` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `student_id` INT NOT NULL,
                `game_name` VARCHAR(100) NOT NULL,
                `current_level` INT DEFAULT 1,
                `max_level_reached` INT DEFAULT 1,
                `total_stars` INT DEFAULT 0,
                `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (`student_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
                UNIQUE KEY `unique_game_progress` (`student_id`, `game_name`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, {"id", "student_id", "game_name", "current_level", "max_level_reached", "total_stars", "updated_at"}),
        ("attendance", """
            CREATE TABLE IF NOT EXISTS `attendance` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `student_id` INT NOT NULL,
                `teacher_id` INT NOT NULL,
                `date` DATE NOT NULL,
                `status` VARCHAR(10) NOT NULL DEFAULT 'present',
                `remark` TEXT,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (`student_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
                FOREIGN KEY (`teacher_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
                UNIQUE KEY `unique_attendance` (`student_id`, `date`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, {"id", "student_id", "teacher_id", "date", "status", "remark", "created_at"}),
        ("fee_structures", """
            CREATE TABLE IF NOT EXISTS `fee_structures` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `school_id` INT NOT NULL,
                `class_level` VARCHAR(20) NOT NULL,
                `fee_type` VARCHAR(20) NOT NULL,
                `label` VARCHAR(100) NOT NULL,
                `total_amount` DECIMAL(10,2) NOT NULL,
                `admission_fee` DECIMAL(10,2) DEFAULT 0,
                `tuition_fee` DECIMAL(10,2) DEFAULT 0,
                `activity_fee` DECIMAL(10,2) DEFAULT 0,
                `transport_fee` DECIMAL(10,2) DEFAULT 0,
                `misc_fee` DECIMAL(10,2) DEFAULT 0,
                `due_date` VARCHAR(50),
                `description` TEXT,
                `is_active` TINYINT(1) DEFAULT 1,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (`school_id`) REFERENCES `schools`(`id`) ON DELETE CASCADE,
                UNIQUE KEY `unique_fee` (`school_id`, `class_level`, `fee_type`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, {"id", "school_id", "class_level", "fee_type", "label", "total_amount", "admission_fee", "tuition_fee", "activity_fee", "transport_fee", "misc_fee", "due_date", "description", "is_active", "created_at"}),
        ("student_fee_payments", """
            CREATE TABLE IF NOT EXISTS `student_fee_payments` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `student_id` INT NOT NULL,
                `school_id` INT NOT NULL,
                `fee_structure_id` INT,
                `payment_mode` VARCHAR(20) DEFAULT 'monthly',
                `amount_paid` DECIMAL(10,2) NOT NULL,
                `month_label` VARCHAR(50),
                `payment_date` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                `payment_method` VARCHAR(50) DEFAULT 'cash',
                `payment_domain` VARCHAR(32) NOT NULL DEFAULT 'school_fee',
                `receipt_no` VARCHAR(50),
                `receipt_file` VARCHAR(255),
                `status` VARCHAR(20) DEFAULT 'pending',
                `verified_by` INT,
                `notes` TEXT,
                FOREIGN KEY (`student_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
                FOREIGN KEY (`school_id`) REFERENCES `schools`(`id`) ON DELETE CASCADE,
                FOREIGN KEY (`fee_structure_id`) REFERENCES `fee_structures`(`id`) ON DELETE SET NULL,
                FOREIGN KEY (`verified_by`) REFERENCES `users`(`id`) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, {"id", "student_id", "school_id", "fee_structure_id", "payment_mode", "amount_paid", "month_label", "payment_date", "payment_method", "payment_domain", "receipt_no", "receipt_file", "status", "verified_by", "notes"}),
    ]


ADDITIVE_COLUMNS = {
    "schools": {
        "subdomain": "ALTER TABLE `schools` ADD COLUMN `subdomain` VARCHAR(100) NULL",
        "subscription_status": "ALTER TABLE `schools` ADD COLUMN `subscription_status` VARCHAR(20) NOT NULL DEFAULT 'active'",
        "valid_until": "ALTER TABLE `schools` ADD COLUMN `valid_until` DATE NULL",
        "created_at": "ALTER TABLE `schools` ADD COLUMN `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    },
    "payments": {"screenshot": "ALTER TABLE `payments` ADD COLUMN `screenshot` VARCHAR(255) NULL"},
    "game_scores": {"level": "ALTER TABLE `game_scores` ADD COLUMN `level` INT DEFAULT 1"},
    "announcements": {"announcement_type": "ALTER TABLE `announcements` ADD COLUMN `announcement_type` VARCHAR(30) DEFAULT 'general'"},
    "student_fee_payments": {"payment_domain": "ALTER TABLE `student_fee_payments` ADD COLUMN `payment_domain` VARCHAR(32) NOT NULL DEFAULT 'school_fee'"},
}

EXPECTED_ADDITIVE_TYPES = {
    "schools": {"subdomain": "varchar", "subscription_status": "varchar", "valid_until": "date", "created_at": "timestamp"},
    "payments": {"screenshot": "varchar"},
    "game_scores": {"level": "int"},
    "announcements": {"announcement_type": "varchar"},
    "student_fee_payments": {"payment_domain": "varchar"},
}


REQUIRED_EXISTING_COLUMNS = {
    "schools": {"id", "name", "address"},
    "payments": {"id", "school_id", "amount", "payment_date", "status", "months", "notes"},
    "users": {"id", "name", "email", "password_hash", "role", "class_level", "school_id", "is_active"},
    "homework": {"id", "teacher_id", "class_level", "title", "description", "homework_type", "due_date"},
    "submissions": {"id", "homework_id", "student_id", "submitted_at"},
    "weekly_progress": {"id", "student_id", "teacher_id", "week_number", "year"},
    "game_scores": {"id", "student_id", "game_name", "score", "stars"},
    "announcements": {"id", "author_id", "title", "content", "target_role", "target_class", "created_at"},
}

EXPECTED_EXISTING_TYPES = {
    "schools": {"id": "int", "name": "varchar", "address": "varchar"},
    "payments": {"id": "int", "school_id": "int", "amount": "decimal", "payment_date": "timestamp", "status": "varchar", "months": "int", "notes": "text"},
    "users": {"id": "int", "name": "varchar", "email": "varchar", "password_hash": "varchar", "role": "varchar", "class_level": "varchar", "school_id": "int", "is_active": "tinyint"},
    "homework": {"id": "int", "teacher_id": "int", "class_level": "varchar", "title": "varchar", "description": "text", "homework_type": "varchar", "due_date": "date"},
    "submissions": {"id": "int", "homework_id": "int", "student_id": "int", "submitted_at": "timestamp"},
    "weekly_progress": {"id": "int", "student_id": "int", "teacher_id": "int", "week_number": "int", "year": "int"},
    "game_scores": {"id": "int", "student_id": "int", "game_name": "varchar", "score": "int", "stars": "int"},
    "announcements": {"id": "int", "author_id": "int", "title": "varchar", "content": "text", "target_role": "varchar", "target_class": "varchar", "created_at": "timestamp"},
}

COMPATIBLE_ENUMS = {
    ("users", "role"): {
        "definition": "enum('admin','teacher','student')",
        "values": {"admin", "teacher", "student"},
        "statement": "ALTER TABLE `users` MODIFY COLUMN `role` VARCHAR(20) NOT NULL DEFAULT 'student'",
    },
    ("users", "class_level"): {
        "definition": "enum('nursery','lkg','ukg')",
        "values": {"nursery", "lkg", "ukg"},
        "statement": "ALTER TABLE `users` MODIFY COLUMN `class_level` VARCHAR(20) NULL",
    },
    ("homework", "class_level"): {
        "definition": "enum('nursery','lkg','ukg','all')",
        "values": {"nursery", "lkg", "ukg", "all"},
        "statement": "ALTER TABLE `homework` MODIFY COLUMN `class_level` VARCHAR(20) NOT NULL DEFAULT 'all'",
    },
    ("homework", "homework_type"): {
        "definition": "enum('drawing','writing','reading','coloring','activity','other')",
        "values": {"drawing", "writing", "reading", "coloring", "activity", "other"},
        "statement": "ALTER TABLE `homework` MODIFY COLUMN `homework_type` VARCHAR(50) DEFAULT 'other'",
    },
    ("announcements", "target_role"): {
        "definition": "enum('all','teacher','student')",
        "values": {"all", "teacher", "student"},
        "statement": "ALTER TABLE `announcements` MODIFY COLUMN `target_role` VARCHAR(20) DEFAULT 'all'",
    },
    ("announcements", "target_class"): {
        "definition": "enum('all','nursery','lkg','ukg')",
        "values": {"all", "nursery", "lkg", "ukg"},
        "statement": "ALTER TABLE `announcements` MODIFY COLUMN `target_class` VARCHAR(20) DEFAULT 'all'",
    },
}

# These are the keys and relationships used by the existing runtime tables.
# A missing key/relationship is repaired only when the existing columns are
# compatible; an incompatible existing definition is a hard stop.
REQUIRED_INDEXES = {
    "schools": (("PRIMARY", True, ("id",)),),
    "payments": (("PRIMARY", True, ("id",)),),
    "users": (("PRIMARY", True, ("id",)), ("email", True, ("email",))),
    "homework": (("PRIMARY", True, ("id",)),),
    "submissions": (("PRIMARY", True, ("id",)), ("unique_submission", True, ("homework_id", "student_id"))),
    "weekly_progress": (("PRIMARY", True, ("id",)), ("unique_weekly", True, ("student_id", "teacher_id", "week_number", "year"))),
    "game_scores": (("PRIMARY", True, ("id",)),),
    "announcements": (("PRIMARY", True, ("id",)),),
}

REQUIRED_FOREIGN_KEYS = {
    "payments": (("school_id", "schools", "id", "CASCADE", "NO ACTION"),),
    "users": (("school_id", "schools", "id", "SET NULL", "NO ACTION"),),
    "homework": (("teacher_id", "users", "id", "CASCADE", "NO ACTION"),),
    "submissions": (
        ("homework_id", "homework", "id", "CASCADE", "NO ACTION"),
        ("student_id", "users", "id", "CASCADE", "NO ACTION"),
    ),
    "weekly_progress": (
        ("student_id", "users", "id", "CASCADE", "NO ACTION"),
        ("teacher_id", "users", "id", "CASCADE", "NO ACTION"),
    ),
    "game_scores": (("student_id", "users", "id", "CASCADE", "NO ACTION"),),
    "announcements": (("author_id", "users", "id", "CASCADE", "NO ACTION"),),
}

# The pre-a5295f2 control schema has these exact legacy delete rules.  The
# application has no normal school-delete workflow, and changing either rule
# could delete historical control/payment data, so these relationships are
# preserved rather than silently rewritten by the base compatibility migration.
LEGACY_FOREIGN_KEY_COMPATIBILITY = {
    ("payments", "school_id", "schools", "id"): ("NO ACTION", "NO ACTION"),
    ("users", "school_id", "schools", "id"): ("NO ACTION", "NO ACTION"),
}

def _inventory(cursor, database):
    cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
        (database,),
    )
    tables = {row[0] for row in cursor.fetchall()}
    columns = {}
    types = {}
    column_types = {}
    for table in tables:
        cursor.execute(
            "SELECT column_name, data_type, column_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
            (database, table),
        )
        rows = cursor.fetchall()
        columns[table] = {row[0] for row in rows}
        types[table] = {row[0]: row[1].lower() for row in rows}
        column_types[table] = {row[0]: row[2].lower() for row in rows}
    cursor.execute(
        "SELECT table_name, index_name, non_unique, seq_in_index, column_name "
        "FROM information_schema.statistics WHERE table_schema=%s "
        "ORDER BY table_name, index_name, seq_in_index",
        (database,),
    )
    indexes = {}
    for table, name, non_unique, seq, column in cursor.fetchall():
        indexes.setdefault(table, {}).setdefault(name, (not bool(non_unique), []))[1].append((seq, column))
    for table in indexes:
        for name, (unique, entries) in indexes[table].items():
            indexes[table][name] = (unique, tuple(column for _, column in sorted(entries)))

    cursor.execute(
        "SELECT k.table_name, k.constraint_name, k.column_name, k.referenced_table_name, "
        "k.referenced_column_name, r.delete_rule, r.update_rule "
        "FROM information_schema.key_column_usage k "
        "JOIN information_schema.referential_constraints r "
        "ON r.constraint_schema=k.constraint_schema "
        "AND r.table_name=k.table_name AND r.constraint_name=k.constraint_name "
        "WHERE k.constraint_schema=%s AND k.referenced_table_name IS NOT NULL "
        "ORDER BY k.table_name, k.constraint_name, k.ordinal_position",
        (database,),
    )
    foreign_keys = {}
    for table, name, column, ref_table, ref_column, delete_rule, update_rule in cursor.fetchall():
        foreign_keys.setdefault(table, {}).setdefault(name, {
            "columns": [], "ref_table": ref_table, "ref_column": ref_column,
            "delete_rule": delete_rule, "update_rule": update_rule,
        })["columns"].append(column)
    return tables, columns, types, column_types, indexes, foreign_keys


def _validate_existing(cursor, tables, columns, types, column_types, actions):
    for table, required in REQUIRED_EXISTING_COLUMNS.items():
        if table not in tables:
            raise MigrationError(f"Required existing table is missing: {table}")
        missing = required - columns.get(table, set())
        allowed = set(ADDITIVE_COLUMNS.get(table, {}))
        unexpected = missing - allowed
        if unexpected:
            raise MigrationError(f"Unexpected schema mismatch in {table}: missing {sorted(unexpected)}")
        for column, expected_type in EXPECTED_EXISTING_TYPES.get(table, {}).items():
            compatible_enum = COMPATIBLE_ENUMS.get((table, column))
            if compatible_enum and column_types.get(table, {}).get(column) == compatible_enum["definition"]:
                cursor.execute(f"SELECT DISTINCT `{column}` FROM `{table}`")
                values = {row[0] for row in cursor.fetchall() if row[0] is not None}
                if not values.issubset(compatible_enum["values"]):
                    raise MigrationError(f"Unexpected values in compatible enum {table}.{column}.")
                actions.append(compatible_enum["statement"])
                continue
            if column in types.get(table, {}) and types[table][column] != expected_type:
                raise MigrationError(
                    f"Unexpected schema mismatch in {table}.{column}: "
                    f"expected {expected_type}, found {types[table][column]}"
                )
        for column, expected_type in EXPECTED_ADDITIVE_TYPES.get(table, {}).items():
            if column in types.get(table, {}) and types[table][column] != expected_type:
                raise MigrationError(
                    f"Unexpected schema mismatch in {table}.{column}: "
                    f"expected {expected_type}, found {types[table][column]}"
                )


def _index_matches(indexes, unique, columns):
    return any(index_unique == unique and index_columns == tuple(columns)
               for index_unique, index_columns in indexes.values())


def _validate_indexes(cursor, database, tables, columns, indexes, actions):
    for table, required_indexes in REQUIRED_INDEXES.items():
        if table not in tables:
            continue
        for name, unique, index_columns in required_indexes:
            if _index_matches(indexes.get(table, {}), unique, index_columns):
                continue
            if name == "unique_weekly":
                cursor.execute(
                    "SELECT student_id, teacher_id, week_number, year, COUNT(*) "
                    "FROM `weekly_progress` GROUP BY student_id, teacher_id, week_number, year HAVING COUNT(*) > 1"
                )
                if cursor.fetchone():
                    raise MigrationError("Cannot add unique_weekly: duplicate weekly_progress groups exist.")
                actions.append("ALTER TABLE `weekly_progress` ADD UNIQUE KEY `unique_weekly` "
                               "(`student_id`, `teacher_id`, `week_number`, `year`)")
            elif name == "PRIMARY":
                raise MigrationError(f"Required primary key is missing or incompatible: {table}.{index_columns}")
            else:
                raise MigrationError(f"Required index is missing or incompatible: {table}.{name}")


def _validate_foreign_keys(tables, columns, foreign_keys, actions):
    for table, expected_keys in REQUIRED_FOREIGN_KEYS.items():
        if table not in tables:
            continue
        for column, ref_table, ref_column, delete_rule, update_rule in expected_keys:
            matching = []
            local_column_keys = []
            for key in foreign_keys.get(table, {}).values():
                if key["columns"] == [column]:
                    local_column_keys.append(key)
                if (key["columns"] == [column] and key["ref_table"] == ref_table and
                        key["ref_column"] == ref_column):
                    matching.append(key)
            if local_column_keys and not matching:
                raise MigrationError(f"Incompatible foreign key exists: {table}.{column}.")
            if matching:
                if any(key["delete_rule"] == delete_rule and key["update_rule"] == update_rule for key in matching):
                    continue
                legacy_rules = LEGACY_FOREIGN_KEY_COMPATIBILITY.get((table, column, ref_table, ref_column))
                legacy_compatible = bool(legacy_rules) and any(
                    key["delete_rule"] == legacy_rules[0] and key["update_rule"] == legacy_rules[1]
                    for key in matching
                )
                if legacy_compatible:
                    continue
                raise MigrationError(f"Incompatible foreign key exists: {table}.{column}.")
            if column not in columns.get(table, set()):
                raise MigrationError(f"Required foreign-key column is missing: {table}.{column}")
            constraint = f"fk_{table}_{column}"
            actions.append(
                f"ALTER TABLE `{table}` ADD CONSTRAINT `{constraint}` FOREIGN KEY (`{column}`) "
                f"REFERENCES `{ref_table}` (`{ref_column}`) ON DELETE {delete_rule} ON UPDATE {update_rule}"
            )


def _school_subdomain_state(cursor, database):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name='schools' AND column_name='subdomain'",
        (database,),
    )
    if cursor.fetchone()[0] == 0:
        return
    cursor.execute(
        "SELECT id, subdomain FROM `schools` WHERE subdomain IS NOT NULL",
    )
    values = cursor.fetchall()
    seen = {}
    for school_id, subdomain in values:
        if subdomain and not SUBDOMAIN_RE.fullmatch(subdomain.lower()):
            raise MigrationError(f"Invalid existing school subdomain for school {school_id}.")
        if subdomain in seen and seen[subdomain] != school_id:
            raise MigrationError(f"Duplicate existing school subdomain detected: {subdomain}")
        seen[subdomain] = school_id


def _has_subdomain_unique_index(indexes):
    return _index_matches(indexes.get("schools", {}), True, ("subdomain",))


def migrate(apply=False, backfill_school_id=None, backfill_subdomain=None):
    config = _config()
    if (backfill_school_id is None) != (backfill_subdomain is None):
        raise MigrationError("Backfill requires both --backfill-school-id and --backfill-subdomain.")
    if backfill_subdomain is not None:
        backfill_subdomain = _subdomain(backfill_subdomain)

    conn = mysql.connector.connect(**config)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE()")
        selected_database = cursor.fetchone()[0]
        if selected_database != config["database"]:
            raise MigrationError("MYSQL_DB was not selected as the connected control database.")
        tables, columns, types, column_types, indexes, foreign_keys = _inventory(cursor, config["database"])
        actions = []
        _validate_existing(cursor, tables, columns, types, column_types, actions)
        _school_subdomain_state(cursor, config["database"])

        for table, changes in ADDITIVE_COLUMNS.items():
            for column, statement in changes.items():
                if table in tables and column not in columns.get(table, set()):
                    actions.append(statement)

        for table, statement, required in _tables():
            if table not in tables:
                actions.append(statement.strip())
            elif not required.issubset(columns.get(table, set())):
                missing = sorted(required - columns.get(table, set()))
                raise MigrationError(f"Unexpected schema mismatch in existing {table}: missing {missing}")

        _validate_indexes(cursor, config["database"], tables, columns, indexes, actions)
        _validate_foreign_keys(tables, columns, foreign_keys, actions)

        if "schools" in tables and (
            "subdomain" not in columns.get("schools", set()) or
            not _has_subdomain_unique_index(indexes)
        ):
            actions.append("ALTER TABLE `schools` ADD UNIQUE KEY `uq_schools_subdomain` (`subdomain`)")

        if backfill_subdomain is not None:
            if "subdomain" in columns.get("schools", set()):
                cursor.execute("SELECT subdomain FROM `schools` WHERE id=%s", (backfill_school_id,))
            else:
                cursor.execute("SELECT id FROM `schools` WHERE id=%s", (backfill_school_id,))
            row = cursor.fetchone()
            if not row:
                raise MigrationError("Approved backfill school ID does not exist.")
            existing_subdomain = row[0] if "subdomain" in columns.get("schools", set()) else None
            if existing_subdomain not in (None, "", backfill_subdomain):
                raise MigrationError("Existing school subdomain differs from requested backfill.")
            if "subdomain" in columns.get("schools", set()):
                cursor.execute("SELECT id FROM `schools` WHERE subdomain=%s AND id<>%s", (backfill_subdomain, backfill_school_id))
                if cursor.fetchone():
                    raise MigrationError("Approved backfill subdomain is already assigned.")
            actions.append(("UPDATE `schools` SET `subdomain`=%s WHERE `id`=%s", (backfill_subdomain, backfill_school_id)))

        if not apply:
            return actions

        completed = []
        for step_number, action in enumerate(actions, start=1):
            try:
                if isinstance(action, tuple):
                    cursor.execute(action[0], action[1])
                else:
                    cursor.execute(action)
                completed.append(step_number)
            except Exception as exc:
                raise MigrationError(
                    f"Migration failed at step {step_number}/{len(actions)}: {exc}. "
                    f"Completed steps: {completed or 'none'}. MySQL DDL is non-transactional; inspect the schema before retrying."
                ) from exc
        conn.commit()
        return actions
    except Exception:
        if apply:
            conn.rollback()
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Inventory or migrate the MySQL control schema.")
    parser.add_argument("--apply", action="store_true", help="Apply additive DDL/backfill; default is read-only.")
    parser.add_argument("--backfill-school-id", type=int)
    parser.add_argument("--backfill-subdomain")
    args = parser.parse_args()
    try:
        actions = migrate(args.apply, args.backfill_school_id, args.backfill_subdomain)
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"{mode}: {len(actions)} validated action(s); no secrets or credentials were printed.")
        for action in actions:
            print(action[0] if isinstance(action, tuple) else action.splitlines()[0])
    except Exception as exc:
        print(f"Migration stopped safely: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
