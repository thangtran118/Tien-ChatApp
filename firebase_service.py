import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

cred = credentials.Certificate("chat-app-tcp-firebase-adminsdk-fbsvc-cfc8cc14f6.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

def save_chat_message(sender, content, room, receiver, msg_type, timestamp, filename=None, filedata=None, filetype=None):
    data = {
        "sender": sender,
        "content": content,
        "room": room,
        "receiver": receiver,
        "type": msg_type,
        "timestamp": datetime.utcnow()
    }
    
    if filename:
        data["filename"] = filename
    if filedata:
        data["filedata"] = filedata
    if filetype:
        data["filetype"] = filetype
    
    db.collection("messages").add(data)


def load_room_history(room_name):
    messages_ref = db.collection("messages")
    query = messages_ref.where("room", "==", room_name).order_by("timestamp")
    docs = query.stream()

    messages = []
    for doc in docs:
        messages.append(doc.to_dict())

    return messages

def save_private_message(user1, user2, sender, content, filename=None, filedata=None, filetype=None):
    try:
        chat_id = "_".join(sorted([user1, user2]))

        data = {
            "sender": sender,
            "content": content,
            "timestamp": datetime.utcnow(),
            "type": "chat"
        }
        
        if filename:
            data["filename"] = filename
        if filedata:
            data["filedata"] = filedata
        if filetype:
            data["filetype"] = filetype

        db.collection("private_chats") \
          .document(chat_id) \
          .collection("messages") \
          .add(data)
    except Exception as e:
        print("Error saving private message:", e)

def load_private_history(user1, user2):
    try:
        chat_id = "_".join(sorted([user1, user2]))

        docs = db.collection("private_chats") \
                 .document(chat_id) \
                 .collection("messages") \
                 .order_by("timestamp") \
                 .stream()

        return [doc.to_dict() for doc in docs]

    except Exception as e:
        print("Error loading private history:", e)
        return []