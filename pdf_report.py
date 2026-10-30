import os
import io
import html
import math
import uuid
import qrcode
import requests
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from security import sign_audit
from shapely.geometry import Polygon
from pyproj import Geod

BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")
LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"
EXPECTED_DATASET = "UMD/hansen/global_forest_change_2023_v1_11"

TDM_GREEN = colors.HexColor("#1E3A32")
TDM_LIGHT_GREEN = colors.HexColor("#E8F2E8")
TDM_GRAY = colors.HexColor("#F5F5F5")

def get_logo():
    try:
        r = requests.get(LOGO_URL, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        return io.BytesIO(r.content)
    except Exception:
        return None

def get_custom_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TDMTitle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=TDM_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='TDMLabel', parent=styles['Normal'], fontSize=8, textColor=colors.gray, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='TDMValue', parent=styles['Normal'], fontSize=9, textColor=colors.black, fontName='Helvetica'))
    styles.add(ParagraphStyle(name='TDMSection', parent=styles['Heading2'], fontSize=12, textColor=TDM_GREEN, fontName='Helvetica-Bold', spaceAfter=10))
    styles.add(ParagraphStyle(name='TDMLegal', parent=styles['Normal'], fontSize=7, textColor=colors.gray, fontName='Helvetica'))
    styles.add(ParagraphStyle(name='TDMDisclaimer', parent=styles['Normal'], fontSize=8, textColor=TDM_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER))
    return styles

def format_val(val, suffix="", min_val=0, max_val=100):
    if isinstance(val, bool) or val is None or not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < min_val or val > max_val:
        return "N/A"
    return f"{val}{suffix}"

def format_loss_year(val):
    if isinstance(val, bool) or val is None or not isinstance(val, (int, float)):
        return "N/A"
    if not math.isfinite(val) or not float(val).is_integer():
        return "N/A"
    
    year = int(val)
    if year == 0:
        return "No loss detected"
    elif 2001 <= year <= 2023:
        return str(year)
    else:
        return "N/A"

def get_loss_display(status, loss_year):
    """Fonction isolée pour être testable unitairement."""
    if status in ("INSUFFICIENT DATA", "ANALYSIS UNAVAILABLE", "UNKNOWN STATUS"):
        return "N/A"
    return format_loss_year(loss_year)

def calculate_geometry(polygon_points):
    if not polygon_points or len(polygon_points) < 3:
        return "N/A", "N/A"
    try:
        poly = Polygon(polygon_points)
        if not poly.is_valid:
            return "Invalid geometry", "N/A"
        centroid = poly.centroid
        geod = Geod(ellps="WGS84")
        area_sq_m, _ = geod.geometry_area_perimeter(poly)
        return f"{centroid.y:.6f}, {centroid.x:.6f}", f"{abs(area_sq_m) / 10000.0:.2f} ha"
    except:
        return "Calculation error", "N/A"

