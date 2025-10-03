# InfiniteKidsCanvas Backend

FastAPI service that manages rooms, turns, and integrations with the AI agent and safety services.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Testing

```bash
pytest -q
```
