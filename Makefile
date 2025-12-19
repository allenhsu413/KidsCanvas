.PHONY: dev dev-backend dev-ai dev-realtime dev-frontend

dev:
	./scripts/dev.sh

dev-backend:
	cd backend && python -m uvicorn app.main:app --reload --port 8000

dev-ai:
	cd ai_agent && python -m uvicorn app.main:app --reload --port 8100

dev-realtime:
	cd realtime && npm run dev

dev-frontend:
	cd frontend && npm run dev -- --host
