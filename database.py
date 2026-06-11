import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            role VARCHAR(20) NOT NULL CHECK (role IN ('admin','teacher','student')),
            batch VARCHAR(50),
            roll VARCHAR(20) UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS notices (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            body TEXT,
            audience VARCHAR(20) DEFAULT 'all',
            created_by VARCHAR(100),
            created_by_name VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            student_id VARCHAR NOT NULL,
            student_name VARCHAR(100),
            roll VARCHAR(20),
            date DATE NOT NULL,
            subject VARCHAR(100),
            status CHAR(1) CHECK (status IN ('P','A','L')),
            batch VARCHAR(50),
            teacher_id VARCHAR,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS marks (
            id SERIAL PRIMARY KEY,
            student_id VARCHAR NOT NULL,
            student_name VARCHAR(100),
            roll VARCHAR(20),
            test_name VARCHAR(200) NOT NULL,
            marks_obtained INTEGER NOT NULL,
            max_marks INTEGER NOT NULL,
            grade VARCHAR(5),
            remarks TEXT,
            batch VARCHAR(50),
            teacher_id VARCHAR,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS timetable (
            id SERIAL PRIMARY KEY,
            day VARCHAR(20) NOT NULL,
            time_slot VARCHAR(50) NOT NULL,
            subject VARCHAR(100) NOT NULL,
            teacher_name VARCHAR(100),
            batch VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS toppers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            rank_achieved VARCHAR(200),
            college VARCHAR(200),
            year VARCHAR(10),
            photo_url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS site_stats (
            id INTEGER PRIMARY KEY DEFAULT 1,
            enrolled INTEGER DEFAULT 0,
            years_running INTEGER DEFAULT 1,
            phone VARCHAR(20),
            email VARCHAR(100),
            address TEXT,
            admission_status VARCHAR(20) DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS absence_messages (
            id SERIAL PRIMARY KEY,
            student_id VARCHAR NOT NULL,
            student_name VARCHAR(100),
            batch VARCHAR(50),
            teacher_id VARCHAR,
            subject VARCHAR(100),
            date DATE,
            reason TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            subject VARCHAR(100),
            exam_date DATE NOT NULL,
            exam_time VARCHAR(50),
            batch VARCHAR(50) NOT NULL,
            description TEXT,
            created_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );

        INSERT INTO site_stats (id, enrolled, years_running)
        VALUES (1, 0, 1)
        ON CONFLICT (id) DO NOTHING;
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized!")
