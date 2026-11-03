import os
import io
import html
import math
import uuid
import time
import qrcode
import requests

from datetime import datetime, timedelta, timezone

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER

from security import sign_audit
from shapely.geometry import Polygon
from pyproj import Geod, Transformer 
from eudr import get_audit
import eudr

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    print("⚠️ Pillow non installé.")
    HAS_PIL = False

try:
    import ee
    HAS_EE = True
except ImportError:
    print("⚠️ earthengine-api non importable.")
    HAS_EE = False

BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")
LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"
EXPECTED_DATASET = "Hansen Global Forest Change 2025 v1.13 (2000-2025)"
EXPECTED_EE_ASSET = "UMD/hansen/global_forest_change_2025_v1_13"

TDM_GREEN = colors.HexColor("#1E3A32")
TDM_LIGHT_GREEN = colors.HexColor("#E8F2E8")
TDM_GRAY = colors.HexColor("#F5F5F5")

_EE_CONFIRMED = False

_nominatim_cache_positive = {}   
_nominatim_cache_blocked = set() 
_nominatim_last_call = [0.0]
_NOMINATIM_MIN_INTERVAL_S = 1.0   
_NOMINATIM_GLOBAL_BUDGET_S = 20.0 

def _nominatim_rate_limit():
    now = time.monotonic()
    elapsed = now - _nominatim_last_call[0]
    if elapsed < _NOMINATIM_MIN_INTERVAL_S:
        time.sleep(_NOMINATIM_MIN_INTERVAL_S - elapsed)
    _nominatim_last_call[0] = time.monotonic()

EN = {
    "title": "EUDR TERRITORIAL TRACEABILITY<br/>&amp; DUE DILIGENCE SUPPORT REPORT",
    "report_id": "Report ID",
    "generated_on": "Generated on",
    "producer": "Producer / Farm",
    "centroid": "Centroid",
    "total_area": "Total Area",
    "boundary_points": "Boundary points",
    "point_mode": "Point mode",
    "map_unavailable": "Satellite parcel map unavailable",
    "tree_cover": "TREE COVER",
    "last_loss": "LAST DETECTED LOSS<br/>(2001–2025)",
    "risk_score": "RISK SCORE",
    "screening_status": "SCREENING STATUS",
    "disclaimer_title": "THIS REPORT IS A TERRITORIAL SCREENING, NOT A CERTIFICATE",
    "disclaimer_text": "This document provides a technical traceability and documentation support report. It is not a certificate of compliance with the EU Deforestation Regulation (EUDR) and does not replace the legal Due Diligence required by the operator or the relevant authorities.",
    "annex_title": "TECHNICAL ASSESSMENT ANNEX",
    "data_methodology": "Data &amp; Methodology",
    "data_source": "Data Source",
    "dataset_version": "Dataset Version",
    "engine_build": "Engine Build",
    "baseline": "Baseline tree-cover reference: 2000",
    "observation": "Annual forest-loss observation period: 2001–2025",
    "eudr_date": "EUDR Reference Date: 31 Dec 2020",
    "resolution": "Hansen Global Forest Change v1.13: approximately 30 m spatial resolution",
    "satellite": "Satellite Imagery: Esri World Imagery (High Resolution)",
    "cloud_note": "Note: cloud percentage shown on satellite maps is the global scene metric, not a cloud-cover measurement over the parcel.",
    "method_note": "Methodological note: Hansen v1.13 includes methodological reprocessing of forest-loss data from 2011 onward. Comparisons between observations before and after 2011 should therefore be interpreted with care.",
    "screening_note": "Interpretation: Hansen forest-loss observations are screening indicators. They do not independently establish a legal determination of deforestation under the EUDR.",
    "metrics_title": "Screening Quality & Coverage Metrics",
    "coverage": "Valid Pixel Ratio<br/>(observed / theoretical)",
    "valid_pixels": "Valid Pixels",
    "nominal_pixels": "Nominal Pixels (Estimate)",
    "insufficient_reason": "Insufficiency Reason",
    "geospatial_data": "Geospatial Data (Polygon)",
    "territorial_context": "TERRITORIAL CONTEXT",
    "verify_at": "Verify at",
    "status_no_loss": "NO POST-2020 LOSS DETECTED",
    "status_potential": "POTENTIAL LOSS SIGNAL",
    "status_below_threshold": "BELOW TDM SCREENING THRESHOLD",
    "status_inconclusive": "SCREENING INCONCLUSIVE",
    "status_unavailable": "ANALYSIS UNAVAILABLE",
    "status_unknown": "UNKNOWN STATUS",
    "no_loss_detected": "No loss detected",
    "treecover_avail": "Treecover Availability",
    "point": "Point",
    "lat": "Latitude",
    "lon": "Longitude",
    "limited_obs_title": "SCREENING INCONCLUSIVE — Limited Valid Observations",
    "limited_obs_text": "The available geospatial observations were insufficient to establish a reliable forest-loss assessment for this parcel.<br/><br/>This result does not indicate zero forest loss, nor does it establish EUDR compliance. <b>Territorial assessment — Additional verification required.</b>",
    "limited_obs_note": "<i>Note: The Valid Pixel Ratio indicates the relative number of valid Hansen observations for this parcel compared to a theoretical estimate. It is not a measure of geographic coverage or forest-loss rate. The 5% threshold is an internal TDM data-quality control, not an EUDR regulatory threshold.</i>",
    "osm_place": "OSM Place",
    "osm_town": "OSM Town",
    "osm_city": "OSM City",
    "osm_municipality": "Municipality",
    "osm_region": "Region",
    "osm_country": "Country",
    "source_nominatim": "Source: Nominatim, OpenStreetMap",
    "err_no_coords": "No coordinates",
    "err_map_failed": "Map generation failed"
}

