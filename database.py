import uuid
import json
import os

SESSIONS_FILE = "sessions.json"

def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r") as f:
            data = json.load(f)
            return data.get("sessions", {}), data.get("chat_to_session", {})
    return {}, {}

def save_sessions(sessions, chat_to_session):
    with open(SESSIONS_FILE, "w") as f:
        json.dump({"sessions": sessions, "chat_to_session": chat_to_session}, f)

# Load existing sessions on startup
sessions, chat_to_session = load_sessions()

def get_or_create_session(chat_id):
    global sessions, chat_to_session
    if str(chat_id) in chat_to_session:
        return chat_to_session[str(chat_id)]
    session_id = str(uuid.uuid4())
    sessions[session_id] = chat_id
    chat_to_session[str(chat_id)] = session_id
    save_sessions(sessions, chat_to_session)
    return session_id

def get_chat_id(session_id):
    return sessions.get(session_id)
