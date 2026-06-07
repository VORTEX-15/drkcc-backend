from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import psycopg2.extras
import os
from dotenv import load_dotenv

from database import get_connection, init_db
from firebase_auth import init_firebase, get_current_user, create_firebase_user, delete_firebase_user

load_dotenv()
init_firebase()

app = FastAPI(title="Dr KCC Academy API", version="1.0.0")

# CORS — allow your frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

# ─────────────────────────────────────────
# PYDANTIC MODELS (request body shapes)
# ─────────────────────────────────────────

class CreateUserBody(BaseModel):
    name: str
    email: str
    password: str
    role: str  # admin / teacher / student
    batch: Optional[str] = None
    roll: Optional[str] = None

class NoticeBody(BaseModel):
    title: str
    body: Optional[str] = ""
    audience: Optional[str] = "all"

class AttendanceRecord(BaseModel):
    student_id: str
    student_name: str
    roll: Optional[str] = ""
    status: str  # P / A / L

class AttendanceBody(BaseModel):
    batch: str
    subject: str
    date: str
    records: List[AttendanceRecord]

class MarksRecord(BaseModel):
    student_id: str
    student_name: str
    roll: Optional[str] = ""
    marks_obtained: int
    grade: Optional[str] = ""
    remarks: Optional[str] = ""

class MarksBody(BaseModel):
    batch: str
    test_name: str
    max_marks: int
    records: List[MarksRecord]

class TimetableBody(BaseModel):
    day: str
    time_slot: str
    subject: str
    teacher_name: Optional[str] = ""
    batch: str

class TopperBody(BaseModel):
    name: str
    rank_achieved: str
    college: Optional[str] = ""
    year: Optional[str] = ""
    photo_url: Optional[str] = ""

class SiteStatsBody(BaseModel):
    enrolled: Optional[int] = None
    years_running: Optional[int] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    admission_status: Optional[str] = None

class EnrollDeltaBody(BaseModel):
    delta: int  # +1 or -1

# ─────────────────────────────────────────
# HELPER — require admin role
# ─────────────────────────────────────────
async def require_admin(user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT role FROM users WHERE id = %s", (user['uid'],))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or row['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admins only")
    return user

async def require_teacher_or_admin(user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT role FROM users WHERE id = %s", (user['uid'],))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or row['role'] not in ('admin', 'teacher'):
        raise HTTPException(status_code=403, detail="Teachers or Admins only")
    return user

# ─────────────────────────────────────────
# ROOT
# ─────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "Dr KCC Academy API is running 🚀"}

# ─────────────────────────────────────────
# AUTH — get role for redirect
# ─────────────────────────────────────────
@app.get("/api/me")
def get_me(user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, name, email, role, batch, roll FROM users WHERE id = %s", (user['uid'],))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found in database")
    return dict(row)

# ─────────────────────────────────────────
# USERS
# ─────────────────────────────────────────
@app.post("/api/users/create")
def create_user(body: CreateUserBody, admin=Depends(require_admin)):
    # Validate role
    if body.role not in ('admin', 'teacher', 'student'):
        raise HTTPException(status_code=400, detail="Invalid role")

    # Check duplicate email in DB
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))
    if cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=400, detail=f"Email '{body.email}' already exists")

    # Check duplicate roll number for students
    if body.role == 'student' and body.roll:
        cur.execute("SELECT id FROM users WHERE roll = %s", (body.roll,))
        if cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=400, detail=f"Roll number '{body.roll}' already exists. Roll numbers must be unique.")

    # Create in Firebase Auth (server-side, admin session unaffected)
    uid = create_firebase_user(body.email, body.password)

    # Save to PostgreSQL
    try:
        cur.execute(
            "INSERT INTO users (id, name, email, role, batch, roll) VALUES (%s, %s, %s, %s, %s, %s)",
            (uid, body.name, body.email, body.role, body.batch, body.roll)
        )

        # Auto-increment enrolled count if student
        if body.role == 'student':
            cur.execute("UPDATE site_stats SET enrolled = enrolled + 1 WHERE id = 1")

        conn.commit()
    except Exception as e:
        conn.rollback()
        delete_firebase_user(uid)  # Rollback Firebase too
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()

    return {"success": True, "uid": uid, "message": f"User '{body.name}' created as {body.role}"}


