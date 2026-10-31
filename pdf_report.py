import os
import io
import html
import math
import uuid
import qrcode
import requests

from datetime import datetime, timedelta

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER

from security import sign_audit
from shapely.geometry import Polygon
from pyproj import Geod
from eudr import get_audit
import eudr

# ==========================================
# DÉPENDANCES OPTIONNELLES
# ==========================================
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

# ==========================================
# CONFIGURATION
# ==========================================
BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")
LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"
EXPECTED_DATASET = "UMD/hansen/global_forest_change_2023_v1_11"

TDM_GREEN = colors.HexColor("#1E3A32")
TDM_LIGHT_GREEN = colors.HexColor("#E8F2E8")
TDM_GRAY = colors.HexColor("#F5F5F5")

_EE_CONFIRMED = False

# ==========================================
# PRESETS DE CADRAGE SATELLITE
# ==========================================
IMAGE_PRESETS = {
    "standard": {
        "parcel_buffer_m": 250,
        "parcel_size": (1400, 850),
        "context_buffer_m": 2500,
        "context_size": (1800, 1100),
    },
    "zoom": {
        "parcel_buffer_m": 100,
        "parcel_size": (1400, 850),
        "context_buffer_m": 1500,
        "context_size": (1800, 1100),
    },
    "wide": {
        "parcel_buffer_m": 500,
        "parcel_size": (1400, 850),
        "context_buffer_m": 4000,
        "context_size": (1800, 1100),
    },
}
DEFAULT_PRESET = "standard"

def resolve_preset(name):
    return IMAGE_PRESETS.get(name) or IMAGE_PRESETS[DEFAULT_PRESET]

# ==========================================
# LOGO & STYLES
# ==========================================
def get_logo():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        r = requests.get(LOGO_URL, timeout=8, headers=headers)
        r.raise_for_status()
        if not r.headers.get("Content-Type", "").startswith("image/"):
            return None
        if HAS_PIL:
            try:
                img = PILImage.open(io.BytesIO(r.content))
                img.verify()
                return io.BytesIO(r.content)
            except Exception:
                return None
        return io.BytesIO(r.content)
    except Exception:
        return None

def get_custom_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TDMTitle", parent=styles["Heading1"], fontSize=16, leading=20, textColor=TDM_GREEN, fontName="Helvetica-Bold", alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="TDMLabel", parent=styles["Normal"], fontSize=8, textColor=colors.gray, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="TDMValue", parent=styles["Normal"], fontSize=9, textColor=colors.black, fontName="Helvetica"))
    styles.add(ParagraphStyle(name="TDMSection", parent=styles["Heading2"], fontSize=12, textColor=TDM_GREEN, fontName="Helvetica-Bold", spaceAfter=10))
    styles.add(ParagraphStyle(name="TDMLegal", parent=styles["Normal"], fontSize=7, textColor=colors.gray, fontName="Helvetica"))
    styles.add(ParagraphStyle(name="TDMDisclaimer", parent=styles["Normal"], fontSize=8, textColor=TDM_GREEN, fontName="Helvetica-Bold", alignment=TA_CENTER))
    return styles

# ==========================================
# FORMATAGE & CALCULS
# ==========================================
def format_val(val, suffix="", min_val=0, max_val=100):
    if (isinstance(val, bool) or val is None or not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < min_val or val > max_val):
        return "N/A"
    return f"{val}{suffix}"

def format_loss_year(val):
    if (isinstance(val, bool) or val is None or not isinstance(val, (int, float))):
        return "N/A"
    if not math.isfinite(val) or not float(val).is_integer():
        return "N/A"
    year = int(val)
    if year == 0: return "No loss detected"
    elif 2001 <= year <= 2023: return str(year)
    else: return "N/A"

def get_loss_display(status, loss_year):
    if status in ("INSUFFICIENT DATA", "ANALYSIS UNAVAILABLE", "UNKNOWN STATUS"):
        return "N/A"
    return format_loss_year(loss_year)

