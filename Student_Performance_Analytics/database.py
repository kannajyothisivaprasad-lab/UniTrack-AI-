"""
UniTrack AI - Database Management Layer
Supports SQLite out-of-the-box for seamless local deployment,
and PostgreSQL for enterprise production environments via DATABASE_URL.
Enforces multi-tenant data separation using tenant foreign keys and indexes.
"""

import os
import sqlite3
import datetime
import json
import threading
from contextlib import contextmanager
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'unitrack.db')
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{DB_PATH}')

_local = threading.local()


def get_db_connection():
    """
    Returns a database connection configured with dict-like row access.
    Supports MySQL, PostgreSQL, and SQLite with automatic fallback.
    """
    use_mysql = os.environ.get('USE_MYSQL', '0') == '1' or DATABASE_URL.startswith('mysql')
    if use_mysql:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
            host = os.environ.get('MYSQL_HOST', 'localhost')
            port = int(os.environ.get('MYSQL_PORT', 3306))
            user = os.environ.get('MYSQL_USER', 'root')
            password = os.environ.get('MYSQL_PASSWORD', '')
            db_name = os.environ.get('MYSQL_DATABASE', 'unitrack_ai')
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=db_name, cursorclass=DictCursor, autocommit=False
            )
            return conn
        except Exception as e:
            # Fallback gracefully to SQLite if MySQL daemon is not running locally
            pass

    if DATABASE_URL.startswith('sqlite') or not (DATABASE_URL.startswith('postgres') or DATABASE_URL.startswith('postgresql')):
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable foreign key constraint enforcement and WAL mode for high concurrency
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn
    else:
        # PostgreSQL support if psycopg2 is installed and postgres URL configured
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn


@contextmanager
def db_session():
    """Context manager with thread-local connection re-use to prevent nested lock deadlocks."""
    if getattr(_local, 'conn', None) is not None:
        yield _local.conn
    else:
        conn = get_db_connection()
        _local.conn = conn
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            _local.conn = None
            conn.close()


