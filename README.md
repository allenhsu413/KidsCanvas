# InfiniteKidsCanvas Monorepo

Prototype workspace for the InfiniteKidsCanvas experience. The repository is organised as a multi-service monorepo to align with the system architecture described in `AGENTS.md`.

## Services

- `backend/`: FastAPI game service responsible for rooms, turns, and integrations.
- `realtime/`: TypeScript WebSocket gateway that synchronises strokes and events between clients.
- `ai_agent/`: Mock AI patch generator that produces storybook-style continuations for committed objects.
- `content_safety/`: Rule-based moderation utilities for prompts and AI outputs.
- `frontend/`: Placeholder for the future canvas client.
- `docs/`: Documentation stubs and technical specs.

## Tooling

- Python projects use **black** and **ruff** for formatting and linting. Activate a virtual environment and install `.[dev]` to get tooling.
- TypeScript projects use **eslint** and **prettier** with strict TypeScript configuration.

## Getting Started

Refer to each service's README for setup instructions. Backend, AI Agent, and Content Safety services expose FastAPI apps ready for expansion. The realtime gateway can be started with `npm run dev` after installing dependencies.
