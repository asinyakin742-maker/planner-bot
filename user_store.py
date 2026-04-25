import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_user_name(raw_name: str):
    return " ".join(raw_name.strip().lower().split())


class JsonFileUserStore:
    def __init__(self, users_file_path: Path):
        self.users_file_path = users_file_path

    def load_users(self):
        if not self.users_file_path.exists():
            logger.warning("Users file not found", extra={"path": str(self.users_file_path)})
            return {}

        try:
            with self.users_file_path.open("r", encoding="utf-8") as file:
                users = json.load(file)
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load users file", extra={"path": str(self.users_file_path)})
            return {}

        normalized_users = {}
        for name, user_data in users.items():
            normalized_users[normalize_user_name(name)] = user_data

        return normalized_users

    def find_user(self, raw_name: str):
        if not raw_name:
            return None

        users = self.load_users()
        return users.get(normalize_user_name(raw_name))

    def upsert_user(self, full_name: str, telegram_chat_id: int, trello_member_id: str = ""):
        normalized_name = normalize_user_name(full_name)
        users = self.load_users()
        existing_user = users.get(normalized_name, {})

        users[normalized_name] = {
            "full_name": full_name.strip(),
            "telegram_chat_id": telegram_chat_id,
            "trello_member_id": trello_member_id or existing_user.get("trello_member_id", ""),
        }

        with self.users_file_path.open("w", encoding="utf-8") as file:
            json.dump(users, file, ensure_ascii=False, indent=2)

        return users[normalized_name]


class GoogleSheetsUserStore:
    def __init__(self, spreadsheet_id: str, credentials_json: str, cell_range: str = "A:C"):
        self.spreadsheet_id = spreadsheet_id.strip()
        self.credentials_json = credentials_json.strip()
        self.cell_range = cell_range.strip()

    def _build_service(self):
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        credentials_info = json.loads(self.credentials_json)
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return build("sheets", "v4", credentials=credentials)

    def load_users(self):
        service = self._build_service()
        response = service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.cell_range,
        ).execute()

        rows = response.get("values", [])
        if not rows:
            return {}

        normalized_users = {}
        for row in rows[1:]:
            full_name = row[0].strip() if len(row) > 0 else ""
            telegram_chat_id = row[1].strip() if len(row) > 1 else ""
            trello_member_id = row[2].strip() if len(row) > 2 else ""

            if not full_name:
                continue

            normalized_users[normalize_user_name(full_name)] = {
                "full_name": full_name,
                "telegram_chat_id": int(telegram_chat_id) if telegram_chat_id else "",
                "trello_member_id": trello_member_id,
            }

        return normalized_users

    def find_user(self, raw_name: str):
        if not raw_name:
            return None

        users = self.load_users()
        return users.get(normalize_user_name(raw_name))

    def upsert_user(self, full_name: str, telegram_chat_id: int, trello_member_id: str = ""):
        service = self._build_service()
        response = service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.cell_range,
        ).execute()

        rows = response.get("values", [])
        normalized_name = normalize_user_name(full_name)
        values = [[full_name.strip(), str(telegram_chat_id), trello_member_id]]

        for index, row in enumerate(rows[1:], start=2):
            existing_name = row[0].strip() if len(row) > 0 else ""
            if normalize_user_name(existing_name) == normalized_name:
                service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"A{index}:C{index}",
                    valueInputOption="RAW",
                    body={"values": values},
                ).execute()
                return {
                    "full_name": full_name.strip(),
                    "telegram_chat_id": telegram_chat_id,
                    "trello_member_id": trello_member_id,
                }

        service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=self.cell_range,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

        return {
            "full_name": full_name.strip(),
            "telegram_chat_id": telegram_chat_id,
            "trello_member_id": trello_member_id,
        }


def build_user_store(
    users_file_path: Path,
    spreadsheet_id: str = "",
    credentials_json: str = "",
    cell_range: str = "A:C",
):
    if spreadsheet_id and credentials_json:
        return GoogleSheetsUserStore(spreadsheet_id, credentials_json, cell_range)

    return JsonFileUserStore(users_file_path)
