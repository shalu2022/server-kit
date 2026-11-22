import io
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_rejects_a_tool_with_no_name() -> None:
    response = client.post(
        "/generate",
        json={
            "server_name": "field-notes",
            "tools": [{"name": "", "purpose": "Save a note", "inputs": []}],
        },
    )
    assert response.status_code == 422


def test_zip_contains_a_server_that_passes_its_own_test(tmp_path) -> None:
    response = client.post(
        "/generate",
        json={
            "server_name": "field-notes",
            "tools": [
                {
                    "name": "add_note",
                    "purpose": "Save a short note",
                    "inputs": [{"name": "text", "type": "string"}],
                },
                {"name": "list_notes", "purpose": "List the notes", "inputs": []},
            ],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('filename="field-notes.zip"')
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert names == {
        "field-notes/server.py",
        "field-notes/test_server.py",
        "field-notes/Dockerfile",
        "field-notes/README.md",
        "field-notes/requirements.txt",
    }
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))

    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "test_server.py"],
        cwd=tmp_path / "field-notes",
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_http_mode_answers_initialize_and_lists_tools(tmp_path) -> None:
    response = client.post(
        "/generate",
        json={
            "server_name": "field-notes",
            "tools": [
                {
                    "name": "add_note",
                    "purpose": "Save a short note",
                    "inputs": [{"name": "text", "type": "string"}],
                }
            ],
        },
    )
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    target = tmp_path / "field-notes" / "server.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(archive.read("field-notes/server.py"))
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-u", "server.py", "--http", "--port", str(port)],
        cwd=target.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 10
        seen = ""
        assert process.stdout is not None
        while time.time() < deadline:
            line = process.stdout.readline()
            if not line:
                break
            seen += line
            if "Streamable HTTP" in line:
                break
        else:
            raise AssertionError(seen or "server did not print a URL")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0"},
            },
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as reply:
            body = json.load(reply)
        assert body["result"]["serverInfo"]["name"] == "field-notes"
        assert body["result"]["protocolVersion"] == "2025-03-26"
        listed = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        with urllib.request.urlopen(listed, timeout=5) as reply:
            tools = json.load(reply)
        assert tools["result"]["tools"][0]["name"] == "add_note"
    except urllib.error.URLError as exc:
        raise AssertionError(seen) from exc
    finally:
        process.kill()
        process.wait(timeout=5)
