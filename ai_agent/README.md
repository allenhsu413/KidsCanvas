# AI Agent Service

Mock implementation of the AI patch generation service used in the InfiniteKidsCanvas prototype.

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
