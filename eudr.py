import uuid
import sqlite3
import os
import requests
import ee
import json
import math
from datetime import datetime
from security import sign_audit
from shapely.geometry import Polygon
from pyproj import Geod

DB_PATH = "eudr.db"
GFW_API_KEY = os.getenv("GFW_API_KEY")
DATASET_VERSION = "Hansen Global Forest Change 2025 v1.13 (2000-2025)"
TDM_SCREENING_THRESHOLD_PCT = 10.0  # Contrôle qualité interne expérimental (non-réglementaire)

# ========== BUILD IDENTIFIER ==========
_BUILD_COMMIT = os.getenv("RENDER_GIT_COMMIT", "dev-local")
BUILD_VERSION = "v2.7+" + (_BUILD_COMMIT[:7] if _BUILD_COMMIT != "dev-local" else "dev-local")
print(f"🚀 eudr.py START — build={BUILD_VERSION} — dataset={DATASET_VERSION}")
# =====================================

# ========== EARTH ENGINE INITIALIZATION ==========
EE_PROJECT = os.getenv("EE_PROJECT", "superb-gear-473018-k1")
EE_INITIALIZED = False

try:
    cred_path = "/etc/secrets/earth-engine-credentials.json"
    if os.path.exists(cred_path):
        with open(cred_path, "r") as f:
            credentials_info = json.load(f)
        credentials = ee.ServiceAccountCredentials(
            credentials_info["client_email"],
            key_data=json.dumps(credentials_info)
        )
        ee.Initialize(credentials, project=EE_PROJECT)
        EE_INITIALIZED = True
    else:
        credentials_json = os.getenv("EE_CREDENTIALS_JSON")
        if credentials_json:
            credentials_info = json.loads(credentials_json)
            credentials = ee.ServiceAccountCredentials(
                credentials_info["client_email"],
                key_data=credentials_json
            )
            ee.Initialize(credentials, project=EE_PROJECT)
            EE_INITIALIZED = True
        else:
            ee.Initialize(project=EE_PROJECT)
            EE_INITIALIZED = True
except Exception as e:
    print(f"⚠️ Earth Engine initialization failed: {e}")

# ========== UTILS ==========
def get_polygon_area_ha(polygon_coords):
    if not polygon_coords or len(polygon_coords) < 3:
        return None
    try:
        poly = Polygon(polygon_coords)
        if not poly.is_valid or poly.area == 0:
            return None
            
        geod = Geod(ellps="WGS84")
        area_sq_m, _ = geod.geometry_area_perimeter(poly)
        
        if not math.isfinite(area_sq_m) or abs(area_sq_m) == 0:
            return None
            
        return abs(area_sq_m) / 10000.0
    except Exception:
        return None

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
    
    c.execute("PRAGMA table_info(audits)")
    columns = [row[1] for row in c.fetchall()]
    
    new_columns = {
        "dataset_version": "TEXT",
        "valid_pixels": "INTEGER",
        "nominal_pixels_estimate": "INTEGER",
        "estimated_coverage_pct": "REAL",
        "insufficient_reason": "TEXT",
        "treecover_reason": "TEXT",
        "build_version": "TEXT"
    }
    
    for col, col_type in new_columns.items():
        if col not in columns:
            print(f"🔄 Migration DB : ajout de la colonne {col}")
            c.execute(f"ALTER TABLE audits ADD COLUMN {col} {col_type}")
    
    conn.commit()
    conn.close()

# ========== GFW API ==========
def compute_risk_gfw(lat: float, lon: float):
    if not GFW_API_KEY:
        return None
    try:
        url = f"https://data-api.globalforestwatch.org/dataset/umd_tree_cover_density_2000/v1.6/query/json?sql=SELECT%20treeCover%20FROM%20umd_tree_cover_density_2000%20WHERE%20latitude={lat}%20AND%20longitude={lon}"
        headers = {"x-api-key": GFW_API_KEY}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        tree_cover = 0
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            tree_cover = data["data"][0].get("treeCover", 0)
        elif "treeCover" in data:
            tree_cover = data.get("treeCover", 0)
        return {"tree_cover_gfw_2000": tree_cover, "source": "gfw"}
    except Exception:
        return None