def t(key):
    return EN.get(key, key)

IMAGE_PRESETS = {
    "standard": {"parcel_buffer_m": 300, "parcel_size": (1200, 800), "context_buffer_m": 2500, "context_size": (1200, 800)},
    "zoom": {"parcel_buffer_m": 150, "parcel_size": (1000, 700), "context_buffer_m": 1500, "context_size": (1200, 800)},
    "wide": {"parcel_buffer_m": 600, "parcel_size": (1400, 900), "context_buffer_m": 4000, "context_size": (1200, 800)},
}
DEFAULT_PRESET = "standard"

def resolve_preset(name):
    return IMAGE_PRESETS.get(name) or IMAGE_PRESETS[DEFAULT_PRESET]

def get_logo():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        r = requests.get(LOGO_URL, timeout=8, headers=headers)
        r.raise_for_status()
        if not r.headers.get("Content-Type", "").startswith("image/"): return None
        if HAS_PIL:
            try:
                img = PILImage.open(io.BytesIO(r.content))
                img.verify()
                return io.BytesIO(r.content)
            except Exception: return None
        return io.BytesIO(r.content)
    except Exception: return None

def get_custom_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TDMTitle", parent=styles["Heading1"], fontSize=14, leading=18, textColor=TDM_GREEN, fontName="Helvetica-Bold", alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="TDMLabel", parent=styles["Normal"], fontSize=8, textColor=colors.gray, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="TDMValue", parent=styles["Normal"], fontSize=9, textColor=colors.black, fontName="Helvetica"))
    styles.add(ParagraphStyle(name="TDMSection", parent=styles["Heading2"], fontSize=12, textColor=TDM_GREEN, fontName="Helvetica-Bold", spaceAfter=10))
    styles.add(ParagraphStyle(name="TDMLegal", parent=styles["Normal"], fontSize=7, textColor=colors.gray, fontName="Helvetica"))
    styles.add(ParagraphStyle(name="TDMDisclaimer", parent=styles["Normal"], fontSize=8, textColor=TDM_GREEN, fontName="Helvetica-Bold", alignment=TA_CENTER))
    return styles

def format_val(val, suffix="", min_val=0, max_val=100):
    if (isinstance(val, bool) or val is None or not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < min_val or val > max_val): return "N/A"
    return f"{val}{suffix}"

def format_loss_year(val):
    if (isinstance(val, bool) or val is None or not isinstance(val, (int, float))): return "N/A"
    if not math.isfinite(val) or not float(val).is_integer(): return "N/A"
    year = int(val)
    if year == 0: return "No loss detected"
    if 2001 <= year <= 2025: return str(year)
    return "N/A"

def get_loss_display(status, loss_year):
    if status in ("INSUFFICIENT DATA", "ANALYSIS UNAVAILABLE", "UNKNOWN STATUS", "SCREENING INCONCLUSIVE"): return "N/A"
    return format_loss_year(loss_year)

def _make_box(lat, lon, size_m=100):
    delta_deg = (size_m / 2) / 111320.0
    return [[lon - delta_deg, lat - delta_deg], [lon + delta_deg, lat - delta_deg], [lon + delta_deg, lat + delta_deg], [lon - delta_deg, lat + delta_deg], [lon - delta_deg, lat - delta_deg]]

def calculate_geometry(polygon_points):
    if not polygon_points or len(polygon_points) < 3: return "N/A", "N/A"
    try:
        poly = Polygon(polygon_points)
        if not poly.is_valid: return "Invalid geometry", "N/A"
        centroid = poly.centroid
        geod = Geod(ellps="WGS84")
        area_sq_m, _ = geod.geometry_area_perimeter(poly)
        return f"{centroid.y:.6f}, {centroid.x:.6f}", f"{abs(area_sq_m) / 10000.0:.2f} ha"
    except Exception: return "Calculation error", "N/A"

def _init_ee():
    global _EE_CONFIRMED
    if not HAS_PIL or not HAS_EE: return False
    if _EE_CONFIRMED: return True
    if not bool(getattr(eudr, "EE_INITIALIZED", False)): return False
    try:
        ee.Number(0).getInfo()
        _EE_CONFIRMED = True
        return True
    except Exception: return False

