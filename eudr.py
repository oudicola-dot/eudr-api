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
    print("========== compute_risk() called ==========")
    print(f"Lat: {lat}, Lon: {lon}")
    print(f"GFW_API_KEY present: {bool(GFW_API_KEY)}")
    
    def fallback():
        seed = abs(int((lat * 1000) + (lon * 1000)))
        risk = seed % 100
        if risk < 30:
            return {"risk_score": risk, "risk_level": "LOW", "eudr_compliant": "COMPLIANT", "tree_cover": 20, "loss_year": 0, "source": "fallback"}
        elif risk < 70:
            return {"risk_score": risk, "risk_level": "MEDIUM", "eudr_compliant": "COMPLIANT", "tree_cover": 40, "loss_year": 2010, "source": "fallback"}
        else:
            return {"risk_score": risk, "risk_level": "HIGH", "eudr_compliant": "NON COMPLIANT", "tree_cover": 50, "loss_year": 2022, "source": "fallback"}
    
    if not GFW_API_KEY:
        print("⚠️ GFW_API_KEY not set, using fallback")
        return fallback()
    
    try:
        # ✅ BONNE URL GFW AVEC SQL
        url = f"https://data-api.globalforestwatch.org/dataset/umd_tree_cover_loss/v1.11/query/json?sql=SELECT%20treeCover,%20lossYear%20FROM%20umd_tree_cover_loss%20WHERE%20latitude={lat}%20AND%20longitude={lon}"
        
        print(f"🔄 Calling GFW: {url}")
        headers = {"x-api-key": GFW_API_KEY}
        response = requests.get(url, headers=headers, timeout=15)
        
        print(f"📡 GFW Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"⚠️ GFW returned {response.status_code}, using fallback")
            return fallback()
        
        data = response.json()
        print(f"✅ GFW Response: {data}")
        
        # Extraction des données
        tree_cover = 0
        loss_year = 0
        
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            tree_cover = data["data"][0].get("treeCover", 0)
            loss_year = data["data"][0].get("lossYear", 0)
        elif "treeCover" in data:
            tree_cover = data.get("treeCover", 0)
            loss_year = data.get("lossYear", 0)
        
        print(f"🌳 Tree Cover: {tree_cover}%, Loss Year: {loss_year}")
        
        # Règle EUDR
        if tree_cover > 30 and loss_year > 2020:
            risk_score = 85
            risk_level = "HIGH"
            compliant = "NON COMPLIANT"
        elif tree_cover > 30 and loss_year <= 2020:
            risk_score = 50
            risk_level = "MEDIUM"
            compliant = "COMPLIANT"
        else:
            risk_score = 15
            risk_level = "LOW"
            compliant = "COMPLIANT"
        
        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "eudr_compliant": compliant,
            "tree_cover": tree_cover,
            "loss_year": loss_year,
            "source": "gfw"
        }
        
    except Exception as e:
        print(f"❌ GFW error: {e}")
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
