import uuid
import sqlite3
import os
import requests
import ee
import json
import math
from datetime import datetime, timezone
from security import sign_audit
from shapely.geometry import Polygon
from pyproj import Geod

DB_PATH = "eudr.db"
GFW_API_KEY = os.getenv("GFW_API_KEY")
DATASET_VERSION = "Hansen Global Forest Change 2025 v1.13 (2000-2025)"
TDM_SCREENING_THRESHOLD_PCT = 5.0

_BUILD_COMMIT = os.getenv("RENDER_GIT_COMMIT", "dev-local")
BUILD_VERSION = "v2.7+" + (_BUILD_COMMIT[:7] if _BUILD_COMMIT != "dev-local" else "dev-local")
print(f"🚀 eudr.py START — build={BUILD_VERSION} — dataset={DATASET_VERSION}")

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


def _finite_number(value):
    """Retourne un float fini; refuse explicitement les booléens."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    try:
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
    finally:
        conn.close()


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
        if "data" in data and isinstance(data["data"], list) and data["data"]:
            tree_cover = data["data"][0].get("treeCover", 0)
        elif "treeCover" in data:
            tree_cover = data.get("treeCover", 0)
        return {"tree_cover_gfw_2000": tree_cover, "source": "gfw"}
    except Exception:
        return None


def compute_risk_ee(lat: float, lon: float, polygon=None):
    if not EE_INITIALIZED:
        return None

    hist_insufficient = False
    hist_reason = None
    loss_percentage = -1
    last_loss_year = -1
    loss_insufficient = False
    pixel_error_reason = None
    valid_pixels = None
    estimated_coverage_pct = None
    nominal_pixels_estimate = None
    treecover_reason = None
    tree_cover_mean_ee = -1

    try:
        if polygon is not None and len(polygon) >= 3:
            geometry = ee.Geometry.Polygon(polygon)
        else:
            geometry = ee.Geometry.Point(lon, lat).buffer(30)

        try:
            area_sq_m = _finite_number(geometry.area(maxError=1).getInfo())
            area_ha = area_sq_m / 10000.0 if area_sq_m is not None and area_sq_m > 0 else None
        except Exception as e:
            print(f"❌ Erreur calcul surface EE : {e}")
            area_ha = None

        dataset = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
        treecover = dataset.select("treecover2000")
        lossyear_raw = dataset.select("lossyear")
        datamask = dataset.select("datamask")

        # Masque territorial valide : terre cartographiée + observation treecover présente
        valid_land_mask = datamask.eq(1).And(treecover.mask()).rename("valid_land")
        # unmask(0) restaure lossyear=0 là où aucune perte n'est détectée,
        # updateMask limite aux terres valides (exclut eau permanente / no-data).
        lossyear = lossyear_raw.unmask(0).updateMask(valid_land_mask).rename("lossyear")

        treecover_val = _finite_number(
            treecover.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=geometry, scale=30, maxPixels=1e9
            ).get("treecover2000").getInfo()
        )

        if treecover_val is None or treecover_val < 0 or treecover_val > 100:
            tree_cover_mean_ee = -1
            treecover_reason = "TREECOVER_UNAVAILABLE"
        else:
            tree_cover_mean_ee = int(round(treecover_val))

        # Diagnostics uniquement : la source autoritaire est count() ci-dessous.
        mask_count = lossyear.mask().reduceRegion(
            reducer=ee.Reducer.sum().unweighted(), geometry=geometry, scale=30, maxPixels=1e9
        ).get("lossyear").getInfo()

        unmasked_count = lossyear.reduceRegion(
            reducer=ee.Reducer.count().unweighted(), geometry=geometry, scale=30, maxPixels=1e9
        ).get("lossyear").getInfo()

        zero_count = lossyear.eq(0).reduceRegion(
            reducer=ee.Reducer.sum().unweighted(), geometry=geometry, scale=30, maxPixels=1e9
        ).get("lossyear").getInfo()

        positive_count = lossyear.gt(0).reduceRegion(
            reducer=ee.Reducer.sum().unweighted(), geometry=geometry, scale=30, maxPixels=1e9
        ).get("lossyear").getInfo()

        print("=== HANSEN MASK DIAGNOSTIC ===")
        print("Mask sum:", mask_count)
        print("Unmasked count:", unmasked_count)
        print("Zero count:", zero_count)
        print("Positive count:", positive_count)
        print("=== END HANSEN MASK DIAGNOSTIC ===")

        valid_pixels_raw = unmasked_count
        if area_ha is not None:
            nominal_pixels_estimate = round((area_ha * 10000) / 900)

        valid_count = _finite_number(valid_pixels_raw)

        if (
            valid_count is None
            or valid_count < 0
            or abs(valid_count - round(valid_count)) > 1e-6
        ):
            loss_insufficient = True
            pixel_error_reason = "INVALID_VALID_PIXEL_COUNT"
        elif valid_count == 0:
            loss_insufficient = True
            valid_pixels = 0
            pixel_error_reason = "NO_VALID_LOSS_PIXELS"
        else:
            valid_pixels = int(round(valid_count))

        if loss_insufficient:
            loss_percentage = -1
            last_loss_year = -1
        else:
            if nominal_pixels_estimate is not None and nominal_pixels_estimate > 0:
                estimated_coverage_pct = round(
                    (valid_pixels / nominal_pixels_estimate) * 100, 2
                )

            loss_hist = lossyear.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram().unweighted(),
                geometry=geometry, scale=30, maxPixels=1e9
            ).get("lossyear").getInfo()

            if loss_hist is None or (isinstance(loss_hist, dict) and not loss_hist):
                hist_insufficient = True
                hist_reason = "HISTOGRAM_EMPTY_WITH_VALID_PIXELS"
            elif not isinstance(loss_hist, dict):
                hist_insufficient = True
                hist_reason = "HISTOGRAM_INVALID_TYPE"
            else:
                try:
                    histogram_pixels = 0.0
                    post_2020_pixels = 0.0
                    last_loss_year_idx = 0

                    for year_key, count_raw in loss_hist.items():
                        count_value = _finite_number(count_raw)
                        if (
                            count_value is None
                            or count_value < 0
                            or abs(count_value - round(count_value)) > 1e-6
                        ):
                            raise ValueError("INVALID_COUNT")

                        if isinstance(year_key, bool):
                            raise ValueError("INVALID_YEAR")
                        year_text = str(year_key).strip()
                        if not year_text.isdigit():
                            raise ValueError("INVALID_YEAR")

                        year_int = int(year_text)
                        if year_int > 25:
                            raise ValueError("INVALID_YEAR")

                        histogram_pixels += count_value
                        if year_int > 20:
                            post_2020_pixels += count_value
                        last_loss_year_idx = max(last_loss_year_idx, year_int)

                    if (
                        not math.isfinite(histogram_pixels)
                        or histogram_pixels <= 0
                        or abs(histogram_pixels - valid_pixels) > 0.01
                    ):
                        raise ValueError("HISTOGRAM_MISMATCH")

                    loss_percentage = (post_2020_pixels / valid_pixels) * 100
                    if not math.isfinite(loss_percentage) or not 0 <= loss_percentage <= 100:
                        raise ValueError("INVALID_PERCENTAGE")

                    last_loss_year = 2000 + last_loss_year_idx if last_loss_year_idx > 0 else 0

                except (TypeError, ValueError, OverflowError) as e:
                    hist_insufficient = True
                    reason = str(e)
                    allowed = {
                        "HISTOGRAM_MISMATCH", "INVALID_PERCENTAGE",
                        "INVALID_YEAR", "INVALID_COUNT"
                    }
                    hist_reason = reason if reason in allowed else "INVALID_DATA"
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

        coverage = _finite_number(result.get("estimated_coverage_pct"))
        if coverage is None or coverage < TDM_SCREENING_THRESHOLD_PCT:
            return {
                "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA",
                "tree_cover": result["tree_cover_mean_ee"], "loss_year": -1, "source": result["source"],
                "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
                "tree_cover_mean_ee": result["tree_cover_mean_ee"], "tree_cover_gfw_2000": None,
                "valid_pixels": result["valid_pixels"], "nominal_pixels_estimate": result["nominal_pixels_estimate"],
                "estimated_coverage_pct": coverage,
                "insufficient_reason": "COVERAGE_BELOW_5_PCT", "treecover_reason": result["treecover_reason"]
            }

        loss_pct = _finite_number(result.get("loss_percentage"))
        if loss_pct is None or loss_pct < 0 or loss_pct > 100:
            return {
                "risk_score": -1, "risk_level": "UNAVAILABLE", "eudr_status": "INSUFFICIENT DATA",
                "tree_cover": result.get("tree_cover_mean_ee", -1), "loss_year": -1,
                "source": result.get("source", "ee"), "dataset_version": DATASET_VERSION,
                "_build": BUILD_VERSION, "tree_cover_mean_ee": result.get("tree_cover_mean_ee", -1),
                "tree_cover_gfw_2000": None, "valid_pixels": result.get("valid_pixels"),
                "nominal_pixels_estimate": result.get("nominal_pixels_estimate"),
                "estimated_coverage_pct": result.get("estimated_coverage_pct"),
                "insufficient_reason": "INVALID_LOSS_PERCENTAGE",
                "treecover_reason": result.get("treecover_reason")
            }

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
            "tree_cover": result["tree_cover_mean_ee"], "loss_year": result["last_loss_year"],
            "source": result["source"], "dataset_version": DATASET_VERSION, "_build": BUILD_VERSION,
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
        "issuer": "Tierras de Montaña", "signature": signature,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": result["dataset_version"],
        "valid_pixels": result.get("valid_pixels"),
        "nominal_pixels_estimate": result.get("nominal_pixels_estimate"),
        "estimated_coverage_pct": result.get("estimated_coverage_pct"),
        "insufficient_reason": result.get("insufficient_reason"),
        "treecover_reason": result.get("treecover_reason"),
        "build_version": result.get("_build", BUILD_VERSION)
    }

    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO audits (
                audit_id, farm_name, latitude, longitude, risk_score, risk_level, eudr_compliant,
                tree_cover, loss_year, source, polygon_points, status, issuer, signature, created_at,
                dataset_version, valid_pixels, nominal_pixels_estimate, estimated_coverage_pct,
                insufficient_reason, treecover_reason, build_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            audit["audit_id"], audit["farm_name"], audit["latitude"], audit["longitude"],
            audit["risk_score"], audit["risk_level"], audit["eudr_compliant"], audit["tree_cover"],
            audit["loss_year"], audit["source"], audit["polygon_points"], audit["status"],
            audit["issuer"], audit["signature"], audit["created_at"], audit["dataset_version"],
            audit["valid_pixels"], audit["nominal_pixels_estimate"], audit["estimated_coverage_pct"],
            audit["insufficient_reason"], audit["treecover_reason"], audit["build_version"]
        ))
        conn.commit()
    finally:
        conn.close()

    return audit


def get_audit(audit_id: str):
    conn = get_conn()
    row = None
    try:
        c = conn.cursor()
        c.execute("""
            SELECT
                audit_id, farm_name, latitude, longitude, risk_score, risk_level, eudr_compliant,
                tree_cover, loss_year, source, polygon_points, status, issuer, signature, created_at,
                dataset_version, valid_pixels, nominal_pixels_estimate, estimated_coverage_pct,
                insufficient_reason, treecover_reason, build_version
            FROM audits WHERE audit_id=?
        """, (audit_id,))
        row = c.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return {
        "audit_id": row[0], "farm_name": row[1], "latitude": row[2], "longitude": row[3],
        "risk_score": row[4], "risk_level": row[5], "eudr_status": row[6], "eudr_compliant": row[6],
        "tree_cover": row[7], "loss_year": row[8], "source": row[9],
        "polygon_points": json.loads(row[10]) if row[10] else None,
        "status": row[11], "issuer": row[12], "signature": row[13], "created_at": row[14],
        "dataset_version": row[15], "valid_pixels": row[16],
        "nominal_pixels_estimate": row[17], "estimated_coverage_pct": row[18],
        "insufficient_reason": row[19], "treecover_reason": row[20], "build_version": row[21]
    }
