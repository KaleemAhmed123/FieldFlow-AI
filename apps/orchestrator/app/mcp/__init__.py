"""The MCP (Model Context Protocol) client seam — the AGENTIC path to Salesforce (build step 12).

Distinct from the deterministic Apex REST adapter (app/tools/salesforce.py): there, our Python calls
named endpoints and the LLM never chooses. Here, the admin copilot's LLM *discovers* Salesforce
tools over a Hosted MCP server and decides which to call. build_mcp_client is the one swap line
(None unless SF_MCP_* creds + the one-time refresh token are armed), like build_vonage.
"""

from app.mcp.client import SalesforceMcpClient, build_mcp_client

__all__ = ["SalesforceMcpClient", "build_mcp_client"]
