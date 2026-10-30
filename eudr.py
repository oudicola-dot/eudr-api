# v3.2 - FINAL: Double validation loss_percentage, positionnement screening strict
import uuid
import sqlite3
import os
import requests
import ee
import json
import math
from datetime import datetime
from security import sign_audit

DB_PATH = "eudr.db"
GFW_API_KEY = os.getenv("GFW_API_KEY")
DATASET_VERSION = "Hansen Global Forest Change 2023 v1.11 (2000-2023)"

# ========== EARTH ENGINE INITIALIZATION ==========
EE_PROJECT = os.getenv("EE_PROJECT", "superb-gear-473018-k1")
EE_INITIALIZED = False

try:
    cred_path = "/etc/secrets/earth-engine-credentials.json"
    if os.path.exists(cred_path):
        with open(cred_path, "r") as f:
            credentials_info = json.load(f)
        credentials = ee.ServiceAccountCredentials(credentials_info["client_email"], key_data=json.dumps(credentials_info))
        ee.Initialize(credentials, project=EE_PROJECT)
        EE_INITIALIZED = True
    else:
        credentials_json = os.getenv("EE_CREDENTIALS_JSON")
        if credentials_json:
            credentials_info = json.loads(credentials_json)
            credentials = ee.ServiceAccountCredentials(credentials_info["client_email"], key_data=credentials_json)
            ee.Initialize(credentials, project=EE_PROJECT)
            EE_INITIALIZED = True
        else:
            ee.Initialize(project=EE_PROJECT)
            EE_INITIALIZED = True
except Exception as e:
    print(f"⚠️ Earth Engine initialization failed: {e}")

