# InfiniteKidsCanvas Monorepo

Prototype workspace for the InfiniteKidsCanvas experience. The repository is organised as a multi-service monorepo to align with the system architecture described in `AGENTS.md`.

## Services

- `backend/`: FastAPI game service responsible for rooms, turns, and integrations.
- `realtime/`: TypeScript WebSocket gateway that synchronises strokes and events between clients.
- `ai_agent/`: Mock AI patch generator that produces storybook-style continuations for committed objects.
- `content_safety/`: Rule-based moderation utilities for prompts and AI outputs.
- `frontend/`: Placeholder for the future canvas client.
- `docs/`: Documentation stubs and technical specs.

## Current Progress Snapshot

- **Backend** – Implements an application factory with health routes and a `POST /api/rooms/{roomId}/objects` flow that stitches
  together the in-memory database, bbox/anchor ring calculations, audit logging, and turn creation queued through the Redis
  wrapper. Unit tests cover the happy path, validation failures, and audit emission inside `backend/app/tests/`.
- **Realtime Gateway** – Provides a WebSocket server scaffold that manages rooms and relays `stroke`, `object`, and `turn`
  events between participants, but still lacks schema validation, auth, and replay/ordering rules.
- **AI Agent** – Exposes `/generate` and returns a static fairytale-style patch payload via `PatchGenerationPipeline`, acting as a
  placeholder for the future generative model and cache integration.
- **Content Safety** – Ships a keyword-driven moderation engine (text + label checks) with configuration via `banned_keywords`
  and pytest coverage under `content_safety/app/tests/`.
- **Frontend / Docs** – Currently contain placeholder README files; canvas UI, workflows, and architectural documentation are yet
  to be implemented.

## Recommended Next Steps

1. **Persist core gameplay data** – Replace the in-memory database with PostgreSQL entities and Redis-backed event queues,
   expand CRUD for rooms/turns/strokes, and connect audit logs to durable storage.
2. **Bridge backend ↔ realtime ↔ AI** – Define event schemas, add authentication/authorisation, and build the orchestration that
   forwards committed objects to the AI agent, evaluates safety results, and broadcasts turn outcomes.
3. **Upgrade safety coverage** – Extend moderation with image-classification hooks, configurable policy responses, and
   escalation flows for moderators/parents.
4. **Prototype the canvas client** – Implement the infinite canvas experience, object grouping, timeline scrubbing, and integrate
   REST + WebSocket pathways.
5. **Build automation** – Establish CI with formatting/linting gates and increase integration-test coverage (REST, WS, AI, safety)
   to reach the 80% coverage target described in `AGENTS.md`.

## Tooling

- Python projects use **black** and **ruff** for formatting and linting. Activate a virtual environment and install `.[dev]` to get tooling.
- TypeScript projects use **eslint** and **prettier** with strict TypeScript configuration.

## Getting Started

Refer to each service's README for setup instructions. Backend, AI Agent, and Content Safety services expose FastAPI apps ready for expansion. The realtime gateway can be started with `npm run dev` after installing dependencies.
