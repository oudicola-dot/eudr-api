import os
import hashlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from eudr import init_db, create_audit, get_audit
from pdf_report import generate_eudr_pdf
from security import verify_signature

app = FastAPI(title="EUDR Enterprise Registry", version="2.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY environment variable missing")

BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")

init_db()

@app.get("/")
def root():
    return {"status": "online", "service": "EUDR API"}

@app.post("/eudr-check")
def eudr_check(payload: dict):
    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))
    polygon = payload.get("polygon")
    
    if polygon and len(polygon) >= 3:
        polygon = [[float(p[0]), float(p[1])] for p in polygon]
    else:
        polygon = None
    
    audit = create_audit(name, lat, lon, polygon)
    audit_id = audit["audit_id"]
    signature = audit["signature"]
    
    sha = hashlib.sha256(f"{audit_id}{name}{lat}{lon}".encode()).hexdigest()
    
    audit["sha256"] = sha
    audit["verify_url"] = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
    audit["pdf_url"] = f"{BASE_URL}/download/{audit_id}?signature={signature}"
    
    return audit

@app.get("/eudr/verify/{audit_id}")
def verify_audit(audit_id: str, signature: str):
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    if not verify_signature(audit_id, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    sha = hashlib.sha256(
        f"{audit_id}{audit['farm_name']}{audit['latitude']}{audit['longitude']}".encode()
    ).hexdigest()
    
    source = audit.get("source", "unknown")
    source_label = "🌍 Earth Engine" if source == "ee" else "🛰️ GFW" if source == "gfw" else "⚠️ Simulation"
    
    return HTMLResponse(f"""
    <html>
    <body style="font-family:Arial;background:#0b1220;color:white;padding:40px;">
        <div style="background:#111a2e;padding:20px;border-radius:12px;max-width:600px;">
            <h2>✅ EUDR Verification</h2>
            <p><b>Status:</b> <span style="color:#00ff99;">VALID CERTIFICATE</span></p>
            <p><b>ID:</b> {audit_id}</p>
            <p><b>Farm:</b> {audit['farm_name']}</p>
            <p><b>Lat:</b> {audit['latitude']}</p>
            <p><b>Lon:</b> {audit['longitude']}</p>
            <p><b>Tree Cover:</b> {audit.get('tree_cover', 'N/A')}%</p>
            <p><b>Loss Year:</b> {audit.get('loss_year', 'N/A')}</p>
            <p><b>Risk:</b> {audit['risk_level']} ({audit['risk_score']})</p>
            <p><b>EUDR Status:</b> {audit['eudr_compliant']}</p>
            <p><b>Data Source:</b> {source_label}</p>
            <hr>
            <p><b>SHA256:</b><br>{sha}</p>
            <a href="/download/{audit_id}?signature={signature}" style="color:#00ff99;">
                Download PDF
            </a>
        </div>
    </body>
    </html>
    """)

@app.get("/download/{audit_id}")
def download_pdf(audit_id: str, signature: str):
    print("========== DOWNLOAD ==========")
    print("AUDIT:", audit_id)

    if not verify_signature(audit_id, signature):
        print("INVALID SIGNATURE")
        raise HTTPException(status_code=403, detail="Invalid signature")

    audit = get_audit(audit_id)
    print("AUDIT DATA:", audit)

    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")

    try:
        file_path = generate_eudr_pdf(
            audit_id=audit["audit_id"],
            name=audit["farm_name"],
            lat=audit["latitude"],
            lon=audit["longitude"],
            risk_score=audit["risk_score"],
            risk_level=audit["risk_level"],
            eudr_compliant=audit["eudr_compliant"],
            tree_cover=audit.get("tree_cover", 0),
            loss_year=audit.get("loss_year", 0),
            source=audit.get("source", "unknown"),
            polygon_points=audit.get("polygon_points")
        )

        print("PDF GENERATED:", file_path)

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=f"EUDR_{audit_id}.pdf"
        )

    except Exception as e:
        print("PDF ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audit/{audit_id}", response_class=HTMLResponse)
def audit_page(audit_id: str):
    audit = get_audit(audit_id)
    if not audit:
        return HTMLResponse("<h1>Audit not found</h1>", status_code=404)
    
    sha = hashlib.sha256(
        f"{audit_id}{audit['farm_name']}{audit['latitude']}{audit['longitude']}".encode()
    ).hexdigest()
    
    signature = audit["signature"]
    
    source = audit.get("source", "unknown")
    source_label = "🌍 Earth Engine" if source == "ee" else "🛰️ GFW" if source == "gfw" else "⚠️ Simulation"
    
    return HTMLResponse(f"""
    <html>
    <body style="font-family:Arial;background:#0b1220;color:white;padding:40px;">
        <div style="background:#111a2e;padding:20px;border-radius:12px;max-width:600px;">
            <h2>🌿 EUDR Audit</h2>
            <p><b>ID:</b> {audit_id}</p>
            <p><b>Farm:</b> {audit['farm_name']}</p>
            <p><b>Lat:</b> {audit['latitude']}</p>
            <p><b>Lon:</b> {audit['longitude']}</p>
            <p><b>Tree Cover:</b> {audit.get('tree_cover', 'N/A')}%</p>
            <p><b>Loss Year:</b> {audit.get('loss_year', 'N/A')}</p>
            <p><b>Risk:</b> {audit['risk_level']} ({audit['risk_score']})</p>
            <p><b>EUDR Status:</b> {audit['eudr_compliant']}</p>
            <p><b>Data Source:</b> {source_label}</p>
            <p style="color:#00ff99;"><b>Status:</b> PRELIMINARY RECORD</p>
            <hr>
            <p><b>SHA256:</b><br>{sha}</p>
            <a href="/download/{audit_id}?signature={signature}" style="color:#00ff99;">
                Download PDF
            </a>
        </div>
    </body>
    </html>
    """)
