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

## Daily commands

- Start locally:
  `uvicorn app:app --reload`
- Run tests:
  `python -m unittest discover -s tests -v`

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
- Keep `users.json` local only.
- Use this repository structure as the starting point for future services.
