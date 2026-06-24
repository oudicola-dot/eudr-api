<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>EUDR Risk Intelligence</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background: #f5f5f5;
            font-family: 'Georgia', 'Times New Roman', serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        /* ========== CONTAINER ========== */
        .eudr-container {
            max-width: 1000px;
            width: 100%;
            background: #ffffff;
            border-radius: 8px;
            padding: 40px 50px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            border: 1px solid #e0e0e0;
        }

        /* ========== HEADER ========== */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 2px solid #000;
            padding-bottom: 20px;
            margin-bottom: 25px;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .logo {
            max-height: 70px;
            width: auto;
        }

        .header-title h1 {
            font-size: 22px;
            font-weight: 700;
            color: #000;
            letter-spacing: 1px;
        }

        .header-title p {
            font-size: 13px;
            color: #555;
            margin-top: 2px;
        }

        .header-right {
            text-align: right;
            font-size: 13px;
            color: #333;
            line-height: 1.6;
        }

        .header-right .nit {
            font-weight: 700;
            font-size: 12px;
            color: #000;
        }

        /* ========== FORM ========== */
        .form-row {
            display: flex;
            gap: 15px;
            margin-bottom: 12px;
        }

        .form-group {
            flex: 1;
        }

        .form-group label {
            display: block;
            font-size: 12px;
            font-weight: 700;
            color: #000;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .form-group input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 14px;
            color: #000;
            background: #fafafa;
            transition: 0.2s;
        }

        .form-group input:focus {
            border-color: #000;
            outline: none;
            background: #fff;
        }

        /* ========== BUTTONS ========== */
        .btn-row {
            display: flex;
            gap: 12px;
            margin: 15px 0 10px 0;
        }

        .btn {
            padding: 12px 28px;
            border: none;
            border-radius: 4px;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            transition: 0.2s;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        .btn-primary {
            background: #000;
            color: #fff;
        }

        .btn-primary:hover {
            background: #333;
        }

        .btn-secondary {
            background: #e0e0e0;
            color: #000;
        }

        .btn-secondary:hover {
            background: #ccc;
        }

        .btn-polygon {
            background: transparent;
            color: #000;
            border: 1px solid #000;
            padding: 8px 16px;
            font-size: 12px;
            margin-bottom: 10px;
        }

        .btn-polygon:hover {
            background: #000;
            color: #fff;
        }

        /* ========== POLYGONE ========== */
        #polygon-section {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin: 10px 0;
            background: #fafafa;
        }

        #polygon-section h4 {
            color: #000;
            font-size: 14px;
            margin-bottom: 5px;
        }

        #polygon-section p {
            color: #666;
            font-size: 12px;
            margin-bottom: 10px;
        }

        .point-row {
            display: flex;
            gap: 8px;
            margin-bottom: 6px;
            align-items: center;
        }

        .point-row input {
            flex: 1;
            padding: 8px 10px;
            border: 1px solid #ccc;
            border-radius: 3px;
            font-size: 13px;
            background: #fff;
        }

        .point-row .btn-remove {
            width: 30px;
            padding: 8px;
            background: #dc3545;
            color: #fff;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 14px;
        }

        .point-row .btn-remove:hover {
            background: #c82333;
        }

        .btn-small {
            padding: 6px 14px;
            font-size: 12px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
        }

        .btn-add {
            background: #28a745;
            color: #fff;
        }

        .btn-add:hover {
            background: #218838;
        }

        .btn-clear {
            background: #dc3545;
            color: #fff;
        }

        .btn-clear:hover {
            background: #c82333;
        }

        /* ========== OUTPUT ========== */
        #out {
            margin-top: 15px;
            background: #fafafa;
            padding: 15px;
            border-radius: 4px;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-word;
            border: 1px solid #e0e0e0;
            color: #000;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
        }

        /* ========== RESPONSIVE ========== */
        @media (max-width: 768px) {
            .eudr-container {
                padding: 20px;
            }

            .header {
                flex-direction: column;
                text-align: center;
                gap: 10px;
            }

            .header-left {
                flex-direction: column;
            }

            .header-right {
                text-align: center;
            }

            .form-row {
                flex-direction: column;
            }

            .btn-row {
                flex-direction: column;
            }

            .btn {
                width: 100%;
            }
        }

        @media print {
            body {
                background: #fff;
                padding: 0;
            }
            .eudr-container {
                box-shadow: none;
                border: none;
                padding: 20px;
            }
            .btn-row,
            .btn-polygon {
                display: none !important;
            }
            #polygon-section .btn-small {
                display: none !important;
            }
        }
    </style>
