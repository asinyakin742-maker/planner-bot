from datetime import datetime


def parse_due_date(raw_due: str):
    """
    Supported formats:
    1) DD.MM       -> 25.04
    2) YYYY-MM-DD  -> 2026-04-25

    Returns Trello-friendly ISO-like string:
    YYYY-MM-DDT09:00:00
    """
    raw_due = raw_due.strip()

    if not raw_due:
        return None

    try:
        parsed = datetime.strptime(raw_due, "%Y-%m-%d")
        return parsed.strftime("%Y-%m-%dT09:00:00")
    except ValueError:
        pass

    try:
        current_year = datetime.now().year
        parsed = datetime.strptime(f"{raw_due}.{current_year}", "%d.%m.%Y")
        return parsed.strftime("%Y-%m-%dT09:00:00")
    except ValueError:
        return None


def parse_task_text(text: str):
    """
    Supports two formats:

    1) Old:
       создай задачу новое демо

    2) New:
       создай задачу
       название: новое демо
       описание: демо для клиента Почта
       срок: 25.04
       ответственный: Иван
    """
    cleaned_text = text.strip()

    command_prefix = "создай задачу"
    if not cleaned_text.lower().startswith(command_prefix):
        return None

    remainder = cleaned_text[len(command_prefix):].strip()

    if remainder and "\n" not in remainder:
        return {
            "title": remainder,
            "description": remainder,
            "due_date": None,
            "assignee": "",
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
                "assignee": "",
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
                "assignee": assignee,
            }

    return {
        "title": title,
        "description": description,
        "due_date": due_date,
        "assignee": assignee,
    }
