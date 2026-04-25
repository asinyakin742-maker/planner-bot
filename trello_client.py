import requests


def _build_result(ok: bool, status_code=None, body=None, error: str = ""):
    return {
        "ok": ok,
        "status_code": status_code,
        "body": body,
        "error": error,
    }


def create_trello_card(
    api_key: str,
    token: str,
    list_id: str,
    title: str,
    description: str,
    due_date: str = None,
    trello_member_id: str = None,
):
    url = "https://api.trello.com/1/cards"
    query = {
        "key": api_key,
        "token": token,
        "idList": list_id,
        "name": title,
        "desc": description,
    }

    if due_date:
        query["due"] = due_date
    if trello_member_id:
        query["idMembers"] = [trello_member_id]

    try:
        response = requests.post(url, params=query, timeout=20)
    except requests.RequestException as exc:
        return _build_result(False, status_code=None, body=None, error=str(exc))

    try:
        body = response.json()
    except ValueError:
        body = response.text

    if response.status_code != 200:
        return _build_result(
            False,
            status_code=response.status_code,
            body=body,
            error=response.text,
        )

    return _build_result(
        True,
        status_code=response.status_code,
        body=body,
        error="",
    )


def set_card_text_custom_field(
    api_key: str,
    token: str,
    card_id: str,
    custom_field_id: str,
    value: str,
):
    url = f"https://api.trello.com/1/cards/{card_id}/customField/{custom_field_id}/item"
    query = {
        "key": api_key,
        "token": token,
    }
    payload = {
        "value": {
            "text": value,
        }
    }

    try:
        response = requests.put(url, params=query, json=payload, timeout=20)
    except requests.RequestException as exc:
        return _build_result(False, status_code=None, body=None, error=str(exc))

    try:
        body = response.json()
    except ValueError:
        body = response.text

    if response.status_code != 200:
        return _build_result(
            False,
            status_code=response.status_code,
            body=body,
            error=response.text,
        )

    return _build_result(
        True,
        status_code=response.status_code,
        body=body,
        error="",
    )
