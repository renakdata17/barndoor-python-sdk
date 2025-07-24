"""Minimal Barndoor → MCP demo for a Notion integration.

This script mirrors `sample_agent.py` but targets a Notion MCP server.
It demonstrates how to:

1. Load credentials from the repo-root `.env` file (expects `AUTH_DOMAIN`, `AGENT_CLIENT_ID`, and `AGENT_CLIENT_SECRET`).
2. Use the Barndoor SDK helpers to:
   • log in interactively
   • ensure the Notion server connection is established (launches OAuth if needed)
   • obtain connection parameters (proxy URL + headers)
3. Feed those params to **any** AI framework – here we show a tiny CrewAI demo.

Environment:
    export MODE=development  # or production / localdev

Run with:
    python sample_notion_agent.py
"""

from __future__ import annotations

import asyncio

from pathlib import Path

# Framework-agnostic SDK helpers ------------------------------------------------
import barndoor.sdk as bd


# Optional: only imported when we actually run the CrewAI demo
from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter
from dotenv import load_dotenv


SERVER_SLUG = "notion"  # target MCP server for this sample


async def main() -> None:  # noqa: D401 (simple function description)
    # ------------------------------------------------------------------
    # 0. Environment / login
    # ------------------------------------------------------------------
    # Load auth creds from repo-root .env
    load_dotenv(Path(__file__).parent.parent / ".env")

    sdk = await bd.login_interactive()  # handles cached JWT, PKCE flow, etc.

    # ------------------------------------------------------------------
    # 1. List available servers for the current user
    # ------------------------------------------------------------------
    servers = await sdk.list_servers()
    print("\nAvailable MCP servers:")
    for s in servers:
        print(f"  • {s.slug:<12} status={s.connection_status}")

    # ------------------------------------------------------------------
    # 2. Ensure the Notion server is connected (will launch OAuth if not)
    # ------------------------------------------------------------------
    await bd.ensure_server_connected(sdk, SERVER_SLUG)

    # ------------------------------------------------------------------
    # 3. Build connection params (works locally & in deployed envs)
    # ------------------------------------------------------------------
    params, public_url = await bd.make_mcp_connection_params(sdk, SERVER_SLUG)
    print(f"✓ Ready – MCP URL: {params['url']}  (public: {public_url})")

    # ------------------------------------------------------------------
    # 4. Tiny CrewAI demo – replace with LangChain etc. if you prefer
    # ------------------------------------------------------------------
    with MCPServerAdapter(params) as mcp_tools:
        agent = Agent(
            role="Notion Workspace Assistant",
            goal="Help users query and update their Notion pages & databases",
            backstory="Sample agent using Barndoor MCP integration with Notion.",
            tools=mcp_tools,
            verbose=True,
        )

        task = Task(
            description="Research Summary",
            expected_output="Update the page Demo Workspace - SwiftShip Data, to append this was written by Test Agent at the end of the page",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        print("\nRunning CrewAI with MCP tools…")
        result = crew.kickoff()
        print(f"\n✓ Result: {result}")

    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
