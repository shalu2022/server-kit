# Server kit

A form that turns a tool list into a downloadable MCP server.

The downloaded zip contains `server.py`, `test_server.py`, a Dockerfile, and a README. `python server.py` listens at `http://127.0.0.1:8080/mcp` so MCP Jam or Inspector on this computer can connect. Tool bodies return the purpose plus the arguments. Replace those bodies when you want real work.

This is the public portfolio app from the placement plan. It is not the Info Origin gateway, and it does not generate a server from a free-text prompt.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Test

The full click-by-click path is `TESTING.md`. Short version:

```bash
pytest
```

With the server running, open http://127.0.0.1:8000/docs for the description of each route.
