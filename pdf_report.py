import os
import io
import html
import math
import uuid
import qrcode
import requests

from datetime import datetime, timedelta

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER

from security import sign_audit
from shapely.geometry import Polygon
from pyproj import Geod
from eudr import get_audit
import eudr  # Accès à eudr.EE_INITIALIZED


# ==========================================
# DÉPENDANCES OPTIONNELLES
# ==========================================

# Sécurité Pillow (fallback logo)
try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    print("⚠️ Pillow non installé. La carte satellite sera désactivée.")
    HAS_PIL = False


# Earth Engine — déjà importé par eudr.py
try:
    import ee
    HAS_EE = True
except ImportError:
    print("⚠️ earthengine-api non importable dans ce contexte isolé.")
    HAS_EE = False


# ==========================================
# CONFIGURATION
# ==========================================

BASE_URL = os.getenv(
    "BASE_URL",
    "https://eudr-api-mi0x.onrender.com"
)

LOGO_URL = (
    "https://tierrasdemontana.com/"
    "wp-content/uploads/2021/03/TDM-L.png"
)

EXPECTED_DATASET = "UMD/hansen/global_forest_change_2023_v1_11"

TDM_GREEN = colors.HexColor("#1E3A32")
TDM_LIGHT_GREEN = colors.HexColor("#E8F2E8")
TDM_GRAY = colors.HexColor("#F5F5F5")

_EE_CONFIRMED = False


# ==========================================
# LOGO
# ==========================================

def get_logo():
    try:
        print("📥 DOWNLOADING LOGO...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }

        r = requests.get(
            LOGO_URL,
            timeout=8,
            headers=headers
        )
        r.raise_for_status()

        content_type = r.headers.get("Content-Type", "")

        if not content_type.startswith("image/"):
            print(
                f"❌ LOGO ERROR: Received {content_type} "
                "instead of an image."
            )
            return None

        if HAS_PIL:
            try:
                img_bytes = r.content
                img = PILImage.open(io.BytesIO(img_bytes))
                img.verify()

                print("✅ LOGO DOWNLOADED AND VERIFIED (Pillow)")
                return io.BytesIO(img_bytes)

            except Exception as e:
                print(f"❌ LOGO ERROR: Image non décodable - {e}")
                return None

        print("✅ LOGO DOWNLOADED (Basic check)")
        return io.BytesIO(r.content)

    except Exception as e:
        print("❌ LOGO DOWNLOAD ERROR:", str(e))
        return None


# ==========================================
# STYLES DU PDF
# ==========================================

def get_custom_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="TDMTitle",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=TDM_GREEN,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TDMLabel",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.gray,
            fontName="Helvetica-Bold",
        )
    )

    styles.add(
        ParagraphStyle(
            name="TDMValue",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.black,
            fontName="Helvetica",
        )
    )

    styles.add(
        ParagraphStyle(
            name="TDMSection",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=TDM_GREEN,
            fontName="Helvetica-Bold",
            spaceAfter=10,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TDMLegal",
            parent=styles["Normal"],
            fontSize=7,
            textColor=colors.gray,
            fontName="Helvetica",
        )
    )

    styles.add(
        ParagraphStyle(
            name="TDMDisclaimer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=TDM_GREEN,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
    )

    return styles


# ==========================================
# FORMATAGE DES DONNÉES
# ==========================================

def format_val(val, suffix="", min_val=0, max_val=100):

    if (
        isinstance(val, bool)
        or val is None
        or not isinstance(val, (int, float))
        or math.isnan(val)
        or math.isinf(val)
        or val < min_val
        or val > max_val
    ):
        return "N/A"

    return f"{val}{suffix}"


def format_loss_year(val):

    if (
        isinstance(val, bool)
        or val is None
        or not isinstance(val, (int, float))
    ):
        return "N/A"

    if not math.isfinite(val) or not float(val).is_integer():
        return "N/A"

    year = int(val)

    if year == 0:
        return "No loss detected"

    elif 2001 <= year <= 2023:
        return str(year)

    else:
        return "N/A"


def get_loss_display(status, loss_year):

    if status in (
        "INSUFFICIENT DATA",
        "ANALYSIS UNAVAILABLE",
        "UNKNOWN STATUS",
    ):
        return "N/A"

    return format_loss_year(loss_year)


# ==========================================
# CALCUL GÉOMÉTRIQUE
# ==========================================

def calculate_geometry(polygon_points):

    if not polygon_points or len(polygon_points) < 3:
        return "N/A", "N/A"

    try:
        poly = Polygon(polygon_points)

        if not poly.is_valid:
            return "Invalid geometry", "N/A"

        centroid = poly.centroid

        geod = Geod(ellps="WGS84")

        area_sq_m, _ = geod.geometry_area_perimeter(poly)

        return (
            f"{centroid.y:.6f}, {centroid.x:.6f}",
            f"{abs(area_sq_m) / 10000.0:.2f} ha",
        )

    except Exception:
        return "Calculation error", "N/A"


# ==========================================
# OUTILS CARTOGRAPHIQUES
# ==========================================

def _init_ee():
    """
    Vérifie la disponibilité d'Earth Engine.

    Source de vérité : eudr.EE_INITIALIZED.
    Aucune authentification ici.
    Aucun ee.Initialize().

    Le cache est positif uniquement.
    """

    global _EE_CONFIRMED

    if not HAS_PIL or not HAS_EE:
        return False

    if _EE_CONFIRMED:
        return True

    ee_ready = bool(
        getattr(eudr, "EE_INITIALIZED", False)
    )

    print(
        f"🔎 Étape A — EE status: "
        f"eudr.EE_INITIALIZED={ee_ready}"
    )

    if not ee_ready:
        return False

    try:
        ee.Number(0).getInfo()

        _EE_CONFIRMED = True

        print("✅ Étape A — Sonde EE OK.")

        return True

    except Exception as e:

        print(
            f"⚠️ Étape A — Sonde EE échouée : "
            f"{type(e).__name__}: {e}"
        )

        return False


# ==========================================
# CONTEXTE TERRITORIAL — NOMINATIM
# ==========================================

def get_territorial_context(lat, lon):
    """
    Nominatim reverse geocoding.
    Les types réels sont préservés.
    """

    try:

        headers = {
            "User-Agent": (
                "TDM-EUDR-Screening/1.0 "
                "(+https://tierrasdemontana.com; "
                "contact@tierrasdemontana.com)"
            )
        }

        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=json&lat={lat}&lon={lon}"
            "&zoom=14&addressdetails=1"
        )

        r = requests.get(
            url,
            headers=headers,
            timeout=5
        )

        if r.status_code != 200:
            print(f"⚠️ Nominatim HTTP {r.status_code}")
            return None

        address = r.json().get("address", {})

        place_name = None

        for key in (
            "village",
            "hamlet",
            "locality",
            "suburb",
            "neighbourhood",
        ):

            if address.get(key):
                place_name = address[key]
                break

        return {
            "place_name": place_name,
            "town_name": address.get("town"),
            "city_name": address.get("city"),
            "municipality_name": address.get("municipality"),
            "region": (
                address.get("state")
                or address.get("province")
                or address.get("region")
            ),
            "country": address.get("country"),
        }

    except Exception as e:

        print(
            f"⚠️ Nominatim indisponible : "
            f"{type(e).__name__}: {e}"
        )

        return None


