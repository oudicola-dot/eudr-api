from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import qrcode
import hashlib
import datetime
import os


def generate_certificate_id(data: dict):

    raw = f"{data['name']}{data['lat']}{data['lon']}{datetime.datetime.utcnow()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_qr(cert_id: str):

    img = qrcode.make(f"EUDR CERTIFICATE ID: {cert_id}")
    path = f"/tmp/{cert_id}.png"
    img.save(path)
    return path


def generate_eudr_pdf(data, filename):

    cert_id = generate_certificate_id(data)
    qr_path = generate_qr(cert_id)

    pdf_path = f"/tmp/{filename}"
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("EUDR DUE DILIGENCE CERTIFICATE", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Certificate ID:</b> {cert_id}", styles["Normal"]))
    story.append(Paragraph(f"<b>Farm:</b> {data['name']}", styles["Normal"]))
    story.append(Paragraph(f"<b>Latitude:</b> {data['lat']}", styles["Normal"]))
    story.append(Paragraph(f"<b>Longitude:</b> {data['lon']}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Forest cover:</b> {data.get('forest_cover', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"<b>Deforestation risk:</b> {data.get('post_2020_deforestation', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"<b>Status:</b> {data.get('eudr_risk', 'UNKNOWN')}", styles["Normal"]))

    story.append(Spacer(1, 12))

    story.append(Paragraph("This certificate is generated automatically using satellite data (Google Earth Engine) and is intended for EUDR compliance verification.", styles["BodyText"]))

    doc.build(story)

    return pdf_path