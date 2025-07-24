"""Minimal Barndoor → MCP demo (LlamaIndex version).

This script mirrors ``sample_salesforce_agent.py`` but showcases how to
use MCP tools inside **LlamaIndex** via the ``llamaindex-mcp-adapter``.

Prerequisites
-------------
1. ``pip install llamaindex llamaindex-mcp-adapter`` (or ``uv pip install``).
2. A ``.env`` next to the repo root providing
   • AGENT_CLIENT_ID / AGENT_CLIENT_SECRET (Barndoor)
   • OPENAI_API_KEY (or compatible LLM key)
3. Ensure the Salesforce MCP server is *connected* to your user – the helper
   below launches OAuth if needed.

Run with:

    export MODE=development  # or localdev / production
    python examples/sample_salesforce_llamaindex_agent.py

Notes
-----
• ``llamaindex-mcp-adapter`` converts MCP tool metadata to LlamaIndex
  ``BaseTool`` objects, which can be bound to any chat engine.
• We keep the async login + ensure_server_connected helpers for parity with
  the other examples.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import barndoor.sdk as bd
from dotenv import load_dotenv

# LlamaIndex imports -----------------------------------------------------------
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.agent import AgentRunner
from llama_index.llms.openai import OpenAI
from llama_index.tools.mcp import aget_tools_from_mcp_url, BasicMCPClient

# MCP client (shared with LangChain demo) -------------------------------------
from langchain_mcp_adapters.client import MultiServerMCPClient

# ----------------------------------------------------------------------------
SERVER_SLUG = "salesforce"


async def main() -> None:  # noqa: D401
    # ------------------------------------------------------------------
    # 0. Environment / login
    # ------------------------------------------------------------------
    load_dotenv(Path(__file__).parent.parent / ".env")

    sdk = await bd.login_interactive()

    # ------------------------------------------------------------------
    # 1. Ensure the target server is connected (OAuth flow if needed)
    # ------------------------------------------------------------------
    await bd.ensure_server_connected(sdk, SERVER_SLUG)

    # ------------------------------------------------------------------
    # 2. Build connection params (proxy URL + headers)
    # ------------------------------------------------------------------
    params, public_url = await bd.make_mcp_connection_params(sdk, SERVER_SLUG)
    print(f"✓ Ready – MCP URL: {params['url']}  (public: {public_url})")

    # Normalise transport key for langchain_mcp_adapters
    conn_cfg = {**params, "transport": params.get("transport", "").replace("-", "_")}

    # ------------------------------------------------------------------
    # 3. Fetch MCP tools and convert to LlamaIndex FunctionTool objects
    # ------------------------------------------------------------------
    # Use the proxy URL with the Authorization header from make_mcp_connection_params
    client = BasicMCPClient(conn_cfg["url"], headers=conn_cfg["headers"])
    li_tools = await aget_tools_from_mcp_url(conn_cfg["url"], client=client)
    print(f"✓ Loaded {len(li_tools)} tools from '{SERVER_SLUG}' server")

    # ------------------------------------------------------------------
    # 4. Create a LlamaIndex chat engine and query
    # ------------------------------------------------------------------
    llm = OpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0.3)

    # Configure global settings (replaces ServiceContext)
    Settings.llm = llm

    # Build a simple React agent runner with the MCP tools
    agent = AgentRunner.from_llm(
        tools=li_tools,
        llm=llm,
        system_prompt="You are a helpful Salesforce data assistant. Return concise markdown reports."
    )

    question = (
        "Fetch the latest Salesforce pipeline metrics (total value, open opportunities per stage) "
        "and return a concise markdown report (3–5 bullet points) analysing noteworthy changes since yesterday. "
        "Also detail the new leads in a separate section."
    )

    print("\nRunning LlamaIndex chat engine with MCP tools…")
    response = await agent.achat(question)

    print("\n✓ Result:\n")
    print(response)

    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main()) 