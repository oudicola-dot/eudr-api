from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
import qrcode
import hashlib
import uuid
import os


TDM_LOGO = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"
EU_FLAG = "https://upload.wikimedia.org/wikipedia/commons/b/b7/Flag_of_Europe.svg"


def sha256(text: str):
    return hashlib.sha256(text.encode()).hexdigest()


def generate_eudr_pdf(audit_id, name, lat, lon, risk):

    filename = f"/tmp/{audit_id}.pdf"
    qr_path = f"/tmp/{audit_id}_qr.png"

    # -------------------------
    # PUBLIC VERIFICATION URL
    # -------------------------
    verify_url = f"https://eudr-api-mi0x.onrender.com/eudr/verify/{audit_id}"

    # -------------------------
    # QR CODE
    # -------------------------
    qr = qrcode.make(verify_url)
    qr.save(qr_path)

    # -------------------------
    # HASH (LEGAL INTEGRITY)
    # -------------------------
    raw = f"{audit_id}{name}{lat}{lon}{risk}"
    pdf_hash = sha256(raw)

    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()

    content = []

    # -------------------------
    # HEADER (LOGOS)
    # -------------------------
    content.append(Paragraph("🌿 EUDR Due Diligence Statement", styles["Title"]))
    content.append(Spacer(1, 10))

    content.append(Paragraph(f"<b>Audit ID:</b> {audit_id}", styles["Normal"]))
    content.append(Paragraph(f"<b>Farm:</b> {name}", styles["Normal"]))
    content.append(Paragraph(f"<b>Location:</b> {lat}, {lon}", styles["Normal"]))
    content.append(Paragraph(f"<b>Risk Level:</b> {risk}", styles["Normal"]))

    content.append(Spacer(1, 10))

    # -------------------------
    # LEGAL NOTICE
    # -------------------------
    content.append(Paragraph(
        "This document represents a preliminary EUDR due diligence statement and does not constitute final EU regulatory approval.",
        styles["Normal"]
    ))

    content.append(Spacer(1, 10))

    # -------------------------
    # QR CODE
    # -------------------------
    content.append(Image(qr_path, width=120, height=120))

    content.append(Spacer(1, 10))

    # -------------------------
    # SHA HASH
    # -------------------------
    content.append(Paragraph(f"<b>Document Hash (SHA256):</b>", styles["Normal"]))
    content.append(Paragraph(pdf_hash, styles["Code"]))

    content.append(Spacer(1, 15))

    # -------------------------
    # FOOTER EU LABEL
    # -------------------------
    content.append(Paragraph("🇪🇺 European Union – EUDR Compliance Framework", styles["Italic"]))

    doc.build(content)

    return filename