def init_db():
    """Initializes all database tables with strict tenant-level separation and indexes."""
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Universities Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS universities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            address TEXT,
            status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'active', 'suspended', 'inactive'
            subscription_plan TEXT DEFAULT 'Standard',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by TEXT
        );
        ''')

        # 2. Users Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL, -- 'super_admin', 'university_admin', 'staff'
            department TEXT,
            permissions TEXT DEFAULT '["all"]', -- JSON list of module permissions
            is_active INTEGER DEFAULT 1,
            failed_logins INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
        );
        ''')

        # 3. Departments Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            head_of_dept TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, code),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
        );
        ''')

        # 4. Sections Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            department_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            academic_year TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, department_id, name, academic_year),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE CASCADE
        );
        ''')

        # 5. Students Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            profile_photo TEXT,
            department_id INTEGER,
            section_id INTEGER,
            academic_year TEXT NOT NULL,
            semester INTEGER DEFAULT 1,
            enrollment_date DATE,
            enrollment_status TEXT DEFAULT 'Active', -- 'Active', 'Inactive', 'Graduated', 'Suspended'
            gender TEXT,
            age INTEGER,
            logins INTEGER DEFAULT 0,
            content_reads INTEGER DEFAULT 0,
            forum_posts INTEGER DEFAULT 0,
            quiz_reviews INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, student_id),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
            FOREIGN KEY (section_id) REFERENCES sections (id) ON DELETE SET NULL
        );
        ''')

        # 6. Subjects Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            department_id INTEGER,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            credits INTEGER DEFAULT 3,
            semester INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, code),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL
        );
        ''')

        # 7. Examinations Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS examinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            name TEXT NOT NULL,
            exam_type TEXT NOT NULL, -- 'Midterm', 'Final', 'Quiz', 'Lab', 'Internal'
            academic_year TEXT NOT NULL,
            semester INTEGER DEFAULT 1,
            exam_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
        );
        ''')

        # 8. Marks Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            examination_id INTEGER NOT NULL,
            internal_marks REAL DEFAULT 0.0,
            external_marks REAL DEFAULT 0.0,
            total_marks REAL NOT NULL,
            max_marks REAL NOT NULL DEFAULT 100.0,
            pass_marks REAL NOT NULL DEFAULT 40.0,
            percentage REAL NOT NULL,
            grade TEXT,
            is_pass INTEGER NOT NULL DEFAULT 1,
            entered_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, student_id, subject_id, examination_id),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
            FOREIGN KEY (examination_id) REFERENCES examinations (id) ON DELETE CASCADE,
            FOREIGN KEY (entered_by) REFERENCES users (id) ON DELETE SET NULL
        );
        ''')

        # 9. Attendance Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            department_id INTEGER,
            section_id INTEGER,
            date DATE NOT NULL,
            status TEXT NOT NULL, -- 'Present', 'Absent', 'Leave'
            marked_by INTEGER,
            correction_reason TEXT,
            method TEXT DEFAULT 'manual', -- 'manual', 'facial_verified'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, student_id, date),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
            FOREIGN KEY (section_id) REFERENCES sections (id) ON DELETE SET NULL,
            FOREIGN KEY (marked_by) REFERENCES users (id) ON DELETE SET NULL
        );
        ''')

        # 10. Attendance Audit Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attendance_id INTEGER NOT NULL,
            university_id TEXT NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            changed_by INTEGER,
            reason TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attendance_id) REFERENCES attendance (id) ON DELETE CASCADE,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (changed_by) REFERENCES users (id) ON DELETE SET NULL
        );
        ''')

        # 11. Assignments Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            department_id INTEGER,
            subject_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            due_date DATE NOT NULL,
            max_points REAL DEFAULT 100.0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
        );
        ''')

        # 12. Assignment Submissions Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending', -- 'Completed', 'Pending', 'Missing', 'Late'
            submitted_at TIMESTAMP,
            score REAL,
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, assignment_id, student_id),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (assignment_id) REFERENCES assignments (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        );
        ''')

        # 13. Fee Records Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fee_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            total_fee REAL NOT NULL,
            paid_amount REAL NOT NULL DEFAULT 0.0,
            pending_amount REAL NOT NULL,
            due_date DATE,
            payment_status TEXT NOT NULL DEFAULT 'Pending', -- 'Paid', 'Partial', 'Pending'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, student_id, academic_year),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        );
        ''')

        # 14. Fee Payments Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fee_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            fee_record_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_date DATE NOT NULL,
            payment_method TEXT NOT NULL, -- 'Bank Transfer', 'Demand Draft', 'UPI', 'Cheque', 'Cash'
            receipt_reference TEXT NOT NULL UNIQUE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (fee_record_id) REFERENCES fee_records (id) ON DELETE CASCADE
        );
        ''')

        # 15. Achievements Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            category TEXT NOT NULL, -- 'Academic', 'Sports', 'Certifications', 'Hackathons', 'Technical Competitions', 'Events and Workshops', 'Awards'
            title TEXT NOT NULL,
            description TEXT,
            organizer TEXT,
            achievement_date DATE,
            proof_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        );
        ''')

        # 16. Risk Predictions Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            risk_level TEXT NOT NULL, -- 'Low Risk', 'Medium Risk', 'High Risk'
            risk_score REAL NOT NULL, -- 0 to 100
            reasons TEXT, -- JSON array of factors
            recommended_action TEXT,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, student_id),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        );
        ''')

        # 17. Audit Logs Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE SET NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
        );
        ''')

        # 18. Courses Table (BTech Trending Courses & Custom Programs)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            intake_capacity INTEGER DEFAULT 120,
            department_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, code),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL
        );
        ''')

        # 19. Batches Table (Unlimited Multi-Year Batches)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            name TEXT NOT NULL, -- e.g. '2024-2028', '2025-2029', '2026-2030'
            start_year INTEGER NOT NULL,
            end_year INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, name),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
        );
        ''')

        # 20. Academic Years Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS academic_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            name TEXT NOT NULL, -- e.g. '2024-2025', '2025-2026'
            is_current INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, name),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
        );
        ''')

        # 21. Face Encodings Table (AI Facial Recognition Biometrics)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_encodings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            student_code TEXT NOT NULL,
            encoding_vector TEXT NOT NULL, -- JSON array of face feature descriptors
            photo_path TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(university_id, student_id),
            FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        );
        ''')

        # Indices for tenant isolation & high performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_uni ON users(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dept_uni ON departments(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sect_uni ON sections(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_students_uni ON students(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_uni ON attendance(university_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_marks_uni ON marks(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fees_uni ON fee_records(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assign_uni ON assignments(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_uni ON audit_logs(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_courses_uni ON courses(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_batches_uni ON batches(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ay_uni ON academic_years(university_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_uni ON face_encodings(university_id);")

        # Upgrade existing table columns safely
        _upgrade_schema_columns(cursor)


def _upgrade_schema_columns(cursor):
    """Safely adds missing columns to existing SQLite tables without losing data."""
    def add_col(table, col, col_type):
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
        except Exception:
            pass  # Column already exists

    # Students table upgrades
    add_col("students", "course_id", "INTEGER")
    add_col("students", "course_name", "TEXT")
    add_col("students", "batch_id", "INTEGER")
    add_col("students", "batch_name", "TEXT")
    add_col("students", "admission_date", "DATE")
    add_col("students", "total_fee", "REAL DEFAULT 0.0")
    add_col("students", "password_hash", "TEXT")

    # Assignments table upgrades
    add_col("assignments", "course_id", "INTEGER")
    add_col("assignments", "batch_id", "INTEGER")
    add_col("assignments", "academic_year", "TEXT")
    add_col("assignments", "file_path", "TEXT")
    add_col("assignments", "file_name", "TEXT")

    # Assignment submissions table upgrades
    add_col("assignment_submissions", "file_path", "TEXT")
    add_col("assignment_submissions", "file_name", "TEXT")
    add_col("assignment_submissions", "file_size", "INTEGER")
    add_col("assignment_submissions", "marks_awarded", "REAL")
    add_col("assignment_submissions", "feedback", "TEXT")
    add_col("assignment_submissions", "evaluated_by", "INTEGER")
    add_col("assignment_submissions", "evaluated_at", "TIMESTAMP")

    # Attendance table upgrades
    add_col("attendance", "timestamp", "TEXT")
    add_col("attendance", "marked_time", "TEXT")


def seed_demo_data():
    """Populates initial universities, roles, staff, students, and academic data."""
    with db_session() as conn:
        cursor = conn.cursor()

        # Check if already seeded
        cursor.execute("SELECT COUNT(*) FROM universities")
        if cursor.fetchone()[0] > 0:
            return  # Already seeded

        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        today = datetime.date.today().strftime('%Y-%m-%d')

        # 1. Platform Super Admin
        super_admin_pass = generate_password_hash("Admin@123")
        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, permissions)
            VALUES (NULL, 'admin@unitrack.ai', ?, 'Platform Super Administrator', 'super_admin', '["all"]')
        ''', (super_admin_pass,))

        # 2. Registered University A: Apex Institute of Technology
        uni_a_id = 'UNI-APEX'
        cursor.execute('''
            INSERT INTO universities (id, name, email, address, status, subscription_plan, approved_at, approved_by)
            VALUES (?, 'Apex Institute of Technology', 'contact@apex.edu', '100 Innovation Boulevard, Tech Park', 'active', 'Enterprise', ?, 'Platform Super Administrator')
        ''', (uni_a_id, now))

        apex_admin_pass = generate_password_hash("ApexAdmin@123")
        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, permissions)
            VALUES (?, 'admin@apex.edu', ?, 'Dr. Rajesh Sharma (Dean)', 'university_admin', '["all"]')
        ''', (uni_a_id, apex_admin_pass))

        apex_staff_pass = generate_password_hash("Staff@123")
        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, department, permissions)
            VALUES (?, 'prof.sharma@apex.edu', ?, 'Prof. Ananya Sharma', 'staff', 'Computer Science', '["students", "attendance", "marks", "assignments", "fees", "achievements", "analytics"]')
        ''', (uni_a_id, apex_staff_pass))

        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, department, permissions)
            VALUES (?, 'dr.patel@apex.edu', ?, 'Dr. Vikram Patel', 'staff', 'Information Technology', '["students", "attendance", "marks", "assignments"]')
        ''', (uni_a_id, apex_staff_pass))

        # Departments for Uni A
        cursor.execute("INSERT INTO departments (university_id, code, name, head_of_dept) VALUES (?, 'CSE', 'Computer Science & Engineering', 'Prof. Ananya Sharma')", (uni_a_id,))
        cse_dept_id = cursor.lastrowid
        cursor.execute("INSERT INTO departments (university_id, code, name, head_of_dept) VALUES (?, 'IT', 'Information Technology', 'Dr. Vikram Patel')", (uni_a_id,))
        it_dept_id = cursor.lastrowid
        cursor.execute("INSERT INTO departments (university_id, code, name, head_of_dept) VALUES (?, 'ECE', 'Electronics & Communication', 'Dr. Meera Nambiar')", (uni_a_id,))
        ece_dept_id = cursor.lastrowid

        # Sections for Uni A
        cursor.execute("INSERT INTO sections (university_id, department_id, name, academic_year) VALUES (?, ?, 'Section A', '2024-2025')", (uni_a_id, cse_dept_id))
        cse_sec_a = cursor.lastrowid
        cursor.execute("INSERT INTO sections (university_id, department_id, name, academic_year) VALUES (?, ?, 'Section B', '2024-2025')", (uni_a_id, cse_dept_id))
        cse_sec_b = cursor.lastrowid
        cursor.execute("INSERT INTO sections (university_id, department_id, name, academic_year) VALUES (?, ?, 'Section A', '2024-2025')", (uni_a_id, it_dept_id))
        it_sec_a = cursor.lastrowid

        # Subjects for Uni A
        cursor.execute("INSERT INTO subjects (university_id, department_id, code, name, credits, semester) VALUES (?, ?, 'CS301', 'Data Structures & Algorithms', 4, 3)", (uni_a_id, cse_dept_id))
        sub_dsa = cursor.lastrowid
        cursor.execute("INSERT INTO subjects (university_id, department_id, code, name, credits, semester) VALUES (?, ?, 'CS302', 'Database Management Systems', 4, 3)", (uni_a_id, cse_dept_id))
        sub_dbms = cursor.lastrowid
        cursor.execute("INSERT INTO subjects (university_id, department_id, code, name, credits, semester) VALUES (?, ?, 'IT201', 'Web Technologies & Cloud', 3, 3)", (uni_a_id, it_dept_id))
        sub_web = cursor.lastrowid

        # Examination for Uni A
        cursor.execute("INSERT INTO examinations (university_id, name, exam_type, academic_year, semester, exam_date) VALUES (?, 'Fall Midterm Examinations 2024', 'Midterm', '2024-2025', 3, '2024-10-15')", (uni_a_id,))
        exam_midterm_a = cursor.lastrowid

        # Uni A Students
        uni_a_students_data = [
            ('APEX-24-001', 'Aarav Mehta', 'aarav.m@apex.edu', '+91 98765 43210', cse_dept_id, cse_sec_a, 3, 'Male', 20, 160, 240, 45, 8, 38000, 38000, 'Paid'),
            ('APEX-24-002', 'Diya Sen', 'diya.sen@apex.edu', '+91 98765 43211', cse_dept_id, cse_sec_a, 3, 'Female', 21, 140, 190, 32, 6, 38000, 25000, 'Partial'),
            ('APEX-24-003', 'Rohan Gupta', 'rohan.g@apex.edu', '+91 98765 43212', cse_dept_id, cse_sec_b, 3, 'Male', 22, 65, 80, 5, 1, 38000, 10000, 'Partial'),
            ('APEX-24-004', 'Sneha Kapoor', 'sneha.k@apex.edu', '+91 98765 43213', it_dept_id, it_sec_a, 3, 'Female', 20, 195, 310, 55, 9, 36000, 36000, 'Paid'),
            ('APEX-24-005', 'Aditya Verma', 'aditya.v@apex.edu', '+91 98765 43214', it_dept_id, it_sec_a, 3, 'Male', 21, 40, 55, 2, 0, 36000, 0, 'Pending'),
            ('APEX-24-006', 'Pooja Nair', 'pooja.n@apex.edu', '+91 98765 43215', cse_dept_id, cse_sec_b, 3, 'Female', 20, 175, 260, 38, 7, 38000, 38000, 'Paid'),
            ('APEX-24-007', 'Kunal Deshmukh', 'kunal.d@apex.edu', '+91 98765 43216', cse_dept_id, cse_sec_a, 3, 'Male', 23, 50, 70, 4, 1, 38000, 15000, 'Partial'),
            ('APEX-24-008', 'Tanvi Joshi', 'tanvi.j@apex.edu', '+91 98765 43217', it_dept_id, it_sec_a, 3, 'Female', 20, 185, 280, 48, 8, 36000, 36000, 'Paid'),
        ]

        student_ids_a = []
        for s in uni_a_students_data:
            cursor.execute('''
                INSERT INTO students (university_id, student_id, full_name, email, phone, department_id, section_id,
                                      academic_year, semester, enrollment_date, enrollment_status, gender, age, logins, content_reads, forum_posts, quiz_reviews)
                VALUES (?, ?, ?, ?, ?, ?, ?, '2024-2025', ?, '2024-08-01', 'Active', ?, ?, ?, ?, ?, ?)
            ''', (uni_a_id, s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11], s[12]))
            st_id = cursor.lastrowid
            student_ids_a.append((st_id, s[0], s[1], s[13], s[14], s[15]))

            # Fee record
            total_fee = s[13]
            paid_fee = s[14]
            pending_fee = total_fee - paid_fee
            cursor.execute('''
                INSERT INTO fee_records (university_id, student_id, academic_year, total_fee, paid_amount, pending_amount, due_date, payment_status)
                VALUES (?, ?, '2024-2025', ?, ?, ?, '2024-11-30', ?)
            ''', (uni_a_id, st_id, total_fee, paid_fee, pending_fee, s[15]))
            fee_rec_id = cursor.lastrowid

            if paid_fee > 0:
                cursor.execute('''
                    INSERT INTO fee_payments (university_id, fee_record_id, amount, payment_date, payment_method, receipt_reference, notes)
                    VALUES (?, ?, ?, '2024-08-15', 'Bank Transfer', ?, 'First semester tuition fee')
                ''', (uni_a_id, fee_rec_id, paid_fee, f"REC-APEX-{st_id}-{s[0]}"))

        # Marks for Uni A students
        sample_marks = [
            (student_ids_a[0][0], sub_dsa, 27, 65, 92, 'A+', 1),
            (student_ids_a[0][0], sub_dbms, 26, 62, 88, 'A', 1),
            (student_ids_a[1][0], sub_dsa, 24, 52, 76, 'B+', 1),
            (student_ids_a[1][0], sub_dbms, 22, 50, 72, 'B', 1),
            (student_ids_a[2][0], sub_dsa, 12, 22, 34, 'F', 0), # Failed
            (student_ids_a[2][0], sub_dbms, 14, 24, 38, 'F', 0), # Failed
            (student_ids_a[3][0], sub_web, 28, 68, 96, 'O', 1),
            (student_ids_a[4][0], sub_web, 10, 18, 28, 'F', 0), # Failed
            (student_ids_a[5][0], sub_dsa, 25, 58, 83, 'A', 1),
            (student_ids_a[6][0], sub_dsa, 13, 23, 36, 'F', 0), # Failed
            (student_ids_a[7][0], sub_web, 27, 63, 90, 'A+', 1),
        ]
        for sm in sample_marks:
            pct = (sm[4] / 100.0) * 100.0
            cursor.execute('''
                INSERT INTO marks (university_id, student_id, subject_id, examination_id, internal_marks, external_marks,
                                   total_marks, max_marks, pass_marks, percentage, grade, is_pass)
                VALUES (?, ?, ?, ?, ?, ?, ?, 100.0, 40.0, ?, ?, ?)
            ''', (uni_a_id, sm[0], sm[1], exam_midterm_a, sm[2], sm[3], sm[4], pct, sm[5], sm[6]))

        # Attendance history for Uni A
        dates = ['2024-11-01', '2024-11-02', '2024-11-03', '2024-11-04', '2024-11-05']
        for d in dates:
            for idx, st in enumerate(student_ids_a):
                # High risk students have lots of Absents
                if idx in [2, 4, 6]:
                    stat = 'Absent' if d in ['2024-11-01', '2024-11-03', '2024-11-04'] else 'Present'
                else:
                    stat = 'Present'
                cursor.execute('''
                    INSERT INTO attendance (university_id, student_id, date, status, method)
                    VALUES (?, ?, ?, ?, 'manual')
                ''', (uni_a_id, st[0], d, stat))

        # Assignments for Uni A
        cursor.execute('''
            INSERT INTO assignments (university_id, department_id, subject_id, title, description, due_date, max_points)
            VALUES (?, ?, ?, 'Implementation of Red-Black Trees', 'Complete Java/C++ implementation and benchmark search complexity.', '2024-11-20', 100)
        ''', (uni_a_id, cse_dept_id, sub_dsa))
        asgn_1_a = cursor.lastrowid

        cursor.execute('''
            INSERT INTO assignments (university_id, department_id, subject_id, title, description, due_date, max_points)
            VALUES (?, ?, ?, 'Relational Database Schema Normalization (BCNF)', 'Normalize the provided E-commerce schema into 3NF and BCNF.', '2024-11-25', 100)
        ''', (uni_a_id, cse_dept_id, sub_dbms))
        asgn_2_a = cursor.lastrowid

        # Assignment Submissions
        cursor.execute('''
            INSERT INTO assignment_submissions (university_id, assignment_id, student_id, status, submitted_at, score, feedback)
            VALUES (?, ?, ?, 'Completed', '2024-11-18 14:30:00', 95.0, 'Exceptional tree balancing logic and clean code comments.')
        ''', (uni_a_id, asgn_1_a, student_ids_a[0][0]))

        cursor.execute('''
            INSERT INTO assignment_submissions (university_id, assignment_id, student_id, status, score, feedback)
            VALUES (?, ?, ?, 'Missing', 0.0, 'No submission received before deadline.')
        ''', (uni_a_id, asgn_1_a, student_ids_a[2][0]))

        # Achievements for Uni A
        cursor.execute('''
            INSERT INTO achievements (university_id, student_id, category, title, description, organizer, achievement_date)
            VALUES (?, ?, 'Hackathons', 'First Place - National Smart India Hackathon', 'Built an autonomous emergency drone dispatch system using OpenCV and Edge AI.', 'Ministry of Education', '2024-09-22')
        ''', (uni_a_id, student_ids_a[0][0]))

        cursor.execute('''
            INSERT INTO achievements (university_id, student_id, category, title, description, organizer, achievement_date)
            VALUES (?, ?, 'Certifications', 'AWS Certified Solutions Architect - Associate', 'Cleared certification with 890/1000 score.', 'Amazon Web Services', '2024-10-10')
        ''', (uni_a_id, student_ids_a[3][0]))

        # Risk predictions for Uni A
        cursor.execute('''
            INSERT INTO risk_predictions (university_id, student_id, risk_level, risk_score, reasons, recommended_action)
            VALUES (?, ?, 'Low Risk', 18.5, ?, 'Maintain current study rhythm. Encourage peer mentoring participation.')
        ''', (uni_a_id, student_ids_a[0][0], json.dumps(["High attendance rate: 96%", "Strong examination average: 90%", "Active forum participation", "All assignments submitted early"])))

        cursor.execute('''
            INSERT INTO risk_predictions (university_id, student_id, risk_level, risk_score, reasons, recommended_action)
            VALUES (?, ?, 'High Risk', 86.2, ?, 'Immediate academic counselor meeting required. Assign remedial coursework in DSA.')
        ''', (uni_a_id, student_ids_a[2][0], json.dumps(["Low attendance: 40% (critical alert)", "Failed 2 subjects (DSA: 34%, DBMS: 38%)", "Missing assignment 1", "Low portal engagement (5 forum posts)"])))

        cursor.execute('''
            INSERT INTO risk_predictions (university_id, student_id, risk_level, risk_score, reasons, recommended_action)
            VALUES (?, ?, 'High Risk', 89.0, ?, 'Parent notification and academic recovery contract recommended.')
        ''', (uni_a_id, student_ids_a[4][0], json.dumps(["Low attendance: 40%", "Failed Web Technologies (28%)", "Zero fee payment recorded", "Infrequent login activity"])))

        cursor.execute('''
            INSERT INTO risk_predictions (university_id, student_id, risk_level, risk_score, reasons, recommended_action)
            VALUES (?, ?, 'Medium Risk', 52.4, ?, 'Review consistency in internal test performances.')
        ''', (uni_a_id, student_ids_a[1][0], json.dumps(["Moderate attendance: 80%", "Pending fee installment", "Occasional late quiz submission"])))


        # 3. Registered University B: Pacific State University
        uni_b_id = 'UNI-PACIFIC'
        cursor.execute('''
            INSERT INTO universities (id, name, email, address, status, subscription_plan, approved_at, approved_by)
            VALUES (?, 'Pacific State University', 'contact@pacific.edu', '500 Ocean Avenue, Coastal City', 'active', 'Premium', ?, 'Platform Super Administrator')
        ''', (uni_b_id, now))

        pacific_admin_pass = generate_password_hash("PacificAdmin@123")
        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, permissions)
            VALUES (?, 'admin@pacific.edu', ?, 'Dr. Elizabeth Warren', 'university_admin', '["all"]')
        ''', (uni_b_id, pacific_admin_pass))

        pacific_staff_pass = generate_password_hash("Staff@123")
        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, department, permissions)
            VALUES (?, 'dr.williams@pacific.edu', ?, 'Dr. Robert Williams', 'staff', 'Mechanical Engineering', '["students", "attendance", "marks", "assignments", "fees", "achievements", "analytics"]')
        ''', (uni_b_id, pacific_staff_pass))

        # Departments for Uni B
        cursor.execute("INSERT INTO departments (university_id, code, name, head_of_dept) VALUES (?, 'MECH', 'Mechanical & Aerospace Engineering', 'Dr. Robert Williams')", (uni_b_id,))
        mech_dept_id = cursor.lastrowid
        cursor.execute("INSERT INTO departments (university_id, code, name, head_of_dept) VALUES (?, 'CIVIL', 'Civil & Environmental Engineering', 'Prof. Linda Gomez')", (uni_b_id,))
        civil_dept_id = cursor.lastrowid

        # Sections for Uni B
        cursor.execute("INSERT INTO sections (university_id, department_id, name, academic_year) VALUES (?, ?, 'Section M1', '2024-2025')", (uni_b_id, mech_dept_id))
        mech_sec_1 = cursor.lastrowid

        # Subjects for Uni B
        cursor.execute("INSERT INTO subjects (university_id, department_id, code, name, credits, semester) VALUES (?, ?, 'ME201', 'Thermodynamics & Heat Transfer', 4, 3)", (uni_b_id, mech_dept_id))
        sub_thermo = cursor.lastrowid

        # Examination for Uni B
        cursor.execute("INSERT INTO examinations (university_id, name, exam_type, academic_year, semester, exam_date) VALUES (?, 'Pacific Midterms Fall 2024', 'Midterm', '2024-2025', 3, '2024-10-18')", (uni_b_id,))
        exam_midterm_b = cursor.lastrowid

        # Students for Uni B
        cursor.execute('''
            INSERT INTO students (university_id, student_id, full_name, email, phone, department_id, section_id,
                                  academic_year, semester, enrollment_date, enrollment_status, gender, age, logins, content_reads, forum_posts, quiz_reviews)
            VALUES (?, 'PAC-24-101', 'Liam O''Connor', 'liam.oc@pacific.edu', '+1 415 555 0192', ?, ?, '2024-2025', 3, '2024-08-10', 'Active', 'Male', 21, 190, 275, 40, 8)
        ''', (uni_b_id, mech_dept_id, mech_sec_1))
        st_b1 = cursor.lastrowid

        cursor.execute('''
            INSERT INTO students (university_id, student_id, full_name, email, phone, department_id, section_id,
                                  academic_year, semester, enrollment_date, enrollment_status, gender, age, logins, content_reads, forum_posts, quiz_reviews)
            VALUES (?, 'PAC-24-102', 'Emma Watson', 'emma.w@pacific.edu', '+1 415 555 0193', ?, ?, '2024-2025', 3, '2024-08-10', 'Active', 'Female', 20, 75, 90, 10, 2)
        ''', (uni_b_id, mech_dept_id, mech_sec_1))
        st_b2 = cursor.lastrowid

        # Fees for Uni B
        cursor.execute('''
            INSERT INTO fee_records (university_id, student_id, academic_year, total_fee, paid_amount, pending_amount, due_date, payment_status)
            VALUES (?, ?, '2024-2025', 45000, 45000, 0, '2024-11-30', 'Paid')
        ''', (uni_b_id, st_b1))
        fee_b1 = cursor.lastrowid
        cursor.execute('''
            INSERT INTO fee_payments (university_id, fee_record_id, amount, payment_date, payment_method, receipt_reference, notes)
            VALUES (?, ?, 45000, '2024-08-12', 'Bank Transfer', 'REC-PAC-B1-001', 'Annual tuition fee paid in full')
        ''', (uni_b_id, fee_b1))

        cursor.execute('''
            INSERT INTO fee_records (university_id, student_id, academic_year, total_fee, paid_amount, pending_amount, due_date, payment_status)
            VALUES (?, ?, '2024-2025', 45000, 20000, 25000, '2024-11-30', 'Partial')
        ''', (uni_b_id, st_b2))

        # Marks for Uni B
        cursor.execute('''
            INSERT INTO marks (university_id, student_id, subject_id, examination_id, internal_marks, external_marks,
                               total_marks, max_marks, pass_marks, percentage, grade, is_pass)
            VALUES (?, ?, ?, ?, 28, 67, 95, 100.0, 40.0, 95.0, 'O', 1)
        ''', (uni_b_id, st_b1, sub_thermo, exam_midterm_b))

        # Attendance for Uni B
        for d in dates:
            cursor.execute('''
                INSERT INTO attendance (university_id, student_id, date, status, method)
                VALUES (?, ?, ?, 'Present', 'manual')
            ''', (uni_b_id, st_b1, d))
            cursor.execute('''
                INSERT INTO attendance (university_id, student_id, date, status, method)
                VALUES (?, ?, ?, ?, 'manual')
            ''', (uni_b_id, st_b2, d, 'Absent' if d == '2024-11-04' else 'Present'))

        # Achievements for Uni B
        cursor.execute('''
            INSERT INTO achievements (university_id, student_id, category, title, description, organizer, achievement_date)
            VALUES (?, ?, 'Sports', 'Gold Medal - Inter-University Rowing Championship', 'Skippered the men''s varsity eight to gold medal finish.', 'National Collegiate Sports Board', '2024-10-05')
        ''', (uni_b_id, st_b1))


        # 4. Pending University Registration: Nova Global University
        uni_c_id = 'UNI-NOVA'
        cursor.execute('''
            INSERT INTO universities (id, name, email, address, status, subscription_plan)
            VALUES (?, 'Nova Global University', 'info@novaglobal.edu', '88 Science Park Drive, Metro City', 'pending', 'Standard')
        ''', (uni_c_id,))

        nova_admin_pass = generate_password_hash("NovaAdmin@123")
        cursor.execute('''
            INSERT INTO users (university_id, email, password_hash, full_name, role, permissions)
            VALUES (?, 'admin@novaglobal.edu', ?, 'Dr. Alan Vance', 'university_admin', '["all"]')
        ''', (uni_c_id, nova_admin_pass))

        # 5. System Initial Audit Log
        cursor.execute('''
            INSERT INTO audit_logs (university_id, user_id, action, details, ip_address)
            VALUES (NULL, 1, 'SYSTEM_INITIALIZATION', 'UniTrack AI multi-university database initialized and seeded with demo accounts.', '127.0.0.1')
        ''')


def seed_trending_courses_and_batches():
    """Seeds BTech trending courses, batches, academic years, and sets student password hashes."""
    with db_session() as conn:
        cursor = conn.cursor()

        # Get all registered universities
        cursor.execute("SELECT id FROM universities")
        unis = [r[0] for r in cursor.fetchall()]
        if not unis:
            return

        trending_courses = [
            ('CSE', 'Computer Science Engineering', 'Core computing, algorithms, systems engineering and software architecture.', 120),
            ('AIML', 'Artificial Intelligence and Machine Learning', 'Deep learning, neural architectures, computer vision, natural language processing and agentic AI.', 90),
            ('DS', 'Data Science', 'Big data engineering, statistical modeling, distributed systems and business predictive analytics.', 90),
            ('CYBER', 'Cyber Security', 'Network defense, digital forensics, ethical hacking, cryptographic protocols and zero-trust systems.', 60),
            ('IT', 'Information Technology', 'Full-stack enterprise application development, database design and modern web platforms.', 90),
            ('CLOUD', 'Cloud Computing', 'Cloud-native infrastructure, DevOps automation, Kubernetes, microservices and serverless architectures.', 60),
            ('IOT', 'Internet of Things', 'Embedded sensor systems, smart devices, edge computing and industrial automation.', 60),
            ('ROBOT', 'Robotics and Automation', 'Kinematics, autonomous robotics, computer vision integration and industrial robotics control.', 60),
        ]

        sample_batches = [
            ('2023-2027', 2023, 2027),
            ('2024-2028', 2024, 2028),
            ('2025-2029', 2025, 2029),
            ('2026-2030', 2026, 2030),
            ('2027-2031', 2027, 2031),
            ('2028-2032', 2028, 2032),
        ]

        sample_ay = [
            ('2023-2024', 0),
            ('2024-2025', 1),
            ('2025-2026', 0),
            ('2026-2027', 0),
        ]

        for uid in unis:
            # Seed courses if empty
            cursor.execute("SELECT COUNT(*) FROM courses WHERE university_id = ?", (uid,))
            if cursor.fetchone()[0] == 0:
                for c in trending_courses:
                    cursor.execute("""
                        INSERT INTO courses (university_id, code, name, description, intake_capacity)
                        VALUES (?, ?, ?, ?, ?)
                    """, (uid, c[0], c[1], c[2], c[3]))

            # Seed batches if empty
            cursor.execute("SELECT COUNT(*) FROM batches WHERE university_id = ?", (uid,))
            if cursor.fetchone()[0] == 0:
                for b in sample_batches:
                    cursor.execute("""
                        INSERT INTO batches (university_id, name, start_year, end_year)
                        VALUES (?, ?, ?, ?)
                    """, (uid, b[0], b[1], b[2]))

            # Seed academic years if empty
            cursor.execute("SELECT COUNT(*) FROM academic_years WHERE university_id = ?", (uid,))
            if cursor.fetchone()[0] == 0:
                for ay in sample_ay:
                    cursor.execute("""
                        INSERT INTO academic_years (university_id, name, is_current)
                        VALUES (?, ?, ?)
                    """, (uid, ay[0], ay[1]))

        # Update any students with missing course_id, batch_name, admission_date, password_hash
        default_student_pwd = generate_password_hash("Student@123")
        cursor.execute("SELECT id, university_id, student_id, course_name, batch_name, password_hash FROM students")
        students = [dict(r) for r in cursor.fetchall()]

        # Distribute students across courses
        cursor.execute("SELECT id, name FROM courses WHERE university_id = 'UNI-APEX' ORDER BY id ASC")
        apex_courses = [dict(r) for r in cursor.fetchall()]

        for idx, s in enumerate(students):
            st_id = s['id']
            st_uni = s['university_id']
            
            c_id = None
            c_name = None
            if apex_courses and st_uni == 'UNI-APEX':
                chosen = apex_courses[idx % len(apex_courses)]
                c_id = chosen['id']
                c_name = chosen['name']
            else:
                cursor.execute("SELECT id, name FROM courses WHERE university_id = ? ORDER BY id ASC LIMIT 1", (st_uni,))
                crow = cursor.fetchone()
                if crow:
                    c_id = crow['id']
                    c_name = crow['name']

            cursor.execute("SELECT id, name FROM batches WHERE university_id = ? ORDER BY id ASC LIMIT 1", (st_uni,))
            brow = cursor.fetchone()
            b_id = brow['id'] if brow else None
            b_name = brow['name'] if brow else '2024-2028'

            cursor.execute("""
                UPDATE students
                SET course_id = COALESCE(course_id, ?),
                    course_name = COALESCE(course_name, ?),
                    batch_id = COALESCE(batch_id, ?),
                    batch_name = COALESCE(batch_name, ?),
                    admission_date = COALESCE(admission_date, '2024-08-01'),
                    password_hash = COALESCE(password_hash, ?)
                WHERE id = ?
            """, (c_id, c_name, b_id, b_name, default_student_pwd, st_id))


# Auto-initialize on import
init_db()
seed_demo_data()
seed_trending_courses_and_batches()
