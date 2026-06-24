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
    PageBreak,
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
    return "#00ff99" if status == "COMPLIANT" else "#ff4444"


# ========== STYLES PERSONNALISÉS ==========

def get_custom_styles():
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Title'],
        fontSize=22,
        textColor=colors.HexColor("#00ff99"),
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='CustomHeading2',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor("#a0aec0"),
        alignment=TA_CENTER,
        spaceAfter=10,
        fontName='Helvetica'
    ))
    
    styles.add(ParagraphStyle(
        name='CustomNormal',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor("#e2e8f0"),
        fontName='Helvetica',
        leading=13
    ))
    
    styles.add(ParagraphStyle(
        name='Footer',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor("#64748b"),
        alignment=TA_CENTER,
        fontName='Helvetica'
    ))
    
    styles.add(ParagraphStyle(
        name='Legal',
        parent=styles['Normal'],
        fontSize=6.5,
        textColor=colors.HexColor("#94a3b8"),
        fontName='Helvetica',
        leading=9,
        alignment=TA_LEFT
    ))
    
    styles.add(ParagraphStyle(
        name='Badge',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#00ff99"),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    ))
    
    return styles


# ========== GÉNÉRATION DU PDF ==========

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
        leftMargin=1.8*cm,
        rightMargin=1.8*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = get_custom_styles()
    content = []
    
    source_label = get_source_label(source)
    status_color = get_status_color(eudr_compliant)
    current_date = datetime.now().strftime("%d/%m/%Y à %H:%M")
    current_date_short = datetime.now().strftime("%d/%m/%Y")
    
    # ==========================================
    # PAGE 1 - PAGE DE GARDE + DÉTAILS
    # ==========================================
    
    # En-tête avec date
    content.append(Paragraph(
        f'<font color="#64748b" size="7">Généré le {current_date}</font>',
        styles["Footer"]
    ))
    content.append(Spacer(1, 0.5*cm))
    
    # Logo
    logo = get_logo()
    if logo:
        try:
            content.append(Image(logo, width=130, height=105))
            content.append(Spacer(1, 0.3*cm))
        except Exception as e:
            print("❌ LOGO ERROR:", str(e))
    
    # Titre
    content.append(Paragraph("TIERRAS DE MONTAÑA", styles["CustomTitle"]))
    content.append(Paragraph("EUDR TRACEABILITY REPORT", styles["CustomHeading2"]))
    content.append(Paragraph(
        '<font color="#64748b" size="9">Règlement Européen (UE) 2023/1115</font>',
        styles["Footer"]
    ))
    
    content.append(Spacer(1, 0.5*cm))
    content.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2d3748")))
    content.append(Spacer(1, 0.3*cm))
    
    # ===== STATUT ET SOURCE =====
    status_data = [
        ["📋 Audit ID", audit_id],
        ["✅ EUDR Status", f'<font color="{status_color}">{eudr_compliant}</font>'],
        ["📡 Data Source", source_label]
    ]
    
    status_table = Table(status_data, colWidths=[3.5*cm, 8.5*cm])
    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#0f172a")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#1a2332")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    content.append(status_table)
    
    content.append(Spacer(1, 0.3*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#2d3748")))
    content.append(Spacer(1, 0.3*cm))
    
    # ===== DÉTAILS DE LA PARCELLE =====
    details = [
        ["🏷️ Farm", name],
        ["🌍 Latitude", f"{lat:.6f}"],
        ["🌍 Longitude", f"{lon:.6f}"],
        ["🌳 Tree Cover", f"{tree_cover}%"],
        ["📅 Loss Year", str(loss_year) if loss_year > 0 else "N/A"],
        ["📊 Risk Score", str(risk_score)],
        ["⚡ Risk Level", risk_level]
    ]
    
    detail_table = Table(details, colWidths=[3.5*cm, 8.5*cm])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#0f172a")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#1a2332")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    content.append(detail_table)
    
    content.append(Spacer(1, 0.3*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#2d3748")))
    
    # ===== FOOTER PAGE 1 =====
    content.append(Spacer(1, 0.2*cm))
    content.append(Paragraph(
        "🏢 Tierras de Montaña - Sarah Jo SAS • NIT: 900693208-2",
        styles["Footer"]
    ))
    content.append(Paragraph(
        f'Page 1/2 • {current_date_short}',
        styles["Footer"]
    ))
    
    content.append(PageBreak())
    
    # ==========================================
    # PAGE 2 - VÉRIFICATION + MENTIONS LÉGALES
    # ==========================================
    
    signature = sign_audit(audit_id)
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}?signature={signature}"
    sha = hashlib.sha256(f"{audit_id}{name}{lat}{lon}".encode()).hexdigest()
    
    # En-tête
    content.append(Paragraph(
        f'<font color="#64748b" size="7">{current_date}</font>',
        styles["Footer"]
    ))
    content.append(Spacer(1, 0.3*cm))
    
    # ===== QR CODE + VÉRIFICATION =====
    qr_path = f"/tmp/{audit_id}_qr.png"
    try:
        qr = qrcode.make(verify_url)
        qr.save(qr_path)
        
        # Tableau QR + infos
        qr_data = [
            ["🔐 VÉRIFICATION", ""],
            ["", ""],
            ["QR Code", f'<font color="#94a3b8" size="8">Scannez pour vérifier</font>']
        ]
        
        qr_table = Table(qr_data, colWidths=[5*cm, 7*cm])
        qr_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2332")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        
        # Insérer l'image dans la cellule
        qr_img = Image(qr_path, width=120, height=120)
        qr_table._cells[(1, 2)] = qr_img
        
        content.append(qr_table)
        content.append(Spacer(1, 0.2*cm))
        
    except Exception as e:
        print("❌ QR ERROR:", str(e))
    
    # ===== URL ET SHA256 =====
    content.append(Paragraph(
        f"<b>🔗 URL:</b> {verify_url}",
        styles["CustomNormal"]
    ))
    content.append(Spacer(1, 0.1*cm))
    content.append(Paragraph(
        f"<b>🔐 SHA256:</b> {sha[:32]}...",
        styles["CustomNormal"]
    ))
    
    content.append(Spacer(1, 0.2*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#2d3748")))
    
    # ===== MENTIONS LÉGALES COMPACTES =====
    legal_text = [
        "⚖️ CADRE LÉGAL",
        "• EUDR (UE) 2023/1115 • OCDE • ONU • OIT • UNCCD • CCNUCC",
        "",
        "🔒 PROTECTION DES DONNÉES (Loi 1581/2012 - RGPD UE 2016/679, Art.6)",
        "",
        "⚠️ CLAUSE DE NON-RESPONSABILITÉ",
        "Ce rapport est généré à partir de données satellitaires. La précision",
        "dépend des données sources. Tierras de Montaña n'est pas responsable",
        "des décisions prises sur la base de ce rapport.",
        "",
        "📧 contact@tierrasdemontana.com"
    ]
    
    for line in legal_text:
        if line == "":
            content.append(Spacer(1, 0.1*cm))
        elif line.startswith("⚖️") or line.startswith("🔒") or line.startswith("⚠️"):
            content.append(Paragraph(f'<font color="#00ff99"><b>{line}</b></font>', styles["CustomNormal"]))
        elif line.startswith("•"):
            content.append(Paragraph(f'<font color="#94a3b8">{line}</font>', styles["Legal"]))
        elif line.startswith("📧"):
            content.append(Paragraph(f'<font color="#00ff99">{line}</font>', styles["CustomNormal"]))
        else:
            content.append(Paragraph(f'<font color="#94a3b8">{line}</font>', styles["Legal"]))
    
    # ===== FOOTER PAGE 2 =====
    content.append(Spacer(1, 0.2*cm))
    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#2d3748")))
    content.append(Paragraph(
        f'Page 2/2 • {current_date_short}',
        styles["Footer"]
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
