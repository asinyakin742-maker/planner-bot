import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import parser as task_parser
import telegram_client
import trello_client
import user_store

app = FastAPI()
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_LIST_ID = os.getenv("TRELLO_LIST_ID")
TRELLO_ASSIGNEE_FULL_NAME_FIELD_ID = os.getenv("TRELLO_ASSIGNEE_FULL_NAME_FIELD_ID", "").strip()
TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID = os.getenv("TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID", "").strip()
USERS_FILE_PATH = Path(os.getenv("USERS_FILE_PATH", "users.json"))
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip()
GOOGLE_SHEETS_RANGE = os.getenv("GOOGLE_SHEETS_RANGE", "A:C").strip()

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
PENDING_REGISTRATIONS = set()


def get_user_store():
    return user_store.build_user_store(
        USERS_FILE_PATH,
        spreadsheet_id=GOOGLE_SHEETS_SPREADSHEET_ID,
        credentials_json=GOOGLE_SHEETS_CREDENTIALS_JSON,
        cell_range=GOOGLE_SHEETS_RANGE,
    )


def send_telegram_message(chat_id: int, text: str):
    return telegram_client.send_telegram_message(TELEGRAM_API_URL, chat_id, text)


def find_user(raw_name: str):
    store = get_user_store()
    return store.find_user(raw_name)


def register_user(full_name: str, telegram_chat_id: int):
    store = get_user_store()
    return store.upsert_user(full_name, telegram_chat_id)


def create_trello_card(
    title: str,
    description: str,
    due_date: str = None,
    trello_member_id: str = None,
):
    return trello_client.create_trello_card(
        TRELLO_API_KEY,
        TRELLO_TOKEN,
        TRELLO_LIST_ID,
        title,
        description,
        due_date,
        trello_member_id,
    )


def set_trello_card_text_custom_field(card_id: str, custom_field_id: str, value: str):
    return trello_client.set_card_text_custom_field(
        TRELLO_API_KEY,
        TRELLO_TOKEN,
        card_id,
        custom_field_id,
        value,
    )


def parse_task_text(text: str):
    return task_parser.parse_task_text(text)


def handle_registration_message(chat_id: int, text: str):
    lowered_text = text.strip().lower()

    if lowered_text == "регистрация":
        PENDING_REGISTRATIONS.add(chat_id)
        send_telegram_message(
            chat_id,
            "Напиши фамилию и имя, чтобы я сохранил тебя в справочник.",
        )
        return True

    if chat_id in PENDING_REGISTRATIONS:
        full_name = text.strip()

        if len(full_name.split()) < 2:
            send_telegram_message(
                chat_id,
                "Нужны фамилия и имя. Пример: Иванов Иван",
            )
            return True

        try:
            register_user(full_name, chat_id)
        except Exception:
            logger.exception("Failed to register user", extra={"chat_id": chat_id, "full_name": full_name})
            send_telegram_message(
                chat_id,
                "Не удалось завершить регистрацию. Попробуй еще раз чуть позже.",
            )
            return True

        PENDING_REGISTRATIONS.discard(chat_id)
        send_telegram_message(
            chat_id,
            f"Регистрация завершена: {full_name}. Теперь тебя можно назначать ответственным.",
        )
        return True

    return False


def notify_assignee(assignee: dict, title: str, description: str, due_text: str):
    if not assignee or not assignee.get("telegram_chat_id"):
        return None

    return send_telegram_message(
        assignee["telegram_chat_id"],
        f"Тебе назначена задача: {title}\nОписание: {description}\nСрок: {due_text}",
    )


