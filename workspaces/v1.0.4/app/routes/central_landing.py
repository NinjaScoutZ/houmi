def get_central_landing_html() -> str:
    return """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Houmi Central Service — Official API & Licensing Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Kanit', sans-serif;
            background: #0b0f19;
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }
        .container {
            max-width: 680px;
            width: 100%;
            background: #131b2e;
            border: 1px solid #1e293b;
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6);
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        .glow {
            position: absolute;
            top: -100px;
            left: 50%;
            transform: translateX(-50%);
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(245,158,11,0.15) 0%, rgba(0,0,0,0) 70%);
            pointer-events: none;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            font-size: 13px;
            font-weight: 600;
            padding: 6px 16px;
            border-radius: 9999px;
            margin-bottom: 20px;
        }
        .dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 10px #10b981;
        }
        h1 {
            font-size: 32px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.5px;
            margin-bottom: 12px;
        }
        h1 span {
            color: #f59e0b;
        }
        p.subtitle {
            color: #94a3b8;
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 32px;
        }
        .cards {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 32px;
        }
        .card {
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 16px;
            padding: 20px;
            text-align: left;
        }
        .card-icon {
            font-size: 24px;
            margin-bottom: 10px;
        }
        .card-title {
            font-size: 14px;
            font-weight: 600;
            color: #f1f5f9;
            margin-bottom: 4px;
        }
        .card-desc {
            font-size: 12px;
            color: #64748b;
        }
        .actions {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
            padding: 16px;
            border-radius: 14px;
            font-size: 15px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        .btn-primary {
            background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
            color: #0b0f19;
            box-shadow: 0 10px 20px -5px rgba(245,158,11,0.3);
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 14px 24px -5px rgba(245,158,11,0.4);
        }
        .btn-secondary {
            background: #1e293b;
            color: #cbd5e1;
            border: 1px solid #334155;
        }
        .btn-secondary:hover {
            background: #334155;
            color: #ffffff;
        }
        footer {
            margin-top: 28px;
            font-size: 12px;
            color: #475569;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="glow"></div>
        <div class="badge">
            <span class="dot"></span> Central Licensing API Service Operational
        </div>
        <h1>HOUMI <span>CENTRAL</span></h1>
        <p class="subtitle">
            เซิร์ฟเวอร์ควบคุมระบบสิทธิ์การใช้งาน (Licensing Control & Auth Service)<br>
            การประมวลผลงานแปลมังงะและ OCR ทำงานบนเครื่องของผู้ใช้แยกอิสระ (Local Processing Engine)
        </p>

        <div class="cards">
            <div class="card">
                <div class="card-icon">🔐</div>
                <div class="card-title">Hardware Lock & Auth</div>
                <div class="card-desc">ควบคุมสิทธิ์ผ่าน Redeem Code ล็อคเครื่อง และระบบสมาชิก</div>
            </div>
            <div class="card">
                <div class="card-icon">⚡</div>
                <div class="card-title">High Security API</div>
                <div class="card-desc">บริการเฉพาะ API Endpoints สำหรับแอปพลิเคชันเดสก์ท็อป</div>
            </div>
        </div>

        <div class="actions">
            <a href="/api/system/download-update" class="btn btn-primary">
                <span>🚀 ดาวน์โหลดโปรแกรม Houmi Studio (.exe / setup)</span>
            </a>
            <a href="/api/admin" class="btn btn-secondary">
                <span>🔑 เข้าสู่ระบบ Admin Dashboard (/api/admin)</span>
            </a>
        </div>

        <footer>
            Houmi Central Service v1.0.0 &bull; Cloudflare Protected Node &bull; PostgreSQL Protected Engine
        </footer>
    </div>
</body>
</html>
"""
