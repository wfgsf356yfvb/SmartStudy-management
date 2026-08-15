"""Run once to add fee_structures table to the database."""
import sqlite3, os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'playschool.db')

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS fee_structures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER NOT NULL,
    class_level VARCHAR(20) NOT NULL,           -- nursery | lkg | ukg
    fee_type VARCHAR(20) NOT NULL,              -- full | half | quarterly
    label VARCHAR(100) NOT NULL,               -- e.g. "Annual Full Fee"
    total_amount REAL NOT NULL,
    admission_fee REAL DEFAULT 0,
    tuition_fee REAL DEFAULT 0,
    activity_fee REAL DEFAULT 0,l̥
    transport_fee REAL DEFAULT 0,
    misc_fee REAL DEFAULT 0,
    due_date VARCHAR(50),                       -- e.g. "1st April"
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
    UNIQUE(school_id, class_level, fee_type)
);
""")

conn.commit()
cur.close()
conn.close()
print("✅ fee_structures table created (or already existed).")
