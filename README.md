# planner-bot

Telegram planner bot on FastAPI with Trello integration.

## What this repository now includes

- app code in `app.py`
- modular bot architecture (`parser.py`, `telegram_client.py`, `trello_client.py`, `user_store.py`)
- basic regression tests in `tests/`
- GitHub Actions CI in `.github/workflows/ci.yml`
- local workflow guide in `WORKFLOW.md`
- sample local user directory in `users.example.json`

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Set environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `TRELLO_API_KEY`
   - `TRELLO_TOKEN`
   - `TRELLO_LIST_ID`
   - `TRELLO_OPEN_LIST_ID`
   - `TRELLO_ASSIGNEE_FULL_NAME_FIELD_ID`
   - `TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID`
   - optional local fallback: `USERS_FILE_PATH`
   - for Google Sheets production storage:
   - `GOOGLE_SHEETS_SPREADSHEET_ID`
   - `GOOGLE_SHEETS_CREDENTIALS_JSON`
   - `GOOGLE_SHEETS_RANGE`
   - for AI parsing:
     - `OPENAI_API_KEY`
     - `OPENAI_MODEL`
4. Run locally:
   `uvicorn app:app --reload`
5. Run tests:
   `python -m unittest discover -s tests -v`

## Supported Bot Flows

- Registration:
  - user sends `регистрация`
  - bot asks for full name
  - bot stores `full_name` and `telegram_chat_id`
- Task creation:
  - old format: `создай задачу демо`
  - structured format:
    - `создай задачу`
    - `название: ...`
    - `описание: ...`
    - `срок: ...`
    - `ответственный: ...`
  - free-text AI format:
    - `Поставь Иванову задачу подготовить демо к пятнице`
    - `Нужно, чтобы Ирина до 30 апреля отправила клиенту КП`
- Manual reminder jobs:
  - `POST /jobs/reminders/due`
  - `POST /jobs/reminders/weekly`

## Delivery flow

1. Work in a branch.
2. Run tests.
3. Push to GitHub.
4. Wait for CI to pass.
5. Merge to `main`.
6. Render deploys from `main`.
