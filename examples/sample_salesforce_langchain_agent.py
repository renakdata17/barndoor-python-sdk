"""Minimal Barndoor → MCP demo (LangChain version).

This example mirrors ``sample_salesforce_agent.py`` but swaps the CrewAI demo
for a LangChain + LangGraph React agent built with ``langchain_mcp_adapters``.

Steps
-----
1. Load a local ``.env`` so we get *AGENT_CLIENT_ID / AGENT_CLIENT_SECRET* and
   ``OPENAI_API_KEY``.
2. Use the SDK quick-start helpers to
   • login & obtain a ready ``BarndoorSDK``
   • ensure the chosen MCP server is *connected*
   • build connection params (proxy URL + auth headers)
3. Convert those params to LangChain tools via ``MultiServerMCPClient``.
4. Ask the agent a Salesforce report question and print the markdown answer.

Usage
-----
Export the desired MODE (localdev | development | production) before running:

    export MODE=development

Then execute:

    python examples/sample_salesforce_langchain_agent.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import barndoor.sdk as bd
from dotenv import load_dotenv

# LangChain / LangGraph imports ------------------------------------------------
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

# ----------------------------------------------------------------------------
# Configuration ----------------------------------------------------------------
# ----------------------------------------------------------------------------
SERVER_SLUG = "salesforce"  # change to any server slug in your registry


async def main() -> None:  # noqa: D401
    # ------------------------------------------------------------------
    # 0. Environment / login
    # ------------------------------------------------------------------
    # Load auth creds (Agent OAuth + OpenAI key) from repo-root .env
    load_dotenv(Path(__file__).parent.parent / ".env")

    # Interactive PKCE flow (cached token) → Barndoor SDK client
    sdk = await bd.login_interactive()

    # ------------------------------------------------------------------
    # 1. Ensure the target server connection is ready (runs OAuth if needed)
    # ------------------------------------------------------------------
    await bd.ensure_server_connected(sdk, SERVER_SLUG)

    # ------------------------------------------------------------------
    # 2. Build connection params – works locally & when deployed
    # ------------------------------------------------------------------
    params, public_url = await bd.make_mcp_connection_params(sdk, SERVER_SLUG)
    print(f"✓ Ready – MCP URL: {params['url']}  (public: {public_url})")

    # langchain_mcp_adapters expects "streamable_http" instead of
    # "streamable-http" – normalise when necessary.
    conn_cfg = {**params, "transport": params.get("transport", "").replace("-", "_")}

    # ------------------------------------------------------------------
    # 3. Convert MCP tools to LangChain tools via MultiServerMCPClient
    # ------------------------------------------------------------------
    client = MultiServerMCPClient({SERVER_SLUG: conn_cfg})
    tools = await client.get_tools()
    print(f"✓ Loaded {len(tools)} tools from '{SERVER_SLUG}' server")

    # ------------------------------------------------------------------
    # 4. Create a React-style agent and run a query
    # ------------------------------------------------------------------
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0.3)

    agent = create_react_agent(
        llm,
        tools,
        prompt=(
            "You are a helpful Salesforce data assistant. Return concise markdown "
            "reports with insights and numbers formatted nicely."
        ),
    )

    question = (
        "Fetch the latest Salesforce pipeline metrics (total value, open opportunities per stage) "
        "and return a concise *written* report – 3-5 bullet points – analysing any noteworthy changes "
        "since yesterday. Also detail the leads with a separate query/section."
    )

    print("\nRunning LangChain agent with MCP tools…")
    response = await agent.ainvoke({"messages": question})

    # The response comes back as a MessagesState dict from LangGraph –
    # extract the assistant content for convenience.
    content = response["messages"][-1].content  # type: ignore[index]
    print("\n✓ Result:\n")
    print(content)

    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main()) 