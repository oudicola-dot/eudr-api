import os
import hashlib
import qrcode
import requests
from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from security import sign_audit

BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")
LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"


# ---------- UTILITY FUNCTIONS ----------
def get_logo():
    path = "/tmp/tdm_logo.png"
    if not os.path.exists(path):
        try:
            print("📥 DOWNLOADING LOGO...")
            r = requests.get(LOGO_URL, timeout=8)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            print("✅ LOGO SAVED:", path)
        except Exception as e:
            print("❌ LOGO DOWNLOAD ERROR:", str(e))
            return None
    return path


def get_source_label(source):
    labels = {
        "ee": "🌍 Earth Engine (Google)",
        "gfw": "🛰️ GFW (Global Forest Watch)",
        "fallback": "⚠️ Simulation",
        "unknown": "❓ Unknown"
    }
    return labels.get(source, f"📡 {source}")


def get_status_color(status):
    return "#00cc66" if status == "COMPLIANT" else "#ff3333"


# ---------- CUSTOM STYLES ----------
def get_custom_styles():
    styles = getSampleStyleSheet()
    
    # Modify existing 'Title' style
    styles['Title'].fontSize = 18
    styles['Title'].textColor = colors.HexColor("#000000")
    styles['Title'].alignment = TA_CENTER
    styles['Title'].fontName = 'Helvetica-Bold'
    styles['Title'].spaceAfter = 4
    
    # Create 'SubTitle' style
    styles.add(ParagraphStyle(
        name='SubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER,
        fontName='Helvetica',
        spaceAfter=8
    ))
    
    # Other styles
    styles.add(ParagraphStyle(
        name='HeaderText',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#333333"),
        fontName='Helvetica'
    ))
    styles.add(ParagraphStyle(
        name='Label',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#555555"),
        fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        name='Value',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#000000"),
        fontName='Helvetica'
    ))
    styles.add(ParagraphStyle(
        name='Legal',
        parent=styles['Normal'],
        fontSize=6,
        textColor=colors.HexColor("#666666"),
        fontName='Helvetica',
        alignment=TA_CENTER,
        leading=8
    ))
    styles.add(ParagraphStyle(
        name='CheckText',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor("#00cc66"),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        name='TitleHeader',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor("#000000"),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=14
    ))
    styles.add(ParagraphStyle(
        name='CompanyInfo',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor("#555555"),
        alignment=TA_LEFT,
        fontName='Helvetica'
    ))
    styles.add(ParagraphStyle(
        name='VerifyText',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor("#000000"),
        fontName='Helvetica',
        alignment=TA_LEFT
    ))
    return styles


