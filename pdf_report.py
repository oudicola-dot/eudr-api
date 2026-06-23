import os
import hashlib
import qrcode

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


BASE_URL = os.getenv(
    "BASE_URL",
    "https://eudr-api-mi0x.onrender.com"
)

# 🔥 IMPORTANT: mettre logo dans repo (PAS URL)
LOGO_PATH = "assets/tdm_logo.png"


# ----------------------------
# SAFE LOGO
# ----------------------------

def get_logo():
    if os.path.exists(LOGO_PATH):
        return LOGO_PATH
    return None


# ----------------------------
# PDF GENERATOR PREMIUM FIXED
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
        "EUDR TRACEABILITY CERTIFICATE",
        styles["Heading2"]
    ))

    content.append(Spacer(1, 20))

    # LOGO SAFE
    logo = get_logo()
    if logo:
        content.append(Image(logo, width=160, height=80))

    content.append(Spacer(1, 30))

    content.append(Paragraph(
        f"<b>Audit ID:</b> {audit_id}",
        styles["Normal"]
    ))

    content.append(Paragraph(
        "Status: PRELIMINARY COMPLIANCE REPORT",
        styles["Normal"]
    ))

    content.append(PageBreak())

    # ---------------- QR ----------------
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}"

    qr = qrcode.make(verify_url)
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr.save(qr_path)

    # ---------------- HASH ----------------
    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    # ---------------- SUMMARY ----------------
    content.append(Paragraph("EXECUTIVE SUMMARY", styles["Heading1"]))
    content.append(Spacer(1, 10))

    content.append(Paragraph(f"Farm: <b>{name}</b>", styles["Normal"]))
    content.append(Paragraph(f"Location: {lat}, {lon}", styles["Normal"]))

    content.append(Spacer(1, 20))

    # ---------------- TABLE ----------------
    table = Table([
        ["Risk Score", risk_score],
        ["Risk Level", risk_level],
        ["Issuer", "Tierras de Montaña"],
        ["Status", "PRELIMINARY"]
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

    content.append(Image(qr_path, width=140, height=140))

    content.append(Spacer(1, 10))

    content.append(Paragraph(
        f"Verification URL: {verify_url}",
        styles["Normal"]
    ))

    # ---------------- SHA ----------------
    content.append(Spacer(1, 15))

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
