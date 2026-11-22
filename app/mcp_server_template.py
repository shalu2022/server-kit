TEMPLATE = r'''import json
import queue
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SERVER_NAME = __SERVER_NAME_JSON__
TOOLS = __TOOLS_JSON__

__HANDLERS__
HANDLERS = {__HANDLER_MAP__}

SESSIONS = {}
SESSIONS_LOCK = threading.Lock()


def respond(message):
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        params = message.get("params") or {}
        version = params.get("protocolVersion") or "2025-03-26"
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "unknown tool"},
            }
        try:
            text = handler(arguments)
            is_error = False
        except ValueError as exc:
            text = str(exc)
            is_error = True
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "method not found"},
    }


def read_message():
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError
        line = line.strip()
        if not line:
            continue
        return json.loads(line)


def write_message(payload):
    sys.stdout.buffer.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
    sys.stdout.buffer.flush()


def run_stdio():
    while True:
        try:
            message = read_message()
        except EOFError:
            return
        response = respond(message)
        if response is not None:
            write_message(response)


def _option(args, name, default):
    if name not in args:
        return default
    index = args.index(name)
    if index + 1 >= len(args):
        raise SystemExit(f"missing value for {name}")
    return args[index + 1]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _cors(self):
        origin = self.headers.get("Origin")
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID",
        )
        self.send_header("Access-Control-Allow-Methods", "POST, GET, DELETE, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _empty(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Max-Age", "86400")
        self._cors()
        self.end_headers()

    def do_DELETE(self):
        self._empty(200)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", ""):
            host, port = self.server.server_address[:2]
            shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
            text = (
                f"{SERVER_NAME} is running.\n"
                f"Streamable HTTP: http://{shown}:{port}/mcp\n"
                f"SSE: http://{shown}:{port}/sse\n"
            )
            body = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/sse":
            self._sse()
            return
        if path == "/mcp":
            self.send_response(405)
            self.send_header("Allow", "POST, DELETE, OPTIONS")
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()
            return
        self._empty(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/messages":
            self._post_message(parsed)
            return
        if parsed.path == "/mcp":
            self._post_mcp()
            return
        self._empty(404)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        return json.loads(raw)

    def _post_mcp(self):
        try:
            incoming = self._read_json()
        except json.JSONDecodeError:
            self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            return
        if incoming is None:
            self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "empty body"}})
            return
        if isinstance(incoming, list):
            replies = [item for item in (respond(message) for message in incoming) if item is not None]
            if not replies:
                self._empty(202)
                return
            self._send_reply(replies)
            return
        reply = respond(incoming)
        if reply is None:
            self._empty(202)
            return
        self._send_reply(reply)

    def _send_reply(self, payload):
        accept = self.headers.get("Accept", "")
        if "text/event-stream" in accept and "application/json" not in accept:
            data = json.dumps(payload)
            body = f"event: message\ndata: {data}\n\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(200, payload)

    def _post_message(self, parsed):
        session_id = parse_qs(parsed.query).get("sessionId", [None])[0]
        with SESSIONS_LOCK:
            mailbox = SESSIONS.get(session_id)
        if mailbox is None:
            self._json(404, {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "unknown session"}})
            return
        try:
            incoming = self._read_json()
        except json.JSONDecodeError:
            self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            return
        messages = incoming if isinstance(incoming, list) else [incoming]
        for message in messages:
            if not isinstance(message, dict):
                continue
            reply = respond(message)
            if reply is not None:
                mailbox.put(reply)
        self._empty(202)

    def _sse(self):
        session_id = uuid.uuid4().hex
        mailbox = queue.Queue()
        with SESSIONS_LOCK:
            SESSIONS[session_id] = mailbox
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        host = self.headers.get("Host")
        if not host:
            bound_host, port = self.server.server_address[:2]
            shown = "127.0.0.1" if bound_host in ("0.0.0.0", "") else bound_host
            host = f"{shown}:{port}"
        endpoint = f"http://{host}/messages?sessionId={session_id}"
        try:
            self.wfile.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    payload = mailbox.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                data = json.dumps(payload)
                self.wfile.write(f"event: message\ndata: {data}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            return
        finally:
            with SESSIONS_LOCK:
                SESSIONS.pop(session_id, None)


def run_http(args):
    host = _option(args, "--host", "127.0.0.1")
    port = int(_option(args, "--port", "8080"))
    last_error = None
    bound = None
    for candidate in range(port, port + 10):
        try:
            bound = ThreadingHTTPServer((host, candidate), Handler)
            port = candidate
            break
        except OSError as exc:
            last_error = exc
    if bound is None:
        raise SystemExit(f"could not listen on {host}:{port} ({last_error})")
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print(f"{SERVER_NAME} is listening", flush=True)
    print(f"  Streamable HTTP  http://{shown}:{port}/mcp", flush=True)
    print(f"  SSE              http://{shown}:{port}/sse", flush=True)
    print("Leave this window open. Paste the Streamable HTTP URL into MCP Jam or MCP Inspector.", flush=True)
    print("Ctrl+C stops the server.", flush=True)
    try:
        bound.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
    finally:
        bound.server_close()


def main():
    args = sys.argv[1:]
    if "--stdio" in args:
        run_stdio()
        return
    if "--http" in args or sys.stdin.isatty():
        run_http(args)
        return
    run_stdio()


if __name__ == "__main__":
    main()
'''
