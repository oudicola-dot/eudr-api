import os
import html
import hashlib
import math
import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from eudr import init_db, create_audit, get_audit
from pdf_report import generate_eudr_pdf
from security import verify_signature
from shapely.geometry import Polygon

app = FastAPI(title="TDM Territorial Screening API", version="3.9")

def get_real_ip(request: Request):
    # Fallback sur request.client.host. Le rate limiting est une protection "best-effort".
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

limiter = Limiter(key_func=get_real_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tierrasdemontana.com", "https://www.tierrasdemontana.com"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET")
if not TURNSTILE_SECRET:
    raise RuntimeError("TURNSTILE_SECRET missing")

BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")
init_db()

@app.get("/")
def root():
    return {"status": "online", "service": "TDM Territorial Screening API"}

async def verify_turnstile(token: str) -> bool:
    if not token: return False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": TURNSTILE_SECRET, "response": token},
                timeout=5
            )
            data = response.json()
            return (
                data.get("success", False) and 
                data.get("action") == "eudr_screening" and
                data.get("hostname") == "tierrasdemontana.com"
            )
    except Exception:
        return False

@app.post("/eudr-check")
@limiter.limit("5/minute")
async def eudr_check(request: Request, payload: dict):
    cf_token = payload.get("cf_turnstile_response")
    if not await verify_turnstile(cf_token):
        raise HTTPException(status_code=403, detail="CAPTCHA verification failed.")

    raw_name = payload.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise HTTPException(status_code=400, detail="Name must be a non-empty string")
    name = raw_name.strip()
    if len(name) > 160:
        raise HTTPException(status_code=400, detail="Name exceeds 160 characters")

    if isinstance(payload.get("lat"), bool) or isinstance(payload.get("lon"), bool):
        raise HTTPException(status_code=400, detail="Coordinates must be numeric")

    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid coordinate format")

    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Coordinates out of bounds")

    polygon = payload.get("polygon")
    if polygon is not None:
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise HTTPException(status_code=400, detail="Polygon must have at least 3 points")
        if len(polygon) > 2000:
            raise HTTPException(status_code=400, detail="Polygon exceeds 2000 points")
        
        valid_poly = []
        for p in polygon:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise HTTPException(status_code=400, detail="Invalid polygon point format")
            if isinstance(p[0], bool) or isinstance(p[1], bool):
                raise HTTPException(status_code=400, detail="Boolean in polygon coordinates")
            try:
                p_lat, p_lon = float(p[0]), float(p[1])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Polygon coordinates must be numbers")
            
            if not math.isfinite(p_lat) or not math.isfinite(p_lon) or not (-90 <= p_lat <= 90) or not (-180 <= p_lon <= 180):
                raise HTTPException(status_code=400, detail="Polygon coordinates out of bounds")
            
            valid_poly.append((p_lon, p_lat))

        if valid_poly[0] != valid_poly[-1]:
            valid_poly.append(valid_poly[0])
        
        if len(valid_poly) > 2000:
            raise HTTPException(status_code=400, detail="Polygon exceeds 2000 points after closure")

        if len(set(valid_poly)) < 3:
            raise HTTPException(status_code=400, detail="Polygon must have at least 3 distinct vertices.")

        try:
            poly_shape = Polygon(valid_poly)
            if not poly_shape.is_valid or poly_shape.area == 0:
                raise HTTPException(status_code=400, detail="Polygon geometry is invalid or zero area.")
        except Exception as e:
            if isinstance(e, HTTPException): raise e
            raise HTTPException(status_code=400, detail="Polygon validation failed.")

        polygon = valid_poly

    audit = await run_in_threadpool(create_audit, name, lat, lon, polygon)
    audit_id = audit["audit_id"]
    signature = audit["signature"]

    sha = hashlib.sha256(f"{audit_id}{name}{lat}{lon}".encode()).hexdigest()
    audit["partial_checksum"] = sha
    audit["verify_url"] = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
    audit["pdf_url"] = f"{BASE_URL}/download/{audit_id}?signature={signature}"
    return audit

