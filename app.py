import os
import json
from datetime import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_LIST_ID = os.getenv("TRELLO_LIST_ID")
USERS_FILE_PATH = Path(os.getenv("USERS_FILE_PATH", "users.json"))
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
GOOGLE_SHEETS_RANGE = os.getenv("GOOGLE_SHEETS_RANGE", "A:C")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
PENDING_REGISTRATIONS = set()


def send_telegram_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload, timeout=20)


def use_google_sheets():
    return bool(GOOGLE_SHEETS_SPREADSHEET_ID and GOOGLE_SHEETS_CREDENTIALS_JSON)


def get_sheets_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials_info = json.loads(GOOGLE_SHEETS_CREDENTIALS_JSON)
    credentials = Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=credentials)


def load_users_from_sheets():
    service = get_sheets_service()
    response = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
        range=GOOGLE_SHEETS_RANGE
    ).execute()

    rows = response.get("values", [])
    users = {}

    for row in rows[1:]:
        full_name = row[0].strip() if len(row) > 0 else ""
        telegram_chat_id = row[1].strip() if len(row) > 1 else ""
        trello_member_id = row[2].strip() if len(row) > 2 else ""

        if not full_name:
            continue

        users[normalize_user_name(full_name)] = {
            "full_name": full_name,
            "telegram_chat_id": int(telegram_chat_id) if telegram_chat_id else "",
            "trello_member_id": trello_member_id
        }

    return users


def upsert_user_in_sheets(full_name: str, chat_id: int, trello_member_id: str = ""):
    service = get_sheets_service()
    response = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
        range=GOOGLE_SHEETS_RANGE
    ).execute()

    rows = response.get("values", [])
    normalized_name = normalize_user_name(full_name)
    values = [[full_name.strip(), str(chat_id), trello_member_id]]

    for index, row in enumerate(rows[1:], start=2):
        existing_name = row[0].strip() if len(row) > 0 else ""
        if normalize_user_name(existing_name) == normalized_name:
            service.spreadsheets().values().update(
                spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
                range=f"A{index}:C{index}",
                valueInputOption="RAW",
                body={"values": values}
            ).execute()
            return normalized_name

    service.spreadsheets().values().append(
        spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
        range=GOOGLE_SHEETS_RANGE,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values}
    ).execute()
    return normalized_name


def load_users():
    if use_google_sheets():
        return load_users_from_sheets()

    if not USERS_FILE_PATH.exists():
        return {}

    with USERS_FILE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_users(users: dict):
    if use_google_sheets():
        raise RuntimeError("Use upsert_user_in_sheets when Google Sheets storage is enabled")

    with USERS_FILE_PATH.open("w", encoding="utf-8") as file:
        json.dump(users, file, ensure_ascii=False, indent=2)


def normalize_user_name(name: str):
    return " ".join(name.strip().lower().split())


def register_user(full_name: str, chat_id: int):
    normalized_name = normalize_user_name(full_name)
    if use_google_sheets():
        return upsert_user_in_sheets(full_name, chat_id)

    users = load_users()
    existing_user = users.get(normalized_name, {})

    users[normalized_name] = {
        "full_name": full_name.strip(),
        "telegram_chat_id": chat_id,
        "trello_member_id": existing_user.get("trello_member_id", "")
    }

    save_users(users)
    return normalized_name


def find_user(full_name: str):
    normalized_name = normalize_user_name(full_name)
    users = load_users()
    return users.get(normalized_name)


def parse_due_date(raw_due: str):
    """
    Поддерживаем:
    1) DD.MM       -> например 25.04
    2) YYYY-MM-DD  -> например 2026-04-25

    Возвращаем строку в ISO-формате для Trello:
    YYYY-MM-DDT09:00:00
    """
    raw_due = raw_due.strip()

    if not raw_due:
        return None

    # Формат YYYY-MM-DD
    try:
        parsed = datetime.strptime(raw_due, "%Y-%m-%d")
        return parsed.strftime("%Y-%m-%dT09:00:00")
    except ValueError:
        pass

    # Формат DD.MM
    try:
        current_year = datetime.now().year
        parsed = datetime.strptime(f"{raw_due}.{current_year}", "%d.%m.%Y")
        return parsed.strftime("%Y-%m-%dT09:00:00")
    except ValueError:
        return None


