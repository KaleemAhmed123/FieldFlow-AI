# Salesforce Hosted MCP — setup recipe (as of October 2026)

How to stand up a **Salesforce Hosted MCP server** (Headless 360) so our **admin copilot** (and any
MCP client — Claude, Cursor, our orchestrator) can call Salesforce as discoverable tools. **GA since
April 2026**, free in Developer Edition.

> **When we use this (vs Apex REST):** the deterministic recovery pipeline uses plain **Apex REST**
> (`apps/salesforce-apex/`). Hosted MCP is for the **agentic admin copilot** — open-ended NL queries
> where the LLM must *discover and pick* tools. See `build-step-12-real-mcp-and-observability.md` and
> `context/03-knowledge-and-tools.md` §B. Guardrail: copilot **writes stay human-confirmed**.

> ⚠ Salesforce UI labels drift — match by intent. Sources at the bottom.

## Option 1 — standard hosted MCP (fastest, no Apex)

Salesforce ships ready hosted MCP endpoints in Developer Edition — generic SObject reads + API
context (`platform/sobject-reads`, `platform/sobject-all`, `platform/salesforce-api-context`). For
read-only copilot queries over our Field Service objects, this may be enough with **zero custom code**.
Just do step C (External Client App) + D (connect) below and point the client at the standard server.

## Option 2 — custom hosted MCP (expose our own Apex as tools)

Use when you want curated, described tools (e.g. "appointment health", "stuck cases") instead of raw
SObject reads.

**A. Write an Apex `@InvocableMethod` tool** (the **description is what the LLM reads to decide to
call it** — write it well):
```apex
public with sharing class FieldFlowCopilotTools {
    public class In  { @InvocableVariable(required=true) public String appointmentId; }
    public class Out { @InvocableVariable public String status; @InvocableVariable public Integer openRisks; }

    @InvocableMethod(label='Appointment health'
        description='Given a ServiceAppointment id, return its status and how many risks are open.')
    public static List<Out> run(List<In> input) {
        // ... SOQL; return one Out per In ...
    }
}
```

**B. Create + activate the MCP server:** Setup → Quick Find **"MCP"** → **MCP Servers** → **New /
Create Salesforce MCP server** → name + a good **description** (the AI uses it to route) → **Create**.
Then **Add Tools → To Apex actions** → pick your invocable class → **Save**. **Activate** the server.
Copy the **server URL** it shows.

**C. External Client App (ECA) — the auth. NOT a Connected App** (hosted MCP requires an ECA):
- Setup → **External Client Apps** → **New External Client App**. Name + your email. **Enable OAuth**.
- **Callback URL:** your client's redirect (for a custom client, e.g. `http://localhost:8000/oauth/callback`; for claude.ai, the connector gives you one).
- **OAuth scopes:** `api` (manage user data via APIs), `sfap_api` (Salesforce API Platform),
  `refresh_token`/`offline_access`, `einstein_gpt_api`, and **access to the hosted MCP server**.
- Enable **"Issue JSON Web Token (JWT)-based access tokens"**. Save → **Create**.
- **Manage Consumer Details** (email verification code) → copy **Consumer Key + Consumer Secret**.
- Salesforce does **not** support OAuth Dynamic Client Registration — the admin pre-creates this ECA.
- Auth mode: **admin-based** (one shared token, simplest for the POC) or **user-based** (per-user).

**D. Connect a client:**
- **claude.ai connector (the demo flex, zero code):** claude.ai → Settings → Connectors → Add custom
  connector → paste the **MCP server URL** + the ECA **client id** → authorize. Now Claude can answer
  "analyze this account/appointment" by invoking your Apex tool (the video flow).
- **Our orchestrator (the copilot `/copilot` route):** a custom MCP client (the `mcp` Python SDK) over
  the MCP server URL, OAuth bearer from the ECA. This is the Step-12 build.

## What this produces (env, for our MCP client)

```
SF_MCP_SERVER_URL=https://<yourdomain>.my.salesforce.com/...   # from step B
SF_MCP_CLIENT_ID=<ECA consumer key>
SF_MCP_CLIENT_SECRET=<ECA consumer secret>
```
(Separate from the Pub/Sub trigger's `SF_*` client-credentials creds and from the Apex REST path.)

## Sources (Oct 2026)
- Hosted MCP overview: https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/hosted-mcp-servers-overview.html
- Expose custom Apex as a hosted MCP tool: https://developer.salesforce.com/blogs/2026/05/expose-custom-apex-as-a-hosted-mcp-tool-for-agents
- Connect Claude to Salesforce Hosted MCP: https://developer.salesforce.com/blogs/2026/05/connect-claude-with-salesforce-hosted-mcp-servers
- Securing hosted MCP (ECA + scopes): https://developer.salesforce.com/blogs/2026/06/how-to-secure-salesforce-hosted-mcp-servers