# ==========================================
# CONTEXTE TERRITORIAL — OVERPASS / OSM
# ==========================================

def fetch_osm_places(lat, lon, radius_m=3000):
    """
    Overpass — node, way, relation via out center.
    Déduplication par nom.
    """

    query = f"""
    [out:json][timeout:8];
    (
      node["place"~"city|town|village"](around:{radius_m},{lat},{lon});
      way["place"~"city|town|village"](around:{radius_m},{lat},{lon});
      relation["place"~"city|town|village"](around:{radius_m},{lat},{lon});
    );
    out center;
    """

    try:

        r = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=10,
        )

        if r.status_code != 200:
            print(f"⚠️ Overpass HTTP {r.status_code}")
            return []

        elements = r.json().get("elements", [])

        raw_places = []

        for el in elements:

            tags = el.get("tags", {})

            if "name" not in tags or "place" not in tags:
                continue

            if (
                el.get("type") == "node"
                and "lat" in el
                and "lon" in el
            ):

                raw_places.append({
                    "name": tags["name"],
                    "lat": el["lat"],
                    "lon": el["lon"],
                    "type": tags.get("place", "unknown"),
                })

            elif (
                "center" in el
                and "lat" in el["center"]
                and "lon" in el["center"]
            ):

                raw_places.append({
                    "name": tags["name"],
                    "lat": el["center"]["lat"],
                    "lon": el["center"]["lon"],
                    "type": tags.get("place", "unknown"),
                })

        seen = set()
        unique = []

        for p in raw_places:

            if p["name"] not in seen:
                seen.add(p["name"])
                unique.append(p)

        return unique

    except Exception as e:

        print(
            f"⚠️ Overpass indisponible : "
            f"{type(e).__name__}: {e}"
        )

        return []# ==========================================
# RÉCUPÉRATION SENTINEL-2
# ==========================================