def calculate_geometry(polygon_points):
    if not polygon_points or len(polygon_points) < 3:
        return "N/A", "N/A"
    try:
        poly = Polygon(polygon_points)
        if not poly.is_valid: return "Invalid geometry", "N/A"
        centroid = poly.centroid
        geod = Geod(ellps="WGS84")
        area_sq_m, _ = geod.geometry_area_perimeter(poly)
        return f"{centroid.y:.6f}, {centroid.x:.6f}", f"{abs(area_sq_m) / 10000.0:.2f} ha"
    except Exception:
        return "Calculation error", "N/A"

# ==========================================
# OUTILS CARTOGRAPHIQUES
# ==========================================
def _init_ee():
    global _EE_CONFIRMED
    if not HAS_PIL or not HAS_EE: return False
    if _EE_CONFIRMED: return True
    if not bool(getattr(eudr, "EE_INITIALIZED", False)): return False
    try:
        ee.Number(0).getInfo()
        _EE_CONFIRMED = True
        return True
    except Exception:
        return False

def get_territorial_context(lat, lon):
    try:
        headers = {"User-Agent": "TDM-EUDR-Screening/1.0 (+https://tierrasdemontana.com)"}
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200: return None
        address = r.json().get("address", {})
        place_name = next((address[k] for k in ("village", "hamlet", "locality", "suburb", "neighbourhood") if address.get(k)), None)
        return {
            "place_name": place_name, "town_name": address.get("town"), "city_name": address.get("city"),
            "municipality_name": address.get("municipality"), "region": (address.get("state") or address.get("province") or address.get("region")),
            "country": address.get("country"),
        }
    except Exception:
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
    except Exception:
        return []

# ==========================================
# RÉCUPÉRATION SENTINEL-2 (CORRIGÉ)
# ==========================================
def _fetch_satellite_image(polygon_points, buffer_m, image_size=(1800, 1100)):
    if (not HAS_PIL or not HAS_EE or not polygon_points or len(polygon_points) < 3): return (None, None, None, "Prerequisites missing")
    if not _init_ee(): return (None, None, None, "Earth Engine not initialized")

    try:
        ring = [[float(p[0]), float(p[1])] for p in polygon_points]
        if ring[0] != ring[-1]: ring.append(ring[0])
        buffered = ee.Geometry.Polygon([ring]).buffer(buffer_m)

        target_aspect = (image_size[0] / image_size[1]) if image_size[1] > 0 else 1.0
        buffered_bounds = buffered.bounds().getInfo()
        bounds_ring = buffered_bounds["coordinates"][0]

        min_lon, max_lon = min(p[0] for p in bounds_ring), max(p[0] for p in bounds_ring)
        min_lat, max_lat = min(p[1] for p in bounds_ring), max(p[1] for p in bounds_ring)
        center_lon, center_lat = (min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0

        lat_rad = math.radians(center_lat)
        m_per_deg_lon, m_per_deg_lat = 111320.0 * math.cos(lat_rad), 110540.0

        width_m, height_m = max((max_lon - min_lon) * m_per_deg_lon, 1.0), max((max_lat - min_lat) * m_per_deg_lat, 1.0)
        
        if (width_m / height_m) < target_aspect:
            new_width_deg = (height_m * target_aspect) / m_per_deg_lon
            min_lon, max_lon = center_lon - new_width_deg / 2.0, center_lon + new_width_deg / 2.0
        else:
            new_height_deg = (width_m / target_aspect) / m_per_deg_lat
            min_lat, max_lat = center_lat - new_height_deg / 2.0, center_lat + new_height_deg / 2.0

        roi = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])
        end_date, start_date = datetime.utcnow(), datetime.utcnow() - timedelta(days=365)

    except Exception as e:
        return (None, None, None, f"ROI build failed ({type(e).__name__})")

    try:
        coll = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(roi).filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if coll.size().getInfo() == 0: return (None, None, None, "No Sentinel-2 scene")
    except Exception:
        return (None, None, None, "S2 collection access failed")

    try:
        clear = coll.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        clear_size = clear.size().getInfo()
        if clear_size > 0:
            final = clear.median()
            info = f"Median composite {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}, {clear_size} scenes <20% cloud"
        else:
            best = coll.sort("CLOUDY_PIXEL_PERCENTAGE").first()
            pct = best.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
            final = best
            info = f"Best available scene, {pct:.1f}% cloud"
    except Exception:
        return (None, None, None, "Composite build failed")

    # --- CORRECTIF ICI : Plus de resample, et on ajoute gamma ---
    try:
        url = (
            final.visualize(
                bands=["B4", "B3", "B2"], 
                min=0, 
                max=3000,
                gamma=1.4 
            )
            .getThumbURL({
                "region": roi,
                "dimensions": f"{image_size[0]}x{image_size[1]}",
                "format": "png",
            })
        )
    except Exception:
        return (None, None, None, "getThumbURL failed")

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception:
        return (None, None, None, "Download failed")

    try:
        img = PILImage.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return (None, None, None, "Decode failed")

    try:
        bounds = roi.bounds().getInfo()["coordinates"][0]
        return (img, info, (min(p[0] for p in bounds), max(p[0] for p in bounds), min(p[1] for p in bounds), max(p[1] for p in bounds)), None)
    except Exception:
        return (None, None, None, "Bounds retrieval failed")

