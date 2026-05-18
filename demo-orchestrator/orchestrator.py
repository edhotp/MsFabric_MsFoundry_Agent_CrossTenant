"""Manager (orchestrator) agent built on Microsoft Agent Framework.

This module wires up exactly **one** tool today — a Microsoft Fabric Data
Agent — and exposes a factory (``build_orchestrator``) that returns a
ready-to-run :class:`agent_framework.Agent`. The same factory is what
``app.py`` (Streamlit UI) and the test suite use; adding more tools later
(a Foundry agent, web search, a Python REPL, …) only requires appending
to ``tools=[…]`` inside :func:`build_orchestrator`.

Design notes — Microsoft Agent Framework patterns used here
-----------------------------------------------------------
- The manager LLM is reached through
  ``agent_framework.openai.OpenAIChatClient`` configured for the
  **Azure AI Foundry v1 OpenAI endpoint** (Entra ID auth, no API keys).
  We pass the full ``.../openai/v1`` URL as ``base_url`` and use
  ``azure.identity.get_bearer_token_provider`` with the
  ``https://ai.azure.com/.default`` scope so the same browser sign-in
  used for Fabric also satisfies the model call.
  See https://learn.microsoft.com/agent-framework/overview/agent-framework-overview
- Tools are plain Python functions decorated with ``@agent_framework.tool``.
  The framework inspects the function signature + docstring to build the
  JSON schema the LLM uses to call the tool.
  See https://learn.microsoft.com/agent-framework/tutorials/agents/agent-with-tools
- The orchestrator is a single :class:`agent_framework.Agent` with a list
  of tools — the simplest "manager" pattern. Multi-agent workflows
  (``WorkflowBuilder``) and "agent-as-tool" (``Agent.as_tool()``) live in
  the same package when this demo grows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from agent_framework import Agent, FunctionTool, tool
from agent_framework.openai import OpenAIChatClient
from azure.identity import get_bearer_token_provider

from chart_utils import extract_answer_text, extract_dataframe
from fabric_data_agent_client import FabricDataAgentClient

# Microsoft Entra scope to request for the Azure AI Foundry v1 OpenAI
# endpoint (``*.services.ai.azure.com/openai/v1``). For classic
# Azure-OpenAI-resource endpoints (``*.openai.azure.com``) the scope is
# ``https://cognitiveservices.azure.com/.default`` instead.
FOUNDRY_SCOPE = "https://ai.azure.com/.default"

# --------------------------------------------------------------------------- #
# Public configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OrchestratorConfig:
    """All values needed to spin up the orchestrator.

    Loaded from environment variables by :meth:`from_env`, but tests
    construct it directly to avoid touching ``os.environ``.
    """

    tenant_id: str
    data_agent_url: str
    azure_openai_endpoint: str
    azure_openai_deployment: str
    # Tenant the Foundry resource lives in. ``None`` (the default) lets
    # the credential resolve the user's home tenant. Set this when
    # Foundry is in a *different* tenant from ``tenant_id`` (Fabric).
    llm_tenant_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        missing = []
        values = {}
        for env_name, attr in (
            ("TENANT_ID", "tenant_id"),
            ("DATA_AGENT_URL", "data_agent_url"),
            ("AZURE_OPENAI_ENDPOINT", "azure_openai_endpoint"),
            ("AZURE_OPENAI_DEPLOYMENT", "azure_openai_deployment"),
        ):
            value = (os.getenv(env_name) or "").strip()
            if not value:
                missing.append(env_name)
            values[attr] = value
        if missing:
            raise RuntimeError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy `.env.example` to `.env` and fill in the values."
            )
        # Optional — only needed in the cross-tenant Foundry case.
        llm_tenant = (os.getenv("LLM_TENANT_ID") or "").strip()
        values["llm_tenant_id"] = llm_tenant or None
        return cls(**values)


# --------------------------------------------------------------------------- #
# Tool factory — Fabric Data Agent as a function tool
# --------------------------------------------------------------------------- #


@dataclass
class FabricToolResult:
    """Plain-data result the orchestrator hands back to the UI.

    Returning the raw ``run_details`` dict here as well lets the Streamlit
    layer render charts from ``sql_data_previews`` *without* a second
    round-trip — same trick the single-agent demo uses.
    """

    answer: str
    run_details: dict


def build_fabric_data_agent_tool(
    client: FabricDataAgentClient,
    *,
    thread_name: str = "orchestrator",
    on_result: Optional[Callable[[FabricToolResult], None]] = None,
) -> FunctionTool:
    """Wrap a :class:`FabricDataAgentClient` as a framework tool.

    ``on_result`` is an optional callback invoked with the full
    :class:`FabricToolResult` every time the tool runs — the Streamlit
    layer uses it to capture ``run_details`` for chart rendering.
    """

    @tool(
        name="ask_fabric_data_agent",
        description=(
            "Ask the Microsoft Fabric Data Agent a question about the "
            "organization's business data (sales, customers, products, "
            "inventory, etc.). The data agent runs SQL/DAX/KQL against "
            "the Fabric workspace's Lakehouse / Warehouse / Semantic "
            "Model. Use this tool whenever the user asks anything that "
            "requires looking up real business numbers."
        ),
    )
    def ask_fabric_data_agent(question: str) -> str:
        """Run ``question`` against the Fabric Data Agent.

        Args:
            question: A natural-language question about the business data
                (e.g. "What were the top 5 products by revenue last
                month?").

        Returns:
            The agent's natural-language answer, including any markdown
            tables it produced.
        """
        if not question or not question.strip():
            return "Error: question is empty."
        run_details = client.get_run_details(question, thread_name=thread_name)
        if isinstance(run_details, dict) and run_details.get("error"):
            return f"Error from Fabric Data Agent: {run_details['error']}"
        answer = extract_answer_text(run_details)
        if on_result is not None:
            try:
                on_result(FabricToolResult(answer=answer, run_details=run_details))
            except Exception:  # noqa: BLE001 — callback must never break the tool
                pass
        return answer

    return ask_fabric_data_agent


# --------------------------------------------------------------------------- #
# Manager agent factory
# --------------------------------------------------------------------------- #

MANAGER_INSTRUCTIONS = """\
You are a data assistant for a Microsoft Fabric workspace.

You have access to a single tool, `ask_fabric_data_agent`, which queries
the organization's business data through a Microsoft Fabric Data Agent.

Rules:
- If the user asks a question that requires *real* business numbers, call
  `ask_fabric_data_agent` exactly once with a clear, self-contained
  question and base your reply on what it returned.
- If the user asks something the tool cannot answer (greetings,
  general-purpose chit-chat, questions about how you work), answer
  directly without calling the tool.
- Always preserve markdown tables returned by the tool verbatim — the UI
  uses them to render charts.
- Never invent numbers. If the tool returns an error, surface it.
"""


def build_orchestrator(
    config: OrchestratorConfig,
    credential,
    *,
    llm_credential=None,
    fabric_client: Optional[FabricDataAgentClient] = None,
    chat_client: Optional[OpenAIChatClient] = None,
    on_fabric_result: Optional[Callable[[FabricToolResult], None]] = None,
    extra_tools: Sequence = (),
    instructions: str = MANAGER_INSTRUCTIONS,
) -> Agent:
    """Build the orchestrator agent.

    Args:
        config: Resolved configuration (use :meth:`OrchestratorConfig.from_env`
            in the app, or pass a hand-built one in tests).
        credential: An ``azure.identity`` credential signed in to Tenant A.
            Used for the Fabric Data Agent call.
        llm_credential: Optional separate ``azure.identity`` credential used
            for the Azure AI Foundry chat model. When ``None`` (default), the
            same ``credential`` is reused — correct only when Foundry lives
            in the same Entra tenant as the Fabric workspace. In a true
            cross-tenant setup (Fabric in Tenant A as a guest, Foundry in the
            user's home tenant) pass a second ``InteractiveBrowserCredential``
            here so each resource gets a token from its own tenant.
        fabric_client: Override to inject a mock client in tests.
        chat_client: Override to inject a mock chat client in tests.
        on_fabric_result: Optional callback that receives the full result
            of each Fabric tool call (used by the UI for chart rendering).
        extra_tools: Reserved for future tools (e.g. a Foundry agent's
            ``.as_tool()``). Passed verbatim into ``Agent(tools=…)``.
        instructions: System prompt for the manager LLM.
    """
    fabric_client = fabric_client or FabricDataAgentClient(
        tenant_id=config.tenant_id,
        data_agent_url=config.data_agent_url,
        external_credential=credential,
    )

    llm_credential = llm_credential or credential

    # ``get_bearer_token_provider`` returns a *synchronous* ``Callable[[], str]``.
    # ``OpenAIChatClient`` with ``base_url=`` routes through OpenAI's
    # ``AsyncOpenAI`` client whose ``_refresh_api_key`` does
    # ``await self._api_key_provider()`` — so we wrap the sync provider in
    # an async function. The framework otherwise hard-codes the classic
    # ``cognitiveservices.azure.com/.default`` scope when given a raw
    # ``credential=``, which is wrong for Foundry's ``/openai/v1`` route.
    sync_token_provider = get_bearer_token_provider(llm_credential, FOUNDRY_SCOPE)

    async def _async_token_provider() -> str:
        return sync_token_provider()

    chat_client = chat_client or OpenAIChatClient(
        model=config.azure_openai_deployment,
        base_url=config.azure_openai_endpoint,
        api_key=_async_token_provider,
    )

    fabric_tool = build_fabric_data_agent_tool(
        fabric_client, on_result=on_fabric_result
    )

    tools = [fabric_tool, *extra_tools]

    return Agent(
        client=chat_client,
        name="FabricOrchestrator",
        description="Manager agent that orchestrates Fabric Data Agent calls.",
        instructions=instructions,
        tools=tools,
    )


__all__ = [
    "FOUNDRY_SCOPE",
    "FabricToolResult",
    "MANAGER_INSTRUCTIONS",
    "OrchestratorConfig",
    "build_fabric_data_agent_tool",
    "build_orchestrator",
]