def _fetch_satellite_image(
    polygon_points,
    buffer_m,
    image_size=800
):
    """
    Sentinel-2 via Earth Engine.

    Retourne :
      (img, info, bounds, None) en cas de succès
      (None, None, None, error_reason) en cas d'échec

    Diagnostics :
      A. Disponibilité EE
      A2. Construction géométrie / dates
      B. Accès collection Sentinel-2
      C. Construction composite
      D. getThumbURL
      E. Téléchargement
      F. Décodage Pillow
      G. Récupération des bounds
    """

    # --------------------------------------
    # ÉTAPE A — DISPONIBILITÉ EE
    # --------------------------------------

    if (
        not HAS_PIL
        or not HAS_EE
        or not polygon_points
        or len(polygon_points) < 3
    ):
        return (
            None,
            None,
            None,
            "Prerequisites missing (Pillow/EE/polygon)",
        )

    if not _init_ee():
        return (
            None,
            None,
            None,
            "Earth Engine not initialized",
        )

    # --------------------------------------
    # ÉTAPE A2 — GÉOMÉTRIE ET PÉRIODE
    # --------------------------------------

    try:

        # Les coordonnées d'entrée sont [longitude, latitude].
        # Conversion explicite en float.
        ring = [
            [
                float(point[0]),
                float(point[1]),
            ]
            for point in polygon_points
        ]

        # Fermeture explicite de l'anneau.
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        # Construction du polygone avec un anneau explicite.
        roi = ee.Geometry.Polygon([ring]).buffer(buffer_m)

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365)

        print(
            f"🔎 Étape A2 — ROI construite : "
            f"{len(ring)} points (fermeture incluse), "
            f"buffer={buffer_m} m."
        )

        print(
            "🔎 Étape A2 — Temporal window : "
            f"{start_date.strftime('%Y-%m-%d')} → "
            f"{end_date.strftime('%Y-%m-%d')}"
        )

    except Exception as e:

        print(
            f"⚠️ Étape A2 — ROI build failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"ROI build failed ({type(e).__name__})",
        )

    # --------------------------------------
    # ÉTAPE B — COLLECTION SENTINEL-2
    # --------------------------------------

    try:

        coll = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(roi)
            .filterDate(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )
        )

        coll_size = coll.size().getInfo()

        print(
            f"🔎 Étape B — S2 scenes on 12-month window: "
            f"{coll_size}"
        )

        if coll_size == 0:
            return (
                None,
                None,
                None,
                "No Sentinel-2 scene on 12-month window",
            )

    except Exception as e:

        print(
            f"⚠️ Étape B — S2 collection access failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"S2 collection access failed ({type(e).__name__})",
        )

    # --------------------------------------
    # ÉTAPE C — COMPOSITE
    # --------------------------------------

    try:

        clear = coll.filter(
            ee.Filter.lt(
                "CLOUDY_PIXEL_PERCENTAGE",
                20
            )
        )

        clear_size = clear.size().getInfo()

        print(
            f"🔎 Étape C — scenes <20% cloud: "
            f"{clear_size}"
        )

        if clear_size > 0:

            final = clear.median()

            info = (
                f"Median composite "
                f"{start_date.strftime('%Y-%m-%d')} → "
                f"{end_date.strftime('%Y-%m-%d')}, "
                f"{clear_size} scenes <20% cloud "
                f"(global scene metric)"
            )

        else:

            best = coll.sort(
                "CLOUDY_PIXEL_PERCENTAGE"
            ).first()

            pct = best.get(
                "CLOUDY_PIXEL_PERCENTAGE"
            ).getInfo()

            scene_date = (
                ee.Date(
                    best.get("system:time_start")
                )
                .format("YYYY-MM-dd")
                .getInfo()
            )

            final = best

            info = (
                f"Best available scene {scene_date}, "
                f"{pct:.1f}% cloud "
                f"(global scene metric)"
            )

        print(
            f"🔎 Étape C — composite built: {info}"
        )

    except Exception as e:

        print(
            f"⚠️ Étape C — composite build failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"Composite build failed ({type(e).__name__})",
        )

    # --------------------------------------
    # ÉTAPE D — GÉNÉRATION DE LA VIGNETTE
    # --------------------------------------

    try:

        url = (
            final.visualize(
                bands=["B4", "B3", "B2"],
                min=0,
                max=3000,
            )
            .getThumbURL({
                "region": roi,
                "dimensions": image_size,
                "format": "png",
            })
        )

        print("🔎 Étape D — getThumbURL OK")

    except Exception as e:

        print(
            f"⚠️ Étape D — getThumbURL failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"getThumbURL failed ({type(e).__name__})",
        )

    # --------------------------------------
    # ÉTAPE E — TÉLÉCHARGEMENT
    # --------------------------------------

    try:

        resp = requests.get(
            url,
            timeout=15
        )

        print(
            f"🔎 Étape E — HTTP {resp.status_code}, "
            f"{len(resp.content)} bytes"
        )

        resp.raise_for_status()

    except Exception as e:

        print(
            f"⚠️ Étape E — download failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"Download failed ({type(e).__name__})",
        )

    # --------------------------------------
    # ÉTAPE F — DÉCODAGE PILLOW
    # --------------------------------------

    try:

        img = PILImage.open(
            io.BytesIO(resp.content)
        ).convert("RGBA")

        print(
            f"🔎 Étape F — image decoded: "
            f"{img.size[0]}x{img.size[1]} px"
        )

    except Exception as e:

        print(
            f"⚠️ Étape F — decode failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"Decode failed ({type(e).__name__})",
        )

    # --------------------------------------
    # ÉTAPE G — BOUNDS GEOJSON
    # --------------------------------------

    try:

        # getInfo() retourne un dictionnaire GeoJSON :
        # {"type": "Polygon", "coordinates": [...]}
        # et non une liste directement indexable par [0].

        bounds_info = roi.bounds().getInfo()

        if not isinstance(bounds_info, dict):
            raise ValueError(
                "Unexpected Earth Engine bounds response "
                "(not a dict)"
            )

        coordinates = bounds_info.get("coordinates")

        if not coordinates or not coordinates[0]:
            raise ValueError(
                "Missing coordinates in Earth Engine bounds"
            )

        bounds = coordinates[0]

        min_lon = min(p[0] for p in bounds)
        max_lon = max(p[0] for p in bounds)

        min_lat = min(p[1] for p in bounds)
        max_lat = max(p[1] for p in bounds)

        if (
            max_lon <= min_lon
            or max_lat <= min_lat
        ):
            raise ValueError(
                "Invalid geographic bounds (degenerate extent)"
            )

        print(
            "🔎 Étape G — bounds OK "
            f"[{min_lon:.4f},{min_lat:.4f} → "
            f"{max_lon:.4f},{max_lat:.4f}]"
        )

        return (
            img,
            info,
            (
                min_lon,
                max_lon,
                min_lat,
                max_lat,
            ),
            None,
        )

    except Exception as e:

        print(
            f"⚠️ Étape G — bounds retrieval failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            None,
            f"Bounds retrieval failed ({type(e).__name__})",
        )


# ==========================================
# OUTILS DE DESSIN CARTOGRAPHIQUE
# ==========================================

def _bbox_overlap(a, b):
    """
    Test de chevauchement entre deux boîtes :
    (left, top, right, bottom).
    """

    return not (
        a[2] < b[0]
        or b[2] < a[0]
        or a[3] < b[1]
        or b[3] < a[1]
    )


def _nice_scale(max_m):
    """
    Plus grande valeur de {1, 2, 5} × 10ⁿ
    inférieure ou égale à max_m.
    """

    if not max_m or max_m <= 0:
        return 1

    exp = math.floor(
        math.log10(max_m)
    )

    for mult in (5, 2, 1):

        val = mult * (10 ** exp)

        if val <= max_m:
            return int(val)

    if exp > 0:
        return int(10 ** (exp - 1))

    return 1