def get_territorial_context(lat, lon):
    try:
        key = (round(float(lat), 4), round(float(lon), 4))
    except (TypeError, ValueError):
        print("[nominatim] key=invalid state=invalid_input")
        return None

    if key in _nominatim_cache_positive:
        print(f"[nominatim] key={key} state=positive cache_hit=True")
        return _nominatim_cache_positive[key]

    if key in _nominatim_cache_blocked:
        print(f"[nominatim] key={key} state=blocked cache_hit=True")
        return None

    headers = {"User-Agent": "TDM-EUDR-Screening/1.0 (+https://tierrasdemontana.com)"}
    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
    )
    start = time.monotonic()

    for attempt in (1, 2):
        elapsed = time.monotonic() - start
        if elapsed >= _NOMINATIM_GLOBAL_BUDGET_S:
            print(f"[nominatim] key={key} budget_exceeded elapsed={elapsed:.1f}s")
            return None

        _nominatim_rate_limit()

        try:
            r = requests.get(url, headers=headers, timeout=10)
        except requests.Timeout:
            print(f"[nominatim] key={key} attempt={attempt} state=timeout")
            continue
        except Exception as e:
            print(f"[nominatim] key={key} attempt={attempt} state=exception type={type(e).__name__}")
            return None

        if r.status_code == 200:
            try:
                address = r.json().get("address", {})
            except Exception:
                print(f"[nominatim] key={key} attempt={attempt} state=invalid_json")
                return None

            if not address:
                print(f"[nominatim] key={key} attempt={attempt} state=empty cache_hit=False")
                return None

            place_name = next(
                (address[k] for k in ("village", "hamlet", "locality", "suburb", "neighbourhood") if address.get(k)),
                None,
            )
            data = {
                "place_name": place_name,
                "town_name": address.get("town"),
                "city_name": address.get("city"),
                "municipality_name": address.get("municipality"),
                "region": (address.get("state") or address.get("province") or address.get("region")),
                "country": address.get("country"),
            }
            _nominatim_cache_positive[key] = data
            print(f"[nominatim] key={key} attempt={attempt} state=positive cache_hit=False")
            return data

        if r.status_code == 403:
            _nominatim_cache_blocked.add(key)
            print(f"[nominatim] key={key} attempt={attempt} state=blocked_403")
            return None

        if r.status_code == 429:
            ra_header = r.headers.get("Retry-After")
            try:
                retry_after = int(ra_header) if ra_header is not None else 2
            except (TypeError, ValueError):
                retry_after = 2
            remaining = _NOMINATIM_GLOBAL_BUDGET_S - (time.monotonic() - start)
            if retry_after > remaining:
                print(f"[nominatim] key={key} attempt={attempt} state=429_abort retry_after={retry_after}s remaining={remaining:.1f}s")
                return None
            print(f"[nominatim] key={key} attempt={attempt} state=429_wait retry_after={retry_after}s")
            if retry_after > 0:
                time.sleep(retry_after)
            continue

        print(f"[nominatim] key={key} attempt={attempt} state=http_{r.status_code}")
        return None

    print(f"[nominatim] key={key} state=exhausted_attempts")
    return None

def fetch_osm_places(lat, lon, radius_m=3000):
    query = f'[out:json][timeout:8];(node["place"~"city|town|village"](around:{radius_m},{lat},{lon});way["place"~"city|town|village"](around:{radius_m},{lat},{lon});relation["place"~"city|town|village"](around:{radius_m},{lat},{lon}););out center;'
    try:
        r = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=10)
        if r.status_code != 200: return []
        raw_places = []
        for el in r.json().get("elements", []):
            tags = el.get("tags", {})
            if "name" not in tags or "place" not in tags: continue
            if el.get("type") == "node" and "lat" in el and "lon" in el:
                raw_places.append({"name": tags["name"], "lat": el["lat"], "lon": el["lon"], "type": tags.get("place", "unknown")})
            elif "center" in el and "lat" in el["center"] and "lon" in el["center"]:
                raw_places.append({"name": tags["name"], "lat": el["center"]["lat"], "lon": el["center"]["lon"], "type": tags.get("place", "unknown")})
        seen, unique = set(), []
        for p in raw_places:
            if p["name"] not in seen: seen.add(p["name"]); unique.append(p)
        return unique
    except Exception: return []

