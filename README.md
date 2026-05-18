# Fabric Data Agent — Cross-Tenant Demos

This repository contains **two** progressively-richer Streamlit demos for
the same cross-tenant scenario: a user in **Tenant B** consuming a
**Microsoft Fabric Data Agent** published in **Tenant A**, using
interactive Microsoft Entra ID sign-in (no service principal).

| Folder | What it shows | When to start here |
|---|---|---|
| [demo/](demo/) | **Direct** call to the Fabric Data Agent (no orchestrator, no LLM in the middle). ~6 files. | You want the smallest possible reference of the Fabric Data Agent Python SDK + cross-tenant sign-in pattern. |
| [demo-orchestrator/](demo-orchestrator/) | A **Microsoft Agent Framework manager agent** with the Fabric Data Agent registered as one tool. Azure OpenAI handles tool planning; the same Entra token is reused for both AOAI and Fabric. Includes a 17-test pytest suite. | You want the recommended manager-agent pattern from Microsoft Agent Framework, ready to extend with more tools (Foundry agent, Bing, custom Python, …). |

Both demos can run side-by-side: the simple demo defaults to port **8501**, the orchestrator demo to port **8502**.

The implementation follows the official Microsoft Learn pattern:
**[Consume a Fabric data agent with the Python client SDK (preview)](https://learn.microsoft.com/fabric/data-science/consume-data-agent-python)**.

> **Preview notice.** Fabric Data Agent, its Python client SDK, and Microsoft Agent Framework are all in
> [Public Preview](https://learn.microsoft.com/fabric/fundamentals/preview).
> APIs, endpoints, and behavior may change without notice.

---

## What this repo contains

### `demo/` — single-agent reference

| File | Purpose |
|---|---|
| [demo/app.py](demo/app.py) | Streamlit chat UI (sign-in gate, sidebar, chat history, per-session thread, **chart rendering**). |
| [demo/chart_utils.py](demo/chart_utils.py) | Client-side helpers: extract answer text + a `pandas` DataFrame from the agent's response and render with Streamlit's native charts. See [chart rendering](demo/README.md#chart-rendering) in the demo README. |
| [demo/fabric_data_agent_client.py](demo/fabric_data_agent_client.py) | Verbatim MIT-licensed copy of the official Microsoft client SDK from [microsoft/fabric_data_agent_client](https://github.com/microsoft/fabric_data_agent_client). One small local edit: `api_key="not-used"` instead of `api_key=""` so the modern OpenAI Python SDK constructor passes its validation (auth is still done via the `Authorization: Bearer …` header). |
| [demo/requirements.txt](demo/requirements.txt) | `streamlit`, `azure-identity`, `openai`, `requests`, `python-dotenv`, `pandas`. |
| [demo/.env.example](demo/.env.example) | Template for the two required values (`TENANT_ID`, `DATA_AGENT_URL`). |
| [demo/README.md](demo/README.md) | Step-by-step setup, run, chart rendering, and troubleshooting guide. |

### `demo-orchestrator/` — manager agent with one tool

| File | Purpose |
|---|---|
| [demo-orchestrator/orchestrator.py](demo-orchestrator/orchestrator.py) | Factory that builds a single `agent_framework.Agent` whose only tool today is `ask_fabric_data_agent`. Designed to be extended with more tools later. |
| [demo-orchestrator/app.py](demo-orchestrator/app.py) | Streamlit chat UI on port **8502** — routes every chat turn through the manager agent. |
| [demo-orchestrator/chart_utils.py](demo-orchestrator/chart_utils.py) | Vendored verbatim from `demo/`. |
| [demo-orchestrator/fabric_data_agent_client.py](demo-orchestrator/fabric_data_agent_client.py) | Vendored from `demo/` with one tiny edit: `__init__` accepts `external_credential=` so the same Entra sign-in covers both Fabric and Azure OpenAI. |
| [demo-orchestrator/tests/](demo-orchestrator/tests/) | Pytest unit tests (17/17 pass, no network). |
| [demo-orchestrator/requirements.txt](demo-orchestrator/requirements.txt) | Adds `agent-framework`, `pytest`, `pytest-asyncio` on top of the simple demo's deps. |
| [demo-orchestrator/README.md](demo-orchestrator/README.md) | Full walkthrough, architecture diagram, test guide, and extension recipes. |

---

## How it works

```mermaid
flowchart LR
    subgraph TenantB["Tenant B (your home tenant)"]
        U([Your Entra ID account])
        APP[Streamlit app<br/>app.py + SDK]
    end
    subgraph Entra["Microsoft Entra"]
        EA[Authority for Tenant A]
    end
    subgraph TenantA["Tenant A (Fabric host)"]
        FDA[Published Fabric<br/>Data Agent]
        DS[(Lakehouse / Warehouse /<br/>Semantic model / KQL DB)]
    end
    U -->|1. start app| APP
    APP -->|2. InteractiveBrowserCredential<br/>tenant_id = Tenant A| EA
    U -.->|3. sign in via browser popup| EA
    EA -->|4. user-delegated access token<br/>aud = api.fabric.microsoft.com| APP
    APP -->|5. client.ask question<br/>Authorization: Bearer …| FDA
    FDA -->|6. NL → SQL / DAX / KQL<br/>as the signed-in user| DS
    DS -->|7. allowed rows only| FDA
    FDA -->|8. natural-language answer| APP
    APP -->|9. render in chat UI| U
```

1. The Streamlit app calls
   [`InteractiveBrowserCredential(tenant_id=<Tenant A>)`](https://learn.microsoft.com/python/api/azure-identity/azure.identity.interactivebrowsercredential)
   from `azure-identity` and opens the system browser.
2. The user picks an Entra ID account that can sign in to Tenant A — this can
   be a **guest** account whose home tenant is Tenant B
   ([Microsoft Entra B2B guest user](https://learn.microsoft.com/entra/external-id/what-is-b2b)).
3. Microsoft Entra issues an access token with the audience
   `https://api.fabric.microsoft.com/.default`.
4. The `FabricDataAgentClient.ask()` method uses that token (via the
   `Authorization: Bearer …` header) to call the Fabric Data Agent's
   Assistants-API endpoint: create assistant → create thread → post message →
   create run → poll until complete → fetch reply.
5. The data agent runs queries **as the signed-in user**, so it only returns
   rows the user is allowed to see (identity passthrough — see the
   [Fabric data agent concept](https://learn.microsoft.com/fabric/data-science/concept-data-agent)).

No app registration is needed for this scenario: `InteractiveBrowserCredential`
defaults to the well-known Azure CLI public client (`04b07795-…`), which is
already consented in most tenants for the Microsoft Fabric scope.

---

## Why this is "cross-tenant"

Microsoft Fabric Data Agents now support **two** identity types on the
call path (both in preview):

1. The **end user** signed in with Microsoft Entra ID — see
   [Consume a Fabric data agent with the Python client SDK](https://learn.microsoft.com/fabric/data-science/consume-data-agent-python).
2. A **service principal** — see
   [Use service principal authentication with Fabric data agent](https://learn.microsoft.com/fabric/data-science/data-agent-service-principal)
   (added in May 2026; **not yet supported** for data agents backed by a
   KQL database).

This demo intentionally uses option **(1)** for the cross-tenant case
because:

- The Tenant A data agent and its data sources enforce permissions per the
  *calling* Microsoft Entra identity. Using each user's own token preserves
  row-level security, sensitivity labels, and audit trails *as that user*
  in Tenant A.
- A service principal would be a single shared, non-interactive identity —
  not the actual end user. It also requires the Tenant A admin to register
  an app (or accept a multi-tenant one), enable
  **"Service principals can use Fabric APIs"**, and grant it Member /
  Contributor on the workspace plus read on every data source. That is the
  right pattern for *automation*, not for "a Tenant B human asks a question".
- Skipping server-to-server token exchange means no app registration, no
  secret management, and no middle-tier in Tenant B at all.

How it works in this demo:

- Skip server-to-server token exchange entirely.
- Sign the user in **directly to Tenant A** with their guest account.
- Pass the resulting user token straight to the Fabric Data Agent.

Result: a Tenant B user gets data from a Tenant A Fabric workspace through a
local Streamlit app, with no extra Azure infrastructure.

---

## Prerequisites

**In Tenant A (Fabric host):**

1. A paid **F2 (or higher) Fabric capacity**, or a **Power BI Premium P1+**
   capacity with [Microsoft Fabric enabled](https://learn.microsoft.com/fabric/admin/fabric-switch)
   ([feature parity list](https://learn.microsoft.com/fabric/enterprise/fabric-features)).
2. Tenant setting **"Cross-geo processing for AI"** and **"Cross-geo storing for AI"** enabled per
   [Fabric data agent tenant settings](https://learn.microsoft.com/fabric/data-science/data-agent-tenant-settings),
   if your capacity is in a different geo than your data.
3. A **published** Fabric Data Agent backed by at least one supported data
   source: Lakehouse, Warehouse, Power BI semantic model, KQL DB, mirrored DB,
   or ontology.

**In Tenant B (your home tenant):**

4. Your Entra ID account has been **invited as a guest** to Tenant A
   ([Microsoft Entra B2B](https://learn.microsoft.com/entra/external-id/b2b-quickstart-add-guest-users-portal))
   and the invitation is accepted.
5. That guest account has **read** access to the data source bound to the agent.

That's it. No app registration, no Key Vault, no Container Apps, no Foundry
project.

---

## Quickstart

### Simple demo (no orchestrator)

```pwsh
cd c:\mycodes\fabric_cross_tenant\demo

# 1. Configure the two values
Copy-Item .env.example .env
notepad .env       # fill in TENANT_ID and DATA_AGENT_URL

# 2. Create venv + install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Run
streamlit run app.py
```

Open <http://localhost:8501>, sign in when the browser pops, then chat.

For the full walkthrough (where to find `DATA_AGENT_URL`, troubleshooting
table, sign-out / new-conversation buttons) see [demo/README.md](demo/README.md).

### Orchestrator demo (Microsoft Agent Framework manager)

```pwsh
cd c:\mycodes\fabric_cross_tenant\demo-orchestrator

# 1. Configure (4 vars: Tenant A + Azure OpenAI)
Copy-Item .env.example .env
notepad .env

# 2. Create venv + install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Run tests (no network)
python -m pytest tests -v

# 4. Run on port 8502 so both demos can coexist
python -m streamlit run app.py --server.port=8502
```

Open <http://localhost:8502>. Full walkthrough, architecture diagram,
and "how to add more tools" recipes in
[demo-orchestrator/README.md](demo-orchestrator/README.md).

---

## Key Microsoft Learn references

- [Consume a Fabric data agent with the Python client SDK (preview)](https://learn.microsoft.com/fabric/data-science/consume-data-agent-python) — the pattern this demo implements.
- [Fabric data agent concept](https://learn.microsoft.com/fabric/data-science/concept-data-agent) — what a Fabric Data Agent is and how authentication works.
- [Fabric data agent tenant settings](https://learn.microsoft.com/fabric/data-science/data-agent-tenant-settings) — cross-geo and cross-tenant prerequisites.
- [`InteractiveBrowserCredential` API reference](https://learn.microsoft.com/python/api/azure-identity/azure.identity.interactivebrowsercredential) — the credential used for sign-in.
- [Microsoft Entra B2B collaboration overview](https://learn.microsoft.com/entra/external-id/what-is-b2b) — how a Tenant B user can sign in to Tenant A as a guest.
- [Microsoft Fabric preview features](https://learn.microsoft.com/fabric/fundamentals/preview) — preview terms.

---

## License

[demo/fabric_data_agent_client.py](demo/fabric_data_agent_client.py) and
[demo-orchestrator/fabric_data_agent_client.py](demo-orchestrator/fabric_data_agent_client.py)
are based on
[microsoft/fabric_data_agent_client](https://github.com/microsoft/fabric_data_agent_client),
published by Microsoft under the [MIT License](https://github.com/microsoft/fabric_data_agent_client/blob/main/LICENSE)
(the orchestrator copy adds a small `external_credential=` parameter to
the constructor).
The remaining files in this repository are provided **as-is**, without
warranty of any kind. Microsoft product names (Microsoft Fabric, Power BI,
Microsoft Entra, Azure, etc.) are trademarks of Microsoft Corporation and are
used here for technical reference only.
