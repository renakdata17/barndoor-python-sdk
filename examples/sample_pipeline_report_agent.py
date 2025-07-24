"""Barndoor demo: pull a Salesforce pipeline report and post it to Notion.

This sample shows how an agent can use **two** MCP server integrations
(simultaneously) inside CrewAI:

• Salesforce (read-only) – fetch the latest pipeline metrics.
• Notion (read-write) – update or create a report page.

Run with:
    python sample_pipeline_report_agent.py

Environment / prerequisites
---------------------------
1. Ensure both Salesforce and Notion MCP servers exist for your org and that your
   user has *connected* them.  If not, the helper below will launch the OAuth
   flows.
2. Make sure the repo-root `.env` contains:
       AUTH_DOMAIN=…
       AGENT_CLIENT_ID=…
       AGENT_CLIENT_SECRET=…
   and export the desired ``MODE`` (localdev | development | production) –
   for shared DEV simply:

       export MODE=development
"""

from __future__ import annotations

import asyncio

from pathlib import Path

import barndoor.sdk as bd

from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter
from dotenv import load_dotenv


# Slugs for the two target servers in your registry
SF_SLUG = "salesforce"
NOTION_SLUG = "notion"


async def main() -> None:  # noqa: D401
    # Load auth creds from repo-root .env so all samples share the same file
    load_dotenv(Path(__file__).parent.parent / ".env")

    sdk = await bd.login_interactive()

    # ------------------------------------------------------------------
    # Ensure both servers are connected (runs OAuth if needed)
    # ------------------------------------------------------------------
    await bd.ensure_server_connected(sdk, SF_SLUG)
    await bd.ensure_server_connected(sdk, NOTION_SLUG)

    # Build connection params
    sf_params, _ = await bd.make_mcp_connection_params(sdk, SF_SLUG)
    notion_params, _ = await bd.make_mcp_connection_params(sdk, NOTION_SLUG)

    # ------------------------------------------------------------------
    # Run CrewAI – give the agent access to tools from *both* servers
    # ------------------------------------------------------------------
    with (
        MCPServerAdapter(sf_params) as sf_tools,
        MCPServerAdapter(notion_params) as notion_tools,
    ):
        # Combine tool collections from both adapters into one list
        tools = list(sf_tools) + list(notion_tools)

        agent = Agent(
            role="Revenue Ops Analyst",
            goal="Keep leadership informed by pulling the latest pipeline numbers from Salesforce and publishing them to Notion",
            backstory=(
                "You are responsible for daily pipeline reporting. You fetch the "
                "current opportunity metrics from Salesforce, then write a "
                "concise summary into the Notion workspace so executives always "
                "have an up-to-date view."
            ),
            tools=tools,
            verbose=True,
        )

        task = Task(
            description=(
                "Generate today's pipeline report and publish it in Notion. "
                "First try to *append blocks* to the existing page named "
                "'Sales Pipeline – Auto-Report'. If that append fails (e.g. the "
                "API returns an error), fall back to creating a *new child page* "
                "under that parent page that contains the report contents."
            ),
            expected_output=(
                "1. Query Salesforce for total pipeline value and number of open "
                "opportunities broken down by stage.\n"
                "2. Either (a) append a new block section titled with today's "
                "date to 'Sales Pipeline – Auto-Report' *or* (b) create a new "
                "child page under it with the same information if append fails.\n"
                "3. Return the final Notion page URL that contains today's report."
            ),
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        print("\nRunning multi-provider CrewAI pipeline report…")
        result = crew.kickoff()
        print(f"\n✓ Notion page created/updated: {result}")

    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
