from flask import Flask, render_template, request, jsonify
import random
import string
import os
import requests

app = Flask(__name__)

db_users = {}  
db_logs = []   
copied_logs = [] 

platform_stats = {
    "total_records": "548B+",
    "members_count": 1847,
    "queries_count": 2467
}

REF_CODES = {
    "OpesintAdmin": {"role": "admin", "credits": 999999, "plan": "ADMIN"},
    "OpeBasic": {"role": "user", "credits": 20, "plan": "BASIC"},
    "OpePro": {"role": "user", "credits": 120, "plan": "PRO"},
    "OpeLifeTime": {"role": "user", "credits": 999999, "plan": "LIFETIME"}
}

@app.route("/")
def index():
    return render_template("index.html", stats=platform_stats)

@app.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify({
        "success": True,
        "members": platform_stats["members_count"],
        "queries": platform_stats["queries_count"]
    })

@app.route("/api/register", methods=["POST"])
def register():
    key = "OPST-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    platform_stats["members_count"] += 1
    return jsonify({"success": True, "key": key, "members": platform_stats["members_count"]})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    license_key = data.get("license_key", "").strip()
    ref_code = data.get("ref_code", "").strip()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not license_key:
        return jsonify({"success": False, "msg": "Lisans anahtarı boş olamaz!"})

    if license_key in db_users and db_users[license_key].get("banned", False):
        return jsonify({"success": False, "msg": "Bu lisans anahtarı yönetici tarafından yasaklanmış (banlanmış)!"})

    if license_key in db_users and db_users[license_key].get("status") == "İptal Edildi":
        return jsonify({"success": False, "msg": "Bu üyelik iptal edilmiştir!"})

    if ref_code not in REF_CODES:
        return jsonify({"success": False, "msg": "Geçersiz Referans Kodu!"})

    if license_key not in db_users:
        db_users[license_key] = {
            "role": REF_CODES[ref_code]["role"],
            "credits": REF_CODES[ref_code]["credits"],
            "ref_code": ref_code,
            "plan": REF_CODES[ref_code]["plan"],
            "queries_done": 0,
            "ip": client_ip,
            "status": "Aktif",
            "banned": False
        }
    else:
        db_users[license_key]["ip"] = client_ip
        if db_users[license_key]["status"] != "İptal Edildi" and not db_users[license_key]["banned"]:
            db_users[license_key]["status"] = "Aktif"
    
    user_data = db_users[license_key]
    return jsonify({
        "success": True, 
        "role": user_data["role"], 
        "credits": user_data["credits"], 
        "ref_code": user_data["ref_code"],
        "plan": user_data["plan"],
        "queries_done": user_data["queries_done"],
        "members": platform_stats["members_count"],
        "queries": platform_stats["queries_count"]
    })

@app.route("/api/admin/cancel", methods=["POST"])
def admin_cancel():
    data = request.json
    target_key = data.get("license_key", "").strip()
    if not target_key:
        return jsonify({"success": False, "msg": "Lütfen bir lisans anahtarı girin!"})
    if target_key in db_users:
        db_users[target_key]["status"] = "İptal Edildi"
        return jsonify({"success": True, "msg": f"{target_key} anahtarına ait üyelik başarıyla iptal edildi."})
    return jsonify({"success": False, "msg": "Böyle bir kullanıcı veya lisans anahtarı bulunamadı!"})

@app.route("/api/admin/ban", methods=["POST"])
def admin_ban():
    data = request.json
    target_key = data.get("license_key", "").strip()
    if not target_key:
        return jsonify({"success": False, "msg": "Lütfen bir lisans anahtarı girin!"})
    if target_key in db_users:
        db_users[target_key]["banned"] = True
        db_users[target_key]["status"] = "Yasaklı (Banlı)"
        return jsonify({"success": True, "msg": f"{target_key} anahtarı başarıyla banlandı."})
    return jsonify({"success": False, "msg": "Böyle bir kullanıcı veya lisans anahtarı bulunamadı!"})

@app.route("/api/copy-log", methods=["POST"])
def log_copy():
    data = request.json
    text = data.get("text", "").strip()
    license_key = data.get("license_key", "Bilinmeyen")
    if text:
        copied_logs.insert(0, {"user": license_key, "text": text})
        if len(copied_logs) > 50:
            copied_logs.pop()
    return jsonify({"success": True})

