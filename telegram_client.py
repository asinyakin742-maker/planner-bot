import logging

import requests

logger = logging.getLogger(__name__)


def _build_result(ok: bool, status_code=None, body=None, error: str = ""):
    return {
        "ok": ok,
        "status_code": status_code,
        "body": body,
        "error": error,
    }


def send_telegram_message(api_url: str, chat_id: int, text: str):
    url = f"{api_url}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=20)
    except requests.RequestException as exc:
        logger.exception("Failed to reach Telegram API", extra={"chat_id": chat_id})
        return _build_result(False, status_code=None, body=None, error=str(exc))

    try:
        body = response.json()
    except ValueError:
        body = None

    if response.status_code >= 400:
        logger.error(
            "Telegram HTTP error",
            extra={
                "chat_id": chat_id,
                "status_code": response.status_code,
                "response_body": body if body is not None else response.text,
            },
        )
        return _build_result(
            False,
            status_code=response.status_code,
            body=body,
            error=response.text,
        )

    if not body or not body.get("ok", False):
        logger.error(
            "Telegram API returned unsuccessful response",
            extra={
                "chat_id": chat_id,
                "status_code": response.status_code,
                "response_body": body,
            },
        )
        return _build_result(
            False,
            status_code=response.status_code,
            body=body,
            error="Telegram API returned ok=false",
        )

    return _build_result(
        True,
        status_code=response.status_code,
        body=body,
        error="",
    )
