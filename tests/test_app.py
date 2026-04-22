import unittest

import app


class PlannerBotTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
