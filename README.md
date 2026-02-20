# Bright Data Testing

## Quickstart

### 1) Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2) Create `.env` from `.env.example`

```bash
cp .env.example .env
```

Set required values in `.env`:

- `BRIGHT_DATA_API_TOKEN`
- `BRIGHT_DATA_PROXY_PASSWORD`
- Either `OPENAI_API_KEY`, or OAuth settings (`OAUTH_URL`, `CLIENT_ID`, `CLIENT_SECRET`, `AZURE_BASE_URL`)

Optional LLM runtime overrides (env-only):

- `AGENT_MODEL`: override model in local/API-key mode
- `AGENT_MODEL_OAUTH`: override model in OAuth/corporate mode
- `AGENT_MAX_TOKENS`: pass `max_tokens` on local/API-key calls
- `AGENT_MAX_TOKENS_OAUTH`: pass `max_tokens` on OAuth/corporate calls

### 3) Run the server

```bash
python -m src serve --host 0.0.0.0 --port 8000
```

Open:

- `http://127.0.0.1:8000`

## Debug Logging

The agent writes structured JSONL logs to:

- `logs/tool_calls.jsonl`

This file includes:

- LLM call records (`type: "llm_call"`) with model, token usage, finish reason, and tool-call count
- Tool execution records (`type: "tool_call"`)
- Loop lifecycle/debug events (`type: "agent_event"`) including why the loop stopped