@app.get("/eudr/verify/{audit_id}")
@limiter.limit("20/minute")
def verify_audit(request: Request, audit_id: str, signature: str):
    if not verify_signature(audit_id, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    sha = hashlib.sha256(f"{audit['audit_id']}{audit['farm_name']}{audit['latitude']}{audit['longitude']}".encode()).hexdigest()

    source_label = "Earth Engine (Hansen)" if audit.get("source") == "ee" else "GFW" if audit.get("source") == "gfw" else "Analysis unavailable"
    screening_status = html.escape(str(audit.get('eudr_status', 'UNKNOWN')))
    
    status_colors = {
        "NO POST-2020 LOSS DETECTED": "#00ff99",
        "BELOW TDM SCREENING THRESHOLD": "#ffaa00",
        "POTENTIAL LOSS SIGNAL": "#ff3333",
        "INSUFFICIENT DATA": "#aaaaaa",
        "ANALYSIS UNAVAILABLE": "#aaaaaa"
    }
    status_color = status_colors.get(screening_status, "#aaaaaa")

    safe_id = html.escape(audit_id)
    safe_name = html.escape(str(audit['farm_name']))
    safe_lat = html.escape(str(audit['latitude']))
    safe_lon = html.escape(str(audit['longitude']))
    safe_tc = html.escape(str(audit.get('tree_cover', 'N/A')))
    safe_ly = html.escape(str(audit.get('loss_year', 'N/A')))
    safe_risk = html.escape(str(audit['risk_score']))
    safe_level = html.escape(str(audit['risk_level']))
    safe_dataset = html.escape(str(audit.get('dataset_version', 'Unknown')))
    
    safe_sig = signature if all(c in "0123456789abcdef" for c in signature.lower()) else ""

    return HTMLResponse(f"""
    <html>
    <body style="font-family:Arial;background:#0b1220;color:white;padding:40px;">
        <div style="background:#111a2e;padding:20px;border-radius:12px;max-width:600px;">
            <h2>🌿 TDM Territorial Screening</h2>
            <p><b>Record Status:</b> <span style="color:#00ff99;">TERRITORIAL SCREENING RECORD</span></p>
            <p><b>ID:</b> {safe_id}</p>
            <p><b>Farm:</b> {safe_name}</p>
            <p><b>Lat:</b> {safe_lat}</p>
            <p><b>Lon:</b> {safe_lon}</p>
            <p><b>Tree Cover:</b> {safe_tc}%</p>
            <p><b>Loss Year:</b> {safe_ly}</p>
            <p><b>Risk:</b> {safe_level} ({safe_risk})</p>
            <p><b>Screening Status:</b> <span style="color:{status_color};"><b>{screening_status}</b></span></p>
            <p><b>Data Source:</b> {source_label}</p>
            <p><b>Dataset:</b> {safe_dataset}</p>
            <hr>
            <p><b>Partial Control Checksum:</b><br>{sha}</p>
            <a href="/download/{safe_id}?signature={safe_sig}" style="color:#00ff99;">Download Report</a>
        </div>
    </body>
    </html>
    """)

def cleanup_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

@app.get("/download/{audit_id}")
@limiter.limit("10/minute")
async def download_pdf(request: Request, background_tasks: BackgroundTasks, audit_id: str, signature: str):
    if not verify_signature(audit_id, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    audit = await run_in_threadpool(get_audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")

    try:
        file_path = await run_in_threadpool(
            generate_eudr_pdf,
            audit_id=audit["audit_id"], name=audit["farm_name"], lat=audit["latitude"], lon=audit["longitude"],
            risk_score=audit["risk_score"], risk_level=audit["risk_level"], eudr_status=audit["eudr_status"],
            tree_cover=audit.get("tree_cover", -1), loss_year=audit.get("loss_year", -1),
            source=audit.get("source", "unknown"), polygon_points=audit.get("polygon_points"), dataset_version=audit.get("dataset_version", "Unknown")
        )
        
        background_tasks.add_task(cleanup_file, file_path)
        return FileResponse(path=file_path, media_type="application/pdf", filename=f"TDM_Screening_{audit_id}.pdf", background=background_tasks)
    except Exception as e:
        print(f"❌ PDF ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred.")