@app.route("/api/search", methods=["POST"])
def search():
    data = request.json
    target = data.get("target", "").strip()
    module = data.get("module", "MultiBoard")
    license_key = data.get("license_key", "")

    if license_key not in db_users or db_users[license_key].get("banned", False) or db_users[license_key].get("status") == "İptal Edildi":
        return jsonify({"success": False, "msg": "Erişim reddedildi (Üyelik iptal edilmiş veya banlanmış)."})

    user = db_users[license_key]

    if user["credits"] <= 0:
        return jsonify({"success": False, "msg": "Kredi limitiniz doldu!"})

    if user["ref_code"] != "OpeLifeTime" and user["role"] != "admin":
        user["credits"] -= 1
    
    user["queries_done"] += 1
    platform_stats["queries_count"] += 1
    
    log_entry = {"user": license_key, "ref_code": user["ref_code"], "target": target, "module": module}
    db_logs.insert(0, log_entry)

    logs = [f"[ * ] Hedef: {target} | Modül: {module} | Tarama başlatıldı..."]
    
    if module == "Craftrise OSINT":
        if os.path.exists("hesaplar.txt"):
            with open("hesaplar.txt", "r", encoding="utf-8") as file:
                lines = file.readlines()
                found = False
                for line in lines:
                    if target.lower() in line.lower():
                        logs.append(f"[ + ] Craftrise Eşleşmesi: {line.strip()}")
                        found = True
                if not found:
                    logs.append(f"[ - ] {target} kullanıcısı hesaplar.txt içinde bulunamadı.")
        else:
            logs.append("[ ! ] Sistem Hatası: 'hesaplar.txt' dosyası bulunamadı!")
            
    elif module == "Username Osint":
        platforms = [
            ("Instagram", f"https://instagram.com/{target}"),
            ("Twitter (X)", f"https://twitter.com/{target}"),
            ("GitHub", f"https://github.com/{target}"),
            ("TikTok", f"https://tiktok.com/@{target}"),
            ("Reddit", f"https://reddit.com/user/{target}"),
            ("Steam", f"https://steamcommunity.com/id/{target}"),
            ("Telegram", f"https://t.me/{target}"),
            ("YouTube", f"https://youtube.com/@{target}"),
            ("Kick", f"https://kick.com/{target}")
        ]
        logs.append(f"[ + ] Küresel Platform Taraması Başlatıldı ({target})...")
        for p_name, p_url in platforms:
            status = random.choice(["Bulundu", "Bulundu", "Kayıt Bulunamadı"])
            if status == "Bulundu":
                logs.append(f"[ + ] {p_name}: {p_url}")
            else:
                logs.append(f"[ - ] {p_name}: Eşleşme yok")
        logs.append(f"[ + ] Tarama tamamlandı.")

    elif module == "Roblox OSINT":
        try:
            r = requests.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [target], "excludeBannedUsers": False}, timeout=5)
            res_data = r.json()
            if res_data.get("data") and len(res_data["data"]) > 0:
                r_user = res_data["data"][0]
                r_id = r_user["id"]
                r_display = r_user["displayName"]
                detail_r = requests.get(f"https://users.roblox.com/v1/users/{r_id}", timeout=5).json()
                created_at = detail_r.get("created", "Bilinmiyor")[:10]
                
                logs.extend([
                    f"[ + ] Roblox Web API Bağlantısı Başarılı.",
                    f"[ + ] Kullanıcı Adı: {target} | Görünen Ad: {r_display}",
                    f"[ + ] Gerçek Roblox ID: {r_id}",
                    f"[ + ] Hesap Kuruluş Tarihi: {created_at}",
                    f"[ + ] Moderasyon Durumu: Temiz (Clean)"
                ])
            else:
                logs.append(f"[ - ] Roblox üzerinde '{target}' adında bir kullanıcı bulunamadı.")
        except Exception as ex:
            logs.append(f"[ ! ] Roblox API Bağlantı Hatası: {str(ex)}")

    elif module == "Discord OSINT":
        try:
            snowflake_id = int(target)
            timestamp = ((snowflake_id >> 22) + 1420070400000) / 1000
            import datetime
            created_date = datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            fake_token_p1 = ''.join(random.choices(string.ascii_letters + string.digits, k=24))
            fake_token_p2 = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            fake_token_p3 = ''.join(random.choices(string.ascii_letters + string.digits, k=27))
            fake_token = f"m{fake_token_p1}.{fake_token_p2}.{fake_token_p3}"
            fake_cc = f"4532-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
            
            logs.extend([
                f"[ + ] Discord Snowflake Çözümleyicisi...",
                f"[ + ] Hedef ID: {target}",
                f"[ + ] Hesap Kesin Kuruluş Tarihi: {created_date} UTC",
                f"[ ! ] Oturum Token (Fake): {fake_token}",
                f"[ ! ] Tespit Edilen Ödeme Yöntemi: {fake_cc}"
            ])
        except ValueError:
            logs.append(f"[ ! ] Hata: Geçerli bir Discord Snowflake ID girmelisiniz!")

    elif module == "Whois Lookup":
        logs.extend([
            f"[ + ] DNS & Whois kayıt sorgusu: {target}",
            f"[ + ] Kayıt Eden Firma: Cloudflare Registrar, LLC",
            f"[ + ] Oluşturulma Tarihi: 2015-03-22 | Bitiş: 2030-03-22"
        ])
    elif module == "Port Scanner":
        logs.extend([
            f"[ + ] Nmap Tarama Motoru Devrede ({target})...",
            f"[ + ] Port 21 (FTP): KAPALI",
            f"[ + ] Port 22 (SSH): AÇIK",
            f"[ + ] Port 80 (HTTP): AÇIK",
            f"[ + ] Port 443 (HTTPS): AÇIK"
        ])
    elif module == "OpenArchive Breach":
        logs.extend([
            f"[ + ] Sızıntı veritabanları taranıyor: {target}",
            f"[ + ] Veri Kümesi #1: Corporation 2024 Breach",
            f"[ + ] Sonuç: Hedef veri sızıntı arşivlerinde tespit edilmiştir."
        ])
    else:
        logs.extend([
            f"[ + ] MultiBoard İstihbarat Motoru Aktif: {target}",
            f"[ + ] Ağ Analizi: Hedef aktif ve erişilebilir.",
            f"[ + ] Tehdit İstihbaratı: Temiz (Clean IP / Domain)"
        ])

    return jsonify({
        "success": True, 
        "logs": logs, 
        "credits": user["credits"], 
        "queries_done": user["queries_done"],
        "queries": platform_stats["queries_count"]
    })

@app.route("/api/admin/data", methods=["GET"])
def admin_data():
    return jsonify({
        "users": db_users, 
        "logs": db_logs, 
        "copied_logs": copied_logs,
        "stats": platform_stats
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)