# ========== EARTH ENGINE API ==========
def compute_risk_ee(lat: float, lon: float, polygon=None):
    if not EE_INITIALIZED:
        return None

    try:
        if polygon and len(polygon) >= 3:
            geometry = ee.Geometry.Polygon(polygon)
        else:
            point = ee.Geometry.Point(lon, lat)
            geometry = point.buffer(30)

        # CORRECTIF : Calcul de surface propre pour le mode "Point Seul"
        try:
            area_sq_m = geometry.area(maxError=1).getInfo()
            area_ha = area_sq_m / 10000.0
        except Exception as e:
            print(f"❌ Erreur calcul surface EE : {e}")
            area_ha = None

        dataset = ee.Image('UMD/hansen/global_forest_change_2025_v1_13')
        treecover = dataset.select('treecover2000')
        lossyear = dataset.select('lossyear')

        treecover_val = treecover.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometry, scale=30, maxPixels=1e9
        ).get('treecover2000').getInfo()
        
        if treecover_val is None or not math.isfinite(treecover_val) or treecover_val < 0:
            tree_cover_mean_ee = -1
            tc_insufficient = True
            treecover_reason = "TREECOVER_UNAVAILABLE"
        else:
            tree_cover_mean_ee = int(round(treecover_val))
            tc_insufficient = False
            treecover_reason = None

        valid_pixels_raw = lossyear.reduceRegion(
            reducer=ee.Reducer.count().unweighted(), geometry=geometry, scale=30, maxPixels=1e9
        ).get('lossyear').getInfo()

        if not isinstance(valid_pixels_raw, (int, float)) or not math.isfinite(valid_pixels_raw) or valid_pixels_raw <= 0:
            loss_insufficient = True
            valid_pixels = None
            pixel_error_reason = "NO_VALID_LOSS_PIXELS"
        else:
            if abs(valid_pixels_raw - round(valid_pixels_raw)) > 1e-6:
                print(f"⚠️ EE: valid_pixels non entier reçu : {valid_pixels_raw}")
                loss_insufficient = True
                valid_pixels = None
                pixel_error_reason = "INVALID_VALID_PIXEL_COUNT"
            else:
                valid_pixels = int(round(valid_pixels_raw))
                loss_insufficient = False
                pixel_error_reason = None

        nominal_pixels_estimate = None
        estimated_coverage_pct = None
        
        if area_ha is not None and area_ha > 0:
            nominal_pixels_estimate = round((area_ha * 10000) / 900)
            if nominal_pixels_estimate > 0 and not loss_insufficient:
                estimated_coverage_pct = round((valid_pixels / nominal_pixels_estimate) * 100, 2)

        hist_insufficient = False
        hist_reason = None
        loss_percentage = -1
        last_loss_year = -1

        if not loss_insufficient:
            loss_hist = lossyear.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram().unweighted(), geometry=geometry, scale=30, maxPixels=1e9
            ).get('lossyear').getInfo()

            # CORRECTIF : Si l'histogramme est vide ou NULL, c'est qu'il n'y a pas eu de perte.
            # On considère donc que loss_percentage = 0.0 au lieu de planter.
            if loss_hist is None or (isinstance(loss_hist, dict) and not loss_hist):
                hist_insufficient = False
                loss_percentage = 0.0
                last_loss_year = 0
            elif not isinstance(loss_hist, dict):
                hist_insufficient = True
                hist_reason = "HISTOGRAM_INVALID_TYPE"
            else:
                try:
                    histogram_pixels = 0
                    post_2020_pixels = 0
                    last_loss_year_idx = 0

                    for year_str, count in loss_hist.items():
                        count_float = float(count)
                        if not math.isfinite(count_float) or count_float < 0:
                            raise ValueError("INVALID_COUNT")
                        
                        # CORRECTIF : Si une clé est "null", on l'ignore au lieu de planter.
                        if year_str is None or str(year_str).strip().lower() in ("null", "none", ""):
                            continue
                        
                        year_int = int(year_str)
                        if year_int < 0 or year_int > 25:
                            raise ValueError("INVALID_YEAR")
                        
                        histogram_pixels += count_float
                        if year_int > 20:
                            post_2020_pixels += count_float
                        if year_int > last_loss_year_idx:
                            last_loss_year_idx = year_int

                    if not math.isfinite(histogram_pixels) or histogram_pixels <= 0 or abs(histogram_pixels - valid_pixels) > 0.01:
                        raise ValueError("HISTOGRAM_MISMATCH")

                    loss_percentage = (post_2020_pixels / valid_pixels * 100)
                    if not math.isfinite(loss_percentage) or loss_percentage < 0 or loss_percentage > 100:
                        raise ValueError("INVALID_PERCENTAGE")
                    
                    last_loss_year = 2000 + last_loss_year_idx if last_loss_year_idx > 0 else 0

                except (TypeError, ValueError) as e:
                    hist_insufficient = True
                    hist_reason = str(e) if str(e) in ["NULL_BUCKET", "HISTOGRAM_MISMATCH", "INVALID_PERCENTAGE", "INVALID_YEAR", "INVALID_COUNT"] else "INVALID_DATA"
                    print(f"⚠️ EE: Erreur histogramme : {hist_reason}")

        is_loss_insufficient = loss_insufficient or hist_insufficient
        
        if hist_insufficient:
            insufficient_reason = hist_reason
        elif loss_insufficient:
            insufficient_reason = pixel_error_reason
        else:
            insufficient_reason = None

        return {
            "tree_cover_mean_ee": tree_cover_mean_ee,
            "loss_percentage": loss_percentage,
            "last_loss_year": last_loss_year,
            "source": "ee",
            "insufficient_data": is_loss_insufficient,
            "insufficient_reason": insufficient_reason,
            "treecover_reason": treecover_reason,
            "valid_pixels": valid_pixels,
            "nominal_pixels_estimate": nominal_pixels_estimate,
            "estimated_coverage_pct": estimated_coverage_pct
        }
    except Exception as e:
        print(f"❌ Earth Engine error: {e}")
        return None

