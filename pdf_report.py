from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
import qrcode
import uuid
import os


def generate_eudr_pdf(audit_id, name, lat, lon, risk):

    filename = f"/tmp/{audit_id}.pdf"
    qr_path = f"/tmp/{audit_id}_qr.png"

    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()

    # --------------------
    # QR CODE CONTENT
    # --------------------
    qr_data = f"""
    EUDR AUDIT
    ID: {audit_id}
    FARM: {name}
    LAT: {lat}
    LON: {lon}
    RISK: {risk}
    """

    qr = qrcode.make(qr_data)
    qr.save(qr_path)

    # --------------------
    # PDF CONTENT
    # --------------------
    content = []

    content.append(Paragraph("EUDR Due Diligence Statement", styles["Title"]))
    content.append(Spacer(1, 12))

    content.append(Paragraph(f"Audit ID: {audit_id}", styles["Normal"]))
    content.append(Paragraph(f"Farm: {name}", styles["Normal"]))
    content.append(Paragraph(f"Latitude: {lat}", styles["Normal"]))
    content.append(Paragraph(f"Longitude: {lon}", styles["Normal"]))
    content.append(Paragraph(f"Risk Level: {risk}", styles["Normal"]))
    content.append(Spacer(1, 20))

    # --------------------
    # QR IMAGE INTO PDF
    # --------------------
    content.append(Image(qr_path, width=120, height=120))

    content.append(Spacer(1, 20))

    content.append(Paragraph(
        "This document is an EUDR preliminary due diligence report.",
        styles["Normal"]
    ))

    doc.build(content)

    return filename