# ---------- PDF GENERATION ----------
def generate_eudr_pdf(
    audit_id,
    name,
    lat,
    lon,
    risk_score,
    risk_level,
    eudr_compliant,
    tree_cover,
    loss_year,
    source="unknown"
):
    print("=" * 40)
    print("📄 PDF GENERATION START")
    print(f"📌 AUDIT: {audit_id}")
    print(f"🏷️ FARM: {name}")
    print(f"📡 SOURCE: {source}")
    print("=" * 40)

    file_path = f"/tmp/{audit_id}.pdf"
    doc = SimpleDocTemplate(
        file_path,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = get_custom_styles()
    content = []
    
    source_label = get_source_label(source)
    status_color = get_status_color(eudr_compliant)
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    current_date_short = datetime.now().strftime("%d/%m/%Y")
    
    signature = sign_audit(audit_id)
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
    sha = hashlib.sha256(f"{audit_id}{name}{lat}{lon}".encode()).hexdigest()
    
    # ---------- QR CODE ----------
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr_image = None
    try:
        qr = qrcode.make(verify_url)
        qr.save(qr_path)
        qr_image = Image(qr_path, width=60, height=60)
        print("✅ QR CODE GENERATED")
    except Exception as e:
        print("❌ QR ERROR:", str(e))
    
    # ---------- HEADER ----------
    logo = get_logo()
    logo_img = None
    if logo:
        try:
            logo_img = Image(logo, width=90, height=73)
        except Exception as e:
            print("❌ LOGO ERROR:", str(e))
    
    header_data = []
    
    # Row 1: Logo, Title, QR
    row1 = []
    if logo_img:
        row1.append(logo_img)
    else:
        row1.append(Paragraph("TIERRAS DE MONTAÑA", styles["Title"]))
    
    row1.append(Paragraph(
        '<font size="12" color="#000000"><b>EUDR TRACEABILITY REPORT</b></font>',
        styles["TitleHeader"]
    ))
    
    if qr_image:
        row1.append(qr_image)
    else:
        row1.append(Paragraph("QR", styles["HeaderText"]))
    
    header_data.append(row1)
    
    # Row 2: Company info (left), date (center), "Check with QR" (right)
    row2 = [
        Paragraph(
            'Sarah Jo SAS • NIT: 900693208-2 • contact@tierrasdemontana.com',
            styles["CompanyInfo"]
        ),
        Paragraph(
            f'{current_date_short}',
            styles["CompanyInfo"]
        ),
        Paragraph(
            f'<font size="7" color="#00cc66"><b>✓ Check with QR</b></font>',
            styles["CheckText"]
        )
    ]
    header_data.append(row2)
    
    header_table = Table(header_data, colWidths=[3*cm, 8*cm, 3*cm])
    header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    content.append(header_table)
    content.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
    content.append(Spacer(1, 0.2*cm))
    
    # ---------- STATUS + SOURCE ----------
    status_data = [
        [
            Paragraph("Status", styles["Label"]),
            Paragraph(f'<font color="{status_color}"><b>{eudr_compliant}</b></font>', styles["Value"]),
            Paragraph("Source", styles["Label"]),
            Paragraph(source_label, styles["Value"]),
            Paragraph("Date", styles["Label"]),
            Paragraph(current_date_short, styles["Value"])
        ]
    ]
    status_table = Table(status_data, colWidths=[1.8*cm, 2.8*cm, 1.8*cm, 3.5*cm, 1.5*cm, 2.2*cm])
    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    content.append(status_table)
    content.append(Spacer(1, 0.2*cm))
    
    # ---------- FARM DETAILS ----------
    details = [
        ["Farm", name],
        ["Latitude", f"{lat:.6f}"],
        ["Longitude", f"{lon:.6f}"],
        ["Tree Cover", f"{tree_cover}%"],
        ["Loss Year", str(loss_year) if loss_year > 0 else "N/A"],
        ["Risk Score", str(risk_score)],
        ["Risk Level", risk_level]
    ]
    detail_rows = []
    for label, value in details:
        detail_rows.append([
            Paragraph(f'<b>{label}</b>', styles["Label"]),
            Paragraph(str(value), styles["Value"])
        ])
    flat_details = []
    for row in detail_rows:
        flat_details.extend(row)
    table_data = []
    for i in range(0, len(flat_details), 4):
        row = flat_details[i:i+4]
        while len(row) < 4:
            row.append(Paragraph("", styles["Normal"]))
        table_data.append(row)
    
    detail_table = Table(table_data, colWidths=[2.5*cm, 3*cm, 2.5*cm, 3*cm])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    content.append(detail_table)
    content.append(Spacer(1, 0.2*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
    content.append(Spacer(1, 0.1*cm))
    
    # ---------- RISK LEGEND ----------
    legend_data = [
        [
            Paragraph('<font color="#28a745">●</font> Low (0-30)', styles["HeaderText"]),
            Paragraph('<font color="#ffc107">●</font> Medium (31-70)', styles["HeaderText"]),
            Paragraph('<font color="#dc3545">●</font> High (71-100)', styles["HeaderText"])
        ]
    ]
    legend_table = Table(legend_data, colWidths=[5*cm, 5*cm, 5*cm])
    legend_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#e8f5e9")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fff8e1")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#ffebee")),
    ]))
    content.append(legend_table)
    content.append(Spacer(1, 0.05*cm))
    content.append(Paragraph(
        '<font size="6" color="#555555"><b>Criteria:</b> Tree Cover > 30% + Loss Year > 2020 = High Risk</font>',
        styles["Legal"]
    ))
    content.append(Spacer(1, 0.1*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
    content.append(Spacer(1, 0.1*cm))
    
    # ---------- VERIFICATION (simple lines, no black box) ----------
    content.append(Paragraph(
        f'<b>Verify:</b> {verify_url}',
        styles["VerifyText"]
    ))
    content.append(Spacer(1, 0.05*cm))
    content.append(Paragraph(
        f'<b>SHA256:</b> {sha}',
        styles["VerifyText"]
    ))
    content.append(Spacer(1, 0.1*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
    content.append(Spacer(1, 0.1*cm))
    
    # ---------- LEGAL NOTICES ----------
    legal_lines = [
        "⚖️ EUDR (EU) 2023/1115 • OECD • UN • ILO • UNCCD • UNFCCC",
        "🔒 Law 1581/2012 • GDPR EU 2016/679, Art.6",
        "⚠️ Report generated from satellite data - Tierras de Montaña is not responsible for decisions made based on this report."
    ]
    for line in legal_lines:
        content.append(Paragraph(
            f'<font size="5" color="#666666">{line}</font>',
            styles["Legal"]
        ))
        content.append(Spacer(1, 0.05*cm))
    
    content.append(Spacer(1, 0.05*cm))
    content.append(Paragraph(
        f'<font size="5" color="#888888">Generated on {current_date} • Audit ID: {audit_id} • Page 1/1</font>',
        styles["Legal"]
    ))
    
    # ---------- BUILD PDF ----------
    print("📄 BUILDING PDF...")
    doc.build(content)
    print("✅ PDF BUILT")
    
    # Cleanup
    try:
        if os.path.exists(qr_path):
            os.remove(qr_path)
            print("🧹 QR CLEANED")
    except Exception as e:
        print("⚠️ QR CLEANUP ERROR:", str(e))
    
    print(f"📁 PDF RETURN: {file_path}")
    return file_path
