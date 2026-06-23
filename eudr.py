import uuid
import sqlite3
import hashlib
import hmac
import os
from datetime import datetime


# ----------------------------
# CONFIG
# ----------------------------

DB_PATH = "eudr.db"

# secret for signing (STEP 3 security layer)
SECRET = os.getenv("API_SECRET", "CHANGE_ME_SECRET")


# ----------------------------
# DB CONNECTION
# ----------------------------

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ----------------------------
# INIT DB
# ----------------------------

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


# ----------------------------
# RISK ENGINE
# ----------------------------

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


# ----------------------------
# CREATE AUDIT (CORE LOGIC)
# ----------------------------

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
        "status": "CREATED",
        "issuer": "Tierras de Montaña",
        "created_at": datetime.utcnow().isoformat()
    }

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        audit["audit_id"],
        audit["farm_name"],
        audit["latitude"],
        audit["longitude"],
        audit["risk_score"],
        audit["risk_level"],
        audit["status"],
        audit["issuer"],
        audit["created_at"]
    ))

    conn.commit()
    conn.close()

    return audit


# ----------------------------
# GET AUDIT
# ----------------------------

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


# ----------------------------
# SECURITY LAYER (STEP 3)
# ----------------------------

def sign_audit(audit_id: str) -> str:
    """
    Generates HMAC signature for QR security (anti-fake certificate)
    """
    return hmac.new(
        SECRET.encode(),
        audit_id.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_signature(audit_id: str, signature: str) -> bool:
    """
    Validates QR signature (prevents fake certificates)
    """
    expected = sign_audit(audit_id)
    return hmac.compare_digest(expected, signature)
