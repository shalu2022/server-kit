from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from app.generate import build_zip
from app.spec import SpecIn

app = FastAPI(
    title="Server kit",
    description=(
        "Turns a server name and a tool list into a zip. "
        "The zip is an MCP server. python server.py listens on http://127.0.0.1:8080/mcp for MCP Jam or Inspector. "
        "Open /docs for the request and response shapes."
    ),
    version="0.1.0",
)


@app.get(
    "/health",
    summary="Liveness check",
    description="Returns ok when the kit process is running. It does not build a server and it does not touch the network.",
)
def health() -> dict[str, str]:
    """Used by a deploy check. A 200 with status ok means the form and /generate can be called."""
    return {"status": "ok"}


@app.get(
    "/",
    response_class=HTMLResponse,
    summary="Tool form",
    description="HTML form for the same request POST /generate accepts. Two example tools are filled in so the download path can be tried immediately.",
)
def form() -> str:
    """Browser page. Submitting it downloads the zip. It is not an MCP endpoint."""
    return _PAGE


@app.post(
    "/generate",
    summary="Build an MCP server zip",
    description=(
        "Accepts a server name and at least one tool. "
        "Returns a zip with server.py, test_server.py, Dockerfile, README.md, and requirements.txt. "
        "A template writes those files. "
        "Rejects a blank tool name, a duplicate tool name, a bad server name, and an unknown input type with 422."
    ),
    responses={
        200: {"description": "Zip archive. The file name is the server name plus .zip."},
        422: {"description": "The body failed validation. The response lists the field and the reason."},
    },
)
def generate(spec: SpecIn) -> Response:
    """Build the zip for this spec. The generated tool bodies return the purpose plus the arguments."""
    payload, filename = build_zip(spec)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Server kit</title>
  <style>
    :root { --ink: #1a1814; --muted: #5e584e; --line: #ddd4c6; --paper: #fffdf8; --bg: #f3efe6; --teal: #0e5c57; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 "Segoe UI", system-ui, sans-serif; }
    main { width: min(760px, calc(100% - 32px)); margin: 28px auto 48px; }
    h1 { font-family: Georgia, serif; font-weight: 400; font-size: 32px; margin: 0 0 8px; }
    p { color: var(--muted); margin: 0 0 16px; }
    form, .tool { background: var(--paper); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }
    .tool { margin-top: 12px; }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--muted); margin-bottom: 10px; }
    input, select { font: inherit; color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 8px; background: #fff; }
    .row { display: grid; grid-template-columns: 1fr 140px auto; gap: 8px; align-items: end; }
    button { font: inherit; border-radius: 999px; border: 1px solid var(--line); background: #fff; padding: 8px 14px; cursor: pointer; }
    button.primary { background: var(--teal); color: #fff; border-color: var(--teal); }
    .actions { display: flex; gap: 8px; margin-top: 14px; }
    .error { color: #8c3a32; white-space: pre-wrap; }
  </style>
</head>
<body>
  <main>
    <h1>Server kit</h1>
    <p>Enter a server name and the tools it should expose. Download a zip. Unzip it and run <code>python -m unittest test_server.py</code>. API descriptions are at <a href="/docs">/docs</a>.</p>
    <form id="kit">
      <label>Server name
        <input name="server_name" required pattern="[a-z][a-z0-9-]{1,40}" placeholder="field-notes" value="field-notes">
      </label>
      <div id="tools"></div>
      <div class="actions">
        <button type="button" id="add">Add tool</button>
        <button type="submit" class="primary">Download zip</button>
      </div>
      <p class="error" id="error"></p>
    </form>
  </main>
  <script>
    const tools = document.getElementById("tools");
    const error = document.getElementById("error");

    function inputRow() {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `
        <label>Input name <input class="in-name" placeholder="city"></label>
        <label>Type
          <select class="in-type">
            <option>string</option>
            <option>number</option>
            <option>boolean</option>
          </select>
        </label>
        <button type="button" class="drop-input">Remove</button>`;
      row.querySelector(".drop-input").onclick = () => row.remove();
      return row;
    }

    function toolBlock(name, purpose) {
      const block = document.createElement("div");
      block.className = "tool";
      block.innerHTML = `
        <label>Tool name <input class="tool-name" required placeholder="add_note"></label>
        <label>Purpose <input class="tool-purpose" required placeholder="Save a short note"></label>
        <div class="inputs"></div>
        <button type="button" class="add-input">Add input</button>
        <button type="button" class="drop-tool">Remove tool</button>`;
      if (name) block.querySelector(".tool-name").value = name;
      if (purpose) block.querySelector(".tool-purpose").value = purpose;
      block.querySelector(".add-input").onclick = () => block.querySelector(".inputs").appendChild(inputRow());
      block.querySelector(".drop-tool").onclick = () => block.remove();
      return block;
    }

    const first = toolBlock("add_note", "Save a short note");
    first.querySelector(".inputs").appendChild(inputRow());
    first.querySelector(".in-name").value = "text";
    tools.appendChild(first);
    tools.appendChild(toolBlock("list_notes", "List the notes"));

    document.getElementById("add").onclick = () => tools.appendChild(toolBlock("", ""));

    document.getElementById("kit").onsubmit = async (event) => {
      event.preventDefault();
      error.textContent = "";
      const payload = {
        server_name: event.target.server_name.value.trim(),
        tools: [...tools.querySelectorAll(".tool")].map((block) => ({
          name: block.querySelector(".tool-name").value.trim(),
          purpose: block.querySelector(".tool-purpose").value.trim(),
          inputs: [...block.querySelectorAll(".row")].filter((row) => row.querySelector(".in-name").value.trim()).map((row) => ({
            name: row.querySelector(".in-name").value.trim(),
            type: row.querySelector(".in-type").value
          }))
        }))
      };
      const response = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        error.textContent = await response.text();
        return;
      }
      const blob = await response.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = payload.server_name + ".zip";
      link.click();
      URL.revokeObjectURL(link.href);
    };
  </script>
</body>
</html>
"""
