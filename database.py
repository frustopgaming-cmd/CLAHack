import uuid

sessions = {}  # { session_id: chat_id }

def create_session(chat_id):
    session_id = str(uuid.uuid4())
    sessions[session_id] = chat_id
    return session_id

def get_chat_id(session_id):
    return sessions.get(session_id)
