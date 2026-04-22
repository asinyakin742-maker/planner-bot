# planner-bot

Telegram planner bot on FastAPI with Trello integration.

## What this repository now includes

- app code in `app.py`
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
4. Run locally:
   `uvicorn app:app --reload`
5. Run tests:
   `python -m unittest discover -s tests -v`

## Delivery flow

1. Work in a branch.
2. Run tests.
3. Push to GitHub.
4. Wait for CI to pass.
5. Merge to `main`.
6. Render deploys from `main`.