# ==========================================
# DESSIN COMMUN AUX DEUX CARTES
# ==========================================

def _draw_common(
    img,
    polygon_points,
    bounds,
    scale_m,
    places=None
):
    """
    Dessine :
      - polygone parcellaire
      - centroïde
      - Nord
      - échelle
      - villages OSM éventuels

    scale_m :
      - 100 m pour la carte parcellaire
      - 1 000 m pour la carte de contexte
    """

    draw = ImageDraw.Draw(img)

    img_w, img_h = img.size

    min_lon, max_lon, min_lat, max_lat = bounds

    def project(lon, lat):

        x = (
            (lon - min_lon)
            / (max_lon - min_lon)
            * img_w
        )

        y = (
            (max_lat - lat)
            / (max_lat - min_lat)
            * img_h
        )

        return (x, y)

    # --------------------------------------
    # VILLAGES ET LOCALITÉS OSM
    # --------------------------------------

    if places:

        try:

            font = ImageFont.truetype(
                "DejaVuSans-Bold.ttf",
                13
            )

        except Exception:

            font = ImageFont.load_default()

        def _prio(p):

            return {
                "city": 0,
                "town": 1,
                "village": 2,
            }.get(
                p.get("type"),
                3
            )

        visible = [
            p
            for p in places
            if (
                min_lon <= p["lon"] <= max_lon
                and min_lat <= p["lat"] <= max_lat
            )
        ]

        visible.sort(key=_prio)

        type_colors = {
            "city": "#FFD700",
            "town": "#FFA500",
            "village": "#FFFFFF",
        }

        type_sizes = {
            "city": 6,
            "town": 5,
            "village": 4,
        }

        placed_boxes = []

        for place in visible:

            px, py = project(
                place["lon"],
                place["lat"]
            )

            ptype = place.get(
                "type",
                "village"
            )

            dot_color = type_colors.get(
                ptype,
                "#FFFFFF"
            )

            dot_r = type_sizes.get(
                ptype,
                4
            )

            draw.ellipse(
                [
                    (px - dot_r, py - dot_r),
                    (px + dot_r, py + dot_r),
                ],
                fill=dot_color,
                outline="#000000",
                width=1,
            )

            try:

                bbox = draw.textbbox(
                    (0, 0),
                    place["name"],
                    font=font
                )

                lw = bbox[2] - bbox[0]
                lh = bbox[3] - bbox[1]

            except Exception:

                lw, lh = 60, 14

            candidates = [
                (
                    px + dot_r + 2,
                    py - lh // 2
                ),
                (
                    px - lw - dot_r - 2,
                    py - lh // 2
                ),
                (
                    px - lw // 2,
                    py - lh - dot_r - 2
                ),
                (
                    px - lw // 2,
                    py + dot_r + 2
                ),
            ]

            for lx, ly in candidates:

                if (
                    lx < 5
                    or ly < 5
                    or lx + lw > img_w - 5
                    or ly + lh > img_h - 5
                ):
                    continue

                box = (
                    lx,
                    ly,
                    lx + lw,
                    ly + lh
                )

                if any(
                    _bbox_overlap(box, ob)
                    for ob in placed_boxes
                ):
                    continue

                draw.text(
                    (lx, ly),
                    place["name"],
                    fill="#FFFFFF",
                    font=font,
                    stroke_width=2,
                    stroke_fill="#000000",
                )

                placed_boxes.append(box)

                break

    # --------------------------------------
    # POLYGONE PARCELLAIRE
    # --------------------------------------

    if polygon_points and len(polygon_points) >= 3:

        coords = [
            project(lon, lat)
            for lon, lat in polygon_points
        ]

        draw.line(
            coords + [coords[0]],
            fill="#CC0000",
            width=4,
        )

        try:

            c = Polygon(
                polygon_points
            ).centroid

            cx, cy = project(
                c.x,
                c.y
            )

            draw.ellipse(
                [
                    (cx - 5, cy - 5),
                    (cx + 5, cy + 5),
                ],
                fill="#CC0000",
                outline="#FFFFFF",
                width=2,
            )

        except Exception:
            pass

    # --------------------------------------
    # FLÈCHE DU NORD
    # --------------------------------------

    try:

        draw.text(
            (img_w - 30, 10),
            "N",
            fill="#FFFFFF",
            anchor="mm",
            stroke_width=2,
            stroke_fill="#000000",
        )

        draw.line(
            [
                (img_w - 30, 20),
                (img_w - 30, 40),
            ],
            fill="#FFFFFF",
            width=2,
        )

        draw.polygon(
            [
                (img_w - 30, 15),
                (img_w - 35, 25),
                (img_w - 25, 25),
            ],
            fill="#FFFFFF",
        )

    except Exception:
        pass

    # --------------------------------------
    # ÉCHELLE GRAPHIQUE
    # --------------------------------------

    try:

        geod = Geod(
            ellps="WGS84"
        )

        _, _, width_m = geod.inv(
            min_lon,
            min_lat,
            max_lon,
            min_lat,
        )

        width_m = abs(width_m)

        if width_m > 0:

            pixels_per_meter = img_w / width_m

            max_bar_pixels = img_w - 40

            max_distance_m = (
                max_bar_pixels
                / pixels_per_meter
            )

            cap_m = (
                min(scale_m, max_distance_m)
                if scale_m
                else max_distance_m
            )

            nice_m = _nice_scale(cap_m)

            x_scale = (
                nice_m
                * pixels_per_meter
            )

            draw.line(
                [
                    (10, img_h - 20),
                    (10 + x_scale, img_h - 20),
                ],
                fill="#FFFFFF",
                width=3,
            )

            draw.text(
                (10, img_h - 35),
                f"{nice_m} m",
                fill="#FFFFFF",
                stroke_width=2,
                stroke_fill="#000000",
            )

    except Exception:
        pass


