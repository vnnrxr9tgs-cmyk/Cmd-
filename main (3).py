from flask import Flask, jsonify
from datetime import datetime, timedelta
import requests

app = Flask(__name__)

ROCKET_URL = "http://rocketchat:000"
USERNAME = "igor"
PASSWORD = "123"
CHANNEL_NAME = "test"

auth_token = None
user_id = None
room_id = None

MESSAGE_LIFETIME_MINUTES = 60
last_message_ids = set()


def rocket_login():
    global auth_token, user_id
    url = f"{ROCKET_URL}/api/v1/login"
    response = requests.post(url, json={
        "user": USERNAME,
        "password": PASSWORD
    })
    data = response.json()
    if data.get("status") == "success":
        auth_token = data["data"]["authToken"]
        user_id = data["data"]["userId"]
        return True
    return False


def rocket_get_room_id():
    global room_id
    url = f"{ROCKET_URL}/api/v1/channels.list"
    headers = {
        "X-Auth-Token": auth_token,
        "X-User-Id": user_id
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    for channel in data.get("channels", []):
        if channel["name"] == CHANNEL_NAME:
            room_id = channel["_id"]
            return True
    return False


def rocket_get_messages():
    url = f"{ROCKET_URL}/api/v1/channels.messages?roomId={room_id}&count=20"
    headers = {
        "X-Auth-Token": auth_token,
        "X-User-Id": user_id
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    messages = []
    for msg in data.get("messages", []):
        if not msg.get("msg"):
            continue
        timestamp = datetime.fromisoformat(msg["ts"].replace("Z", "+00:00"))
        messages.append({
            "id": msg["_id"],
            "user": msg["u"]["username"],
            "text": msg["msg"],
            "timestamp": timestamp.isoformat()
        })
    return messages


def filter_recent(messages):
    limit = datetime.utcnow() - timedelta(minutes=MESSAGE_LIFETIME_MINUTES)
    return [m for m in messages if datetime.fromisoformat(m["timestamp"]) > limit]


def detect_new(messages):
    global last_message_ids
    current_ids = {m["id"] for m in messages}
    new_ids = current_ids - last_message_ids
    last_message_ids = current_ids
    return list(new_ids)


@app.route("/api/notifications")
def notifications():
    if not auth_token or not room_id:
        return jsonify({"notifications": [], "new": []})

    messages = rocket_get_messages()
    messages = filter_recent(messages)
    new_ids = detect_new(messages)
    return jsonify({
        "notifications": messages,
        "new": new_ids
    })


if __name__ == "__main__":
    # Инициализация Rocket.Chat
    if not rocket_login():
        print("Ошибка: не удалось залогиниться в Rocket.Chat")
    elif not rocket_get_room_id():
        print(f"Ошибка: канал '{CHANNEL_NAME}' не найден")
    else:
        print(f"Подключено к Rocket.Chat каналу '{CHANNEL_NAME}'")

    # Запуск Flask
    app.run(debug=True, port=5000)