# ==========================================
# DESSIN
# ==========================================
def _bbox_overlap(a, b): return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
def _nice_scale(max_m):
    if not max_m or max_m <= 0: return 1
    exp = math.floor(math.log10(max_m))
    for mult in (5, 2, 1):
        if mult * (10 ** exp) <= max_m: return int(mult * (10 ** exp))
    return int(10 ** (exp - 1)) if exp > 0 else 1

def _draw_common(img, polygon_points, bounds, scale_m, places=None):
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.size
    min_lon, max_lon, min_lat, max_lat = bounds
    def project(lon, lat): return ((lon - min_lon) / (max_lon - min_lon) * img_w, (max_lat - lat) / (max_lat - min_lat) * img_h)

    if places:
        try: font = ImageFont.truetype("DejaVuSans-Bold.ttf", 13)
        except Exception: font = ImageFont.load_default()
        visible = [p for p in places if (min_lon <= p["lon"] <= max_lon and min_lat <= p["lat"] <= max_lat)]
        visible.sort(key=lambda p: {"city": 0, "town": 1, "village": 2}.get(p.get("type"), 3))
        type_colors, type_sizes = {"city": "#FFD700", "town": "#FFA500", "village": "#FFFFFF"}, {"city": 6, "town": 5, "village": 4}
        placed_boxes = []
        for place in visible:
            px, py = project(place["lon"], place["lat"])
            ptype = place.get("type", "village")
            dot_color, dot_r = type_colors.get(ptype, "#FFFFFF"), type_sizes.get(ptype, 4)
            draw.ellipse([(px - dot_r, py - dot_r), (px + dot_r, py + dot_r)], fill=dot_color, outline="#000000", width=1)
            try:
                bbox = draw.textbbox((0, 0), place["name"], font=font)
                lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception: lw, lh = 60, 14
            for lx, ly in [(px + dot_r + 2, py - lh // 2), (px - lw - dot_r - 2, py - lh // 2), (px - lw // 2, py - lh - dot_r - 2), (px - lw // 2, py + dot_r + 2)]:
                if (lx < 5 or ly < 5 or lx + lw > img_w - 5 or ly + lh > img_h - 5): continue
                if any(_bbox_overlap((lx, ly, lx + lw, ly + lh), ob) for ob in placed_boxes): continue
                draw.text((lx, ly), place["name"], fill="#FFFFFF", font=font, stroke_width=2, stroke_fill="#000000")
                placed_boxes.append((lx, ly, lx + lw, ly + lh))
                break

    if polygon_points and len(polygon_points) >= 3:
        coords = [project(lon, lat) for lon, lat in polygon_points]
        draw.line(coords + [coords[0]], fill="#CC0000", width=4)
        try:
            c = Polygon(polygon_points).centroid
            cx, cy = project(c.x, c.y)
            draw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill="#CC0000", outline="#FFFFFF", width=2)
        except Exception: pass

    try:
        draw.text((img_w - 30, 10), "N", fill="#FFFFFF", anchor="mm", stroke_width=2, stroke_fill="#000000")
        draw.line([(img_w - 30, 20), (img_w - 30, 40)], fill="#FFFFFF", width=2)
        draw.polygon([(img_w - 30, 15), (img_w - 35, 25), (img_w - 25, 25)], fill="#FFFFFF")
    except Exception: pass

    try:
        _, _, width_m = Geod(ellps="WGS84").inv(min_lon, min_lat, max_lon, min_lat)
        width_m = abs(width_m)
        if width_m > 0:
            pixels_per_meter = img_w / width_m
            nice_m = _nice_scale(min(scale_m, (img_w - 40) / pixels_per_meter) if scale_m else (img_w - 40) / pixels_per_meter)
            draw.line([(10, img_h - 20), (10 + nice_m * pixels_per_meter, img_h - 20)], fill="#FFFFFF", width=3)
            draw.text((10, img_h - 35), f"{nice_m} m", fill="#FFFFFF", stroke_width=2, stroke_fill="#000000")
    except Exception: pass

# ==========================================
# GÉNÉRATION CARTES
# ==========================================
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
        _draw_common(img, polygon_points, bounds, scale_m=1000, places=places)
        img.convert("RGB").save(path, format="PNG")
        return path, info, None
    except Exception: return None, None, "Save failed"

# ==========================================
# GÉNÉRATION PDF (2 PAGES)
# ==========================================
def generate_eudr_pdf(audit_id, name, lat, lon, risk_score, risk_level, eudr_status, tree_cover, loss_year, source="unknown", polygon_points=None, dataset_version="Unknown", image_preset=DEFAULT_PRESET, **kwargs):
    preset = resolve_preset(image_preset)
    temp_id = uuid.uuid4().hex
    file_path = f"/tmp/{audit_id}_{temp_id}.pdf"
    qr_path = f"/tmp/{audit_id}_{temp_id}_qr.png"
    parcel_path = f"/tmp/{audit_id}_{temp_id}_parcel.png"
    context_path = f"/tmp/{audit_id}_{temp_id}_context.png"
    success = False

    try:
        full_audit = get_audit(audit_id) or {}
        valid_pixels, nominal_pixels = full_audit.get("valid_pixels"), full_audit.get("nominal_pixels_estimate")
        coverage_pct, insufficient_reason, treecover_reason = full_audit.get("estimated_coverage_pct"), full_audit.get("insufficient_reason"), full_audit.get("treecover_reason")

        doc = SimpleDocTemplate(file_path, leftMargin=2*cm, rightMargin=2*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        styles = get_custom_styles()
        content = []
        current_date = datetime.now().strftime("%d %b %Y – %H:%M")

        signature = sign_audit(audit_id)
        verify_url = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
        safe_name, safe_id = html.escape(str(name)), html.escape(str(audit_id))

        valid_statuses = ["NO POST-2020 LOSS DETECTED", "BELOW TDM SCREENING THRESHOLD", "POTENTIAL LOSS SIGNAL", "INSUFFICIENT DATA", "ANALYSIS UNAVAILABLE"]
        safe_status = html.escape(str(eudr_status)) if eudr_status in valid_statuses else "UNKNOWN STATUS"

        qrcode.make(verify_url).save(qr_path)
        qr_img = Image(qr_path, width=60, height=60)
        logo_data = get_logo()
        logo_img = Image(logo_data, width=80, height=65) if logo_data else Paragraph("TDM", styles["TDMTitle"])

        header_table = Table([[logo_img, Paragraph("EUDR TERRITORIAL TRACEABILITY<br/>&amp; DUE DILIGENCE SUPPORT REPORT", styles["TDMTitle"]), qr_img]], colWidths=[3*cm, 11*cm, 3*cm])
        header_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ALIGN", (0,0), (0,0), "LEFT"), ("ALIGN", (1,0), (1,0), "CENTER"), ("ALIGN", (2,0), (2,0), "RIGHT")]))
        content.append(header_table)
        content.append(Spacer(1, 0.5 * cm))

        centroid_str, area_str = calculate_geometry(polygon_points) if polygon_points else (f"{lat:.6f}, {lon:.6f}", "N/A")
        display_point_count = (len(polygon_points) - 1 if (polygon_points and len(polygon_points) >= 2 and polygon_points[0] == polygon_points[-1]) else (len(polygon_points) if polygon_points else None))

        id_data = [
            [Paragraph("Report ID", styles["TDMLabel"]), Paragraph("Generated on", styles["TDMLabel"]), Paragraph("Producer / Farm", styles["TDMLabel"]), Paragraph("Centroid", styles["TDMLabel"])],
            [Paragraph(safe_id, styles["TDMValue"]), Paragraph(current_date, styles["TDMValue"]), Paragraph(safe_name, styles["TDMValue"]), Paragraph(centroid_str, styles["TDMValue"])],
        ]
        id_table = Table(id_data, colWidths=[4*cm]*4)
        id_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,0), 2)]))
        content.append(id_table)
        content.append(Spacer(1, 0.5 * cm))

        # --- CARTE PARCELLAIRE ---
        if polygon_points and len(polygon_points) >= 3:
            parcel_map, parcel_info, parcel_err = generate_parcel_map(polygon_points, parcel_path, buffer_m=preset["parcel_buffer_m"], image_size=preset["parcel_size"])
        else:
            parcel_map, parcel_info, parcel_err = None, None, "No polygon"

        parcel_inserted = False
        if (parcel_map and os.path.exists(parcel_map)):
            try:
                with PILImage.open(parcel_map) as src: w, h = src.size
                display_w = 17 * cm
                display_h = display_w * h / w
                if display_h > 12 * cm: display_h = 12 * cm; display_w = display_h * w / h
                content.append(Image(parcel_map, width=display_w, height=display_h))
                if parcel_info: content.append(Paragraph(f"<font size='7' color='#888888'>Sentinel-2 B4/B3/B2 — {html.escape(parcel_info)}</font>", styles["TDMLegal"]))
                content.append(Paragraph(f"Total Area: {area_str} | Boundary points: {display_point_count if display_point_count is not None else 'Point mode'}", styles["TDMValue"]))
                parcel_inserted = True
            except Exception as e: print(f"⚠️ Erreur insertion parcelle: {e}")

        if not parcel_inserted:
            map_box = Table([[Paragraph(f"Total Area: {area_str}<br/><i>Satellite parcel map unavailable</i>", styles["TDMValue"])]], colWidths=[17*cm], rowHeights=[3*cm])
            map_box.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), TDM_LIGHT_GREEN), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("BOX", (0,0), (-1,-1), 1, TDM_GREEN)]))
            content.append(map_box)
        content.append(Spacer(1, 0.5 * cm))

        status_color = "#1E3A32" if "NO POST-2020" in safe_status else "#CC0000" if "POTENTIAL" in safe_status else "#D97706" if "INSUFFICIENT DATA" in safe_status else "#F59E0B"
        tc_display, score_display = format_val(tree_cover, "%", 0, 100), format_val(risk_score, "", 0, 100)
        loss_display = get_loss_display(safe_status, loss_year)

        findings_data = [
            [Paragraph("Tree Cover", styles["TDMLabel"]), Paragraph("Last Loss", styles["TDMLabel"]), Paragraph("Risk Score", styles["TDMLabel"]), Paragraph("Screening Status", styles["TDMLabel"])],
            [Paragraph(f"<b>{tc_display}</b>", styles["TDMValue"]), Paragraph(f"<b>{loss_display}</b>", styles["TDMValue"]), Paragraph(f"<b>{score_display}</b>", styles["TDMValue"]), Paragraph(f"<font color='{status_color}'><b>{safe_status}</b></font>", styles["TDMValue"])],
        ]
        findings_table = Table(findings_data, colWidths=[4.25*cm]*4)
        findings_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), TDM_GRAY), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8), ("LINEBEFORE", (1,0), (-1,-1), 0.5, colors.lightgrey)]))
        content.append(findings_table)
        content.append(Spacer(1, 0.5 * cm))

        disclaimer = Table([[Paragraph("<b>THIS REPORT IS A TERRITORIAL SCREENING, NOT A CERTIFICATE</b><br/>This document provides a technical traceability and documentation support report. It is not a certificate of compliance with the EU Deforestation Regulation (EUDR) and does not replace the legal Due Diligence required by the operator or the relevant authorities.", styles["TDMDisclaimer"])]], colWidths=[17*cm])
        disclaimer.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), TDM_LIGHT_GREEN), ("BOX", (0,0), (-1,-1), 1, TDM_GREEN), ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10)]))
        content.append(disclaimer)

        # ======================================
        # PAGE 2 : ANNEXE TECHNIQUE
        # ======================================
        content.append(PageBreak())
        content.append(Paragraph("TECHNICAL ASSESSMENT ANNEX", styles["TDMSection"]))
        content.append(Spacer(1, 0.3 * cm))

        source_desc = "Google Earth Engine (Hansen)" if source == "ee" else ("Global Forest Watch" if source == "gfw" else "Analysis Unavailable")
        period_text = "• Dataset Coverage: 2001–2023<br/>" if (source == "ee" and dataset_version == EXPECTED_DATASET) else ""
        hansen_line = "• Hansen Global Forest Change: 30 m resolution<br/>" if (source == "ee" and dataset_version == EXPECTED_DATASET) else ""
        method_text = f"<b>Data &amp; Methodology</b><br/>• Data Source: {html.escape(source_desc)}<br/>• Dataset Version: {html.escape(str(dataset_version))}<br/>{period_text}• EUDR Reference Date: 31 Dec 2020<br/>{hansen_line}• Sentinel-2 RGB (B4/B3/B2): 10 m native resolution<br/><i>Note: cloud percentage shown on satellite maps is the global scene metric, not a cloud-cover measurement over the parcel.</i>"
        content.append(Paragraph(method_text, styles["TDMValue"]))
        content.append(Spacer(1, 0.5 * cm))

        if (coverage_pct is not None or valid_pixels is not None or insufficient_reason or treecover_reason):
            content.append(Paragraph("Screening Quality & Coverage Metrics", styles["TDMSection"]))
            cov_display = f"<b>{coverage_pct:.2f}%</b>" if (isinstance(coverage_pct, (int, float)) and not isinstance(coverage_pct, bool) and math.isfinite(coverage_pct) and coverage_pct >= 0) else "N/A"
            metrics_data = [
                [Paragraph("Estimated Coverage", styles["TDMLabel"]), Paragraph("Valid Pixels", styles["TDMLabel"]), Paragraph("Nominal Pixels (Estimate)", styles["TDMLabel"])],
                [Paragraph(cov_display, styles["TDMValue"]), Paragraph(f"{valid_pixels}" if valid_pixels is not None else "N/A", styles["TDMValue"]), Paragraph(f"{nominal_pixels}" if nominal_pixels is not None else "N/A", styles["TDMValue"])],
            ]
            metrics_table = Table(metrics_data, colWidths=[5.66*cm]*3)
            metrics_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), TDM_GRAY), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey)]))
            content.append(metrics_table)
            content.append(Spacer(1, 0.3 * cm))
            if insufficient_reason: content.append(Paragraph(f"<b>Insufficiency Reason:</b> {html.escape(str(insufficient_reason))}", styles["TDMValue"]))
            if treecover_reason: content.append(Paragraph(f"<b>Treecover Availability:</b> {html.escape(str(treecover_reason))}", styles["TDMValue"]))
            content.append(Spacer(1, 0.5 * cm))

        if polygon_points and len(polygon_points) >= 3:
            content.append(Paragraph("Geospatial Data (Polygon)", styles["TDMSection"]))
            content.append(Paragraph(f"Centroid: {centroid_str} | Area: {area_str}", styles["TDMValue"]))
            content.append(Spacer(1, 0.2 * cm))
            poly_data = [[Paragraph("Point", styles["TDMLabel"]), Paragraph("Latitude", styles["TDMLabel"]), Paragraph("Longitude", styles["TDMLabel"])]]
            display_points = polygon_points[:-1] if polygon_points[0] == polygon_points[-1] else polygon_points
            for i, (p_lon, p_lat) in enumerate(display_points, start=1):
                poly_data.append([Paragraph(str(i), styles["TDMValue"]), Paragraph(f"{p_lat:.6f}", styles["TDMValue"]), Paragraph(f"{p_lon:.6f}", styles["TDMValue"])])
            poly_table = Table(poly_data, colWidths=[2*cm, 5*cm, 5*cm], repeatRows=1, splitByRow=1)
            poly_table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey), ("BACKGROUND", (0,0), (-1,0), TDM_GRAY)]))
            content.append(poly_table)

        # ======================================
        # SUITE PAGE 2 : CONTEXTE TERRITORIAL (SANS PAGEBREAK)
        # ======================================
        content.append(Spacer(1, 0.5 * cm))
        content.append(Paragraph("TERRITORIAL CONTEXT", styles["TDMSection"]))
        content.append(Spacer(1, 0.3 * cm))

        if (polygon_points and len(polygon_points) >= 3 and lat is not None and lon is not None):
            context_map, context_info, context_err = generate_context_map(polygon_points, lat, lon, context_path, buffer_m=preset["context_buffer_m"], image_size=preset["context_size"])
        else:
            context_map, context_info, context_err = None, None, "No polygon or coordinates"

        if (context_map and os.path.exists(context_map)):
            try:
                with PILImage.open(context_map) as src: w, h = src.size
                display_w = 17 * cm
                display_h = display_w * h / w
                if display_h > 10 * cm: display_h = 10 * cm; display_w = display_h * w / h
                content.append(Image(context_map, width=display_w, height=display_h))
                if context_info: content.append(Paragraph(f"<font size='7' color='#888888'>Sentinel-2 B4/B3/B2 — {html.escape(context_info)}</font>", styles["TDMLegal"]))
            except Exception as e: content.append(Paragraph("<i>Territorial context map unavailable.</i>", styles["TDMValue"]))
        else:
            content.append(Paragraph(f"<i>Territorial context map unavailable ({html.escape(context_err or 'unavailable')}).</i>", styles["TDMValue"]))

        terr_context = get_territorial_context(lat, lon) if (lat is not None and lon is not None) else None
        if terr_context:
            parts = []
            if terr_context.get("place_name"): parts.append("OSM Place: " + html.escape(terr_context["place_name"]))
            if terr_context.get("town_name"): parts.append("OSM Town: " + html.escape(terr_context["town_name"]))
            if terr_context.get("city_name"): parts.append("OSM City: " + html.escape(terr_context["city_name"]))
            if terr_context.get("municipality_name"): parts.append("Municipality: " + html.escape(terr_context["municipality_name"]))
            if terr_context.get("region"): parts.append("Region: " + html.escape(terr_context["region"]))
            if terr_context.get("country"): parts.append("Country: " + html.escape(terr_context["country"]))
            if parts:
                content.append(Spacer(1, 0.3 * cm))
                content.append(Paragraph("<br/>".join(parts), styles["TDMValue"]))
                content.append(Paragraph("<font size='7' color='#888888'>Source: Nominatim, OpenStreetMap</font>", styles["TDMLegal"]))

        content.append(Spacer(1, 0.5 * cm))
        content.append(Paragraph(f"Verify at: {html.escape(verify_url)}", styles["TDMLegal"]))

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