# ==========================================
# CARTE PARCELLAIRE
# ==========================================

def generate_parcel_map(
    polygon_points,
    path
):
    """
    Carte parcellaire :
      - buffer 200 m
      - échelle cible 100 m
    """

    img, info, bounds, error = _fetch_satellite_image(
        polygon_points,
        buffer_m=200
    )

    if img is None:
        return None, None, error

    try:

        _draw_common(
            img,
            polygon_points,
            bounds,
            scale_m=100,
            places=None,
        )

        img.convert("RGB").save(
            path,
            format="PNG"
        )

    except Exception as e:

        print(
            f"⚠️ Étape H (parcel) — save failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            f"Save failed ({type(e).__name__})",
        )

    return path, info, None


# ==========================================
# CARTE DE CONTEXTE TERRITORIAL
# ==========================================

def generate_context_map(
    polygon_points,
    lat,
    lon,
    path
):
    """
    Carte de contexte :
      - buffer 2 500 m
      - échelle cible 1 000 m
      - recherche Overpass dans un rayon de 3 000 m
    """

    img, info, bounds, error = _fetch_satellite_image(
        polygon_points,
        buffer_m=2500
    )

    if img is None:
        return None, None, error

    places = fetch_osm_places(
        lat,
        lon,
        radius_m=3000
    )

    try:

        _draw_common(
            img,
            polygon_points,
            bounds,
            scale_m=1000,
            places=places,
        )

        img.convert("RGB").save(
            path,
            format="PNG"
        )

    except Exception as e:

        print(
            f"⚠️ Étape H (context) — save failed: "
            f"{type(e).__name__}: {e}"
        )

        return (
            None,
            None,
            f"Save failed ({type(e).__name__})",
        )

    return path, info, None# ==========================================
# GÉNÉRATION DU PDF
# ==========================================

