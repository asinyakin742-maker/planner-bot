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


def create_trello_card(title: str, description: str):
    url = "https://api.trello.com/1/cards"
    query = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": TRELLO_LIST_ID,
        "name": title,
        "desc": description
    }
    response = requests.post(url, params=query, timeout=20)
    return response.status_code, response.text


def parse_task_text(text: str):
    """
    Поддерживает 2 формата:

    1) Старый:
       создай задачу новое демо

    2) Новый:
       создай задачу
       название: новое демо
       описание: демо для клиента Почта
    """
    cleaned_text = text.strip()

    command_prefix = "создай задачу"
    if not cleaned_text.lower().startswith(command_prefix):
        return None

    remainder = cleaned_text[len(command_prefix):].strip()

    # Старый формат: всё после команды считаем названием,
    # а описание дублирует название
    if remainder and "\n" not in remainder:
        return {
            "title": remainder,
            "description": remainder
        }

    # Новый формат: читаем построчно
    title = ""
    description = ""

    lines = [line.strip() for line in remainder.splitlines() if line.strip()]

    for line in lines:
        lowered = line.lower()

        if lowered.startswith("название:"):
            title = line.split(":", 1)[1].strip()
        elif lowered.startswith("описание:"):
            description = line.split(":", 1)[1].strip()

    if not title and not description and remainder:
        # На случай, если сообщение многострочное, но без ключей
        fallback_text = " ".join(lines).strip()
        if fallback_text:
            return {
                "title": fallback_text,
                "description": fallback_text
            }

    if title and not description:
        description = title

    return {
        "title": title,
        "description": description
    }


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
    text = message.get("text", "").strip()

    parsed_task = parse_task_text(text)

    if parsed_task is not None:
        title = parsed_task["title"]
        description = parsed_task["description"]

        if not title:
            send_telegram_message(
                chat_id,
                "Не удалось создать задачу: укажи название.\n\n"
                "Примеры:\n"
                "создай задачу новое демо\n\n"
                "или\n\n"
                "создай задачу\n"
                "название: новое демо\n"
                "описание: демо для клиента Почта"
            )
            return JSONResponse({"ok": True})

        status_code, response_text = create_trello_card(title, description)

        if status_code == 200:
            send_telegram_message(
                chat_id,
                f"Задача создана.\nНазвание: {title}\nОписание: {description}"
            )
        else:
            send_telegram_message(
                chat_id,
                f"Не удалось создать задачу.\nКод: {status_code}\nОтвет Trello: {response_text}"
            )
    else:
        send_telegram_message(
            chat_id,
            "Пока умею создавать задачи.\n\n"
            "Формат 1:\n"
            "создай задачу новое демо\n\n"
            "Формат 2:\n"
            "создай задачу\n"
            "название: новое демо\n"
            "описание: демо для клиента Почта"
        )

    return JSONResponse({"ok": True})
