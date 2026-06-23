from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import os
import ee

from pdf_report import generate_eudr_pdf

# ==========================
# CONFIG
# ==========================

API_KEY = os.getenv("API_KEY", "EUDR-SECRET-123")

EE_PROJECT = os.getenv(
    "EE_PROJECT",
    "superb-gear-473018-k1"
)

EUDR_CUTOFF_YEAR = 2020
FOREST_THRESHOLD = 30

# ==========================
# EARTH ENGINE
# ==========================

try:
    ee.Initialize(project=EE_PROJECT)
    print("EARTH ENGINE OK")

except Exception as e:
    print("EE INIT ERROR:", e)

# ==========================
# API
# ==========================

app = FastAPI(
    title="EUDR Platform",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ==========================
# REQUEST
# ==========================

class RequestData(BaseModel):
    api_key: str
    name: str
    lat: float
    lon: float

# ==========================
# ANALYSE
# ==========================

def calculate_eudr(data):

    point = ee.Geometry.Point(
        [data.lon, data.lat]
    )

    buffer = point.buffer(1000)

    forest = (
        ee.Image(
            "UMD/hansen/global_forest_change_2024_v1_12"
        )
        .select("treecover2000")
    )

    cover = (
        forest
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=buffer,
            scale=30
        )
        .get("treecover2000")
        .getInfo()
    )

    if cover is None:
        cover = 0

    risk = round(max(
        0,
        (FOREST_THRESHOLD-cover)/100
    ),3)

    compliant = risk < 0.05

    return {

        "document":
        "EUDR Due Diligence Statement",

        "farm":
        data.name,

        "coordinates": {
            "lat": data.lat,
            "lon": data.lon
        },

        "forest_cover":
        round(cover,2),

        "cutoff_year":
        EUDR_CUTOFF_YEAR,

        "risk_score":
        risk,

        "status":
        "COMPLIANT"
        if compliant
        else "NON_COMPLIANT",

        "method":
        "Google Earth Engine + Hansen"
    }

# ==========================
# CHECK
# ==========================

@app.post("/eudr-check")
def eudr_check(data: RequestData):

    if data.api_key != API_KEY:

        raise HTTPException(
            401,
            "INVALID API KEY"
        )

    try:

        result = calculate_eudr(data)

        return result

    except Exception as e:

        raise HTTPException(
            500,
            str(e)
        )

# ==========================
# PDF
# ==========================

@app.post("/eudr-pdf")
def eudr_pdf(data: RequestData):

    if data.api_key != API_KEY:

        raise HTTPException(
            401,
            "INVALID API KEY"
        )

    try:

        result = calculate_eudr(data)

        filename = os.path.join(
            tempfile.gettempdir(),
            f"EUDR_{data.name}.pdf"
        )

        generate_eudr_pdf(
            result,
            filename
        )

        return FileResponse(
            filename,
            media_type="application/pdf",
            filename=f"EUDR_{data.name}.pdf"
        )

    except Exception as e:

        raise HTTPException(
            500,
            str(e)
        )

# ==========================
# ROOT
# ==========================

@app.get("/")
def home():

    return {
        "platform":
        "EUDR API ONLINE",

        "status":
        "RUNNING"
    }
