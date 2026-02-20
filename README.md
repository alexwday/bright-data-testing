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

### 3) Run the server

```bash
python -m src serve --host 0.0.0.0 --port 8000
```

Open:

- `http://127.0.0.1:8000`