def sync_trello_assignee_metadata(assignee: dict, card_id: str):
    if not assignee or not card_id:
        return {"ok": True, "skipped": True}

    if not TRELLO_ASSIGNEE_FULL_NAME_FIELD_ID or not TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID:
        logger.warning("Trello custom field ids are not configured")
        return {
            "ok": False,
            "skipped": False,
            "error": "Trello custom field ids are not configured",
        }

    full_name_result = set_trello_card_text_custom_field(
        card_id,
        TRELLO_ASSIGNEE_FULL_NAME_FIELD_ID,
        assignee["full_name"],
    )
    if not full_name_result["ok"]:
        return {
            "ok": False,
            "skipped": False,
            "error": f"Failed to write assignee full name: {full_name_result['error'] or full_name_result['body']}",
        }

    chat_id_result = set_trello_card_text_custom_field(
        card_id,
        TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID,
        str(assignee["telegram_chat_id"]),
    )
    if not chat_id_result["ok"]:
        return {
            "ok": False,
            "skipped": False,
            "error": f"Failed to write assignee chat id: {chat_id_result['error'] or chat_id_result['body']}",
        }

    return {"ok": True, "skipped": False}


def process_task_request(chat_id: int, parsed_task: dict):
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
            "срок: 25.04",
        )
        return

    if due_date == "INVALID_DATE":
        send_telegram_message(
            chat_id,
            "Не удалось распознать срок.\n"
            "Используй один из форматов:\n"
            "- 25.04\n"
            "- 2026-04-25",
        )
        return

    try:
        assignee = find_user(assignee_name) if assignee_name else None
    except Exception:
        logger.exception("Failed to load assignee from user store", extra={"assignee_name": assignee_name})
        send_telegram_message(
            chat_id,
            "Не удалось проверить справочник сотрудников. Попробуй еще раз чуть позже.",
        )
        return

    if assignee_name and assignee is None:
        send_telegram_message(
            chat_id,
            f"Не удалось найти ответственного: {assignee_name}. Пусть он сначала зарегистрируется в боте.",
        )
        return

    trello_member_id = assignee.get("trello_member_id") if assignee else None
    trello_result = create_trello_card(
        title,
        description,
        due_date,
        trello_member_id=trello_member_id,
    )

    if not trello_result["ok"]:
        send_telegram_message(
            chat_id,
            f"Не удалось создать задачу.\n"
            f"Код: {trello_result['status_code']}\n"
            f"Ответ Trello: {trello_result['error'] or trello_result['body']}",
        )
        return

    card_id = ""
    if isinstance(trello_result.get("body"), dict):
        card_id = trello_result["body"].get("id", "")

    assignee_sync_result = sync_trello_assignee_metadata(assignee, card_id)
    if assignee and not assignee_sync_result["ok"]:
        logger.warning(
            "Failed to sync Trello assignee metadata",
            extra={
                "assignee_name": assignee_name,
                "card_id": card_id,
                "error": assignee_sync_result.get("error"),
            },
        )

    due_text = due_date if due_date else "не указан"
    assignee_text = assignee_name if assignee_name else "не указан"
    send_telegram_message(
        chat_id,
        f"Задача создана.\nНазвание: {title}\nОписание: {description}\nСрок: {due_text}\nОтветственный: {assignee_text}",
    )

    assignee_delivery = notify_assignee(assignee, title, description, due_text)
    if assignee and assignee_delivery and not assignee_delivery.get("ok"):
        logger.warning(
            "Failed to notify assignee",
            extra={
                "assignee_name": assignee_name,
                "telegram_chat_id": assignee.get("telegram_chat_id"),
                "telegram_status_code": assignee_delivery.get("status_code"),
                "telegram_error": assignee_delivery.get("error"),
                "telegram_body": assignee_delivery.get("body"),
            },
        )
        send_telegram_message(
            chat_id,
            f"Задача создана, но уведомление ответственному не доставлено: {assignee_name}.",
        )

    if assignee and not assignee_sync_result["ok"]:
        send_telegram_message(
            chat_id,
            f"Задача создана, но данные ответственного не записаны в Trello для будущих напоминаний: {assignee_name}.",
        )


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "planner-bot"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    logger.info(
        "Received Telegram update",
        extra={
            "update_id": update.get("update_id"),
            "has_message": bool(update.get("message")),
        },
    )

    message = update.get("message")
    if not message:
        return JSONResponse({"ok": True})

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if handle_registration_message(chat_id, text):
        return JSONResponse({"ok": True})

    parsed_task = parse_task_text(text)

    if parsed_task is not None:
        process_task_request(chat_id, parsed_task)
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
            "срок: 25.04",
        )

    return JSONResponse({"ok": True})