@app.get("/api/users")
def get_users(role: Optional[str] = None, admin=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if role:
        cur.execute("SELECT id, name, email, role, batch, roll, created_at FROM users WHERE role = %s ORDER BY created_at DESC", (role,))
    else:
        cur.execute("SELECT id, name, email, role, batch, roll, created_at FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]


@app.delete("/api/users/{uid}")
def delete_user(uid: str, admin=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT role FROM users WHERE id = %s", (uid,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))
        # Auto-decrement count if student
        if row['role'] == 'student':
            cur.execute("UPDATE site_stats SET enrolled = GREATEST(enrolled - 1, 0) WHERE id = 1")
        conn.commit()
    except Exception as e:
        conn.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()

    delete_firebase_user(uid)
    return {"success": True, "message": "User deleted"}

# ─────────────────────────────────────────
# NOTICES
# ─────────────────────────────────────────
@app.get("/api/notices")
def get_notices(user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM notices ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@app.post("/api/notices")
def post_notice(body: NoticeBody, user=Depends(require_teacher_or_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO notices (title, body, audience, created_by) VALUES (%s, %s, %s, %s) RETURNING *",
        (body.title, body.body, body.audience, user['email'])
    )
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return dict(row)

@app.delete("/api/notices/{notice_id}")
def delete_notice(notice_id: int, user=Depends(require_teacher_or_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notices WHERE id = %s", (notice_id,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}

# ─────────────────────────────────────────
# TIMETABLE
# ─────────────────────────────────────────
@app.get("/api/timetable")
def get_timetable(batch: Optional[str] = None, user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if batch:
        cur.execute("SELECT * FROM timetable WHERE batch = %s ORDER BY day, time_slot", (batch,))
    else:
        cur.execute("SELECT * FROM timetable ORDER BY day, time_slot")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@app.post("/api/timetable")
def add_timetable(body: TimetableBody, user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO timetable (day, time_slot, subject, teacher_name, batch) VALUES (%s,%s,%s,%s,%s) RETURNING *",
        (body.day, body.time_slot, body.subject, body.teacher_name, body.batch)
    )
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return dict(row)

@app.delete("/api/timetable/{entry_id}")
def delete_timetable(entry_id: int, user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM timetable WHERE id = %s", (entry_id,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}

# ─────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────
@app.post("/api/attendance")
def submit_attendance(body: AttendanceBody, user=Depends(require_teacher_or_admin)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for rec in body.records:
            cur.execute(
                """INSERT INTO attendance 
                   (student_id, student_name, roll, date, subject, status, batch, teacher_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (rec.student_id, rec.student_name, rec.roll,
                 body.date, body.subject, rec.status,
                 body.batch, user['uid'])
            )
        conn.commit()
    except Exception as e:
        conn.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
    return {"success": True, "message": f"Attendance saved for {len(body.records)} students"}

@app.get("/api/attendance/{student_id}")
def get_student_attendance(student_id: str, user=Depends(get_current_user)):
    # Students can only see their own
    if user['uid'] != student_id:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT role FROM users WHERE id = %s", (user['uid'],))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row or row['role'] not in ('admin', 'teacher'):
            raise HTTPException(status_code=403, detail="Access denied")

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM attendance WHERE student_id = %s ORDER BY date DESC",
        (student_id,)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@app.get("/api/attendance/batch/{batch}")
def get_batch_attendance(batch: str, user=Depends(require_teacher_or_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM attendance WHERE batch = %s ORDER BY date DESC", (batch,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

# ─────────────────────────────────────────
# MARKS
# ─────────────────────────────────────────
@app.post("/api/marks")
def submit_marks(body: MarksBody, user=Depends(require_teacher_or_admin)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for rec in body.records:
            cur.execute(
                """INSERT INTO marks
                   (student_id, student_name, roll, test_name, marks_obtained,
                    max_marks, grade, remarks, batch, teacher_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (rec.student_id, rec.student_name, rec.roll,
                 body.test_name, rec.marks_obtained, body.max_marks,
                 rec.grade, rec.remarks, body.batch, user['uid'])
            )
        conn.commit()
    except Exception as e:
        conn.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
    return {"success": True, "message": f"Marks saved for {len(body.records)} students"}

@app.get("/api/marks/{student_id}")
def get_student_marks(student_id: str, user=Depends(get_current_user)):
    if user['uid'] != student_id:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT role FROM users WHERE id = %s", (user['uid'],))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row or row['role'] not in ('admin', 'teacher'):
            raise HTTPException(status_code=403, detail="Access denied")

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM marks WHERE student_id = %s ORDER BY created_at DESC", (student_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

# ─────────────────────────────────────────
# TOPPERS
# ─────────────────────────────────────────
@app.get("/api/toppers")
def get_toppers():  # Public — no auth needed
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM toppers ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@app.post("/api/toppers")
def add_topper(body: TopperBody, user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO toppers (name, rank_achieved, college, year, photo_url) VALUES (%s,%s,%s,%s,%s) RETURNING *",
        (body.name, body.rank_achieved, body.college, body.year, body.photo_url)
    )
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return dict(row)

@app.delete("/api/toppers/{topper_id}")
def delete_topper(topper_id: int, user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM toppers WHERE id = %s", (topper_id,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}

# ─────────────────────────────────────────
# SITE STATS (enrolled count, website info)
# ─────────────────────────────────────────
@app.get("/api/site/stats")
def get_site_stats():  # Public — shown on index.html
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM site_stats WHERE id = 1")
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else {}

@app.patch("/api/site/stats")
def update_site_stats(body: SiteStatsBody, user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    updates = []
    values = []
    if body.enrolled is not None: updates.append("enrolled = %s"); values.append(body.enrolled)
    if body.years_running is not None: updates.append("years_running = %s"); values.append(body.years_running)
    if body.phone is not None: updates.append("phone = %s"); values.append(body.phone)
    if body.email is not None: updates.append("email = %s"); values.append(body.email)
    if body.address is not None: updates.append("address = %s"); values.append(body.address)
    if body.admission_status is not None: updates.append("admission_status = %s"); values.append(body.admission_status)
    if updates:
        cur.execute(f"UPDATE site_stats SET {', '.join(updates)} WHERE id = 1", values)
        conn.commit()
    cur.close(); conn.close()
    return {"success": True}

@app.post("/api/site/enrolled/adjust")
def adjust_enrolled(body: EnrollDeltaBody, user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("UPDATE site_stats SET enrolled = GREATEST(enrolled + %s, 0) WHERE id = 1 RETURNING enrolled", (body.delta,))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return {"enrolled": row['enrolled']}
