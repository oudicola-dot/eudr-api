import uuid
import sqlite3
from datetime import datetime

DB_PATH = "eudr.db"


# ---------------- DB CONNECTION ----------------

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ---------------- INIT DB ----------------

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS audits (
        audit_id TEXT PRIMARY KEY,
        farm_name TEXT,
        latitude REAL,
        longitude REAL,
        risk_score INTEGER,
        risk_level TEXT,
        status TEXT,
        issuer TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# ---------------- RISK ENGINE ----------------

def compute_risk(lat: float, lon: float):
    seed = abs(int((lat * 1000) + (lon * 1000)))
    risk = seed % 100

    if risk < 30:
        level = "LOW"
    elif risk < 70:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return risk, level


# ---------------- CREATE AUDIT ----------------

def create_audit(name: str, lat: float, lon: float):

    audit_id = str(uuid.uuid4())
    risk_score, risk_level = compute_risk(lat, lon)

    audit = {
        "audit_id": audit_id,
        "farm_name": name,
        "latitude": lat,
        "longitude": lon,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "status": "PRELIMINARY_RECORD",
        "issuer": "Tierras de Montaña",
        "created_at": datetime.utcnow().isoformat()
    }

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)
    """, tuple(audit.values()))

    conn.commit()
    conn.close()

    return audit


# ---------------- GET AUDIT ----------------

def get_audit(audit_id: str):

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM audits WHERE audit_id=?", (audit_id,))
    row = c.fetchone()

    conn.close()

    if not row:
        return None

    return {
        "audit_id": row[0],
        "farm_name": row[1],
        "latitude": row[2],
        "longitude": row[3],
        "risk_score": row[4],
        "risk_level": row[5],
        "status": row[6],
        "issuer": row[7],
        "created_at": row[8]
    }