def _fetch_satellite_image(polygon_points, buffer_m, image_size=(1800, 1100)):
    if not HAS_PIL or not polygon_points or len(polygon_points) < 3: return None, None, None, t("err_no_coords")
    try:
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        
        ring = [[float(p[0]), float(p[1])] for p in polygon_points]
        if ring[0] != ring[-1]: ring.append(ring[0])
        
        poly_3857 = [transformer.transform(lon, lat) for lon, lat in ring]
        min_x = min(p[0] for p in poly_3857)
        max_x = max(p[0] for p in poly_3857)
        min_y = min(p[1] for p in poly_3857)
        max_y = max(p[1] for p in poly_3857)
        
        min_x -= buffer_m
        max_x += buffer_m
        min_y -= buffer_m
        max_y += buffer_m
        
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        width_m = max_x - min_x
        height_m = max_y - min_y
        target_aspect = image_size[0] / image_size[1]
        
        min_size_m = 500.0
        if width_m < min_size_m:
            min_x = center_x - (min_size_m / 2)
            max_x = center_x + (min_size_m / 2)
            width_m = min_size_m
        if height_m < min_size_m:
            min_y = center_y - (min_size_m / 2)
            max_y = center_y + (min_size_m / 2)
            height_m = min_size_m

        if (width_m / height_m) < target_aspect:
            new_width = height_m * target_aspect
            min_x = center_x - new_width / 2
            max_x = center_x + new_width / 2
        else:
            new_height = width_m / target_aspect
            min_y = center_y - new_height / 2
            max_y = center_y + new_height / 2

    except Exception as e: 
        return None, None, None, f"ROI build failed ({type(e).__name__})"
    
    try:
        if width_m < 200: image_size = (600, 400) 
        
        esri_url = (
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
            f"?bbox={min_x},{min_y},{max_x},{max_y}"
            "&bboxSR=3857&imageSR=3857"
            f"&size={image_size[0]},{image_size[1]}"
            "&format=png&f=image"
        )
        resp = requests.get(esri_url, timeout=15)
        resp.raise_for_status()
        img = PILImage.open(io.BytesIO(resp.content)).convert("RGBA")
        return (img, "Esri World Imagery (High Resolution)", (min_x, max_x, min_y, max_y), None)
    except Exception as e:
        if not _init_ee(): return (None, None, None, t("err_map_failed"))
        try:
            roi = ee.Geometry.Rectangle([min_x, min_y, max_x, max_y], proj='EPSG:3857')
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=365)
            coll = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(roi).filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
            clear = coll.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            if clear.size().getInfo() > 0:
                final = clear.median()
                info = f"Sentinel-2 Composite (Fallback)"
            else:
                final = coll.sort("CLOUDY_PIXEL_PERCENTAGE").first()
                info = "Sentinel-2 Best Available (Fallback)"
            url = final.visualize(bands=["B4", "B3", "B2"], min=0, max=3000, gamma=1.4).getThumbURL({"region": roi, "dimensions": f"{image_size[0]}x{image_size[1]}", "format": "png"})
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            img = PILImage.open(io.BytesIO(resp.content)).convert("RGBA")
            return (img, info, (min_x, max_x, min_y, max_y), None)
        except Exception as e2: return (None, None, None, t("err_map_failed"))

def _bbox_overlap(a, b): return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

def _nice_scale(max_m):
    if not max_m or max_m <= 0: return 1
    exp = math.floor(math.log10(max_m))
    for mult in (5, 2, 1):
        if mult * (10 ** exp) <= max_m: return int(mult * (10 ** exp))
    return int(10 ** (exp - 1)) if exp > 0 else 1

