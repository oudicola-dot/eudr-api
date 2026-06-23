import os
import tempfile

import ee
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pdf_report import generate_eudr_pdf

app = FastAPI()

# -------------------
# CONFIG
# -------------------
API_KEY = "EUDR-SECRET-123"
EE_PROJECT = "superb-gear-473018-k1"

# CORS (important pour Elementor)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------
# INIT EARTH ENGINE
# -------------------
ee.Initialize(project=EE_PROJECT)


# -------------------
# INPUT
# -------------------
class Request(BaseModel):
    api_key: str
    name: str
    lat: float
    lon: float


# -------------------
# CORE ANALYSIS
# -------------------
def analyze(lat, lon):
    point = ee.Geometry.Point([lon, lat]).buffer(1000)

    img = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")

    treecover = img.select("treecover2000")
    loss = img.select("loss")

    forest = treecover.reduceRegion(
        ee.Reducer.mean(),
        point,
        30,
        maxPixels=1e9
    ).get("treecover2000").getInfo()

    defor = loss.reduceRegion(
        ee.Reducer.mean(),
        point,
        30,
        maxPixels=1e9
    ).get("loss").getInfo()

    forest = float(forest or 0)
    defor = float(defor or 0)

    risk = "COMPLIANT"
    if defor > 0.02:
        risk = "NON_COMPLIANT"

    return forest, defor, risk


# -------------------
# API JSON
# -------------------
@app.post("/eudr-check")
def check(req: Request):

    if req.api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    forest, defor, risk = analyze(req.lat, req.lon)

    return {
        "name": req.name,
        "forest_cover": forest,
        "post_2020_deforestation": defor,
        "risk": risk
    }


# -------------------
# API PDF
# -------------------
@app.post("/eudr-pdf")
def pdf(req: Request):

    if req.api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    forest, defor, risk = analyze(req.lat, req.lon)

    result = {
        "name": req.name,
        "lat": req.lat,
        "lon": req.lon,
        "forest_cover": forest,
        "post_2020_deforestation": defor,
        "risk": risk,
        "cutoff": 2020
    }

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)

    generate_eudr_pdf(result, path)

    return FileResponse(path, filename=f"EUDR_{req.name}.pdf")
from pdf_report import generate_eudr_pdf


@app.post("/eudr-pdf")
def eudr_pdf(req: Request):

    data = {
        "name": req.name,
        "lat": req.lat,
        "lon": req.lon,
        "forest_cover": compute_forest(req.lat, req.lon),
        "post_2020_deforestation": compute_loss(req.lat, req.lon),
        "eudr_risk": "COMPLIANT"
    }

    pdf_path = generate_eudr_pdf(data, f"EUDR_{req.name}.pdf")

    return {
        "status": "ok",
        "pdf_path": pdf_path
    }