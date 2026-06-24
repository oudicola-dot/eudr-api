import os
import hashlib
import qrcode
import requests
from datetime import datetime
from io import BytesIO

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


# ========== FONCTIONS UTILITAIRES ==========

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


# ========== STYLES PERSONNALISÉS ==========

def get_custom_styles():
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='Title',
        parent=styles['Normal'],
        fontSize=18,
        textColor=colors.HexColor("#000000"),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=4
    ))
    
    styles.add(ParagraphStyle(
        name='SubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER,
        fontName='Helvetica',
        spaceAfter=8
    ))
    
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
        name='Status',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER
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
    
    return styles


# ========== GÉNÉRATION DU PDF (1 PAGE) ==========

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
    current_date = datetime.now().strftime("%d/%m/%Y à %H:%M")
    current_date_short = datetime.now().strftime("%d/%m/%Y")
    
    signature = sign_audit(audit_id)
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
    sha = hashlib.sha256(f"{audit_id}{name}{lat}{lon}".encode()).hexdigest()
    
    # ==========================================
    # QR CODE en mémoire pour l'en-tête
    # ==========================================
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr_image = None
    try:
        qr = qrcode.make(verify_url)
        qr.save(qr_path)
        qr_image = Image(qr_path, width=60, height=60)
        print("✅ QR CODE GENERATED")
    except Exception as e:
        print("❌ QR ERROR:", str(e))
    
    # ==========================================
    # EN-TÊTE : Logo à gauche + QR à droite
    # ==========================================
    
    # Logo
    logo = get_logo()
    logo_img = None
    if logo:
        try:
            logo_img = Image(logo, width=90, height=73)
        except Exception as e:
            print("❌ LOGO ERROR:", str(e))
    
    # Construction de l'en-tête en tableau
    header_data = []
    
    # Ligne 1 : Logo + QR
    header_row = []
    if logo_img:
        header_row.append(logo_img)
    else:
        header_row.append(Paragraph("TIERRAS DE MONTAÑA", styles["Title"]))
    
    # Centre : titre
    center_cell = Paragraph(
        f'<font size="14" color="#000000"><b>EUDR TRACEABILITY REPORT</b></font>',
        styles["HeaderText"]
    )
    header_row.append(center_cell)
    
    # Droite : QR
    if qr_image:
        qr_cell = qr_image
    else:
        qr_cell = Paragraph("QR", styles["HeaderText"])
    header_row.append(qr_cell)
    
    header_data.append(header_row)
    
    # Ligne 2 : sous-titre + infos entreprise
    header_data.append([
        Paragraph("", styles["HeaderText"]),
        Paragraph(
            '<font size="8" color="#555555">Sarah Jo SAS • NIT: 900693208-2 • contact@tierrasdemontana.com</font>',
            styles["HeaderText"]
        ),
        Paragraph(
            f'<font size="7" color="#00cc66"><b>✓ Check with QR</b></font>',
            styles["CheckText"]
        )
    ])
    
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
    
    # ==========================================
    # STATUT + SOURCE
    # ==========================================
    status_data = [
        ["Status", f'<font color="{status_color}"><b>{eudr_compliant}</b></font>'],
        ["Source", source_label],
        ["Date", current_date_short]
    ]
    
    status_table = Table(status_data, colWidths=[2.5*cm, 4*cm, 2.5*cm])
    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    content.append(status_table)
    content.append(Spacer(1, 0.2*cm))
    
    # ==========================================
    # DÉTAILS DE LA PARCELLE
    # ==========================================
    details = [
        ["Farm", name],
        ["Latitude", f"{lat:.6f}"],
        ["Longitude", f"{lon:.6f}"],
        ["Tree Cover", f"{tree_cover}%"],
        ["Loss Year", str(loss_year) if loss_year > 0 else "N/A"],
        ["Risk Score", str(risk_score)],
        ["Risk Level", risk_level]
    ]
    
    detail_table = Table(details, colWidths=[2.5*cm, 3*cm, 2.5*cm, 3*cm])
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
    
    # ==========================================
    # LÉGENDE DES RISQUES
    # ==========================================
    legend_data = [
        ["🟢 Faible (0-30)", "🟡 Moyen (31-70)", "🔴 Élevé (71-100)"]
    ]
    legend_table = Table(legend_data, colWidths=[5*cm, 5*cm, 5*cm])
    legend_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    content.append(legend_table)
    
    content.append(Spacer(1, 0.2*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
    content.append(Spacer(1, 0.1*cm))
    
    # ==========================================
    # VERIFICATION : URL + SHA256
    # ==========================================
    content.append(Paragraph(
        f'<font size="7"><b>🔗 Verify:</b> {verify_url}</font>',
        styles["HeaderText"]
    ))
    content.append(Spacer(1, 0.05*cm))
    content.append(Paragraph(
        f'<font size="7"><b>🔐 SHA256:</b> {sha}</font>',
        styles["HeaderText"]
    ))
    
    content.append(Spacer(1, 0.1*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
    content.append(Spacer(1, 0.1*cm))
    
    # ==========================================
    # MENTIONS LÉGALES (compactes)
    # ==========================================
    legal_text = (
        "⚖️ EUDR (UE) 2023/1115 • OCDE • ONU • OIT • UNCCD • CCNUCC • "
        "🔒 Loi 1581/2012 • RGPD UE 2016/679, Art.6 • "
        "⚠️ Rapport généré à partir de données satellitaires - "
        "Tierras de Montaña n'est pas responsable des décisions prises sur la base de ce rapport"
    )
    content.append(Paragraph(
        f'<font size="5" color="#666666">{legal_text}</font>',
        styles["Legal"]
    ))
    
    content.append(Spacer(1, 0.05*cm))
    content.append(Paragraph(
        f'<font size="5" color="#888888">Généré le {current_date} • Audit ID: {audit_id} • Page 1/1</font>',
        styles["Legal"]
    ))
    
    # ==========================================
    # GÉNÉRATION
    # ==========================================
    
    print("📄 BUILDING PDF...")
    doc.build(content)
    print("✅ PDF BUILT")
    
    # Nettoyage
    try:
        if os.path.exists(qr_path):
            os.remove(qr_path)
            print("🧹 QR CLEANED")
    except Exception as e:
        print("⚠️ QR CLEANUP ERROR:", str(e))
    
    print(f"📁 PDF RETURN: {file_path}")
    return file_path
