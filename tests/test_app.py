import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class PlannerBotTests(unittest.TestCase):
    def setUp(self):
        app.PENDING_REGISTRATIONS.clear()

    def test_health_endpoint_payload(self):
        self.assertEqual(
            app.health(),
            {"status": "ok", "service": "planner-bot"}
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
            "срок: 2026-04-25"
        )

        parsed = app.parse_task_text(text)

        self.assertEqual(parsed["title"], "демо")
        self.assertEqual(parsed["description"], "встреча с клиентом")
        self.assertEqual(parsed["due_date"], "2026-04-25T09:00:00")

    def test_invalid_due_date(self):
        text = (
            "создай задачу\n"
            "название: демо\n"
            "описание: встреча с клиентом\n"
            "срок: завтра"
        )

        parsed = app.parse_task_text(text)

        self.assertEqual(parsed["due_date"], "INVALID_DATE")

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
    def test_registration_saves_user(self, mock_send_telegram_message):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"

            app.PENDING_REGISTRATIONS.add(101)

            with patch.object(app, "USERS_FILE_PATH", users_path):
                handled = app.handle_registration_message(101, "Иванов Иван")

            self.assertTrue(handled)
            self.assertNotIn(101, app.PENDING_REGISTRATIONS)

            saved_users = json.loads(users_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_users["иванов иван"]["telegram_chat_id"], 101)
            self.assertEqual(saved_users["иванов иван"]["full_name"], "Иванов Иван")
            self.assertEqual(saved_users["иванов иван"]["trello_member_id"], "")
            mock_send_telegram_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