</head>
<body>

    <div class="eudr-container">

        <!-- ========== HEADER ========== -->
        <div class="header">
            <div class="header-left">
                <img class="logo" src="https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png" alt="Logo" />
                <div class="header-title">
                    <h1>TIERRAS DE MONTAÑA</h1>
                    <p>EUDR Traceability Report</p>
                </div>
            </div>
            <div class="header-right">
                <div><strong>Sarah Jo SAS</strong></div>
                <div class="nit">NIT: 900693208-2</div>
                <div style="font-size:11px; color:#666;">contact@tierrasdemontana.com</div>
            </div>
        </div>

        <!-- ========== FORM ========== -->
        <div class="form-row">
            <div class="form-group">
                <label>Nom de la parcelle *</label>
                <input id="name" placeholder="Ex: Finca El Paraíso" value="test_finca" />
            </div>
        </div>

        <div class="form-row">
            <div class="form-group">
                <label>Latitude *</label>
                <input id="lat" placeholder="Ex: 4.500000" value="4.5" />
            </div>
            <div class="form-group">
                <label>Longitude *</label>
                <input id="lon" placeholder="Ex: -74.200000" value="-74.2" />
            </div>
        </div>

        <!-- ========== POLYGONE ========== -->
        <button class="btn-polygon" onclick="togglePolygon()">📐 Ajouter un polygone (optionnel)</button>

        <div id="polygon-section" style="display:none;">
            <h4>📐 Polygone (optionnel)</h4>
            <p>Ajoutez 3 points minimum pour délimiter la parcelle</p>
            <div id="polygon-points">
                <div class="point-row">
                    <input class="poly-lat" placeholder="Latitude" />
                    <input class="poly-lon" placeholder="Longitude" />
                    <button class="btn-remove" onclick="removePoint(this)">✕</button>
                </div>
            </div>
            <div style="display:flex; gap:8px; margin-top:8px;">
                <button class="btn-small btn-add" onclick="addPoint()">➕ Ajouter un point</button>
                <button class="btn-small btn-clear" onclick="clearPolygon()">🗑️ Supprimer</button>
            </div>
        </div>

        <!-- ========== BUTTONS ========== -->
        <div class="btn-row">
            <button class="btn btn-primary" onclick="runEUDR()">🌿 Run EUDR Analysis</button>
            <button class="btn btn-secondary" onclick="openPDF()">📄 Open PDF Certificate</button>
        </div>

        <!-- ========== OUTPUT ========== -->
        <pre id="out">Ready</pre>

    </div>

    <script>
        const API = "https://eudr-api-mi0x.onrender.com";
        let lastAudit = null;
        let polygonActive = false;

        function togglePolygon() {
            polygonActive = !polygonActive;
            document.getElementById("polygon-section").style.display = polygonActive ? "block" : "none";
        }

        function addPoint() {
            const container = document.getElementById("polygon-points");
            const row = document.createElement("div");
            row.className = "point-row";
            row.innerHTML = `
                <input class="poly-lat" placeholder="Latitude" />
                <input class="poly-lon" placeholder="Longitude" />
                <button class="btn-remove" onclick="removePoint(this)">✕</button>
            `;
            container.appendChild(row);
        }

        function removePoint(btn) {
            const row = btn.parentElement;
            if (document.querySelectorAll(".point-row").length > 1) {
                row.remove();
            } else {
                alert("❌ Il faut au moins un point");
            }
        }

        function clearPolygon() {
            const container = document.getElementById("polygon-points");
            container.innerHTML = `
                <div class="point-row">
                    <input class="poly-lat" placeholder="Latitude" />
                    <input class="poly-lon" placeholder="Longitude" />
                    <button class="btn-remove" onclick="removePoint(this)">✕</button>
                </div>
            `;
        }

        function getPolygonPoints() {
            const lats = document.querySelectorAll(".poly-lat");
            const lons = document.querySelectorAll(".poly-lon");
            const points = [];
            for (let i = 0; i < lats.length; i++) {
                const lat = parseFloat(lats[i].value);
                const lon = parseFloat(lons[i].value);
                if (!isNaN(lat) && !isNaN(lon)) {
                    points.push([lat, lon]);
                }
            }
            return points;
        }

        async function runEUDR() {
            const out = document.getElementById("out");
            out.innerText = "⏳ Analyzing...";

            try {
                const payload = {
                    api_key: "EUDR-SECRET-123",
                    name: document.getElementById("name").value,
                    lat: Number(document.getElementById("lat").value),
                    lon: Number(document.getElementById("lon").value)
                };

                const points = getPolygonPoints();
                if (points.length >= 3) {
                    payload.polygon = points;
                    console.log("📐 Polygone détecté:", points.length, "points");
                } else if (points.length > 0 && points.length < 3) {
                    out.innerText = "⚠️ Le polygone doit avoir au moins 3 points";
                    return;
                }

                const res = await fetch(API + "/eudr-check", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                const json = await res.json();

                if (!res.ok) {
                    throw new Error(json.detail || "Erreur API");
                }

                lastAudit = json;
                out.innerText = JSON.stringify(json, null, 2);
                console.log("✅ Audit créé :", json.audit_id);

            } catch (err) {
                out.innerText = "❌ ERROR:\n" + err.message;
            }
        }

        function openPDF() {
            const out = document.getElementById("out");
            if (!lastAudit || !lastAudit.pdf_url) {
                out.innerText = "⚠️ Run analysis first";
                return;
            }
            window.open(lastAudit.pdf_url, "_blank");
            out.innerText = "📄 Opening PDF...";
        }
    </script>

</body>
</html>