def generate_eudr_pdf(
    audit_id,
    name,
    lat,
    lon,
    risk_score,
    risk_level,
    eudr_status,
    tree_cover,
    loss_year,
    source="unknown",
    polygon_points=None,
    dataset_version="Unknown",
    **kwargs
):

    temp_id = uuid.uuid4().hex

    file_path = f"/tmp/{audit_id}_{temp_id}.pdf"
    qr_path = f"/tmp/{audit_id}_{temp_id}_qr.png"
    parcel_path = f"/tmp/{audit_id}_{temp_id}_parcel.png"
    context_path = f"/tmp/{audit_id}_{temp_id}_context.png"

    success = False

    try:

        # ======================================
        # DONNÉES DE L'AUDIT
        # ======================================

        full_audit = get_audit(audit_id) or {}

        valid_pixels = full_audit.get("valid_pixels")
        nominal_pixels = full_audit.get("nominal_pixels_estimate")
        coverage_pct = full_audit.get("estimated_coverage_pct")
        insufficient_reason = full_audit.get("insufficient_reason")
        treecover_reason = full_audit.get("treecover_reason")

        # ======================================
        # DOCUMENT ET STYLES
        # ======================================

        doc = SimpleDocTemplate(
            file_path,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        styles = get_custom_styles()

        content = []

        current_date = datetime.now().strftime(
            "%d %b %Y – %H:%M"
        )

        # ======================================
        # SIGNATURE ET VÉRIFICATION
        # ======================================

        signature = sign_audit(audit_id)

        verify_url = (
            f"{BASE_URL}/eudr/verify/"
            f"{audit_id}?signature={signature}"
        )

        safe_name = html.escape(str(name))
        safe_id = html.escape(str(audit_id))

        valid_statuses = [
            "NO POST-2020 LOSS DETECTED",
            "BELOW TDM SCREENING THRESHOLD",
            "POTENTIAL LOSS SIGNAL",
            "INSUFFICIENT DATA",
            "ANALYSIS UNAVAILABLE",
        ]

        safe_status = (
            html.escape(str(eudr_status))
            if eudr_status in valid_statuses
            else "UNKNOWN STATUS"
        )

        # ======================================
        # QR CODE ET LOGO
        # ======================================

        qrcode.make(verify_url).save(qr_path)

        qr_img = Image(
            qr_path,
            width=60,
            height=60
        )

        logo_data = get_logo()

        logo_img = (
            Image(
                logo_data,
                width=80,
                height=65
            )
            if logo_data
            else Paragraph(
                "TDM",
                styles["TDMTitle"]
            )
        )

        # ======================================
        # EN-TÊTE DU RAPPORT
        # ======================================

        header_data = [[
            logo_img,

            Paragraph(
                "EUDR TERRITORIAL TRACEABILITY<br/>"
                "&amp; DUE DILIGENCE SUPPORT REPORT",
                styles["TDMTitle"]
            ),

            qr_img,
        ]]

        header_table = Table(
            header_data,
            colWidths=[
                3 * cm,
                11 * cm,
                3 * cm,
            ],
        )

        header_table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (0, 0),
                    "LEFT",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, 0),
                    "CENTER",
                ),
                (
                    "ALIGN",
                    (2, 0),
                    (2, 0),
                    "RIGHT",
                ),
            ])
        )

        content.append(header_table)

        content.append(
            Spacer(1, 0.5 * cm)
        )

        # ======================================
        # GÉOMÉTRIE ET SUPERFICIE
        # ======================================

        if polygon_points:

            centroid_str, area_str = calculate_geometry(
                polygon_points
            )

        elif lat is not None and lon is not None:

            centroid_str = f"{lat:.6f}, {lon:.6f}"
            area_str = "N/A"

        else:

            centroid_str = "N/A"
            area_str = "N/A"

        display_point_count = (
            len(polygon_points) - 1
            if (
                polygon_points
                and len(polygon_points) >= 2
                and polygon_points[0] == polygon_points[-1]
            )
            else (
                len(polygon_points)
                if polygon_points
                else None
            )
        )

        # ======================================
        # IDENTIFICATION DE L'AUDIT
        # ======================================

        id_data = [

            [
                Paragraph(
                    "Report ID",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Generated on",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Producer / Farm",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Centroid",
                    styles["TDMLabel"]
                ),
            ],

            [
                Paragraph(
                    safe_id,
                    styles["TDMValue"]
                ),

                Paragraph(
                    current_date,
                    styles["TDMValue"]
                ),

                Paragraph(
                    safe_name,
                    styles["TDMValue"]
                ),

                Paragraph(
                    centroid_str,
                    styles["TDMValue"]
                ),
            ],
        ]

        id_table = Table(
            id_data,
            colWidths=[
                4 * cm,
                4 * cm,
                4 * cm,
                4 * cm,
            ],
        )

        id_table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, 0),
                    2,
                ),
            ])
        )

        content.append(id_table)

        content.append(
            Spacer(1, 0.5 * cm)
        )

        # ======================================
        # CARTE PARCELLAIRE
        # ======================================

        if polygon_points and len(polygon_points) >= 3:

            parcel_map, parcel_info, parcel_err = (
                generate_parcel_map(
                    polygon_points,
                    parcel_path
                )
            )

        else:

            parcel_map = None
            parcel_info = None
            parcel_err = "No polygon"

        parcel_inserted = False

        if (
            parcel_map
            and os.path.exists(parcel_map)
        ):

            try:

                with PILImage.open(parcel_map) as src:
                    w, h = src.size

                scale = min(
                    (17 * cm) / w,
                    (9 * cm) / h
                )

                content.append(
                    Image(
                        parcel_map,
                        width=w * scale,
                        height=h * scale,
                    )
                )

                if parcel_info:

                    content.append(
                        Paragraph(
                            "<font size='7' color='#888888'>"
                            "Sentinel-2 B4/B3/B2 "
                            "(10 m native) — "
                            f"{html.escape(parcel_info)}"
                            "</font>",
                            styles["TDMLegal"],
                        )
                    )

                content.append(
                    Paragraph(
                        "Total Area: "
                        f"{area_str} | Boundary points: "
                        f"{display_point_count if display_point_count is not None else 'Point mode'}",
                        styles["TDMValue"],
                    )
                )

                parcel_inserted = True

            except Exception as e:

                print(
                    "⚠️ Erreur insertion carte parcellaire : "
                    f"{type(e).__name__}: {e}"
                )

        if not parcel_inserted:

            reason = html.escape(
                parcel_err or "unavailable"
            )

            map_box = Table(
                [[
                    Paragraph(
                        f"Total Area: {area_str}<br/>"
                        "Boundary points: "
                        f"{display_point_count if display_point_count is not None else 'Point mode'}"
                        "<br/>"
                        f"<i>Satellite parcel map unavailable ({reason})</i>",
                        styles["TDMValue"],
                    )
                ]],
                colWidths=[17 * cm],
                rowHeights=[3 * cm],
            )

            map_box.setStyle(
                TableStyle([
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        TDM_LIGHT_GREEN,
                    ),
                    (
                        "ALIGN",
                        (0, 0),
                        (-1, -1),
                        "CENTER",
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        1,
                        TDM_GREEN,
                    ),
                ])
            )

            content.append(map_box)

        content.append(
            Spacer(1, 0.5 * cm)
        )

        # ======================================
        # COULEUR DU STATUT
        # ======================================

        if "NO POST-2020" in safe_status:

            status_color = "#1E3A32"

        elif "POTENTIAL" in safe_status:

            status_color = "#CC0000"

        elif "INSUFFICIENT DATA" in safe_status:

            status_color = "#D97706"

        else:

            status_color = "#F59E0B"

        # ======================================
        # INDICATEURS PRINCIPAUX
        # ======================================

        tc_display = format_val(
            tree_cover,
            "%",
            0,
            100
        )

        score_display = format_val(
            risk_score,
            "",
            0,
            100
        )

        loss_display = get_loss_display(
            safe_status,
            loss_year
        )

        findings_data = [

            [
                Paragraph(
                    "Tree Cover",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Last Loss",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Risk Score",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Screening Status",
                    styles["TDMLabel"]
                ),
            ],

            [
                Paragraph(
                    f"<b>{tc_display}</b>",
                    styles["TDMValue"]
                ),

                Paragraph(
                    f"<b>{loss_display}</b>",
                    styles["TDMValue"]
                ),

                Paragraph(
                    f"<b>{score_display}</b>",
                    styles["TDMValue"]
                ),

                Paragraph(
                    f"<font color='{status_color}'>"
                    f"<b>{safe_status}</b>"
                    "</font>",
                    styles["TDMValue"]
                ),
            ],
        ]

        findings_table = Table(
            findings_data,
            colWidths=[4.25 * cm] * 4
        )

        findings_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    TDM_GRAY,
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "LINEBEFORE",
                    (1, 0),
                    (-1, -1),
                    0.5,
                    colors.lightgrey,
                ),
            ])
        )

        content.append(findings_table)

        content.append(
            Spacer(1, 0.5 * cm)
        )

        # ======================================
        # DISCLAIMER EUDR
        # ======================================

        disclaimer_text = (
            "<b>THIS REPORT IS A TERRITORIAL SCREENING, "
            "NOT A CERTIFICATE</b><br/>"
            "This document provides a technical traceability "
            "and documentation support report. "
            "It is not a certificate of compliance with "
            "the EU Deforestation Regulation (EUDR) "
            "and does not replace the legal Due Diligence "
            "required by the operator or the relevant authorities."
        )

        disclaimer = Table(
            [[
                Paragraph(
                    disclaimer_text,
                    styles["TDMDisclaimer"]
                )
            ]],
            colWidths=[17 * cm]
        )

        disclaimer.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    TDM_LIGHT_GREEN,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    1,
                    TDM_GREEN,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
            ])
        )

        content.append(disclaimer)

        # ======================================
        # ANNEXE TECHNIQUE — PAGE 2
        # ======================================

        content.append(PageBreak())

        content.append(
            Paragraph(
                "TECHNICAL ASSESSMENT ANNEX",
                styles["TDMSection"]
            )
        )

        content.append(
            Spacer(1, 0.3 * cm)
        )

        source_desc = (
            "Google Earth Engine (Hansen)"
            if source == "ee"
            else (
                "Global Forest Watch"
                if source == "gfw"
                else "Analysis Unavailable"
            )
        )

        period_text = ""

        if (
            source == "ee"
            and dataset_version == EXPECTED_DATASET
        ):

            period_text = (
                "• Dataset Coverage: 2001–2023<br/>"
            )

        # Hansen 30 m seulement si :
        # source == "ee"
        # ET dataset_version correspond au dataset attendu.

        hansen_line = (
            "• Hansen Global Forest Change: "
            "30 m resolution<br/>"
            if (
                source == "ee"
                and dataset_version == EXPECTED_DATASET
            )
            else ""
        )

        method_text = (
            "<b>Data &amp; Methodology</b><br/>"

            f"• Data Source: "
            f"{html.escape(source_desc)}<br/>"

            f"• Dataset Version: "
            f"{html.escape(str(dataset_version))}<br/>"

            f"{period_text}"

            "• EUDR Reference Date: 31 Dec 2020<br/>"

            f"{hansen_line}"

            "• Sentinel-2 RGB (B4/B3/B2): "
            "10 m native resolution<br/>"

            "<i>Note: cloud percentage shown on satellite maps "
            "is the global scene metric, not a cloud-cover "
            "measurement over the parcel.</i><br/><br/>"

            "<i>Note: This report is a general agricultural "
            "territorial screening. It does not certify "
            "compliance with EUDR, which only applies to "
            "specific commodities and operators.</i>"
        )

        content.append(
            Paragraph(
                method_text,
                styles["TDMValue"]
            )
        )

        content.append(
            Spacer(1, 0.5 * cm)
        )

        # ======================================
        # QUALITÉ ET COUVERTURE DES DONNÉES
        # ======================================

        if (
            coverage_pct is not None
            or valid_pixels is not None
            or insufficient_reason
            or treecover_reason
        ):

            content.append(
                Paragraph(
                    "Screening Quality & Coverage Metrics",
                    styles["TDMSection"]
                )
            )

            if (
                isinstance(coverage_pct, (int, float))
                and not isinstance(coverage_pct, bool)
                and math.isfinite(coverage_pct)
                and coverage_pct >= 0
            ):

                cov_display = (
                    f"<b>{coverage_pct:.2f}%</b>"
                )

                if coverage_pct > 100:

                    cov_display += (
                        "<br/>"
                        "<font color='#D97706'>"
                        "Above nominal estimate"
                        "</font>"
                    )

            else:

                cov_display = "N/A"

            metrics_data = [

                [
                    Paragraph(
                        "Estimated Coverage",
                        styles["TDMLabel"]
                    ),

                    Paragraph(
                        "Valid Pixels",
                        styles["TDMLabel"]
                    ),

                    Paragraph(
                        "Nominal Pixels (Estimate)",
                        styles["TDMLabel"]
                    ),
                ],

                [
                    Paragraph(
                        cov_display,
                        styles["TDMValue"]
                    ),

                    Paragraph(
                        (
                            f"{valid_pixels}"
                            if valid_pixels is not None
                            else "N/A"
                        ),
                        styles["TDMValue"]
                    ),

                    Paragraph(
                        (
                            f"{nominal_pixels}"
                            if nominal_pixels is not None
                            else "N/A"
                        ),
                        styles["TDMValue"]
                    ),
                ],
            ]

            metrics_table = Table(
                metrics_data,
                colWidths=[5.66 * cm] * 3
            )

            metrics_table.setStyle(
                TableStyle([
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        TDM_GRAY,
                    ),
                    (
                        "ALIGN",
                        (0, 0),
                        (-1, -1),
                        "CENTER",
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.lightgrey,
                    ),
                ])
            )

            content.append(metrics_table)

            content.append(
                Spacer(1, 0.3 * cm)
            )

            if insufficient_reason:

                content.append(
                    Paragraph(
                        "<b>Insufficiency Reason:</b> "
                        f"{html.escape(str(insufficient_reason))}",
                        styles["TDMValue"]
                    )
                )

            if treecover_reason:

                content.append(
                    Paragraph(
                        "<b>Treecover Availability:</b> "
                        f"{html.escape(str(treecover_reason))}",
                        styles["TDMValue"]
                    )
                )

            content.append(
                Spacer(1, 0.5 * cm)
            )

        # ======================================
        # DONNÉES GÉOSPATIALES
        # ======================================

        if polygon_points and len(polygon_points) >= 3:

            content.append(
                Paragraph(
                    "Geospatial Data (Polygon)",
                    styles["TDMSection"]
                )
            )

            content.append(
                Paragraph(
                    f"Centroid: {centroid_str} "
                    f"| Area: {area_str}",
                    styles["TDMValue"]
                )
            )

            content.append(
                Spacer(1, 0.2 * cm)
            )

            poly_data = [[

                Paragraph(
                    "Point",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Latitude",
                    styles["TDMLabel"]
                ),

                Paragraph(
                    "Longitude",
                    styles["TDMLabel"]
                ),

            ]]

            display_points = (
                polygon_points[:-1]
                if polygon_points[0] == polygon_points[-1]
                else polygon_points
            )

            for i, (p_lon, p_lat) in enumerate(
                display_points,
                start=1
            ):

                poly_data.append([

                    Paragraph(
                        str(i),
                        styles["TDMValue"]
                    ),

                    Paragraph(
                        f"{p_lat:.6f}",
                        styles["TDMValue"]
                    ),

                    Paragraph(
                        f"{p_lon:.6f}",
                        styles["TDMValue"]
                    ),

                ])

            poly_table = Table(
                poly_data,
                colWidths=[
                    2 * cm,
                    5 * cm,
                    5 * cm,
                ],
                repeatRows=1,
                splitByRow=1,
            )

            poly_table.setStyle(
                TableStyle([
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.lightgrey,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        TDM_GRAY,
                    ),
                ])
            )

            content.append(poly_table)

        # ======================================
        # CONTEXTE TERRITORIAL — PAGE 3
        # ======================================

        content.append(PageBreak())

        content.append(
            Paragraph(
                "TERRITORIAL CONTEXT &amp; AUDIT",
                styles["TDMSection"]
            )
        )

        content.append(
            Spacer(1, 0.3 * cm)
        )

        if (
            polygon_points
            and len(polygon_points) >= 3
            and lat is not None
            and lon is not None
        ):

            (
                context_map,
                context_info,
                context_err,
            ) = generate_context_map(
                polygon_points,
                lat,
                lon,
                context_path,
            )

        else:

            context_map = None
            context_info = None
            context_err = "No polygon or coordinates"

        # ======================================
        # INSERTION DE LA CARTE TERRITORIALE
        # ======================================

        if (
            context_map
            and os.path.exists(context_map)
        ):

            try:

                with PILImage.open(context_map) as src:
                    w, h = src.size

                scale = min(
                    (17 * cm) / w,
                    (10 * cm) / h
                )

                content.append(
                    Image(
                        context_map,
                        width=w * scale,
                        height=h * scale,
                    )
                )

                if context_info:

                    content.append(
                        Paragraph(
                            "<font size='7' color='#888888'>"
                            "Sentinel-2 B4/B3/B2 "
                            "(10 m native) — "
                            f"{html.escape(context_info)}"
                            "</font>",
                            styles["TDMLegal"],
                        )
                    )

            except Exception as e:

                print(
                    "⚠️ Erreur insertion carte contexte : "
                    f"{type(e).__name__}: {e}"
                )

                content.append(
                    Paragraph(
                        "<i>Territorial context map "
                        "unavailable (rendering error).</i>",
                        styles["TDMValue"],
                    )
                )

        else:

            reason = html.escape(
                context_err or "unavailable"
            )

            content.append(
                Paragraph(
                    "<i>Territorial context map unavailable "
                    f"({reason}).</i>",
                    styles["TDMValue"],
                )
            )

        # ======================================
        # CONTEXTE ADMINISTRATIF — NOMINATIM
        # ======================================

        terr_context = (
            get_territorial_context(lat, lon)
            if (
                lat is not None
                and lon is not None
            )
            else None
        )

        if terr_context:

            parts = []

            if terr_context.get("place_name"):

                parts.append(
                    "OSM Place: "
                    + html.escape(
                        terr_context["place_name"]
                    )
                )

            if terr_context.get("town_name"):

                parts.append(
                    "OSM Town: "
                    + html.escape(
                        terr_context["town_name"]
                    )
                )

            if terr_context.get("city_name"):

                parts.append(
                    "OSM City: "
                    + html.escape(
                        terr_context["city_name"]
                    )
                )

            if terr_context.get("municipality_name"):

                parts.append(
                    "Municipality: "
                    + html.escape(
                        terr_context["municipality_name"]
                    )
                )

            if terr_context.get("region"):

                parts.append(
                    "Region: "
                    + html.escape(
                        terr_context["region"]
                    )
                )

            if terr_context.get("country"):

                parts.append(
                    "Country: "
                    + html.escape(
                        terr_context["country"]
                    )
                )

            if parts:

                content.append(
                    Spacer(1, 0.4 * cm)
                )

                content.append(
                    Paragraph(
                        "<br/>".join(parts),
                        styles["TDMValue"]
                    )
                )

                content.append(
                    Paragraph(
                        "<font size='7' color='#888888'>"
                        "Source: Nominatim, OpenStreetMap"
                        "</font>",
                        styles["TDMLegal"],
                    )
                )

        # ======================================
        # VÉRIFICATION FINALE
        # ======================================

        content.append(
            Spacer(1, 1 * cm)
        )

        content.append(
            Paragraph(
                f"Verify at: {html.escape(verify_url)}",
                styles["TDMLegal"]
            )
        )

        # ======================================
        # CONSTRUCTION DU PDF
        # ======================================

        doc.build(content)

        success = True

        return file_path

    finally:

        # ======================================
        # NETTOYAGE DES FICHIERS TEMPORAIRES
        # ======================================

        for path in (
            qr_path,
            parcel_path,
            context_path,
        ):

            try:
                os.remove(path)

            except OSError:
                pass

        if not success:

            try:
                os.remove(file_path)

            except OSError:
                pass
