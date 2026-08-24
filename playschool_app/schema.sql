-- =============================================
-- PlaySchool Management System - Database Schema
-- =============================================

CREATE DATABASE IF NOT EXISTS playschool_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE playschool_db;

-- Schools Table
CREATE TABLE IF NOT EXISTS schools (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    address VARCHAR(255),
    subscription_status VARCHAR(20) DEFAULT 'active',
    valid_until DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payments Logs
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    school_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    months INT DEFAULT 12,
    notes TEXT,
    FOREIGN KEY (school_id) REFERENCES schools(id)
);

-- Platform subscription billing only. School fee money remains separate.
CREATE TABLE IF NOT EXISTS platform_subscription_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    duration_days INT NOT NULL,
    grace_days INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS platform_subscription_payments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id INT NOT NULL,
    plan_id INT NULL,
    amount DECIMAL(12,2) NOT NULL,
    duration_days INT NOT NULL DEFAULT 30,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'unreconciled',
    provider VARCHAR(32) NOT NULL DEFAULT 'manual_upi',
    provider_order_id VARCHAR(128) NULL UNIQUE,
    provider_payment_id VARCHAR(128) NULL UNIQUE,
    provider_refund_id VARCHAR(128) NULL,
    provider_dispute_id VARCHAR(128) NULL,
    idempotency_key VARCHAR(160) NOT NULL UNIQUE,
    invoice_no VARCHAR(96) NOT NULL,
    receipt_file VARCHAR(255) NULL,
    notes TEXT NULL,
    paid_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES platform_subscription_plans(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS platform_payment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(200) NOT NULL UNIQUE,
    event_type VARCHAR(120) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'received',
    processed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS school_payment_config (
    school_id INT PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'manual_upi',
    upi_id VARCHAR(160) NULL,
    display_name VARCHAR(160) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE
);

-- Users Table (Super Admin, Admin, Teacher, Student)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(15),
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'teacher', 'student') NOT NULL DEFAULT 'student',
    class_level ENUM('nursery', 'lkg', 'ukg') NULL,  -- only for students
    parent_name VARCHAR(100),                          -- for students
    parent_phone VARCHAR(15),                          -- for students
    profile_pic VARCHAR(255),
    school_id INT,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (school_id) REFERENCES schools(id)
);

-- Homework Table
CREATE TABLE IF NOT EXISTS homework (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_id INT NOT NULL,
    class_level ENUM('nursery', 'lkg', 'ukg', 'all') NOT NULL DEFAULT 'all',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    file_path VARCHAR(255),
    homework_type ENUM('drawing','writing','reading','coloring','activity','other') DEFAULT 'other',
    due_date DATE NOT NULL,
    max_marks INT DEFAULT 10,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Homework Submissions Table
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
    FOREIGN KEY (homework_id) REFERENCES homework(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_submission (homework_id, student_id)
);

-- Weekly Progress Table
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
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Game Scores Table
CREATE TABLE IF NOT EXISTS game_scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    game_name VARCHAR(100) NOT NULL,
    score INT DEFAULT 0,
    stars INT DEFAULT 0,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Announcements Table
CREATE TABLE IF NOT EXISTS announcements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    author_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    target_role ENUM('all','teacher','student') DEFAULT 'all',
    target_class ENUM('all','nursery','lkg','ukg') DEFAULT 'all',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);