def create_trello_card(
    title: str,
    description: str,
    due_date: str = None,
    trello_member_id: str = None
):
    url = "https://api.trello.com/1/cards"
    query = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": TRELLO_LIST_ID,
        "name": title,
        "desc": description
    }

    if due_date:
        query["due"] = due_date
    if trello_member_id:
        query["idMembers"] = [trello_member_id]

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
       срок: 25.04
    """
    cleaned_text = text.strip()

    command_prefix = "создай задачу"
    if not cleaned_text.lower().startswith(command_prefix):
        return None

    remainder = cleaned_text[len(command_prefix):].strip()

    # Старый формат: всё после команды считаем названием,
    # а описание дублирует название, срок пустой
    if remainder and "\n" not in remainder:
        return {
            "title": remainder,
            "description": remainder,
            "due_date": None,
            "assignee": ""
        }

    title = ""
    description = ""
    raw_due = ""
    assignee = ""

    lines = [line.strip() for line in remainder.splitlines() if line.strip()]

    for line in lines:
        lowered = line.lower()

        if lowered.startswith("название:"):
            title = line.split(":", 1)[1].strip()
        elif lowered.startswith("описание:"):
            description = line.split(":", 1)[1].strip()
        elif lowered.startswith("срок:"):
            raw_due = line.split(":", 1)[1].strip()
        elif lowered.startswith("ответственный:"):
            assignee = line.split(":", 1)[1].strip()

    if not title and not description and not raw_due and remainder:
        fallback_text = " ".join(lines).strip()
        if fallback_text:
            return {
                "title": fallback_text,
                "description": fallback_text,
                "due_date": None,
                "assignee": ""
            }

    if title and not description:
        description = title

    due_date = None
    if raw_due:
        due_date = parse_due_date(raw_due)

        if due_date is None:
            return {
                "title": title,
                "description": description,
                "due_date": "INVALID_DATE",
                "assignee": assignee
            }

    return {
        "title": title,
        "description": description,
        "due_date": due_date,
        "assignee": assignee
    }


def handle_registration_message(chat_id: int, text: str):
    lowered_text = text.strip().lower()

    if lowered_text == "регистрация":
        PENDING_REGISTRATIONS.add(chat_id)
        send_telegram_message(
            chat_id,
            "Напиши фамилию и имя, чтобы я сохранил тебя в справочник."
        )
        return True

    if chat_id in PENDING_REGISTRATIONS:
        full_name = text.strip()

        if len(full_name.split()) < 2:
            send_telegram_message(
                chat_id,
                "Нужны фамилия и имя. Пример: Иванов Иван"
            )
            return True

        register_user(full_name, chat_id)
        PENDING_REGISTRATIONS.discard(chat_id)
        send_telegram_message(
            chat_id,
            f"Регистрация завершена: {full_name}. Теперь тебя можно назначать ответственным."
        )
        return True

    return False


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "planner-bot"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    print(update)

    message = update.get("message")
    if not message:
        return JSONResponse({"ok": True})

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if handle_registration_message(chat_id, text):
        return JSONResponse({"ok": True})

    parsed_task = parse_task_text(text)

    if parsed_task is not None:
        title = parsed_task["title"]
        description = parsed_task["description"]
        due_date = parsed_task["due_date"]
        assignee_name = parsed_task.get("assignee", "")

        if not title:
            send_telegram_message(
                chat_id,
                "Не удалось создать задачу: укажи название.\n\n"
                "Примеры:\n"
                "создай задачу новое демо\n\n"
                "или\n\n"
                "создай задачу\n"
                "название: новое демо\n"
                "описание: демо для клиента Почта\n"
                "срок: 25.04"
            )
            return JSONResponse({"ok": True})

        if due_date == "INVALID_DATE":
            send_telegram_message(
                chat_id,
                "Не удалось распознать срок.\n"
                "Используй один из форматов:\n"
                "- 25.04\n"
                "- 2026-04-25"
            )
            return JSONResponse({"ok": True})

        assignee = None
        trello_member_id = None
        if assignee_name:
            assignee = find_user(assignee_name)

            if assignee is None:
                send_telegram_message(
                    chat_id,
                    f"Не удалось найти ответственного: {assignee_name}. Пусть он сначала зарегистрируется в боте."
                )
                return JSONResponse({"ok": True})

            trello_member_id = assignee.get("trello_member_id") or None

        status_code, response_text = create_trello_card(
            title,
            description,
            due_date,
            trello_member_id=trello_member_id
        )

        if status_code == 200:
            due_text = due_date if due_date else "не указан"
            assignee_text = assignee_name if assignee_name else "не указан"
            send_telegram_message(
                chat_id,
                f"Задача создана.\nНазвание: {title}\nОписание: {description}\nСрок: {due_text}\nОтветственный: {assignee_text}"
            )
            if assignee:
                send_telegram_message(
                    assignee["telegram_chat_id"],
                    f"Тебе назначена задача: {title}\nОписание: {description}\nСрок: {due_text}"
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
            "описание: демо для клиента Почта\n"
            "срок: 25.04"
        )

    return JSONResponse({"ok": True})
