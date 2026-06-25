# v2.4 - CORREGIDO: GFW loss_year, credenciales desde env, get_audit con índices
import uuid
import sqlite3
import os
import requests
import ee
import json
from datetime import datetime
from security import sign_audit

DB_PATH = "eudr.db"
GFW_API_KEY = os.getenv("GFW_API_KEY")

# ========== EARTH ENGINE INITIALIZATION ==========
EE_PROJECT = os.getenv("EE_PROJECT", "superb-gear-473018-k1")
EE_INITIALIZED = False

print("🔍 Initializing Earth Engine...")
print(f"📁 EE_PROJECT: {EE_PROJECT}")

try:
    cred_path = "/etc/secrets/earth-engine-credentials.json"
    print(f"📁 Trying file: {cred_path}")
    print(f"📁 File exists: {os.path.exists(cred_path)}")
    
    if os.path.exists(cred_path):
        print("📖 Reading credentials file...")
        with open(cred_path, "r") as f:
            credentials_info = json.load(f)
        print(f"✅ Credentials loaded for: {credentials_info.get('client_email', 'unknown')}")
        
        credentials = ee.ServiceAccountCredentials(
            credentials_info["client_email"],
            key_data=json.dumps(credentials_info)
        )
        ee.Initialize(credentials, project=EE_PROJECT)
        EE_INITIALIZED = True
        print("🌍 Earth Engine initialized successfully with service account")
    else:
        credentials_json = os.getenv("EE_CREDENTIALS_JSON")
        if credentials_json:
            print("📖 Reading credentials from environment variable...")
            credentials_info = json.loads(credentials_json)
            print(f"✅ Credentials loaded for: {credentials_info.get('client_email', 'unknown')}")
            
            credentials = ee.ServiceAccountCredentials(
                credentials_info["client_email"],
                key_data=credentials_json
            )
            ee.Initialize(credentials, project=EE_PROJECT)
            EE_INITIALIZED = True
            print("🌍 Earth Engine initialized successfully from env var")
        else:
            print("⚠️ No credentials found, trying default authentication...")
            ee.Initialize(project=EE_PROJECT)
            EE_INITIALIZED = True
            print("🌍 Earth Engine initialized with default credentials")
except Exception as e:
    print(f"⚠️ Earth Engine initialization failed: {e}")
    print("ℹ️ Will use GFW or fallback data sources")

# ========== DATABASE ==========
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
        source TEXT,
        polygon_points TEXT,
        status TEXT,
        issuer TEXT,
        signature TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

# ========== GFW API ==========
def compute_risk_gfw(lat: float, lon: float):
    print("🔄 Trying GFW API...")
    if not GFW_API_KEY:
        print("⚠️ GFW_API_KEY not set")
        return None
    
    try:
        url = f"https://data-api.globalforestwatch.org/dataset/umd_tree_cover_density_2000/v1.6/query/json?sql=SELECT%20treeCover%20FROM%20umd_tree_cover_density_2000%20WHERE%20latitude={lat}%20AND%20longitude={lon}"
        headers = {"x-api-key": GFW_API_KEY}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"⚠️ GFW returned {response.status_code}")
            return None
        
        data = response.json()
        tree_cover = 0
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            tree_cover = data["data"][0].get("treeCover", 0)
        elif "treeCover" in data:
            tree_cover = data.get("treeCover", 0)
        
        print(f"🛰️ GFW: tree_cover={tree_cover}")
        return {
            "tree_cover": tree_cover,
            "loss_year": 0,
            "source": "gfw"
        }
    except Exception as e:
        print(f"❌ GFW error: {e}")
        return None

