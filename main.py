import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from eudr import init_db, create_audit, get_audit
from pdf_report import generate_eudr_pdf


# ---------------- APP ----------------

app = FastAPI(title="EUDR API V1 Clean", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


API_KEY = os.getenv("API_KEY", "CHANGE_ME")
BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")


# ---------------- INIT DB ----------------

init_db()


# ---------------- ROOT ----------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "EUDR Clean API V1"
    }


# ---------------- CHECK (CREATE AUDIT) ----------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    audit = create_audit(name, lat, lon)

    return audit


# ---------------- PDF GENERATION ----------------

@app.post("/eudr-pdf")
def eudr_pdf(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    audit_id = payload.get("audit_id")

    audit = get_audit(audit_id)

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

    return {
        "audit_id": audit_id,
        "pdf_url": f"{BASE_URL}/download/{audit_id}",
        "verify_url": f"{BASE_URL}/eudr/verify/{audit_id}"
    }


# ---------------- DOWNLOAD PDF ----------------

@app.get("/download/{audit_id}")
def download(audit_id: str):

    file_path = f"/tmp/{audit_id}.pdf"

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="PDF not found"
        )

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"EUDR_{audit_id}.pdf"
    )


# ---------------- VERIFY (TRUTH LAYER) ----------------

@app.get("/eudr/verify/{audit_id}")
def verify(audit_id: str):

    audit = get_audit(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return audit
