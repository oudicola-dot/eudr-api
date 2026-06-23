import uuid
import sqlite3
from datetime import datetime

DB_PATH = "eudr.db"


# ----------------------------
# INIT DB
# ----------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
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


init_db()


# ----------------------------
# RISK ENGINE (stable deterministic)
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
# CREATE AUDIT (SaaS CORE)
# ----------------------------

def create_audit(api_key, expected_key, name, lat, lon):

    if api_key != expected_key:
        return None, "INVALID_API_KEY"

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

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        audit_id,
        name,
        lat,
        lon,
        risk_score,
        risk_level,
        audit["status"],
        audit["issuer"],
        audit["created_at"]
    ))

    conn.commit()
    conn.close()

    return audit, None


# ----------------------------
# GET AUDIT (REAL QUERY DB)
# ----------------------------

def get_audit(audit_id: str):

    conn = sqlite3.connect(DB_PATH)
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
