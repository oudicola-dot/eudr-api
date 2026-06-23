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
    TableStyle
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")

# 🔥 LOGO TIERRAS DE MONTAÑA
LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"


def download_logo():
    """Télécharge le logo en local (Render-safe)"""
    path = "/tmp/tdm_logo.png"

    if not os.path.exists(path):
        r = requests.get(LOGO_URL, timeout=10)
        with open(path, "wb") as f:
            f.write(r.content)

    return path


def generate_eudr_pdf(
    audit_id,
    name,
    lat,
    lon,
    risk_score,
    risk_level
):

    file_path = f"/tmp/{audit_id}.pdf"
    doc = SimpleDocTemplate(file_path)

    styles = getSampleStyleSheet()
    content = []

    # ---------------- TITLE ----------------
    content.append(Paragraph(
        "<b>TIERRAS DE MONTAÑA</b>",
        styles["Title"]
    ))

    content.append(Paragraph(
        "EUDR TRACEABILITY & COMPLIANCE REPORT",
        styles["Heading2"]
    ))

    content.append(Spacer(1, 15))

    # ---------------- LOGO ----------------
    try:
        logo_path = download_logo()
        logo = Image(logo_path, width=140, height=70)
        content.append(logo)
        content.append(Spacer(1, 20))
    except:
        pass

    # ---------------- QR ----------------
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}"

    qr = qrcode.make(verify_url)
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr.save(qr_path)

    content.append(Image(qr_path, width=140, height=140))
    content.append(Spacer(1, 15))

    # ---------------- SECURITY HASH ----------------
    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    # ---------------- TABLE ----------------
    table_data = [
        ["Field", "Value"],
        ["Audit ID", audit_id],
        ["Farm", name],
        ["Latitude", str(lat)],
        ["Longitude", str(lon)],
        ["Risk Score", str(risk_score)],
        ["Risk Level", risk_level],
        ["Status", "PRELIMINARY COMPLIANCE"],
    ]

    table = Table(table_data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.white),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    content.append(table)
    content.append(Spacer(1, 20))

    # ---------------- FOOTER ----------------
    content.append(Paragraph(
        f"<b>SHA256:</b> {sha}",
        styles["Normal"]
    ))

    content.append(Spacer(1, 8))

    content.append(Paragraph(
        f"<b>Verify:</b> {verify_url}",
        styles["Normal"]
    ))

    # ---------------- BUILD ----------------
    doc.build(content)

    try:
        os.remove(qr_path)
    except:
        pass

    return file_path
