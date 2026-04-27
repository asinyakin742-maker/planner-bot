import json
from datetime import date

import requests


OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def _tool_schema():
    return {
        "type": "function",
        "function": {
            "name": "task_draft",
            "description": "Parse a task request into a structured task draft for a Telegram planner bot.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "is_task_request": {"type": "boolean"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "due_date": {"type": "string"},
                    "assignee": {"type": "string"},
                    "missing_fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["title", "description", "due_date", "assignee"],
                        },
                    },
                    "needs_clarification": {"type": "boolean"},
                    "clarification_question": {"type": "string"},
                    "quality_warnings": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "is_task_request",
                    "title",
                    "description",
                    "due_date",
                    "assignee",
                    "missing_fields",
                    "needs_clarification",
                    "clarification_question",
                    "quality_warnings",
                ],
            },
        },
    }


def _default_result():
    return {
        "ok": False,
        "draft": None,
        "error": "",
    }


def _build_headers(api_key: str):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _extract_tool_arguments(body: dict):
    choices = body.get("choices", [])
    if not choices:
        raise ValueError("OpenAI response has no choices")

    message = choices[0].get("message", {})
    tool_calls = message.get("tool_calls", [])
    if not tool_calls:
        raise ValueError("OpenAI response has no tool calls")

    function = tool_calls[0].get("function", {})
    arguments = function.get("arguments")
    if not arguments:
        raise ValueError("OpenAI tool call has no arguments")

    return json.loads(arguments)


def _call_openai(api_key: str, model: str, system_prompt: str, user_prompt: str):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [_tool_schema()],
        "tool_choice": {
            "type": "function",
            "function": {"name": "task_draft"},
        },
    }

    try:
        response = requests.post(
            OPENAI_API_URL,
            headers=_build_headers(api_key),
            json=payload,
            timeout=40,
        )
    except requests.RequestException as exc:
        result = _default_result()
        result["error"] = str(exc)
        return result

    try:
        body = response.json()
    except ValueError:
        result = _default_result()
        result["error"] = response.text
        return result

    if response.status_code >= 400:
        result = _default_result()
        result["error"] = json.dumps(body, ensure_ascii=False)
        return result

    try:
        draft = _extract_tool_arguments(body)
    except (ValueError, json.JSONDecodeError) as exc:
        result = _default_result()
        result["error"] = str(exc)
        return result

    return {
        "ok": True,
        "draft": draft,
        "error": "",
    }


def parse_task_request(api_key: str, model: str, text: str, today: date):
    system_prompt = (
        "You extract a task draft from a Russian Telegram message for a task bot. "
        "Return a structured task draft only via the provided function. "
        "If the message is not a task request, set is_task_request=false. "
        "Use today's date provided in the prompt to resolve relative dates like today, tomorrow, this Friday, or this week. "
        "For due_date return either an ISO date in YYYY-MM-DD format or an empty string. "
        "If required fields are missing, set needs_clarification=true and provide one concise Russian clarification question. "
        "If the text is vague, add short Russian hints to quality_warnings."
    )
    user_prompt = (
        f"Сегодняшняя дата: {today.isoformat()}.\n"
        f"Сообщение пользователя:\n{text}"
    )
    return _call_openai(api_key, model, system_prompt, user_prompt)


def continue_task_request(api_key: str, model: str, current_draft: dict, clarification_text: str, today: date):
    system_prompt = (
        "You update an existing Russian task draft for a Telegram planner bot using the user's clarification. "
        "Return the full updated draft only via the provided function. "
        "Use today's date provided in the prompt to resolve relative dates. "
        "Keep already known values unless the user's clarification clearly changes them. "
        "For due_date return either an ISO date in YYYY-MM-DD format or an empty string."
    )
    user_prompt = (
        f"Сегодняшняя дата: {today.isoformat()}.\n"
        f"Текущий draft задачи:\n{json.dumps(current_draft, ensure_ascii=False)}\n\n"
        f"Уточнение пользователя:\n{clarification_text}"
    )
    return _call_openai(api_key, model, system_prompt, user_prompt)
