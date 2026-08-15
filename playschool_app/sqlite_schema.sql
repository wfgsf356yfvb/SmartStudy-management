-- =============================================
-- PlaySchool Management System - SQLite Database Schema
-- =============================================

-- Schools Table
CREATE TABLE IF NOT EXISTS schools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    address VARCHAR(255),
    subscription_status VARCHAR(20) DEFAULT 'active',
    valid_until DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payments Logs
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    months INTEGER DEFAULT 12,
    notes TEXT,
    FOREIGN KEY (school_id) REFERENCES schools (id)
);

-- Users Table (Super Admin, Admin, Teacher, Student)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(15),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'student',
    class_level VARCHAR(20) NULL,
    parent_name VARCHAR(100),
    parent_phone VARCHAR(15),
    profile_pic VARCHAR(255),
    school_id INTEGER REFERENCES schools(id),
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Homework Table
CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    class_level VARCHAR(20) NOT NULL DEFAULT 'all',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    file_path VARCHAR(255),
    homework_type VARCHAR(50) DEFAULT 'other',
    due_date DATE NOT NULL,
    max_marks INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Homework Submissions Table
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    homework_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    file_path VARCHAR(255),
    remarks TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    marks INTEGER NULL,
    grade VARCHAR(5) NULL,
    feedback TEXT NULL,
    graded_at TIMESTAMP NULL,
    FOREIGN KEY (homework_id) REFERENCES homework(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (homework_id, student_id)
);

-- Weekly Progress Table
CREATE TABLE IF NOT EXISTS weekly_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    year INTEGER NOT NULL,
    subject VARCHAR(50) DEFAULT 'Overall',
    marks_obtained DECIMAL(5,2) DEFAULT 0,
    total_marks DECIMAL(5,2) DEFAULT 100,
    grade VARCHAR(5),
    teacher_remarks TEXT,
    parent_notified INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(student_id, teacher_id, week_number, year)
);

-- Game Scores Table
CREATE TABLE IF NOT EXISTS game_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    game_name VARCHAR(100) NOT NULL,
    score INTEGER DEFAULT 0,
    stars INTEGER DEFAULT 0,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Announcements Table
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    target_role VARCHAR(20) DEFAULT 'all',
    target_class VARCHAR(20) DEFAULT 'all',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Attendance Table
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    date DATE NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'present', -- present, absent, late
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(student_id, date)
);


-- Seed Default Data
INSERT OR IGNORE INTO schools (id, name, address) VALUES (1, 'Default School', 'Main Campus');

-- Default super_admin: superadmin@playschool.com / superadmin123 (Assigned no specific school_id so views all)
INSERT OR IGNORE INTO users (name, email, phone, password_hash, role, school_id) VALUES
('Super Admin', 'superadmin@playschool.com', '0000000000',
 'scrypt:32768:8:1$salt$hash_placeholder',
 'super_admin', NULL);

-- Default school admin: admin@playschool.com / admin123 (Assigned to default school)
INSERT OR IGNORE INTO users (name, email, phone, password_hash, role, school_id) VALUES
('School Admin', 'admin@playschool.com', '9999999999',
 'scrypt:32768:8:1$salt$hash_placeholder',
 'admin', 1);
