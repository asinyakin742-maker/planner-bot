import logging

import requests

logger = logging.getLogger(__name__)


def send_telegram_message(api_url: str, chat_id: int, text: str):
    url = f"{api_url}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            logger.error(
                "Telegram API returned unsuccessful response",
                extra={"chat_id": chat_id, "response": body},
            )
            return {
                "ok": False,
                "status_code": response.status_code,
                "body": body,
            }
        return {
            "ok": True,
            "status_code": response.status_code,
            "body": body,
        }
    except (requests.RequestException, ValueError):
        logger.exception("Failed to send Telegram message", extra={"chat_id": chat_id})
        return {
            "ok": False,
            "status_code": None,
            "body": None,
        }
