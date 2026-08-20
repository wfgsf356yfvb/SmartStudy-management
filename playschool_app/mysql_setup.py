"""
PlaySchool ERP - MySQL Database Setup

Run this script ONCE to create the database and tables.
It does not create default or demo accounts.

Usage:
    python mysql_setup.py
"""

import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash
import os
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# MYSQL CONFIGURATION
# ============================================================

MYSQL_HOST = "localhost"
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = "playschool_db"
MYSQL_PORT = 3306


# ============================================================
# CREATE DATABASE
# ============================================================

def create_database():
    """Create the database if it doesn't exist."""

    try:
        if not MYSQL_PASSWORD:
            print("⚠️ MYSQL_PASSWORD not set. If your MySQL requires a password, set the MYSQL_PASSWORD environment variable or create a .env file.")

        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            port=MYSQL_PORT
        )

        cursor = conn.cursor()

        cursor.execute(
            f"""
            CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )

        print(f"✅ Database '{MYSQL_DB}' created/verified.")

        cursor.close()
        conn.close()

    except Error as e:
        print(f"❌ Error creating database: {e}")
        raise


def create_database_for(db_name):
    """Create a named database if it doesn't exist."""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            port=MYSQL_PORT
        )
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE DATABASE IF NOT EXISTS `{db_name}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )
        print(f"✅ Database '{db_name}' created/verified.")
        cursor.close()
        conn.close()
    except Error as e:
        print(f"❌ Error creating database {db_name}: {e}")
        raise


# ============================================================
# CREATE TABLES
# ============================================================

def create_tables():
    """Create all tables."""

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            port=MYSQL_PORT
        )

        cursor = conn.cursor()

        # ----------------------------------------------------
        # Schools Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schools (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                address VARCHAR(255),
                subdomain VARCHAR(100) UNIQUE,
                subscription_status VARCHAR(20) DEFAULT 'active',
                valid_until DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ schools table")

        # ----------------------------------------------------
        # Payments Logs
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                school_id INT NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending',
                months INT DEFAULT 12,
                notes TEXT,
                screenshot VARCHAR(255),
                FOREIGN KEY (school_id)
                    REFERENCES schools(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ payments table")

        # ----------------------------------------------------
        # Users Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL,
                phone VARCHAR(15),
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'student',
                class_level VARCHAR(20) NULL,
                parent_name VARCHAR(100),
                parent_phone VARCHAR(15),
                profile_pic VARCHAR(255),
                school_id INT,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (school_id)
                    REFERENCES schools(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ users table")

        # ----------------------------------------------------
        # Homework Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id INT AUTO_INCREMENT PRIMARY KEY,
                teacher_id INT NOT NULL,
                class_level VARCHAR(20) NOT NULL DEFAULT 'all',
                title VARCHAR(200) NOT NULL,
                description TEXT,
                file_path VARCHAR(255),
                homework_type VARCHAR(50) DEFAULT 'other',
                due_date DATE NOT NULL,
                max_marks INT DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ homework table")

        # ----------------------------------------------------
        # Submissions Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                homework_id INT NOT NULL,
                student_id INT NOT NULL,
                file_path VARCHAR(255),
                remarks TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                marks INT NULL,
                grade VARCHAR(5) NULL,
                feedback TEXT NULL,
                graded_at TIMESTAMP NULL,

                FOREIGN KEY (homework_id)
                    REFERENCES homework(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (student_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                UNIQUE KEY unique_submission
                    (homework_id, student_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ submissions table")

        # ----------------------------------------------------
        # Weekly Progress Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_progress (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                teacher_id INT NOT NULL,
                week_number INT NOT NULL,
                year INT NOT NULL,
                subject VARCHAR(50) DEFAULT 'Overall',
                marks_obtained DECIMAL(5,2) DEFAULT 0,
                total_marks DECIMAL(5,2) DEFAULT 100,
                grade VARCHAR(5),
                teacher_remarks TEXT,
                parent_notified TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (student_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (teacher_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                UNIQUE KEY unique_weekly
                    (student_id, teacher_id, week_number, year)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ weekly_progress table")

        # ----------------------------------------------------
        # Game Scores Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_scores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                game_name VARCHAR(100) NOT NULL,
                score INT DEFAULT 0,
                stars INT DEFAULT 0,
                level INT DEFAULT 1,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (student_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ game_scores table")

        # ----------------------------------------------------
        # Game Progress Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_progress (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                game_name VARCHAR(100) NOT NULL,
                current_level INT DEFAULT 1,
                max_level_reached INT DEFAULT 1,
                total_stars INT DEFAULT 0,
                updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,

                FOREIGN KEY (student_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                UNIQUE KEY unique_game_progress
                    (student_id, game_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ game_progress table")

        # ----------------------------------------------------
        # Announcements Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                author_id INT NOT NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                target_role VARCHAR(20) DEFAULT 'all',
                target_class VARCHAR(20) DEFAULT 'all',
                announcement_type VARCHAR(30) DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (author_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ announcements table")

        # ----------------------------------------------------
        # Attendance Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                teacher_id INT NOT NULL,
                date DATE NOT NULL,
                status VARCHAR(10) NOT NULL DEFAULT 'present',
                remark TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (student_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (teacher_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                UNIQUE KEY unique_attendance
                    (student_id, date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ attendance table")

        # ----------------------------------------------------
        # Fee Structures Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fee_structures (
                id INT AUTO_INCREMENT PRIMARY KEY,
                school_id INT NOT NULL,
                class_level VARCHAR(20) NOT NULL,
                fee_type VARCHAR(20) NOT NULL,
                label VARCHAR(100) NOT NULL,
                total_amount DECIMAL(10,2) NOT NULL,

                admission_fee DECIMAL(10,2) DEFAULT 0,
                tuition_fee DECIMAL(10,2) DEFAULT 0,
                activity_fee DECIMAL(10,2) DEFAULT 0,
                transport_fee DECIMAL(10,2) DEFAULT 0,
                misc_fee DECIMAL(10,2) DEFAULT 0,

                due_date VARCHAR(50),
                description TEXT,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (school_id)
                    REFERENCES schools(id)
                    ON DELETE CASCADE,

                UNIQUE KEY unique_fee
                    (school_id, class_level, fee_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ fee_structures table")

        # ----------------------------------------------------
        # Student Fee Payments Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_fee_payments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                school_id INT NOT NULL,
                fee_structure_id INT,

                payment_mode VARCHAR(20) DEFAULT 'monthly',
                amount_paid DECIMAL(10,2) NOT NULL,
                month_label VARCHAR(50),

                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                payment_method VARCHAR(50) DEFAULT 'cash',

                receipt_no VARCHAR(50),
                receipt_file VARCHAR(255),

                status VARCHAR(20) DEFAULT 'pending',
                verified_by INT,
                notes TEXT,

                FOREIGN KEY (student_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (school_id)
                    REFERENCES schools(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (fee_structure_id)
                    REFERENCES fee_structures(id)
                    ON DELETE SET NULL,

                FOREIGN KEY (verified_by)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ student_fee_payments table")

        # ----------------------------------------------------
        # Commit & Close
        # ----------------------------------------------------

        conn.commit()

        cursor.close()
        conn.close()

        print("\n✅ All tables created successfully!")

    except Error as e:
        print(f"❌ Error creating tables: {e}")
        raise


# ============================================================
# SEED DEFAULT DATA
# ============================================================

def seed_data():
    """Create the configured schema without seeding accounts."""
    return create_tables_for_db(MYSQL_DB)


def create_tables_for_db(db_name):
    """Create all tables in the specified database."""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=db_name,
            port=MYSQL_PORT
        )

        cursor = conn.cursor()

        # ----------------------------------------------------
        # Schools Table
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schools (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                address VARCHAR(255),
                subdomain VARCHAR(100) UNIQUE,
                subscription_status VARCHAR(20) DEFAULT 'active',
                valid_until DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        print("  ✅ schools table")
        # Account and tenant provisioning are controlled workflows. This
        # schema helper must never create default or demo credentials.
        conn.commit()

        cursor.close()
        conn.close()

        print("\n✅ Schema created; no default accounts were seeded.")

    except Error as e:
        print(f"❌ Error seeding data: {e}")
        raise


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 50)
    print("🏫 PlaySchool ERP - MySQL Database Setup")
    print("=" * 50)

    print(
        f"\nConnecting to MySQL at "
        f"{MYSQL_HOST}:{MYSQL_PORT} "
        f"as '{MYSQL_USER}'..."
    )

    print(f"Database: {MYSQL_DB}\n")

    # Create Database
    create_database()

    # Create Tables
    print("\n--- Creating Tables ---")
    create_tables()

    # Verify schema only; account provisioning is a controlled workflow.
    print("\n--- Creating Schema Without Default Accounts ---")
    seed_data()

    print("\n" + "=" * 50)
    print("🎉 Setup Complete! You can now run: python app.py")
    print("=" * 50)

    print("=" * 50)