# ========== DATABASE ==========
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS audits (
        audit_id TEXT PRIMARY KEY, farm_name TEXT, latitude REAL, longitude REAL,
        risk_score INTEGER, risk_level TEXT, eudr_compliant TEXT, tree_cover INTEGER,
        loss_year INTEGER, source TEXT, polygon_points TEXT, status TEXT,
        issuer TEXT, signature TEXT, created_at TEXT
    )
    """)
    c.execute("PRAGMA table_info(audits)")
    columns = [row[1] for row in c.fetchall()]
    if "dataset_version" not in columns:
        c.execute("ALTER TABLE audits ADD COLUMN dataset_version TEXT")
    conn.commit()
    conn.close()

# ========== GFW API ==========
def compute_risk_gfw(lat: float, lon: float):
    if not GFW_API_KEY: return None
    try:
        url = f"https://data-api.globalforestwatch.org/dataset/umd_tree_cover_density_2000/v1.6/query/json?sql=SELECT%20treeCover%20FROM%20umd_tree_cover_density_2000%20WHERE%20latitude={lat}%20AND%20longitude={lon}"
        response = requests.get(url, headers={"x-api-key": GFW_API_KEY}, timeout=10)
        if response.status_code != 200: return None
        data = response.json()
        
        tree_cover = None
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            tree_cover = data["data"][0].get("treeCover")
        elif "treeCover" in data:
            tree_cover = data.get("treeCover")

        if tree_cover is None or not isinstance(tree_cover, (int, float)): return None
        if not math.isfinite(tree_cover) or tree_cover < 0 or tree_cover > 100: return None
            
        return {"tree_cover": int(tree_cover), "source": "gfw"}
    except Exception:
        return None

# ========== EARTH ENGINE API ==========
def compute_risk_ee(lat: float, lon: float, polygon=None):
    if not EE_INITIALIZED: return None
    try:
        if polygon and len(polygon) >= 3:
            geometry = ee.Geometry.Polygon(polygon)
        else:
            geometry = ee.Geometry.Point(lon, lat).buffer(30)

        dataset = ee.Image('UMD/hansen/global_forest_change_2023_v1_11')
        
        treecover_val = dataset.select('treecover2000').reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometry, scale=30, maxPixels=1e9
        ).get('treecover2000').getInfo()
        
        if treecover_val is None or not isinstance(treecover_val, (int, float)) or not math.isfinite(treecover_val) or treecover_val < 0 or treecover_val > 100:
            tree_cover = -1
        else:
            tree_cover = int(round(treecover_val))

        valid_pixels = dataset.select('lossyear').reduceRegion(
            reducer=ee.Reducer.count(), geometry=geometry, scale=30, maxPixels=1e9
        ).get('lossyear').getInfo()

        if valid_pixels is None or not isinstance(valid_pixels, (int, float)) or not math.isfinite(valid_pixels) or valid_pixels <= 0 or tree_cover == -1:
            return {"tree_cover": tree_cover, "loss_percentage": -1, "last_loss_year": -1, "source": "ee", "insufficient_data": True}

        loss_hist = dataset.select('lossyear').reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(), geometry=geometry, scale=30, maxPixels=1e9
        ).get('lossyear').getInfo()

        if not isinstance(loss_hist, dict) or not loss_hist:
            return {"tree_cover": tree_cover, "loss_percentage": -1, "last_loss_year": -1, "source": "ee", "insufficient_data": True}

        try:
            histogram_pixels = 0
            post_2020_pixels = 0
            last_loss_year = 0

            for year_str, count in loss_hist.items():
                count_float = float(count)
                if not math.isfinite(count_float) or count_float < 0:
                    raise ValueError("Invalid count")
                
                year_int = int(year_str)
                if year_int < 0 or year_int > 23:
                    raise ValueError("Invalid year")
                
                histogram_pixels += count_float
                if year_int > 20:
                    post_2020_pixels += count_float
                if year_int > last_loss_year:
                    last_loss_year = year_int

            if not math.isfinite(histogram_pixels) or histogram_pixels <= 0 or abs(histogram_pixels - valid_pixels) > 0.01:
                raise ValueError("Histogram mismatch")

            loss_percentage = (post_2020_pixels / valid_pixels * 100)
            if not math.isfinite(loss_percentage) or loss_percentage < 0 or loss_percentage > 100:
                raise ValueError("Invalid percentage")

        except (TypeError, ValueError):
            return {"tree_cover": tree_cover, "loss_percentage": -1, "last_loss_year": -1, "source": "ee", "insufficient_data": True}

        return {
            "tree_cover": tree_cover, "loss_percentage": loss_percentage,
            "last_loss_year": 2000 + last_loss_year if last_loss_year > 0 else 0,
            "source": "ee", "insufficient_data": False
        }
    except Exception:
        return None

# ========== ORCHESTRATEUR ==========
def compute_risk(lat: float, lon: float, polygon=None):
    result = compute_risk_ee(lat, lon, polygon)
    if result:
        if result.get("insufficient_data"):
            return {"risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", "tree_cover": result["tree_cover"], "loss_year": -1, "source": result["source"], "dataset_version": DATASET_VERSION}

        loss_pct = result.get("loss_percentage")
        
        # Double validation (défense en profondeur)
        if loss_pct is None or not isinstance(loss_pct, (int, float)) or not math.isfinite(loss_pct) or loss_pct < 0 or loss_pct > 100:
            return {"risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", "tree_cover": result.get("tree_cover", -1), "loss_year": -1, "source": "ee", "dataset_version": DATASET_VERSION}

        if loss_pct > 5.0:
            risk_score, risk_level, status = 100, "HIGH", "POTENTIAL LOSS SIGNAL"
        elif loss_pct >= 1.0:
            risk_score, risk_level, status = 50, "MEDIUM", "POTENTIAL LOSS SIGNAL"
        elif loss_pct > 0.0:
            risk_score, risk_level, status = 10, "LOW", "BELOW TDM SCREENING THRESHOLD"
        else:
            risk_score, risk_level, status = 0, "LOW", "NO POST-2020 LOSS DETECTED"
            
        return {"risk_score": risk_score, "risk_level": risk_level, "eudr_status": status, "tree_cover": result["tree_cover"], "loss_year": result.get("last_loss_year", 0), "source": result["source"], "dataset_version": DATASET_VERSION}

    result = compute_risk_gfw(lat, lon)
    if result:
        return {"risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", "tree_cover": result["tree_cover"], "loss_year": -1, "source": result["source"], "dataset_version": DATASET_VERSION}

    return {"risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "ANALYSIS UNAVAILABLE", "tree_cover": -1, "loss_year": -1, "source": "fallback", "dataset_version": DATASET_VERSION}

# ========== AUDIT FUNCTIONS ==========
def create_audit(name: str, lat: float, lon: float, polygon=None):
    audit_id = str(uuid.uuid4())
    result = compute_risk(lat, lon, polygon)
    signature = sign_audit(audit_id)
    
    audit = {
        "audit_id": audit_id, "farm_name": name, "latitude": lat, "longitude": lon,
        "risk_score": result["risk_score"], "risk_level": result["risk_level"],
        "eudr_status": result["eudr_status"], "eudr_compliant": result["eudr_status"],
        "tree_cover": result["tree_cover"], "loss_year": result["loss_year"], "source": result["source"],
        "polygon_points": json.dumps(polygon) if polygon else None, "status": "CREATED", 
        "issuer": "Tierras de Montaña", "signature": signature, "created_at": datetime.utcnow().isoformat(),
        "dataset_version": result["dataset_version"]
    }

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO audits (
            audit_id, farm_name, latitude, longitude, risk_score, risk_level, eudr_compliant,
            tree_cover, loss_year, source, polygon_points, status, issuer, signature, created_at, dataset_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        audit["audit_id"], audit["farm_name"], audit["latitude"], audit["longitude"], audit["risk_score"], audit["risk_level"], audit["eudr_compliant"],
        audit["tree_cover"], audit["loss_year"], audit["source"], audit["polygon_points"], audit["status"], audit["issuer"], audit["signature"], audit["created_at"],
        audit["dataset_version"]
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
    if not row: return None
    ds_version = row[15] if len(row) > 15 and row[15] is not None else None
    return {
        "audit_id": row[0], "farm_name": row[1], "latitude": row[2], "longitude": row[3],
        "risk_score": row[4], "risk_level": row[5], "eudr_status": row[6], "eudr_compliant": row[6],
        "tree_cover": row[7], "loss_year": row[8], "source": row[9],
        "polygon_points": json.loads(row[10]) if row[10] else None,
        "status": row[11], "issuer": row[12], "signature": row[13], "created_at": row[14],
        "dataset_version": ds_version
    }
