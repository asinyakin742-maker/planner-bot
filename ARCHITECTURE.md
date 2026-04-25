# Planner Bot Architecture

## Goal

The service should support this durable business flow:

1. Manager sends a task to the Telegram bot.
2. The bot parses task fields: title, description, due date, assignee.
3. The service looks up the assignee in a persistent user directory.
4. The service creates a Trello card.
5. The service notifies the assignee in Telegram.
6. The workflow remains stable across deploys and restarts.

## System Boundaries

- `app.py`
  FastAPI entrypoint and webhook orchestration only.
- `parser.py`
  Parses Telegram text into structured task data.
- `user_store.py`
  User directory backend abstraction and implementations.
- `telegram_client.py`
  Sends Telegram messages and validates delivery result.
- `trello_client.py`
  Creates Trello cards and returns API result.

## Current Architecture Decision

The service is being refactored in phases:

1. Separate orchestration from integrations and parsing.
2. Replace local user storage with a persistent backend.
3. Reintroduce registration flow on top of the new storage layer.
4. Add workflow-level tests for the full assignment scenario.

## Main Risks To Address

- Local file storage is not durable in production.
- Telegram delivery failures must be surfaced, not silently ignored.
- New features should not be added directly into the webhook handler.
- The key business scenario must be protected by end-to-end tests.

## Near-Term Plan

1. Keep current task creation behavior stable.
2. Move business logic into dedicated modules.
3. Introduce a storage adapter interface.
4. Implement Google Sheets as the source of truth for users.
5. Add registration and assignment tests before adding more features.

## Current Production State

- Telegram webhook is active on Render.
- User directory is stored in Google Sheets when the related env vars are configured.
- Registration flow is active:
  - user sends `регистрация`
  - bot asks for full name
  - bot stores `full_name` and `telegram_chat_id`
- Assignment flow is active:
  - manager sends a task with `ответственный:`
  - service looks up the employee
  - service creates a Trello card
  - service sends a Telegram notification to the assignee
- Reminder flow is now designed around Trello as the task registry:
  - active tasks live in list `Open`
  - assignee Telegram metadata is stored in Trello custom fields
  - reminder jobs read cards from `Open`
  - after sending a reminder, the service writes a comment to the card

## Operational Rules

- Render secrets are the source of truth for API credentials.
- Google Sheets is the source of truth for employees.
- `users.json` remains only a local fallback for development.
- Production changes should be shipped phase by phase, with smoke tests after each deploy.
