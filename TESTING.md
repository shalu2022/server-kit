# How to test the server kit

Two layers. Test the kit, then test the server it downloads.

## 1. Start the kit

From the `server-kit` folder:

```bash
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Leave that window open. The form is http://127.0.0.1:8000

## 2. Read each API

Open http://127.0.0.1:8000/docs

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | Liveness. Returns `{"status":"ok"}`. Does not build a zip. |
| GET | `/` | The form. Same fields as the generate body. |
| POST | `/generate` | Builds the zip. Body is the server name and the tool list. |

`GET /docs` and `GET /openapi.json` are the catalog of those three routes.

## 3. Happy path in the browser

1. Open http://127.0.0.1:8000
2. Leave the filled-in server `field-notes` and the two tools, `add_note` and `list_notes`.
3. Click **Download zip**.
4. Unzip `field-notes.zip`.
5. In that folder run:

```bash
python -m unittest test_server.py
```

`OK` means the generated process started, listed both tools, and answered `add_note`.

## 4. Happy path from the docs page

On http://127.0.0.1:8000/docs open **POST /generate**, click **Try it out**, and send:

```json
{
  "server_name": "field-notes",
  "tools": [
    {
      "name": "add_note",
      "purpose": "Save a short note",
      "inputs": [{ "name": "text", "type": "string" }]
    },
    {
      "name": "list_notes",
      "purpose": "List the notes",
      "inputs": []
    }
  ]
}
```

A 200 response is the zip file. Download it and run the same unittest as in step 3.

Field meanings:

- `server_name` becomes the folder name and the MCP server name. Lowercase letters, digits, and hyphens.
- `tools[].name` is the name a client calls.
- `tools[].purpose` is the tool description. The stub returns this sentence plus the arguments.
- `tools[].inputs[].name` is one argument.
- `tools[].inputs[].type` is `string`, `number`, or `boolean`.

## 5. Rejection

On **POST /generate**, send a tool with an empty name:

```json
{
  "server_name": "field-notes",
  "tools": [{ "name": "", "purpose": "Save a note", "inputs": [] }]
}
```

Expect **422**. The body names the field that failed. The same status is returned for a duplicate tool name, a server name with spaces, or an input type other than string, number, or boolean.

## 6. The whole suite

Stop is not required. In a second terminal, from `server-kit`:

```bash
.venv\Scripts\activate
pytest
```

Four tests: health, the empty-name rejection, a generated server whose own unittest passes, and a generated server that answers Streamable HTTP.

## Connect MCP Jam or Inspector

In the unzipped folder:

```bash
python server.py
```

Leave that window open. Paste the printed `http://127.0.0.1:8080/mcp` URL into the local MCP Jam app (`npx @mcpjam/inspector@latest`) or MCP Inspector (`npx @modelcontextprotocol/inspector`) as Streamable HTTP.

https://app.mcpjam.com cannot reach a server that is only on this computer. Use the local inspector for that URL.

`python -m unittest test_server.py` still checks the same tools without a UI.
