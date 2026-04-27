import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import telegram_client
import user_store
from fastapi.testclient import TestClient
from zoneinfo import ZoneInfo


class PlannerBotTests(unittest.TestCase):
    def setUp(self):
        app.PENDING_REGISTRATIONS.clear()
        app.PENDING_AI_DRAFTS.clear()
        self.client = TestClient(app.app)

    def test_health_endpoint_payload(self):
        self.assertEqual(
            app.health(),
            {"status": "ok", "service": "planner-bot"},
        )

    def test_parse_old_format(self):
        parsed = app.parse_task_text("создай задачу демо")

        self.assertEqual(parsed["title"], "демо")
        self.assertEqual(parsed["description"], "демо")
        self.assertIsNone(parsed["due_date"])

    def test_parse_new_format_with_due_date(self):
        text = (
            "создай задачу\n"
            "название: демо\n"
            "описание: встреча с клиентом\n"
            "срок: 2026-04-25\n"
            "ответственный: Иванов Иван"
        )

        parsed = app.parse_task_text(text)

        self.assertEqual(parsed["title"], "демо")
        self.assertEqual(parsed["description"], "встреча с клиентом")
        self.assertEqual(parsed["due_date"], "2026-04-25T09:00:00")
        self.assertEqual(parsed["assignee"], "Иванов Иван")

    def test_invalid_due_date(self):
        text = (
            "создай задачу\n"
            "название: демо\n"
            "описание: встреча с клиентом\n"
            "срок: завтра"
        )

        parsed = app.parse_task_text(text)

        self.assertEqual(parsed["due_date"], "INVALID_DATE")

    def test_find_user_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"
            users_path.write_text(
                json.dumps(
                    {
                        "иван": {
                            "trello_member_id": "member-1",
                            "telegram_chat_id": 12345
                        }
                    },
                    ensure_ascii=False
                ),
                encoding="utf-8"
            )

            with patch.object(app, "USERS_FILE_PATH", users_path):
                user = app.find_user("ИВАН")

        self.assertEqual(user["trello_member_id"], "member-1")
        self.assertEqual(user["telegram_chat_id"], 12345)

    def test_build_user_store_defaults_to_json_file(self):
        store = user_store.build_user_store(Path("users.json"))

        self.assertIsInstance(store, user_store.JsonFileUserStore)

    def test_build_user_store_uses_google_sheets_when_configured(self):
        store = user_store.build_user_store(
            Path("users.json"),
            spreadsheet_id="sheet-id",
            credentials_json='{"type":"service_account"}',
        )

        self.assertIsInstance(store, user_store.GoogleSheetsUserStore)

    @patch("user_store.GoogleSheetsUserStore._build_service")
    def test_google_sheets_user_store_loads_rows(self, mock_build_service):
        mock_service = mock_build_service.return_value
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [
                ["full_name", "telegram_chat_id", "trello_member_id"],
                ["Иванов Иван", "12345", "member-1"],
            ]
        }

        store = user_store.GoogleSheetsUserStore(
            "sheet-id",
            '{"type":"service_account"}',
        )
        user = store.find_user("Иванов Иван")

        self.assertEqual(user["full_name"], "Иванов Иван")
        self.assertEqual(user["telegram_chat_id"], 12345)
        self.assertEqual(user["trello_member_id"], "member-1")

    @patch("app.send_telegram_message")
    def test_registration_starts_on_command(self, mock_send_telegram_message):
        handled = app.handle_registration_message(101, "регистрация")

        self.assertTrue(handled)
        self.assertIn(101, app.PENDING_REGISTRATIONS)
        mock_send_telegram_message.assert_called_once()

    @patch("app.send_telegram_message")
    def test_registration_requires_full_name(self, mock_send_telegram_message):
        app.PENDING_REGISTRATIONS.add(101)

        handled = app.handle_registration_message(101, "Иванов")

        self.assertTrue(handled)
        self.assertIn(101, app.PENDING_REGISTRATIONS)
        mock_send_telegram_message.assert_called_once()

    @patch("app.send_telegram_message")
    def test_registration_saves_user_to_json_store(self, mock_send_telegram_message):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"

            app.PENDING_REGISTRATIONS.add(101)

            with patch.object(app, "USERS_FILE_PATH", users_path):
                handled = app.handle_registration_message(101, "Иванов Иван")

            self.assertTrue(handled)
            self.assertNotIn(101, app.PENDING_REGISTRATIONS)

            saved_users = json.loads(users_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_users["иванов иван"]["full_name"], "Иванов Иван")
            self.assertEqual(saved_users["иванов иван"]["telegram_chat_id"], 101)
            self.assertEqual(saved_users["иванов иван"]["trello_member_id"], "")
            mock_send_telegram_message.assert_called_once()

    @patch("user_store.GoogleSheetsUserStore._build_service")
    def test_google_sheets_user_store_upserts_user(self, mock_build_service):
        mock_service = mock_build_service.return_value
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [["full_name", "telegram_chat_id", "trello_member_id"]]
        }

        store = user_store.GoogleSheetsUserStore(
            "sheet-id",
            '{"type":"service_account"}',
        )
        saved_user = store.upsert_user("Иванов Иван", 12345)

        self.assertEqual(saved_user["full_name"], "Иванов Иван")
        self.assertEqual(saved_user["telegram_chat_id"], 12345)
        mock_service.spreadsheets.return_value.values.return_value.append.assert_called_once()

    @patch("app.send_telegram_message")
    @patch("app.create_trello_card")
    def test_process_task_request_reports_missing_assignee(self, mock_create_trello_card, mock_send_telegram_message):
        parsed_task = {
            "title": "демо",
            "description": "встреча",
            "due_date": "2026-04-25T09:00:00",
            "assignee": "Иванов Иван",
        }

        with patch("app.find_user", return_value=None):
            app.process_task_request(101, parsed_task)

        mock_create_trello_card.assert_not_called()
        mock_send_telegram_message.assert_called_once()

    @patch("app.send_telegram_message")
    @patch("app.create_trello_card")
    def test_process_task_request_creates_task_and_notifies_assignee(self, mock_create_trello_card, mock_send_telegram_message):
        parsed_task = {
            "title": "демо",
            "description": "встреча",
            "due_date": "2026-04-25T09:00:00",
            "assignee": "Иванов Иван",
        }
        assignee = {
            "full_name": "Иванов Иван",
            "telegram_chat_id": 202,
            "trello_member_id": "member-1",
        }
        mock_create_trello_card.return_value = {
            "ok": True,
            "status_code": 200,
            "body": {"id": "card-1"},
            "error": "",
        }
        mock_send_telegram_message.return_value = {"ok": True, "status_code": 200, "body": {"ok": True}}

        with patch("app.find_user", return_value=assignee), patch(
            "app.sync_trello_assignee_metadata",
            return_value={"ok": True, "skipped": False},
        ):
            app.process_task_request(101, parsed_task)

        mock_create_trello_card.assert_called_once()
        self.assertEqual(mock_send_telegram_message.call_count, 2)

    @patch("app.send_telegram_message")
    @patch("app.create_trello_card")
    def test_process_task_request_reports_failed_assignee_notification(self, mock_create_trello_card, mock_send_telegram_message):
        parsed_task = {
            "title": "демо",
            "description": "встреча",
            "due_date": "2026-04-25T09:00:00",
            "assignee": "Иванов Иван",
        }
        assignee = {
            "full_name": "Иванов Иван",
            "telegram_chat_id": 202,
            "trello_member_id": "member-1",
        }
        mock_create_trello_card.return_value = {
            "ok": True,
            "status_code": 200,
            "body": {"id": "card-1"},
            "error": "",
        }
        mock_send_telegram_message.side_effect = [
            {"ok": True, "status_code": 200, "body": {"ok": True}},
            {"ok": False, "status_code": 403, "body": {"ok": False}},
            {"ok": True, "status_code": 200, "body": {"ok": True}},
        ]

        with patch("app.find_user", return_value=assignee), patch(
            "app.sync_trello_assignee_metadata",
            return_value={"ok": True, "skipped": False},
        ):
            app.process_task_request(101, parsed_task)

        self.assertEqual(mock_send_telegram_message.call_count, 3)

    @patch("trello_client.requests.post")
    def test_create_trello_card_with_member(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"id": "card-1"}

        result = app.create_trello_card(
            "Задача",
            "Описание",
            "2026-04-25T09:00:00",
            trello_member_id="member-1"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(mock_post.call_args.kwargs["params"]["idMembers"], ["member-1"])

    @patch("app.send_telegram_message")
    @patch("app.create_trello_card")
    def test_process_task_request_reports_failed_trello_metadata_sync(self, mock_create_trello_card, mock_send_telegram_message):
        parsed_task = {
            "title": "демо",
            "description": "встреча",
            "due_date": "2026-04-25T09:00:00",
            "assignee": "Иванов Иван",
        }
        assignee = {
            "full_name": "Иванов Иван",
            "telegram_chat_id": 202,
            "trello_member_id": "",
        }
        mock_create_trello_card.return_value = {
            "ok": True,
            "status_code": 200,
            "body": {"id": "card-1"},
            "error": "",
        }
        mock_send_telegram_message.return_value = {"ok": True, "status_code": 200, "body": {"ok": True}}

        with patch("app.find_user", return_value=assignee), patch(
            "app.sync_trello_assignee_metadata",
            return_value={"ok": False, "skipped": False, "error": "boom"},
        ):
            app.process_task_request(101, parsed_task)

        self.assertEqual(mock_send_telegram_message.call_count, 3)

    @patch("trello_client.requests.put")
    def test_set_trello_card_text_custom_field(self, mock_put):
        mock_put.return_value.status_code = 200
        mock_put.return_value.json.return_value = {"idCustomField": "field-1"}

        result = app.set_trello_card_text_custom_field("card-1", "field-1", "Иванов Иван")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(
            mock_put.call_args.kwargs["json"]["value"]["text"],
            "Иванов Иван",
        )

    @patch("app.send_telegram_message")
    def test_registration_reports_storage_failure(self, mock_send_telegram_message):
        app.PENDING_REGISTRATIONS.add(101)

        with patch("app.register_user", side_effect=RuntimeError("boom")):
            handled = app.handle_registration_message(101, "Иванов Иван")

        self.assertTrue(handled)
        self.assertIn(101, app.PENDING_REGISTRATIONS)
        self.assertEqual(mock_send_telegram_message.call_count, 1)

    @patch("app.send_telegram_message")
    @patch("app.create_trello_card")
    def test_process_task_request_reports_user_store_failure(self, mock_create_trello_card, mock_send_telegram_message):
        parsed_task = {
            "title": "демо",
            "description": "встреча",
            "due_date": "2026-04-25T09:00:00",
            "assignee": "Иванов Иван",
        }

        with patch("app.find_user", side_effect=RuntimeError("boom")):
            app.process_task_request(101, parsed_task)

        mock_create_trello_card.assert_not_called()
        mock_send_telegram_message.assert_called_once()

    @patch("telegram_client.requests.post")
    def test_send_telegram_message_reports_api_error(self, mock_post):
        mock_post.return_value.status_code = 403
        mock_post.return_value.json.return_value = {"ok": False, "description": "bot was blocked by the user"}
        mock_post.return_value.text = '{"ok": false}'

        result = telegram_client.send_telegram_message("https://api.telegram.org/bot123", 101, "hi")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 403)

    @patch(
        "telegram_client.requests.post",
        side_effect=telegram_client.requests.RequestException("boom"),
    )
    def test_send_telegram_message_reports_transport_error(self, mock_post):
        result = telegram_client.send_telegram_message("https://api.telegram.org/bot123", 101, "hi")

        self.assertFalse(result["ok"])
        self.assertIsNone(result["status_code"])

    def test_webhook_ignores_updates_without_message(self):
        response = self.client.post("/webhook", json={"update_id": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    @patch("app.send_telegram_message")
    def test_webhook_registration_flow_persists_user(self, mock_send_telegram_message):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"

            with patch.object(app, "USERS_FILE_PATH", users_path):
                first_response = self.client.post(
                    "/webhook",
                    json={
                        "update_id": 1001,
                        "message": {
                            "chat": {"id": 101},
                            "text": "регистрация",
                        },
                    },
                )
                second_response = self.client.post(
                    "/webhook",
                    json={
                        "update_id": 1002,
                        "message": {
                            "chat": {"id": 101},
                            "text": "Иванов Иван",
                        },
                    },
                )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        saved_users = json.loads(users_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_users["иванов иван"]["telegram_chat_id"], 101)
        self.assertEqual(mock_send_telegram_message.call_count, 2)

    @patch("app.send_telegram_message")
    @patch("app.create_trello_card")
    @patch("app.find_user")
    def test_webhook_task_creation_flow_notifies_manager_and_assignee(
        self,
        mock_find_user,
        mock_create_trello_card,
        mock_send_telegram_message,
    ):
        mock_find_user.return_value = {
            "full_name": "Иванов Иван",
            "telegram_chat_id": 202,
            "trello_member_id": "member-1",
        }
        mock_create_trello_card.return_value = {
            "ok": True,
            "status_code": 200,
            "body": {"id": "card-1"},
            "error": "",
        }
        mock_send_telegram_message.return_value = {
            "ok": True,
            "status_code": 200,
            "body": {"ok": True},
            "error": "",
        }

        with patch(
            "app.sync_trello_assignee_metadata",
            return_value={"ok": True, "skipped": False},
        ):
            response = self.client.post(
                "/webhook",
                json={
                    "update_id": 2001,
                    "message": {
                        "chat": {"id": 101},
                        "text": (
                            "создай задачу\n"
                            "название: тест\n"
                            "описание: проверка\n"
                            "срок: 2026-04-25\n"
                            "ответственный: Иванов Иван"
                        ),
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        mock_find_user.assert_called_once_with("Иванов Иван")
        mock_create_trello_card.assert_called_once()
        self.assertEqual(mock_send_telegram_message.call_count, 2)

    @patch("app.process_task_request")
    @patch("app.parse_task_text_with_ai")
    def test_handle_ai_task_request_creates_task(self, mock_parse_task_text_with_ai, mock_process_task_request):
        mock_parse_task_text_with_ai.return_value = {
            "ok": True,
            "draft": {
                "is_task_request": True,
                "title": "Подготовить демо",
                "description": "Подготовить демо для клиента",
                "due_date": "2026-04-30",
                "assignee": "Иванов Иван",
                "missing_fields": [],
                "needs_clarification": False,
                "clarification_question": "",
                "quality_warnings": [],
            },
            "error": "",
        }

        with patch.object(app, "OPENAI_API_KEY", "test-key"), patch.object(app, "OPENAI_MODEL", "gpt-4.1-mini"):
            handled = app.handle_ai_task_request(101, "Поставь Иванову задачу подготовить демо к 30 апреля")

        self.assertTrue(handled)
        mock_process_task_request.assert_called_once()

    @patch("app.send_telegram_message")
    @patch("app.parse_task_text_with_ai")
    def test_handle_ai_task_request_asks_for_clarification(self, mock_parse_task_text_with_ai, mock_send_telegram_message):
        mock_parse_task_text_with_ai.return_value = {
            "ok": True,
            "draft": {
                "is_task_request": True,
                "title": "Подготовить демо",
                "description": "Подготовить демо",
                "due_date": "",
                "assignee": "Иванов Иван",
                "missing_fields": ["due_date"],
                "needs_clarification": True,
                "clarification_question": "Не вижу срок задачи. Напиши дедлайн, пожалуйста.",
                "quality_warnings": [],
            },
            "error": "",
        }

        with patch.object(app, "OPENAI_API_KEY", "test-key"), patch.object(app, "OPENAI_MODEL", "gpt-4.1-mini"):
            handled = app.handle_ai_task_request(101, "Поставь Иванову задачу подготовить демо")

        self.assertTrue(handled)
        self.assertIn(101, app.PENDING_AI_DRAFTS)
        mock_send_telegram_message.assert_called_once()

    @patch("app.send_telegram_message")
    @patch("app.process_task_request")
    @patch("app.continue_task_text_with_ai")
    def test_handle_ai_clarification_completes_draft(self, mock_continue_task_text_with_ai, mock_process_task_request, mock_send_telegram_message):
        app.PENDING_AI_DRAFTS[101] = {
            "is_task_request": True,
            "title": "Подготовить демо",
            "description": "Подготовить демо",
            "due_date": "",
            "assignee": "Иванов Иван",
            "missing_fields": ["due_date"],
            "needs_clarification": True,
            "clarification_question": "Не вижу срок задачи. Напиши дедлайн, пожалуйста.",
            "quality_warnings": [],
        }
        mock_continue_task_text_with_ai.return_value = {
            "ok": True,
            "draft": {
                "is_task_request": True,
                "title": "Подготовить демо",
                "description": "Подготовить демо",
                "due_date": "2026-04-30",
                "assignee": "Иванов Иван",
                "missing_fields": [],
                "needs_clarification": False,
                "clarification_question": "",
                "quality_warnings": [],
            },
            "error": "",
        }

        handled = app.handle_ai_clarification(101, "Срок 30 апреля")

        self.assertTrue(handled)
        self.assertNotIn(101, app.PENDING_AI_DRAFTS)
        mock_process_task_request.assert_called_once()

    def test_prepare_ai_task_payload_resolves_partial_assignee(self):
        draft = {
            "title": "Подготовить демо для Почты",
            "description": "",
            "due_date": "2026-05-01",
            "assignee": "Иванову",
        }

        with patch("app.find_user", return_value=None), patch(
            "app.load_all_users",
            return_value={
                "иванов иван": {
                    "full_name": "Иванов Иван",
                    "telegram_chat_id": 101,
                    "trello_member_id": "",
                }
            },
        ):
            prepared = app.prepare_ai_task_payload(draft)

        self.assertTrue(prepared["ok"])
        self.assertEqual(prepared["parsed_task"]["assignee"], "Иванов Иван")
        self.assertEqual(prepared["parsed_task"]["description"], "Подготовить демо для Почты")

    def test_prepare_ai_task_payload_requires_due_date(self):
        draft = {
            "title": "Подготовить демо для Почты",
            "description": "",
            "due_date": "",
            "assignee": "Иванов Иван",
        }

        prepared = app.prepare_ai_task_payload(draft)

        self.assertFalse(prepared["ok"])
        self.assertIn("срок", prepared["message"].lower())
        mock_send_telegram_message.assert_not_called()

    def test_extract_card_text_custom_field(self):
        card = {
            "customFieldItems": [
                {
                    "idCustomField": "field-1",
                    "value": {"text": "Иванов Иван"},
                }
            ]
        }

        value = app.extract_card_text_custom_field(card, "field-1")

        self.assertEqual(value, "Иванов Иван")

    def test_is_due_today(self):
        now_msk = app.datetime(2026, 4, 27, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        card = {"due": "2026-04-27T09:00:00+03:00"}

        self.assertTrue(app.is_due_today(card, now_msk))

    def test_is_due_this_week(self):
        now_msk = app.datetime(2026, 4, 27, 9, 30, tzinfo=ZoneInfo("Europe/Moscow"))
        card = {"due": "2026-04-29T09:00:00+03:00"}

        self.assertTrue(app.is_due_this_week(card, now_msk))

    @patch("app.add_trello_card_comment")
    @patch("app.send_telegram_message")
    @patch("app.get_trello_open_cards")
    def test_send_due_reminders(self, mock_get_cards, mock_send_telegram_message, mock_add_trello_card_comment):
        mock_get_cards.return_value = {
            "ok": True,
            "body": [
                {
                    "id": "card-1",
                    "name": "Тест today",
                    "due": "2026-04-27T09:00:00+03:00",
                    "customFieldItems": [
                        {
                            "idCustomField": app.TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID,
                            "value": {"text": "202"},
                        }
                    ],
                }
            ],
            "error": "",
        }
        mock_send_telegram_message.return_value = {"ok": True, "status_code": 200, "body": {"ok": True}}
        mock_add_trello_card_comment.return_value = {"ok": True, "status_code": 200, "body": {"id": "comment-1"}}

        with patch.object(app, "TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID", "field-chat-id"):
            mock_get_cards.return_value["body"][0]["customFieldItems"][0]["idCustomField"] = "field-chat-id"
            result = app.send_due_reminders(
                app.datetime(2026, 4, 27, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["sent"], 1)
        mock_send_telegram_message.assert_called_once()
        mock_add_trello_card_comment.assert_called_once()

    @patch("app.add_trello_card_comment")
    @patch("app.send_telegram_message")
    @patch("app.get_trello_open_cards")
    def test_send_weekly_reminders(self, mock_get_cards, mock_send_telegram_message, mock_add_trello_card_comment):
        mock_get_cards.return_value = {
            "ok": True,
            "body": [
                {
                    "id": "card-1",
                    "name": "Тест week",
                    "due": "2026-04-29T09:00:00+03:00",
                    "customFieldItems": [
                        {
                            "idCustomField": app.TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID,
                            "value": {"text": "202"},
                        }
                    ],
                }
            ],
            "error": "",
        }
        mock_send_telegram_message.return_value = {"ok": True, "status_code": 200, "body": {"ok": True}}
        mock_add_trello_card_comment.return_value = {"ok": True, "status_code": 200, "body": {"id": "comment-1"}}

        with patch.object(app, "TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID", "field-chat-id"):
            mock_get_cards.return_value["body"][0]["customFieldItems"][0]["idCustomField"] = "field-chat-id"
            result = app.send_weekly_reminders(
                app.datetime(2026, 4, 27, 9, 30, tzinfo=ZoneInfo("Europe/Moscow"))
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["sent"], 1)
        mock_send_telegram_message.assert_called_once()
        mock_add_trello_card_comment.assert_called_once()
