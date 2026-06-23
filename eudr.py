import uuid
import sqlite3
import os
import requests
from datetime import datetime
from security import sign_audit

DB_PATH = "eudr.db"
GFW_API_KEY = os.getenv("GFW_API_KEY")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

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
        eudr_compliant TEXT,
        tree_cover INTEGER,
        loss_year INTEGER,
        status TEXT,
        issuer TEXT,
        signature TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def compute_risk(lat: float, lon: float):

    print("################################")
    print("COMPUTE_RISK EXECUTED")
    print("################################")

    def fallback():
        return {
            "risk_score": 50,
            "risk_level": "MEDIUM",
            "eudr_compliant": "COMPLIANT",
            "tree_cover": 0,
            "loss_year": 0,
            "source": "fallback"
        }

    print("========== GFW DEBUG ==========")
    print("GFW_API_KEY =", GFW_API_KEY)

    if not GFW_API_KEY:
        print("NO GFW API KEY FOUND")
        return fallback()

    try:

        print("LAT:", lat)
        print("LON:", lon)

        response = requests.get(
            "https://data-api.globalforestwatch.org",
            headers={
                "x-api-key": GFW_API_KEY
            },
            timeout=10
        )

        print("STATUS:", response.status_code)
        print("BODY:")
        print(response.text[:3000])

    except Exception as e:

        print("DEBUG ERROR:", str(e))

    print("========== END DEBUG ==========")

    return fallback()

def create_audit(name: str, lat: float, lon: float):
    audit_id = str(uuid.uuid4())
    result = compute_risk(lat, lon)
    signature = sign_audit(audit_id)
    
    audit = {
        "audit_id": audit_id,
        "farm_name": name,
        "latitude": lat,
        "longitude": lon,
        "risk_score": result["risk_score"],
        "risk_level": result["risk_level"],
        "eudr_compliant": result["eudr_compliant"],
        "tree_cover": result.get("tree_cover", 0),
        "loss_year": result.get("loss_year", 0),
        "status": "CREATED",
        "issuer": "Tierras de Montaña",
        "signature": signature,
        "created_at": datetime.utcnow().isoformat()
    }
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        audit["audit_id"],
        audit["farm_name"],
        audit["latitude"],
        audit["longitude"],
        audit["risk_score"],
        audit["risk_level"],
        audit["eudr_compliant"],
        audit["tree_cover"],
        audit["loss_year"],
        audit["status"],
        audit["issuer"],
        audit["signature"],
        audit["created_at"]
    ))
    conn.commit()
    conn.close()
    
    return audit

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
        "eudr_compliant": row[6],
        "tree_cover": row[7],
        "loss_year": row[8],
        "status": row[9],
        "issuer": row[10],
        "signature": row[11],
        "created_at": row[12]
    }
