import os
import hashlib
import qrcode
import requests

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = os.getenv(
    "BASE_URL",
    "https://eudr-api-mi0x.onrender.com"
)

LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"


# ----------------------------
# LOGO SAFE DOWNLOAD (CACHE)
# ----------------------------

def get_logo():
    path = "/tmp/tdm_logo.png"

    if not os.path.exists(path):
        try:
            r = requests.get(LOGO_URL, timeout=8)
            r.raise_for_status()

            with open(path, "wb") as f:
                f.write(r.content)
        except:
            return None

    return path


# ----------------------------
# PDF GENERATOR (CLEAN V1)
# ----------------------------

def generate_eudr_pdf(audit_id, name, lat, lon, risk_score, risk_level):

    file_path = f"/tmp/{audit_id}.pdf"
    doc = SimpleDocTemplate(file_path)

    styles = getSampleStyleSheet()
    content = []

    # ---------------- COVER ----------------
    content.append(Spacer(1, 40))

    content.append(Paragraph(
        "<b>TIERRAS DE MONTAÑA</b>",
        styles["Title"]
    ))

    content.append(Paragraph(
        "EUDR TRACEABILITY REPORT",
        styles["Heading2"]
    ))

    content.append(Spacer(1, 20))

    # LOGO SAFE
    logo = get_logo()
    if logo:
        try:
            content.append(Image(logo, width=160, height=80))
        except:
            pass

    content.append(Spacer(1, 25))

    content.append(Paragraph(
        f"<b>Audit ID:</b> {audit_id}",
        styles["Normal"]
    ))

    content.append(Paragraph(
        "Status: PRELIMINARY EUDR RECORD",
        styles["Normal"]
    ))

    content.append(PageBreak())

    # ---------------- QR ----------------
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}"

    qr = qrcode.make(verify_url)
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr.save(qr_path)

    # ---------------- SHA256 ----------------
    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    # ---------------- SECTION ----------------
    content.append(Paragraph("EXECUTIVE SUMMARY", styles["Heading1"]))
    content.append(Spacer(1, 10))

    content.append(Paragraph(f"<b>Farm:</b> {name}", styles["Normal"]))
    content.append(Paragraph(f"<b>Latitude:</b> {lat}", styles["Normal"]))
    content.append(Paragraph(f"<b>Longitude:</b> {lon}", styles["Normal"]))

    content.append(Spacer(1, 20))

    # ---------------- TABLE ----------------
    table = Table([
        ["Risk Score", risk_score],
        ["Risk Level", risk_level],
        ["Issuer", "Tierras de Montaña"],
        ["Status", "PRELIMINARY EUDR RECORD"]
    ])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1f2937")),
    ]))

    content.append(table)

    content.append(Spacer(1, 25))

    # ---------------- QR ----------------
    content.append(Paragraph("VERIFY CERTIFICATE", styles["Heading1"]))
    content.append(Spacer(1, 10))

    try:
        content.append(Image(qr_path, width=150, height=150))
    except:
        pass

    content.append(Spacer(1, 10))

    content.append(Paragraph(
        f"<b>Verification URL:</b> {verify_url}",
        styles["Normal"]
    ))

    content.append(Spacer(1, 15))

    # ---------------- SHA ----------------
    content.append(Paragraph(
        f"<b>SHA256:</b> {sha}",
        styles["Normal"]
    ))

    # ---------------- BUILD ----------------
    doc.build(content)

    # cleanup
    try:
        os.remove(qr_path)
    except:
        pass

    return file_path