def generate_eudr_pdf(audit_id, name, lat, lon, risk_score, risk_level, eudr_status, tree_cover, loss_year, source="unknown", polygon_points=None, dataset_version="Unknown"):
    
    temp_id = uuid.uuid4().hex
    file_path = f"/tmp/{audit_id}_{temp_id}.pdf"
    qr_path = f"/tmp/{audit_id}_{temp_id}_qr.png"
    
    doc = SimpleDocTemplate(file_path, leftMargin=2*cm, rightMargin=2*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = get_custom_styles()
    content = []
    
    current_date = datetime.now().strftime("%d %b %Y – %H:%M")
    signature = sign_audit(audit_id)
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"

    safe_name = html.escape(str(name))
    safe_id = html.escape(str(audit_id))
    
    valid_statuses = ["NO POST-2020 LOSS DETECTED", "BELOW TDM SCREENING THRESHOLD", "POTENTIAL LOSS SIGNAL", "INSUFFICIENT DATA", "ANALYSIS UNAVAILABLE"]
    safe_status = html.escape(str(eudr_status)) if eudr_status in valid_statuses else "UNKNOWN STATUS"

    qrcode.make(verify_url).save(qr_path)
    qr_img = Image(qr_path, width=60, height=60)
    logo_data = get_logo()
    logo_img = Image(logo_data, width=80, height=65) if logo_data else Paragraph("TDM", styles['TDMTitle'])
    
    header_data = [[logo_img, Paragraph("EUDR TERRITORIAL TRACEABILITY<br/>& DUE DILIGENCE SUPPORT REPORT", styles['TDMTitle']), qr_img]]
    header_table = Table(header_data, colWidths=[3*cm, 11*cm, 3*cm])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'RIGHT')]))
    content.append(header_table)
    content.append(Spacer(1, 0.5*cm))

    centroid_str, area_str = calculate_geometry(polygon_points) if polygon_points else (f"{lat:.6f}, {lon:.6f}", "N/A")
    
    id_data = [
        [Paragraph("Report ID", styles['TDMLabel']), Paragraph("Generated on", styles['TDMLabel']), Paragraph("Producer / Farm", styles['TDMLabel']), Paragraph("Centroid", styles['TDMLabel'])],
        [Paragraph(safe_id, styles['TDMValue']), Paragraph(current_date, styles['TDMValue']), Paragraph(safe_name, styles['TDMValue']), Paragraph(centroid_str, styles['TDMValue'])]
    ]
    id_table = Table(id_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    id_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,0), 2)]))
    content.append(id_table)
    content.append(Spacer(1, 0.5*cm))

    map_box = Table([[Paragraph(f"Total Area: {area_str}<br/>Boundary points: {len(polygon_points) if polygon_points else 'Point mode'}", styles['TDMValue'])]], colWidths=[17*cm], rowHeights=[3*cm])
    map_box.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), TDM_LIGHT_GREEN), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BOX', (0,0), (-1,-1), 1, TDM_GREEN)]))
    content.append(map_box)
    content.append(Spacer(1, 0.5*cm))

    status_color = "#1E3A32" if "NO POST-2020" in safe_status else "#CC0000" if "POTENTIAL" in safe_status else "#888888"
    
    tc_display = format_val(tree_cover, "%", 0, 100)
    score_display = format_val(risk_score, "", 0, 100)
    
    # Utilisation de la nouvelle fonction
    loss_display = get_loss_display(safe_status, loss_year)

    findings_data = [
        [Paragraph("Tree Cover", styles['TDMLabel']), Paragraph("Last Loss", styles['TDMLabel']), Paragraph("Risk Score", styles['TDMLabel']), Paragraph("Screening Status", styles['TDMLabel'])],
        [Paragraph(f"<b>{tc_display}</b>", styles['TDMValue']), Paragraph(f"<b>{loss_display}</b>", styles['TDMValue']), Paragraph(f"<b>{score_display}</b>", styles['TDMValue']), Paragraph(f"<font color='{status_color}'><b>{safe_status}</b></font>", styles['TDMValue'])]
    ]
    findings_table = Table(findings_data, colWidths=[4.25*cm]*4)
    findings_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), TDM_GRAY), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8), ('LINEBEFORE', (1,0), (-1,-1), 0.5, colors.lightgrey)]))
    content.append(findings_table)
    content.append(Spacer(1, 0.5*cm))

    disclaimer_text = "<b>THIS REPORT IS A TERRITORIAL SCREENING, NOT A CERTIFICATE</b><br/>This document provides a technical traceability and documentation support report. It is not a certificate of compliance with the EU Deforestation Regulation (EUDR) and does not replace the legal Due Diligence required by the operator or the relevant authorities."
    disclaimer = Table([[Paragraph(disclaimer_text, styles['TDMDisclaimer'])]], colWidths=[17*cm])
    disclaimer.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), TDM_LIGHT_GREEN), ('BOX', (0,0), (-1,-1), 1, TDM_GREEN), ('TOPPADDING', (0,0), (-1,-1), 10), ('BOTTOMPADDING', (0,0), (-1,-1), 10)]))
    content.append(disclaimer)

    content.append(PageBreak())
    content.append(Paragraph("TECHNICAL ASSESSMENT ANNEX", styles['TDMSection']))
    content.append(Spacer(1, 0.3*cm))
    
    source_desc = "Google Earth Engine (Hansen)" if source == "ee" else "Global Forest Watch" if source == "gfw" else "Analysis Unavailable"
    
    period_text = ""
    if source == "ee" and dataset_version == EXPECTED_DATASET:
        period_text = "• Dataset Coverage: 2001–2023<br/>"
    
    method_text = f"<b>Data & Methodology</b><br/>• Data Source: {html.escape(source_desc)}<br/>• Dataset Version: {html.escape(str(dataset_version))}<br/>{period_text}• EUDR Reference Date: 31 Dec 2020<br/>• Spatial Resolution: 30m (when applicable)<br/><br/><i>Note: This report is a general agricultural territorial screening. It does not certify compliance with EUDR, which only applies to specific commodities and operators.</i>"
    content.append(Paragraph(method_text, styles['TDMValue']))
    content.append(Spacer(1, 0.5*cm))
    
    if polygon_points and len(polygon_points) >= 3:
        content.append(Paragraph("Geospatial Data (Polygon)", styles['TDMSection']))
        content.append(Paragraph(f"Centroid: {centroid_str} | Area: {area_str}", styles['TDMValue']))
        content.append(Spacer(1, 0.2*cm))
        
        poly_data = [[Paragraph("Point", styles['TDMLabel']), Paragraph("Latitude", styles['TDMLabel']), Paragraph("Longitude", styles['TDMLabel'])]]
        display_points = polygon_points[:-1] if polygon_points[0] == polygon_points[-1] else polygon_points
        for i, (p_lon, p_lat) in enumerate(display_points[:30], start=1):
            poly_data.append([Paragraph(str(i), styles['TDMValue']), Paragraph(f"{p_lat:.6f}", styles['TDMValue']), Paragraph(f"{p_lon:.6f}", styles['TDMValue'])])
            
        poly_table = Table(poly_data, colWidths=[2*cm, 5*cm, 5*cm])
        poly_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('BACKGROUND', (0,0), (-1,0), TDM_GRAY)]))
        content.append(poly_table)
        
        if len(display_points) > 30:
            content.append(Spacer(1, 0.2*cm))
            content.append(Paragraph(f"Note: {len(display_points) - 30} additional points are not displayed due to space constraints.", styles['TDMLegal']))
    
    content.append(Spacer(1, 1*cm))
    content.append(Paragraph(f"Verify at: {html.escape(verify_url)}", styles['TDMLegal']))
    
    doc.build(content)
    
    try: os.remove(qr_path)
    except: pass
    
    return file_path
