# Fabric Orchestrator — Cross-Tenant Demo (Manager Agent)

A best-practice **Microsoft Agent Framework** [manager agent](https://learn.microsoft.com/agent-framework/user-guide/agents/agent-with-tools) sample, in the same spirit as the simpler [`../demo/`](../demo/) folder but with one extra layer:

> **The user no longer talks to the Fabric Data Agent directly. They talk to a "manager" agent that *decides* whether to call the Fabric Data Agent (as a tool) for each turn.**

The demo is intentionally minimal — **one tool, one agent** — so the manager-agent pattern shows through without ceremony. Adding more tools later (Foundry agent, Bing search, a custom Python tool, etc.) is a one-liner; see [Extending the orchestrator](#extending-the-orchestrator) below.

> **Preview notice.** Microsoft Agent Framework, Microsoft Fabric Data Agent, and the Fabric Data Agent Python client SDK are all in [Public Preview](https://learn.microsoft.com/fabric/fundamentals/preview). APIs may change without notice.

---

## What this demo contains

| File | Purpose |
|---|---|
| [orchestrator.py](orchestrator.py) | The manager agent factory. Builds a single `agent_framework.Agent` with one tool: `ask_fabric_data_agent`. |
| [app.py](app.py) | Streamlit chat UI (port **8502**) — same sign-in pattern as the simpler demo, but the chat loop goes through the manager agent. |
| [chart_utils.py](chart_utils.py) | Verbatim copy from `../demo/` — extracts a `pandas` DataFrame from the Fabric agent's reply and renders Streamlit native charts. |
| [fabric_data_agent_client.py](fabric_data_agent_client.py) | Verbatim MIT copy of [microsoft/fabric_data_agent_client](https://github.com/microsoft/fabric_data_agent_client) with **one** local change: the `__init__` accepts an `external_credential=` so the orchestrator can share the same `InteractiveBrowserCredential` between Fabric and Azure OpenAI (one sign-in, both audiences). |
| [tests/](tests/) | Pytest unit tests for the tool wrapper, config loader, and agent factory. **17/17 pass** with no network calls. |
| [requirements.txt](requirements.txt) | `agent-framework`, `azure-identity`, `openai`, `streamlit`, `pandas`, `pytest`. |
| [.env.example](.env.example) | Required environment variables (see below). |

The simpler `../demo/` is **untouched** — it stays a clean reference for the no-orchestrator case.

---

## How it works

```mermaid
flowchart LR
    U([Your Entra ID account<br/>signed in to Tenant A])
    APP[Streamlit UI<br/>app.py]
    MGR[Manager Agent<br/>Agent Framework]
    AOAI[(Azure OpenAI<br/>in your tenant)]
    TOOL[Tool:<br/>ask_fabric_data_agent]
    FDA[(Fabric Data Agent<br/>in Tenant A)]

    U -->|chat message| APP
    APP -->|run prompt| MGR
    MGR <-->|chat completion<br/>(Entra token)| AOAI
    MGR -->|tool call when needed| TOOL
    TOOL -->|HTTPS + Bearer token| FDA
    FDA -->|natural-language answer<br/>+ run_details| TOOL
    TOOL -->|answer text| MGR
    MGR -->|final reply| APP
    APP -->|render chart from run_details| U
```

Key properties:

- **One sign-in covers everything.** `InteractiveBrowserCredential(tenant_id=<Tenant A>)` is created once and reused for both the Fabric scope (`https://api.fabric.microsoft.com/.default`) and the Azure OpenAI scope (`https://cognitiveservices.azure.com/.default`).
- **The manager LLM is Azure OpenAI in *your* tenant.** Only the data tool reaches across into Tenant A. Your prompts and tool-call planning never leave your tenant.
- **`run_details` short-circuits the chart path.** The tool's `on_result` callback hands the raw Fabric `run_details` dict to the Streamlit layer, which calls `chart_utils.extract_dataframe(...)` the same way [`../demo/app.py`](../demo/app.py) does. No second round-trip.
- **The manager pattern keeps the agent code small.** A single `Agent(client=..., tools=[fabric_tool])` is the whole orchestrator — see [`build_orchestrator`](orchestrator.py).

---

## Prerequisites

In addition to the prerequisites for the simpler [`../demo/`](../README.md#prerequisites) (Fabric capacity in Tenant A, published data agent, Tenant B user invited as guest), you also need:

**In your home tenant (Tenant B):**

1. An **Azure OpenAI resource** with a chat-model deployment (`gpt-4o-mini`, `gpt-4.1-mini`, etc.). Note its endpoint and deployment name.
2. Your Entra ID account assigned the [**Cognitive Services OpenAI User**](https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control) role on that Azure OpenAI resource (this is what lets the same user token call AOAI).
3. A modern Python (3.11+) and `pip`.

That's it — no app registration, no service principal, no Key Vault.

---

## Quickstart

```pwsh
cd c:\mycodes\fabric_cross_tenant\demo-orchestrator

# 1. Configure
Copy-Item .env.example .env
notepad .env       # fill in the 4 values

# 2. Create venv + install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Run
python -m streamlit run app.py --server.port=8502
```

Open <http://localhost:8502>, sign in when the Entra browser pops, then chat.

> The simpler demo runs on port **8501** by default. The orchestrator demo
> runs on **8502** so both can run side-by-side.

### Environment variables (`.env`)

```ini
# Tenant A (where the Fabric Data Agent lives)
TENANT_ID=00000000-0000-0000-0000-000000000000
DATA_AGENT_URL=https://api.fabric.microsoft.com/v1/workspaces/<ws>/aiskills/<agent>/openai

# Azure OpenAI in your home tenant
AZURE_OPENAI_ENDPOINT=https://<your-aoai-resource>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview   # optional; default shown
```

`AZURE_OPENAI_DEPLOYMENT` is the **deployment name** (what you named it in Azure AI Foundry / Azure OpenAI Studio), *not* the underlying model name.

---

## Tests

Comprehensive unit tests live in [tests/](tests/). They mock the Azure OpenAI client and the `FabricDataAgentClient` — no real network calls are made.

```pwsh
cd c:\mycodes\fabric_cross_tenant\demo-orchestrator
.\.venv\Scripts\python.exe -m pytest tests -v
```

Expected output: **17 passed**.

What's covered:

- **`tests/test_tools.py`** — the Fabric tool wrapper
  - Correct `name`, `description`, and JSON schema (`question: string`, required).
  - Returns the assistant text extracted from `run_details`.
  - Uses the supplied `thread_name`.
  - Fires the `on_result` callback with a `FabricToolResult` instance.
  - Callback exceptions are swallowed (a broken UI must never break the tool).
  - Empty / blank input → friendly error, no client call.
  - Error dict from the client → surfaced verbatim.
  - Empty assistant messages → `"(no answer returned)"` fallback.
  - End-to-end async invocation via `FunctionTool.invoke(...)` — exercises the framework's argument-parsing path.
- **`tests/test_orchestrator.py`** — config + factory
  - `OrchestratorConfig.from_env`: happy path, default API version, missing-var detection (lists only the *missing* ones), whitespace-only treated as missing.
  - `build_orchestrator`: returns a real `Agent`, registers the Fabric tool, respects custom instructions, and accepts `extra_tools` so you can append more tools without touching the factory.

---

## Extending the orchestrator

Adding a second tool is exactly two lines. Example — a hypothetical web-search tool:

```python
from agent_framework import tool

@tool(name="web_search", description="Search the public web for a phrase.")
def web_search(query: str) -> str:
    ...

agent = build_orchestrator(
    config,
    credential,
    extra_tools=[web_search],
)
```

Or wrap **another agent** as a tool (the "agent-as-tool" pattern from the Agent Framework docs):

```python
foundry_agent = Agent(client=..., name="ResearchAgent", instructions="...")
agent = build_orchestrator(
    config,
    credential,
    extra_tools=[foundry_agent.as_tool(
        name="ask_research_agent",
        description="Delegate deep research questions to the research agent.",
        arg_name="task",
    )],
)
```

See:

- [Microsoft Agent Framework — Agent with tools](https://learn.microsoft.com/agent-framework/user-guide/agents/agent-with-tools)
- [Microsoft Agent Framework — Multi-agent workflows](https://learn.microsoft.com/agent-framework/user-guide/workflows/overview)
- [`Agent.as_tool`](https://learn.microsoft.com/python/api/agent-framework/agent_framework.agent.agent#agent-framework-agent-agent-as-tool) — wrap one agent as a tool for another.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Missing required environment variable(s): …` on startup | `.env` not next to `app.py` or one of the four vars is blank. |
| Browser opens but sign-in fails with `AADSTS50020` | Your Entra account isn't invited as a guest to Tenant A. See [Microsoft Entra B2B](https://learn.microsoft.com/entra/external-id/b2b-quickstart-add-guest-users-portal). |
| `(401) Authorization failed` from Azure OpenAI | The signed-in user doesn't have **Cognitive Services OpenAI User** role on the AOAI resource. See [AOAI RBAC](https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control). |
| `404 DeploymentNotFound` from Azure OpenAI | `AZURE_OPENAI_DEPLOYMENT` doesn't match a deployment in your AOAI resource. Check Azure AI Foundry → Deployments. |
| `403 Forbidden` from the Fabric Data Agent | The signed-in user isn't on the workspace or doesn't have read on the underlying data source. |
| `streamlit.exe` not found in `.venv\Scripts\` | Run via `python -m streamlit run app.py --server.port=8502` instead. |
| `ExperimentalWarning: [HARNESS]…` in the log | Harmless — Agent Framework's preview-feature notice. |

---

## Key Microsoft Learn references

- [Microsoft Agent Framework — overview](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
- [Agent Framework — Agent with tools](https://learn.microsoft.com/agent-framework/user-guide/agents/agent-with-tools)
- [Agent Framework — Multi-agent workflows](https://learn.microsoft.com/agent-framework/user-guide/workflows/overview)
- [Consume a Fabric data agent with the Python client SDK (preview)](https://learn.microsoft.com/fabric/data-science/consume-data-agent-python)
- [Azure OpenAI — Entra ID role-based access control](https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control)
- [Azure Identity — `InteractiveBrowserCredential`](https://learn.microsoft.com/python/api/azure-identity/azure.identity.interactivebrowsercredential)

---

## License

[fabric_data_agent_client.py](fabric_data_agent_client.py) is a near-verbatim copy of [microsoft/fabric_data_agent_client](https://github.com/microsoft/fabric_data_agent_client) (MIT). The remaining files are provided **as-is** with no warranty. Microsoft product names are trademarks of Microsoft Corporation and used here for technical reference only.