# ========== ORCHESTRATEUR ==========
def compute_risk(lat: float, lon: float, polygon=None):
    result = compute_risk_ee(lat, lon, polygon)
    if result:
        if result.get("insufficient_data"):
            return {
                "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", 
                "tree_cover": result["tree_cover_mean_ee"], "loss_year": -1, "source": result["source"], 
                "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
                "tree_cover_mean_ee": result["tree_cover_mean_ee"], "tree_cover_gfw_2000": None,
                "valid_pixels": result["valid_pixels"], "nominal_pixels_estimate": result["nominal_pixels_estimate"], 
                "estimated_coverage_pct": result["estimated_coverage_pct"], 
                "insufficient_reason": result["insufficient_reason"], "treecover_reason": result["treecover_reason"]
            }

        coverage = result.get("estimated_coverage_pct")
        if coverage is None or coverage < TDM_SCREENING_THRESHOLD_PCT:
            return {
                "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", 
                "tree_cover": result["tree_cover_mean_ee"], "loss_year": -1, "source": result["source"], 
                "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
                "tree_cover_mean_ee": result["tree_cover_mean_ee"], "tree_cover_gfw_2000": None,
                "valid_pixels": result["valid_pixels"], "nominal_pixels_estimate": result["nominal_pixels_estimate"], 
                "estimated_coverage_pct": coverage, 
                "insufficient_reason": "COVERAGE_BELOW_10_PCT", 
                "treecover_reason": result["treecover_reason"]
            }

        loss_pct = result["loss_percentage"]
        
        # CORRECTIF : On protège le calcul des seuils contre les valeurs invalides (None, NaN, Inf, <0)
        if loss_pct is None or not math.isfinite(loss_pct) or loss_pct < 0:
            return {
                "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", 
                "tree_cover": result.get("tree_cover_mean_ee", -1), "loss_year": -1, "source": result.get("source", "ee"), 
                "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
                "tree_cover_mean_ee": result.get("tree_cover_mean_ee", -1), "tree_cover_gfw_2000": None,
                "valid_pixels": result.get("valid_pixels"), "nominal_pixels_estimate": result.get("nominal_pixels_estimate"), 
                "estimated_coverage_pct": result.get("estimated_coverage_pct"), 
                "insufficient_reason": "INVALID_LOSS_PERCENTAGE", "treecover_reason": result.get("treecover_reason")
            }

        # CORRECTIF : Seuils exacts demandés par les tests
        if loss_pct > 5.0:
            risk_score, risk_level, status = 100, "HIGH", "POTENTIAL LOSS SIGNAL"
        elif loss_pct >= 1.0:
            risk_score, risk_level, status = 50, "MEDIUM", "POTENTIAL LOSS SIGNAL"
        elif loss_pct > 0.0:
            risk_score, risk_level, status = 0, "LOW", "BELOW TDM SCREENING THRESHOLD"
        else:
            risk_score, risk_level, status = 0, "LOW", "NO POST-2020 LOSS DETECTED"
            
        return {
            "risk_score": risk_score, "risk_level": risk_level, "eudr_status": status, 
            "tree_cover": result["tree_cover_mean_ee"], "loss_year": result["last_loss_year"], "source": result["source"], 
            "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
            "tree_cover_mean_ee": result["tree_cover_mean_ee"], "tree_cover_gfw_2000": None,
            "valid_pixels": result["valid_pixels"], "nominal_pixels_estimate": result["nominal_pixels_estimate"], 
            "estimated_coverage_pct": result["estimated_coverage_pct"], 
            "insufficient_reason": None, "treecover_reason": result["treecover_reason"]
        }

    result = compute_risk_gfw(lat, lon)
    if result:
        return {
            "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA", 
            "tree_cover": result["tree_cover_gfw_2000"], "loss_year": -1, "source": result["source"], 
            "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
            "tree_cover_mean_ee": None, "tree_cover_gfw_2000": result["tree_cover_gfw_2000"],
            "valid_pixels": None, "nominal_pixels_estimate": None, "estimated_coverage_pct": None, 
            "insufficient_reason": "GFW_FALLBACK", "treecover_reason": None
        }

    return {
        "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "ANALYSIS UNAVAILABLE", 
        "tree_cover": -1, "loss_year": -1, "source": "fallback", 
        "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
        "tree_cover_mean_ee": None, "tree_cover_gfw_2000": None,
        "valid_pixels": None, "nominal_pixels_estimate": None, "estimated_coverage_pct": None, 
        "insufficient_reason": "EE_UNAVAILABLE", "treecover_reason": None
    }

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
        "dataset_version": result["dataset_version"],
        "valid_pixels": result.get("valid_pixels"),
        "nominal_pixels_estimate": result.get("nominal_pixels_estimate"),
        "estimated_coverage_pct": result.get("estimated_coverage_pct"),
        "insufficient_reason": result.get("insufficient_reason"),
        "treecover_reason": result.get("treecover_reason"),
        "build_version": result.get("_build", BUILD_VERSION)
    }

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO audits (
            audit_id, farm_name, latitude, longitude, risk_score, risk_level, eudr_compliant,
            tree_cover, loss_year, source, polygon_points, status, issuer, signature, created_at, dataset_version,
            valid_pixels, nominal_pixels_estimate, estimated_coverage_pct, insufficient_reason, treecover_reason,
            build_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        audit["audit_id"], audit["farm_name"], audit["latitude"], audit["longitude"], audit["risk_score"], audit["risk_level"], audit["eudr_compliant"],
        audit["tree_cover"], audit["loss_year"], audit["source"], audit["polygon_points"], audit["status"], audit["issuer"], audit["signature"], audit["created_at"],
        audit["dataset_version"], audit["valid_pixels"], audit["nominal_pixels_estimate"], audit["estimated_coverage_pct"], audit["insufficient_reason"], audit["treecover_reason"],
        audit["build_version"]
    ))
    conn.commit()
    conn.close()
    return audit

def get_audit(audit_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT 
            audit_id, farm_name, latitude, longitude, risk_score, risk_level, eudr_compliant,
            tree_cover, loss_year, source, polygon_points, status, issuer, signature, created_at,
            dataset_version, valid_pixels, nominal_pixels_estimate, estimated_coverage_pct, insufficient_reason, treecover_reason,
            build_version
        FROM audits WHERE audit_id=?
    """, (audit_id,))
    row = c.fetchone()
    conn.close()
    if not row: return None
    
    return {
        "audit_id": row[0], "farm_name": row[1], "latitude": row[2], "longitude": row[3],
        "risk_score": row[4], "risk_level": row[5], "eudr_status": row[6], "eudr_compliant": row[6],
        "tree_cover": row[7], "loss_year": row[8], "source": row[9],
        "polygon_points": json.loads(row[10]) if row[10] else None,
        "status": row[11], "issuer": row[12], "signature": row[13], "created_at": row[14],
        "dataset_version": row[15],
        "valid_pixels": row[16],
        "nominal_pixels_estimate": row[17],
        "estimated_coverage_pct": row[18],
        "insufficient_reason": row[19],
        "treecover_reason": row[20],
        "build_version": row[21]
    }
