import io
import json
import zipfile

from app.mcp_server_template import TEMPLATE
from app.spec import SpecIn


def build_zip(spec: SpecIn) -> tuple[bytes, str]:
    folder = spec.server_name
    files = {
        "server.py": _server_py(spec),
        "test_server.py": _test_py(spec),
        "Dockerfile": _dockerfile(spec),
        "README.md": _readme(spec),
        "requirements.txt": "# Python standard library only.\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(f"{folder}/{name}", text)
    filename = f"{folder}.zip"
    return buffer.getvalue(), filename


def _server_py(spec: SpecIn) -> str:
    tools = []
    handlers = []
    for tool in spec.tools:
        properties = {item.name: {"type": item.type} for item in tool.inputs}
        required = [item.name for item in tool.inputs]
        tools.append(
            {
                "name": tool.name,
                "description": tool.purpose,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )
        required_literal = json.dumps(required)
        handlers.append(
            f"def _handle_{tool.name}(arguments):\n"
            f"    missing = [key for key in {required_literal} if key not in arguments]\n"
            f"    if missing:\n"
            f"        raise ValueError('missing ' + ', '.join(missing))\n"
            f"    # Replace this body with the real tool.\n"
            f"    return {json.dumps(tool.purpose)} + ' ' + json.dumps(arguments, sort_keys=True)\n"
        )
    handler_map = ", ".join(f"{json.dumps(tool.name)}: _handle_{tool.name}" for tool in spec.tools)
    return (
        TEMPLATE.replace("__SERVER_NAME_JSON__", json.dumps(spec.server_name))
        .replace("__TOOLS_JSON__", json.dumps(tools, indent=4))
        .replace("__HANDLERS__", "\n".join(handlers))
        .replace("__HANDLER_MAP__", handler_map)
    )


def _test_py(spec: SpecIn) -> str:
    first = spec.tools[0]
    arguments = {}
    for item in first.inputs:
        if item.type == "string":
            arguments[item.name] = "demo"
        elif item.type == "number":
            arguments[item.name] = 1
        else:
            arguments[item.name] = True
    names = [tool.name for tool in spec.tools]
    return f'''import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parent
EXPECTED = {json.dumps(names)}
CALL_NAME = {json.dumps(first.name)}
CALL_ARGS = {json.dumps(arguments)}
PURPOSE = {json.dumps(first.purpose)}


class Client:
    def __init__(self, process):
        self.process = process
        self.next_id = 1

    def request(self, method, params=None):
        message = {{"jsonrpc": "2.0", "id": self.next_id, "method": method}}
        self.next_id += 1
        if params is not None:
            message["params"] = params
        self.process.stdin.write(json.dumps(message).encode() + b"\\n")
        self.process.stdin.flush()
        return self.read()

    def read(self):
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout")
        return json.loads(line)


class ServerTest(unittest.TestCase):
    def test_lists_tools_and_answers_a_call(self):
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py"), "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        client = Client(process)
        try:
            started = client.request(
                "initialize",
                {{
                    "protocolVersion": "2024-11-05",
                    "capabilities": {{}},
                    "clientInfo": {{"name": "smoke", "version": "0"}},
                }},
            )
            self.assertEqual(started["result"]["serverInfo"]["name"], {json.dumps(spec.server_name)})
            listed = client.request("tools/list")
            listed_names = [tool["name"] for tool in listed["result"]["tools"]]
            self.assertEqual(listed_names, EXPECTED)
            called = client.request(
                "tools/call",
                {{"name": CALL_NAME, "arguments": CALL_ARGS}},
            )
            text = called["result"]["content"][0]["text"]
            self.assertIn(PURPOSE, text)
            self.assertFalse(called["result"]["isError"])
        finally:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
'''


def _dockerfile(spec: SpecIn) -> str:
    return f"""FROM python:3.12-slim
WORKDIR /app
COPY server.py .
EXPOSE 8080
CMD ["python", "server.py", "--http", "--host", "0.0.0.0", "--port", "8080"]
"""


def _readme(spec: SpecIn) -> str:
    tool_lines = "\n".join(
        f"- `{tool.name}` — {tool.purpose}" for tool in spec.tools
    )
    return f"""# {spec.server_name}

MCP server generated by server-kit. `python server.py` stays running and listens on this computer so MCP Jam or MCP Inspector can connect.

The tool bodies return the purpose plus the arguments. Replace those bodies with real work.

## Tools

{tool_lines}

## Run for MCP Jam or Inspector

```bash
python server.py
```

Leave that window open. It prints a URL like `http://127.0.0.1:8080/mcp`.

- Local MCP Jam: `npx @mcpjam/inspector@latest`. Transport HTTP, not stdio. Paste that URL.
- MCP Inspector: `npx @modelcontextprotocol/inspector`. Transport Streamable HTTP. Paste that URL.
- Stdio, only if the client asks for a command: `python server.py --stdio`. One JSON message per line. Do not use Content-Length headers.
- https://app.mcpjam.com only reaches public HTTPS servers. It cannot open a localhost URL. Use the local inspector on this computer.

## Check without a UI

```bash
python -m unittest test_server.py
```

`OK` means the server listed its tools and answered a call.

## Docker

```bash
docker build -t {spec.server_name} .
docker run -p 8080:8080 {spec.server_name}
```

The URL from another program on this computer is `http://127.0.0.1:8080/mcp`.
"""