def _draw_common(img, polygon_points, bounds, scale_m, places=None, font_size=13):
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.size
    min_x, max_x, min_y, max_y = bounds

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    def project(lon, lat):
        x, y = transformer.transform(lon, lat)
        return ((x - min_x) / (max_x - min_x) * img_w, (max_y - y) / (max_y - min_y) * img_h)

    if places:
        try: font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except Exception: font = ImageFont.load_default()
        
        visible = []
        for p in places:
            px, py = transformer.transform(p["lon"], p["lat"])
            if min_x <= px <= max_x and min_y <= py <= max_y:
                visible.append(p)
                
        visible.sort(key=lambda p: {"city": 0, "town": 1, "village": 2}.get(p.get("type"), 3))
        type_colors = {"city": "#FFD700", "town": "#FFA500", "village": "#FFFFFF"}
        
        if font_size > 20:
            type_sizes = {"city": 12, "town": 10, "village": 8}
            stroke_w = 3
        else:
            type_sizes = {"city": 6, "town": 5, "village": 4}
            stroke_w = 2

        placed_boxes = []
        for place in visible:
            px, py = project(place["lon"], place["lat"])
            ptype = place.get("type", "village")
            dot_color = type_colors.get(ptype, "#FFFFFF")
            dot_r = type_sizes.get(ptype, 4)
            draw.ellipse([(px - dot_r, py - dot_r), (px + dot_r, py + dot_r)], fill=dot_color, outline="#000000", width=1)
            try:
                bbox = draw.textbbox((0, 0), place["name"], font=font)
                lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception: lw, lh = 60, 14
            for lx, ly in [(px + dot_r + 2, py - lh // 2), (px - lw - dot_r - 2, py - lh // 2), (px - lw // 2, py - lh - dot_r - 2), (px - lw // 2, py + dot_r + 2)]:
                if (lx < 5 or ly < 5 or lx + lw > img_w - 5 or ly + lh > img_h - 5): continue
                if any(_bbox_overlap((lx, ly, lx + lw, ly + lh), ob) for ob in placed_boxes): continue
                draw.text((lx, ly), place["name"], fill="#FFFFFF", font=font, stroke_width=stroke_w, stroke_fill="#000000")
                placed_boxes.append((lx, ly, lx + lw, ly + lh))
                break
                
    if polygon_points and len(polygon_points) >= 3:
        coords = [project(lon, lat) for lon, lat in polygon_points]
        draw.line(coords + [coords[0]], fill="#CC0000", width=4)
        try:
            poly_3857 = Polygon([transformer.transform(lon, lat) for lon, lat in polygon_points])
            c_3857 = poly_3857.centroid
            cx = (c_3857.x - min_x) / (max_x - min_x) * img_w
            cy = (max_y - c_3857.y) / (max_y - min_y) * img_h
            draw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill="#CC0000", outline="#FFFFFF", width=2)
        except Exception: pass
        
    try:
        draw.text((img_w - 30, 10), "N", fill="#FFFFFF", anchor="mm", stroke_width=2, stroke_fill="#000000")
        draw.line([(img_w - 30, 20), (img_w - 30, 40)], fill="#FFFFFF", width=2)
        draw.polygon([(img_w - 30, 15), (img_w - 35, 25), (img_w - 25, 25)], fill="#FFFFFF")
    except Exception: pass
    
    try:
        width_m = max_x - min_x
        if width_m > 0:
            pixels_per_meter = img_w / width_m
            nice_m = _nice_scale(min(scale_m, (img_w - 40) / pixels_per_meter) if scale_m else (img_w - 40) / pixels_per_meter)
            draw.line([(10, img_h - 20), (10 + nice_m * pixels_per_meter, img_h - 20)], fill="#FFFFFF", width=3)
            draw.text((10, img_h - 35), f"{nice_m} m", fill="#FFFFFF", stroke_width=2, stroke_fill="#000000")
    except Exception: pass

def generate_parcel_map(polygon_points, path, buffer_m=250, image_size=(1400, 850)):
    img, info, bounds, error = _fetch_satellite_image(polygon_points, buffer_m, image_size)
    if img is None: return None, None, error
    try:
        _draw_common(img, polygon_points, bounds, scale_m=100)
        img.convert("RGB").save(path, format="PNG")
        return path, info, None
    except Exception: return None, None, "Save failed"

def generate_context_map(polygon_points, lat, lon, path, buffer_m=2500, image_size=(1800, 1100)):
    img, info, bounds, error = _fetch_satellite_image(polygon_points, buffer_m, image_size)
    if img is None: return None, None, error
    places = fetch_osm_places(lat, lon, radius_m=3000)
    try:
        _draw_common(img, polygon_points, bounds, scale_m=1000, places=places, font_size=32)
        img.convert("RGB").save(path, format="PNG")
        return path, info, None
    except Exception: return None, None, "Save failed"

def generate_eudr_pdf(audit_id, name, lat, lon, risk_score, risk_level, eudr_status, tree_cover, loss_year, source="unknown", polygon_points=None, dataset_version="Unknown", image_preset=DEFAULT_PRESET, **kwargs):
    preset = resolve_preset(image_preset)
    temp_id = uuid.uuid4().hex
    file_path = f"/tmp/{audit_id}_{temp_id}.pdf"
    qr_path = f"/tmp/{audit_id}_{temp_id}_qr.png"
    parcel_path = f"/tmp/{audit_id}_{temp_id}_parcel.png"
    context_path = f"/tmp/{audit_id}_{temp_id}_context.png"
    success = False

    try:
        full_audit = get_audit(audit_id)
        if not full_audit: raise ValueError(f"CRITICAL: Audit {audit_id} introuvable en DB.")

        name = full_audit.get("farm_name", name)
        lat = full_audit.get("latitude", lat)
        lon = full_audit.get("longitude", lon)
        risk_score = full_audit.get("risk_score", risk_score)
        risk_level = full_audit.get("risk_level", risk_level)
        eudr_status = full_audit.get("eudr_status") or full_audit.get("eudr_compliant") or eudr_status
        tree_cover = full_audit.get("tree_cover", tree_cover)
        loss_year = full_audit.get("loss_year", loss_year)
        polygon_points = full_audit.get("polygon_points", polygon_points)
        dataset_version = full_audit.get("dataset_version", dataset_version)
        
        valid_pixels = full_audit.get("valid_pixels")
        nominal_pixels = full_audit.get("nominal_pixels_estimate")
        coverage_pct = full_audit.get("estimated_coverage_pct")
        insufficient_reason = full_audit.get("insufficient_reason")
        treecover_reason = full_audit.get("treecover_reason")
        build_version = full_audit.get("build_version", "Unknown")

        is_hansen_2025 = (source == "ee" and dataset_version in (EXPECTED_DATASET, EXPECTED_EE_ASSET))

        doc = SimpleDocTemplate(file_path, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
        styles = get_custom_styles()
        content = []
        
        current_date = datetime.now(timezone.utc).strftime("%d %b %Y – %H:%M UTC")

        signature = sign_audit(audit_id)
        verify_url = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
        safe_name, safe_id = html.escape(str(name)), html.escape(str(audit_id))

        valid_statuses = ["NO POST-2020 LOSS DETECTED", "BELOW TDM SCREENING THRESHOLD", "POTENTIAL LOSS SIGNAL", "INSUFFICIENT DATA", "ANALYSIS UNAVAILABLE", "SCREENING INCONCLUSIVE"]
        raw_status = str(eudr_status or "UNKNOWN").strip()
        
        if raw_status == "INSUFFICIENT DATA" or raw_status == "SCREENING INCONCLUSIVE":
            display_status_key = "status_inconclusive"
        elif raw_status == "NO POST-2020 LOSS DETECTED":
            display_status_key = "status_no_loss"
        elif raw_status == "BELOW TDM SCREENING THRESHOLD":
            display_status_key = "status_below_threshold"
        elif raw_status == "POTENTIAL LOSS SIGNAL":
            display_status_key = "status_potential"
        elif raw_status == "ANALYSIS UNAVAILABLE":
            display_status_key = "status_unavailable"
        else:
            display_status_key = "status_unknown"

        safe_status = t(display_status_key)
        status_for_color = raw_status if raw_status in valid_statuses else "UNKNOWN STATUS"

        qrcode.make(verify_url).save(qr_path)
        qr_img = Image(qr_path, width=60, height=60)
        logo_data = get_logo()
        logo_img = Image(logo_data, width=80, height=65) if logo_data else Paragraph("TDM", styles["TDMTitle"])

        header_table = Table([[logo_img, Paragraph(t("title"), styles["TDMTitle"]), qr_img]], colWidths=[3 * cm, 11 * cm, 3 * cm])
        header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (1, 0), (1, 0), "CENTER"), ("ALIGN", (2, 0), (2, 0), "RIGHT")]))
        content.append(header_table)
        content.append(Spacer(1, 0.5 * cm))

        if polygon_points:
            centroid_str, area_str = calculate_geometry(polygon_points)
        elif lat is not None and lon is not None:
            centroid_str, area_str = f"{float(lat):.6f}, {float(lon):.6f}", "N/A"
        else:
            centroid_str, area_str = "N/A", "N/A"

        display_point_count = (len(polygon_points) - 1 if (polygon_points and len(polygon_points) >= 2 and polygon_points[0] == polygon_points[-1]) else (len(polygon_points) if polygon_points else None))

        id_data = [
            [Paragraph(t("report_id"), styles["TDMLabel"]), Paragraph(t("generated_on"), styles["TDMLabel"]), Paragraph(t("producer"), styles["TDMLabel"]), Paragraph(t("centroid"), styles["TDMLabel"])],
            [Paragraph(safe_id, styles["TDMValue"]), Paragraph(current_date, styles["TDMValue"]), Paragraph(safe_name, styles["TDMValue"]), Paragraph(centroid_str, styles["TDMValue"])],
        ]
        id_table = Table(id_data, colWidths=[4 * cm] * 4)
        id_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, 0), 2)]))
        content.append(id_table)
        content.append(Spacer(1, 0.5 * cm))

        map_poly = polygon_points if (polygon_points and len(polygon_points) >= 3) else (_make_box(lat, lon, size_m=150) if (lat is not None and lon is not None) else None)
        
        if map_poly:
            parcel_map, parcel_info, parcel_err = generate_parcel_map(map_poly, parcel_path, buffer_m=preset["parcel_buffer_m"], image_size=preset["parcel_size"])
        else:
            parcel_map, parcel_info, parcel_err = None, None, t("err_no_coords")

        parcel_inserted = False
        if (parcel_map and os.path.exists(parcel_map)):
            try:
                with PILImage.open(parcel_map) as src: w, h = src.size
                display_w = 17 * cm
                display_h = display_w * h / w
                if display_h > 12 * cm: display_h = 12 * cm; display_w = display_h * w / h

                content.append(Image(parcel_map, width=display_w, height=display_h))
                if parcel_info: content.append(Paragraph(f"<font size='7' color='#888888'>{html.escape(parcel_info)}</font>", styles["TDMLegal"]))
                content.append(Paragraph(f"{t('total_area')}: {area_str} | {t('boundary_points')}: {display_point_count if display_point_count is not None else t('point_mode')}", styles["TDMValue"]))
                parcel_inserted = True
            except Exception as e:
                print(f"⚠️ Erreur insertion parcelle: {e}")

        if not parcel_inserted:
            map_box = Table([[Paragraph(f"{t('total_area')}: {area_str}<br/><i>{t('map_unavailable')}</i>", styles["TDMValue"])]], colWidths=[17 * cm], rowHeights=[3 * cm])
            map_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TDM_LIGHT_GREEN), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 1, TDM_GREEN)]))
            content.append(map_box)

        content.append(Spacer(1, 0.5 * cm))

        tc_display, score_display = format_val(tree_cover, "%", 0, 100), format_val(risk_score, "", 0, 100)
        loss_display = get_loss_display(status_for_color, loss_year)

        if "NO POST-2020" in status_for_color:
            bg_status_color = colors.HexColor("#D1FAE5")
            status_color = "#065F46" 
        elif "BELOW TDM" in status_for_color:
            bg_status_color = colors.HexColor("#FEF3C7")
            status_color = "#92400E"
        elif "POTENTIAL" in status_for_color:
            bg_status_color = colors.HexColor("#FEE2E2")
            status_color = "#991B1B" 
        elif "INSUFFICIENT" in status_for_color or "INCONCLUSIVE" in status_for_color:
            bg_status_color = colors.HexColor("#FEF3C7")
            status_color = "#92400E" 
        else:
            bg_status_color = TDM_GRAY
            status_color = colors.black

        findings_data = [
            [Paragraph(t("tree_cover"), styles["TDMLabel"]), Paragraph(t("last_loss"), styles["TDMLabel"]), Paragraph(t("risk_score"), styles["TDMLabel"]), Paragraph(t("screening_status"), styles["TDMLabel"])],
            [Paragraph(f"<font size='16'><b>{tc_display}</b></font>", styles["TDMValue"]), Paragraph(f"<font size='14'><b>{loss_display}</b></font>", styles["TDMValue"]), Paragraph(f"<font size='16'><b>{score_display}</b></font>", styles["TDMValue"]), Paragraph(f"<font size='10' color='{status_color}'><b>{safe_status}</b></font>", styles["TDMValue"])],
        ]
        
        findings_table = Table(findings_data, colWidths=[4.25 * cm] * 4)
        findings_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LINEBEFORE", (1, 0), (-1, -1), 1, colors.white),
            ("BACKGROUND", (0, 0), (0, -1), TDM_GRAY),
            ("BACKGROUND", (1, 0), (1, -1), TDM_GRAY),
            ("BACKGROUND", (2, 0), (2, -1), TDM_GRAY),
            ("BACKGROUND", (3, 0), (3, -1), bg_status_color),
            ("BOX", (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        
        content.append(findings_table)
        content.append(Spacer(1, 0.5 * cm))

        disclaimer = Table([[Paragraph(f"<b>{t('disclaimer_title')}</b><br/>{t('disclaimer_text')}", styles["TDMDisclaimer"])]], colWidths=[17 * cm])
        disclaimer.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TDM_LIGHT_GREEN), ("BOX", (0, 0), (-1, -1), 1, TDM_GREEN), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        content.append(disclaimer)

        content.append(PageBreak())
        content.append(Paragraph(t("annex_title"), styles["TDMSection"]))
        content.append(Spacer(1, 0.3 * cm))

        source_desc = "Google Earth Engine — Hansen Global Forest Change" if source == "ee" else ("Global Forest Watch" if source == "gfw" else t("status_unavailable"))
        if is_hansen_2025:
            period_text = f"• {t('baseline')}<br/>• {t('observation')}<br/>"
            hansen_line = f"• {t('resolution')}<br/>"
            methodology_note = f"<i>{t('method_note')}</i><br/>"
            screening_note = f"<i>{t('screening_note')}</i>"
        else:
            period_text = ""; hansen_line = ""; methodology_note = ""
            screening_note = f"<i>{t('screening_note')}</i>"

        method_text = (
            f"<b>{t('data_methodology')}</b><br/>"
            f"• {t('data_source')}: {html.escape(source_desc)}<br/>"
            f"• {t('dataset_version')}: {html.escape(str(dataset_version))}<br/>"
            f"• {t('engine_build')}: {html.escape(str(build_version))}<br/>"
            f"{period_text}"
            f"• {t('eudr_date')}<br/>"
            f"{hansen_line}"
            f"• {t('satellite')}<br/>"
            f"<i>{t('cloud_note')}</i><br/>"
            f"{methodology_note}"
            f"{screening_note}"
        )
        content.append(Paragraph(method_text, styles["TDMValue"]))
        content.append(Spacer(1, 0.5 * cm))

        if coverage_pct is not None or valid_pixels is not None or insufficient_reason or treecover_reason:
            content.append(Paragraph(t("metrics_title"), styles["TDMSection"]))
            cov_display = f"<b>{coverage_pct:.2f}%</b>" if (isinstance(coverage_pct, (int, float)) and not isinstance(coverage_pct, bool) and math.isfinite(coverage_pct) and coverage_pct >= 0) else "N/A"
            metrics_data = [
                [Paragraph(t("coverage"), styles["TDMLabel"]), Paragraph(t("valid_pixels"), styles["TDMLabel"]), Paragraph(t("nominal_pixels"), styles["TDMLabel"])],
                [Paragraph(cov_display, styles["TDMValue"]), Paragraph(f"{valid_pixels}" if valid_pixels is not None else "N/A", styles["TDMValue"]), Paragraph(f"{nominal_pixels}" if nominal_pixels is not None else "N/A", styles["TDMValue"])],
            ]
            metrics_table = Table(metrics_data, colWidths=[5.66 * cm] * 3)
            metrics_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TDM_GRAY), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey)]))
            content.append(metrics_table)
            content.append(Spacer(1, 0.3 * cm))

            if (isinstance(coverage_pct, (int, float)) and not isinstance(coverage_pct, bool)
                    and math.isfinite(coverage_pct) and coverage_pct > 100):
                content.append(Paragraph(
                    "<i>Note: the Valid Pixel Ratio compares observed Hansen pixels to a theoretical "
                    "estimate (polygon area ÷ 900 m²). Values above 100% may occur on small parcels "
                    "due to raster grid discretization (30 m cells do not align exactly with polygon "
                    "edges) and to differences between Earth Engine's area computation and the area "
                    "displayed in this report. This ratio indicates data availability, not geographic "
                    "coverage or EUDR compliance.</i>",
                    styles["TDMLegal"]
                ))
                content.append(Spacer(1, 0.2 * cm))

            if insufficient_reason:
                content.append(Paragraph(f"<b>{t('insufficient_reason')}:</b> {html.escape(str(insufficient_reason))}", styles["TDMValue"]))
            
            if raw_status == "INSUFFICIENT DATA" or raw_status == "SCREENING INCONCLUSIVE":
                content.append(Spacer(1, 0.2 * cm))
                content.append(Paragraph(
                    f"<b>{t('limited_obs_title')}</b><br/>"
                    f"{t('limited_obs_text')}",
                    styles["TDMLegal"]
                ))
                
                if insufficient_reason == "COVERAGE_BELOW_5_PCT":
                    content.append(Spacer(1, 0.2 * cm))
                    content.append(Paragraph(f"{t('limited_obs_note')}", styles["TDMLegal"]))

            if treecover_reason: content.append(Paragraph(f"<b>{t('treecover_avail')}:</b> {html.escape(str(treecover_reason))}", styles["TDMValue"]))
            content.append(Spacer(1, 0.5 * cm))

        if polygon_points and len(polygon_points) >= 3:
            content.append(Paragraph(t("geospatial_data"), styles["TDMSection"]))
            content.append(Paragraph(f"{t('centroid')}: {centroid_str} | {t('total_area')}: {area_str}", styles["TDMValue"]))
            content.append(Spacer(1, 0.2 * cm))
            poly_data = [[Paragraph(t("point"), styles["TDMLabel"]), Paragraph(t("lat"), styles["TDMLabel"]), Paragraph(t("lon"), styles["TDMLabel"])]]
            display_points = polygon_points[:-1] if polygon_points[0] == polygon_points[-1] else polygon_points
            for i, (p_lon, p_lat) in enumerate(display_points, start=1):
                poly_data.append([Paragraph(str(i), styles["TDMValue"]), Paragraph(f"{p_lat:.6f}", styles["TDMValue"]), Paragraph(f"{p_lon:.6f}", styles["TDMValue"])])
            poly_table = Table(poly_data, colWidths=[2 * cm, 5 * cm, 5 * cm], repeatRows=1, splitByRow=1)
            poly_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("BACKGROUND", (0, 0), (-1, 0), TDM_GRAY)]))
            content.append(poly_table)

        content.append(PageBreak())
        content.append(Paragraph(t("territorial_context"), styles["TDMSection"]))
        content.append(Spacer(1, 0.3 * cm))

        if map_poly and lat is not None and lon is not None:
            context_map, context_info, context_err = generate_context_map(map_poly, lat, lon, context_path, buffer_m=preset["context_buffer_m"], image_size=preset["context_size"])
        else:
            context_map, context_info, context_err = None, None, t("err_no_coords")

        if context_map and os.path.exists(context_map):
            try:
                with PILImage.open(context_map) as src: w, h = src.size
                display_w = 17 * cm
                display_h = display_w * h / w
                if display_h > 10 * cm: display_h = 10 * cm; display_w = display_h * w / h
                content.append(Image(context_map, width=display_w, height=display_h))
                if context_info: content.append(Paragraph(f"<font size='7' color='#888888'>{html.escape(context_info)}</font>", styles["TDMLegal"]))
            except Exception:
                content.append(Paragraph(f"<i>{t('map_unavailable')}</i>", styles["TDMValue"]))
        else:
            content.append(Paragraph(f"<i>{t('map_unavailable')} ({html.escape(context_err or 'unavailable')}).</i>", styles["TDMValue"]))

        terr_context = get_territorial_context(lat, lon) if lat is not None and lon is not None else None
        if terr_context:
            parts = []
            if terr_context.get("place_name"): parts.append(f"{t('osm_place')}: {html.escape(terr_context['place_name'])}")
            if terr_context.get("town_name"): parts.append(f"{t('osm_town')}: {html.escape(terr_context['town_name'])}")
            if terr_context.get("city_name"): parts.append(f"{t('osm_city')}: {html.escape(terr_context['city_name'])}")
            if terr_context.get("municipality_name"): parts.append(f"{t('osm_municipality')}: {html.escape(terr_context['municipality_name'])}")
            if terr_context.get("region"): parts.append(f"{t('osm_region')}: {html.escape(terr_context['region'])}")
            if terr_context.get("country"): parts.append(f"{t('osm_country')}: {html.escape(terr_context['country'])}")
            if parts:
                content.append(Spacer(1, 0.3 * cm))
                content.append(Paragraph("<br/>".join(parts), styles["TDMValue"]))
                content.append(Paragraph(f"<font size='7' color='#888888'>{t('source_nominatim')}</font>", styles["TDMLegal"]))
        else:
            content.append(Spacer(1, 0.3 * cm))
            content.append(Paragraph(
                "Territorial context could not be retrieved during report generation. "
                "The geographic coordinates and polygon are retained. "
                "No territorial identification is inferred.",
                styles["TDMLegal"]
            ))

        content.append(Spacer(1, 0.5 * cm))
        content.append(Paragraph(f"{t('verify_at')}: {html.escape(verify_url)}", styles["TDMLegal"]))

        doc.build(content)
        success = True
        return file_path

    finally:
        for path in (qr_path, parcel_path, context_path):
            try: os.remove(path)
            except OSError: pass
        if not success:
            try: os.remove(file_path)
            except OSError: pass
