import os
import uuid
import hashlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pdf_report import generate_eudr_pdf

app = FastAPI(title="EUDR API V1 Stable", version="1.1")

# ---------------- CORS ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "CHANGE_ME_NOW")
BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")

# ---------------- MEMORY STORE ----------------
# (OK pour V1 demo, remplacé par DB en V2)
AUDITS = {}

# ---------------- ROOT ----------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "EUDR API V1 Stable"
    }


# ---------------- RISK ENGINE ----------------

def compute_risk(lat: float, lon: float):
    seed = abs(int((lat * 1000) + (lon * 1000)))
    risk = seed % 100

    if risk < 30:
        level = "LOW"
    elif risk < 70:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return risk, level


# ---------------- CHECK (AUDIT CREATION) ----------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    audit_id = str(uuid.uuid4())

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    risk_score, risk_level = compute_risk(lat, lon)

    AUDITS[audit_id] = {
        "audit_id": audit_id,
        "farm_name": name,
        "latitude": lat,
        "longitude": lon,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "status": "CREATED"
    }

    return AUDITS[audit_id]


# ---------------- PDF GENERATION (FIXED FLOW) ----------------

@app.post("/eudr-pdf")
def eudr_pdf(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    audit_id = payload.get("audit_id")

    # 🔥 IMPORTANT: must exist first
    audit = AUDITS.get(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    file_path = generate_eudr_pdf(
        audit_id=audit_id,
        name=audit["farm_name"],
        lat=audit["latitude"],
        lon=audit["longitude"],
        risk_score=audit["risk_score"],
        risk_level=audit["risk_level"]
    )

    audit["status"] = "PDF_GENERATED"
    audit["pdf_ready"] = True

    return {
        "audit_id": audit_id,
        "pdf_url": f"{BASE_URL}/download/{audit_id}",
        "verify_url": f"{BASE_URL}/eudr/verify/{audit_id}"
    }


# ---------------- DOWNLOAD ----------------

@app.get("/download/{audit_id}")
def download(audit_id: str):

    file_path = f"/tmp/{audit_id}.pdf"

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="PDF not found (Render /tmp is ephemeral)"
        )

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"EUDR_{audit_id}.pdf"
    )


# ---------------- VERIFY (TRUTH SOURCE) ----------------

@app.get("/eudr/verify/{audit_id}")
def verify(audit_id: str):

    audit = AUDITS.get(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return audit
