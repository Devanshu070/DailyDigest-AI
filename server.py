"""
server.py — Local development entrypoint for the FastAPI server.

Usage:
    uv run python server.py

For production, Render uses:
    uv run uvicorn app.api.app:app --host 0.0.0.0 --port $PORT
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
