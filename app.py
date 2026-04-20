from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import os

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_LIST_ID = os.getenv("TRELLO_LIST_ID")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_telegram_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload, timeout=20)


def create_trello_card(title: str):
    url = "https://api.trello.com/1/cards"
    query = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": TRELLO_LIST_ID,
        "name": title,
        "desc": title
    }
    response = requests.post(url, params=query, timeout=20)
    return response.status_code, response.text


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    message = update.get("message")
    if not message:
        return JSONResponse({"ok": True})

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.lower().startswith("создай задачу"):
        task_title = text.replace("создай задачу", "").strip()

        if not task_title:
            send_telegram_message(chat_id, "Напиши название задачи после команды")
        else:
            status_code, response_text = create_trello_card(task_title)

            if status_code == 200:
                send_telegram_message(chat_id, f"Задача создана: {task_title}")
            else:
                send_telegram_message(
                    chat_id,
                    f"Не удалось создать задачу.\nКод: {status_code}\nОтвет Trello: {response_text}"
                )
    else:
        send_telegram_message(
            chat_id,
            "Пока умею создавать задачи 😄\nНапиши: создай задачу ..."
        )

    return JSONResponse({"ok": True})