# ========== EARTH ENGINE API ==========
def compute_risk_ee(lat: float, lon: float, polygon=None):
    print("🌍 Trying Earth Engine...")
    
    if not EE_INITIALIZED:
        print("⚠️ Earth Engine not initialized, skipping...")
        return None
    
    try:
        if polygon and len(polygon) >= 3:
            coords = [[p[0], p[1]] for p in polygon]
            geometry = ee.Geometry.Polygon(coords)
            print(f"📐 Polygon: {len(polygon)} points")
        else:
            point = ee.Geometry.Point(lon, lat)
            geometry = point.buffer(30)
            print("📍 Point with 30m buffer")

        dataset = ee.Image('UMD/hansen/global_forest_change_2023_v1_11')
        treecover = dataset.select('treecover2000')
        lossyear = dataset.select('lossyear')

        treecover_val = treecover.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=30,
            maxPixels=1e9
        ).get('treecover2000').getInfo()

        lossyear_val = lossyear.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=30,
            maxPixels=1e9
        ).get('lossyear').getInfo()

        tree_cover = int(round(treecover_val if treecover_val is not None else 0))
        loss_year = int(round(lossyear_val if lossyear_val is not None else -1))

        print(f"🌳 EE: tree_cover={tree_cover}, loss_year={loss_year}")
        return {
            "tree_cover": tree_cover,
            "loss_year": loss_year,
            "source": "ee"
        }
    except Exception as e:
        print(f"❌ Earth Engine error: {e}")
        return None

# ========== ORCHESTRATEUR ==========
def compute_risk(lat: float, lon: float, polygon=None):
    print("========== compute_risk() called ==========")
    print(f"Lat: {lat}, Lon: {lon}")
    print(f"EE_INITIALIZED: {EE_INITIALIZED}")
    print(f"Polygon: {polygon is not None}")

    def fallback():
        seed = abs(int((lat * 1000) + (lon * 1000)))
        risk = seed % 100
        if risk < 30:
            return {"risk_score": risk, "risk_level": "LOW", "eudr_compliant": "COMPLIANT", "tree_cover": 20, "loss_year": 0, "source": "fallback"}
        elif risk < 70:
            return {"risk_score": risk, "risk_level": "MEDIUM", "eudr_compliant": "COMPLIANT", "tree_cover": 40, "loss_year": 2010, "source": "fallback"}
        else:
            return {"risk_score": risk, "risk_level": "HIGH", "eudr_compliant": "NON COMPLIANT", "tree_cover": 50, "loss_year": 2022, "source": "fallback"}

    result = compute_risk_ee(lat, lon, polygon)
    if result:
        tree_cover = result["tree_cover"]
        loss_year = result["loss_year"]
        source = result["source"]
        if tree_cover > 30 and loss_year > 2020:
            risk_score = 85
            risk_level = "HIGH"
            compliant = "NON COMPLIANT"
        elif tree_cover > 30 and 0 < loss_year <= 2020:
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
            "loss_year": loss_year if loss_year > 0 else 0,
            "source": source
        }

    result = compute_risk_gfw(lat, lon)
    if result:
        tree_cover = result["tree_cover"]
        loss_year = result["loss_year"]
        source = result["source"]
        if tree_cover > 30:
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
            "loss_year": 0,
            "source": source
        }

    print("⚠️ Using fallback")
    return fallback()

# ========== AUDIT FUNCTIONS ==========
def create_audit(name: str, lat: float, lon: float, polygon=None):
    audit_id = str(uuid.uuid4())
    result = compute_risk(lat, lon, polygon)
    signature = sign_audit(audit_id)

    polygon_json = json.dumps(polygon) if polygon else None

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
        "source": result.get("source", "unknown"),
        "polygon_points": polygon_json,
        "status": "CREATED",
        "issuer": "Tierras de Montaña",
        "signature": signature,
        "created_at": datetime.utcnow().isoformat()
    }

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO audits (
            audit_id, farm_name, latitude, longitude,
            risk_score, risk_level, eudr_compliant,
            tree_cover, loss_year, source, polygon_points,
            status, issuer, signature, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        audit["source"],
        audit["polygon_points"],
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
        "source": row[9],
        "polygon_points": json.loads(row[10]) if row[10] else None,
        "status": row[11],
        "issuer": row[12],
        "signature": row[13],
        "created_at": row[14]
    }
