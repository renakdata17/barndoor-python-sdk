# Barndoor SDK

A lightweight, **framework-agnostic** Python client for the Barndoor Platform REST APIs and Model Context Protocol (MCP) servers.

The SDK removes boiler-plate around:

* Secure, offline-friendly **authentication to Barndoor** (interactive PKCE flow + token caching).
* **Server registry** – list, inspect and connect third-party providers (Salesforce, Notion, Slack …).
* **Managed Connector Proxy** – build ready-to-use connection parameters for any LLM/agent framework (CrewAI, LangChain, custom code …) without importing Barndoor-specific adapters.

---

## How it works

The SDK orchestrates a multi-step flow to connect your code to third-party services:

```
You → Barndoor Auth (get JWT) → Registry API (with JWT) → MCP Proxy (with JWT) → Third-party service
```

1. **Authentication**: You log in via Barndoor to get a JWT token
2. **Registry API**: Using the JWT, query available MCP servers and manage OAuth connections
3. **MCP Proxy**: Stream requests through Barndoor's proxy with the JWT for authorization
4. **Third-party service**: The proxy forwards your requests to Salesforce, Notion, etc.

This architecture provides secure, managed access to external services without handling OAuth flows or storing third-party credentials in your code.

---

## Installation

```bash
pip install barndoor-sdk  # coming soon – for now use an editable install
# or, inside this repo
pip install -e libs/barndoor[dev]
```

Python ≥ 3.10 is required.

---

## Local development with uv

For the fastest install and reproducible builds you can use [uv](https://github.com/astral-sh/uv) instead of `pip`.

```bash
# 1) (one-off) install uv
brew install uv        # or follow the install script on Linux/Windows

# 2) create an isolated virtual environment in the repo
uv venv .venv
source .venv/bin/activate

# 3) install the SDK in editable mode plus the example extras
uv pip install -e '.[examples]'

# 4) install MCP support for CrewAI examples
uv pip install 'crewai-tools[mcp]'

# 5) copy the environment template and add your credentials
cp env.example .env
# Edit .env to add AGENT_CLIENT_ID, AGENT_CLIENT_SECRET, and OPENAI_API_KEY

# 6) run the interactive login utility once (opens browser)
uv run python -m barndoor.sdk.cli_login

# 7) kick off the Notion sample agent
uv run python examples/sample_notion_agent.py
```

**Note:** The OAuth default callback uses port 52765. Make sure this is registered in your Barndoor Agent as:
```
http://localhost:52765/cb
```

### Using a custom OAuth callback port

If port `52765` is blocked (or you prefer another), you can:

1. **Register the new callback URL** in your Barndoor Agent application, e.g.
   ```
   http://localhost:60000/cb
   ```
2. **Run the login helper with the matching port**
   ```bash
   # CLI
   uv run python -m barndoor.sdk.cli_login --port 60000

   # In code
   sdk = await bd.login_interactive(port=60000)
   ```

The SDK will spin up the local callback server on that port and embed the new URL in the request.

The examples expect a `.env` file next to each script containing:

```bash
# Minimal .env (local or dev)
AUTH0_DOMAIN=barndoor-local.us.auth0.com      # or your dev tenant
AGENT_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
AGENT_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyy

# Optional – only when you need to override the defaults
# MODE=development          # localdev | development | production
# BARNDOOR_API=…            # custom registry host
# BARNDOOR_URL=…            # custom MCP host
```

---

## Authentication workflow

Barndoor APIs expect a **user JWT** issued by your Barndoor tenant.  The SDK offers two ways to obtain & store such a token:

| Option | Command | When to use |
|--------|---------|-------------|
| Interactive CLI | `python -m barndoor.sdk.cli_login` *(alias: `barndoor-login`)* | One-time setup on laptops / CI machines |
| In-code helper | `await barndoor.sdk.login_interactive()` | Notebooks or scripts where you do not want a separate login step |

Both variants:

1. Spin up a tiny localhost callback server.
2. Open the system browser to Barndoor.
3. Exchange the returned *code* for a JWT.
4. Persist the token to `~/.barndoor/token.json` (0600 permissions).

Environment variables (or a neighbouring `.env` file) must define the Agent OAuth application:

```
AGENT_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
AGENT_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyy
# optional overrides
AUTH0_DOMAIN=barndoor-local.us.auth0.com
BARNDOOR_API=http://localhost:8003
```

The cached token is auto-refreshed on every run; if it is expired or revoked a new browser flow is launched.

## Quick-start in four lines

```python
import barndoor.sdk as bd

sdk = await bd.login_interactive()         # 1️⃣ ensure valid token
await bd.ensure_server_connected(sdk, "salesforce")  # 2️⃣ make sure OAuth is done
params, _public_url = await bd.make_mcp_connection_params(sdk, "salesforce")
```

`params` is a plain dict with `url`, `headers` and (optionally) `transport` – ready to plug into **any** HTTP / SSE / WebSocket client.  See the examples below for CrewAI & LangChain usage.

---

## Using the Registry API

```python
# List all MCP servers available to the current user
servers = await sdk.list_servers()
print([s.slug for s in servers])  # ['salesforce', 'notion', ...]

# Get detailed metadata (quota, scopes, etc.)
details = await sdk.get_server(server_id=servers[0].id)
print(details)
```

Additional helpers:

* `await sdk.initiate_connection(server_id)` – returns an OAuth URL the user must visit.
* `await bd.ensure_server_connected(sdk, "notion")` – combines status polling + browser launch.

---

## Model Context Protocol Connection

Once a server is **connected** you can stream requests through Barndoor’s proxy edge.

```python
params, public_url = await bd.make_mcp_connection_params(sdk, "notion")

print(params["url"])         # http(s)://…/mcp/notion
print(params["headers"])     # {'Authorization': 'Bearer ey…', 'x-barndoor-session-id': …}
```
