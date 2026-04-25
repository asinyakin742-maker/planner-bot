# Workflow

## Goal

This repository is the template for a simple service workflow:

1. make a small change in a branch
2. run local checks
3. push to GitHub
4. let GitHub Actions run regression checks
5. merge to `main`
6. let Render deploy from `main`

## Local setup

1. Create a virtual environment:
   `python -m venv .venv`
2. Activate it in PowerShell:
   `.venv\Scripts\Activate.ps1`
3. Install dependencies:
   `pip install -r requirements.txt`
4. Copy `users.example.json` to `users.json`
5. Add the required environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `TRELLO_API_KEY`
   - `TRELLO_TOKEN`
   - `TRELLO_LIST_ID`
   - `TRELLO_OPEN_LIST_ID`
   - `TRELLO_ASSIGNEE_FULL_NAME_FIELD_ID`
   - `TRELLO_ASSIGNEE_CHAT_ID_FIELD_ID`
   - if using Google Sheets:
     - `GOOGLE_SHEETS_SPREADSHEET_ID`
     - `GOOGLE_SHEETS_CREDENTIALS_JSON`
     - `GOOGLE_SHEETS_RANGE`

## Daily commands

- Start locally:
  `uvicorn app:app --reload`
- Run tests:
  `python -m unittest discover -s tests -v`
- Run due reminders manually:
  `POST /jobs/reminders/due`
- Run weekly reminders manually:
  `POST /jobs/reminders/weekly`

## Smoke Test After Deploy

1. Check `/health`
2. Verify registration flow:
   - send `регистрация`
   - send `Фамилия Имя`
3. Verify task creation with a missing assignee
4. Verify task creation with a registered assignee
5. Confirm:
   - Google Sheets row exists
   - Trello card exists
   - Telegram notification arrives
6. If reminder flow changed:
   - call `/jobs/reminders/due` or `/jobs/reminders/weekly`
   - confirm Telegram reminder arrives
   - confirm a Trello comment is added to the card

## Release flow

1. Create a working branch.
2. Make a small safe change.
3. Run tests locally.
4. Commit and push.
5. Wait for GitHub Actions to pass.
6. Merge into `main`.
7. Render auto-deploys the new version from `main`.

## Notes

- Do not store secrets in the repository.
- Use Google Sheets as the production employee directory.
- Keep `users.json` local only as a fallback for development.
- Use this repository structure as the starting point for future services.
