"""Streamlit chat UI for the orchestrator (manager) demo.

Same cross-tenant pattern as ``../demo/app.py``, but the chat input is
routed through a Microsoft Agent Framework "manager" agent instead of
calling the Fabric Data Agent directly. The manager decides whether the
user's question needs a tool call and, if so, invokes the
``ask_fabric_data_agent`` tool. The tool's structured result is also
captured for client-side chart rendering — exactly the same UX as the
single-agent demo.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pandas as pd
import streamlit as st
from azure.identity import InteractiveBrowserCredential
from dotenv import load_dotenv

# Load env vars from .env next to this script BEFORE importing orchestrator
# (orchestrator.OrchestratorConfig.from_env reads os.environ at call time).
load_dotenv()

from chart_utils import (
    CHART_TYPES,
    extract_dataframe,
    render_chart,
)
from orchestrator import (
    FabricToolResult,
    OrchestratorConfig,
    build_orchestrator,
)

# --------------------------------------------------------------------------- #
# Page chrome
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Fabric Orchestrator — Cross-Tenant",
    page_icon="🧭",
    layout="centered",
)
st.title("🧭 Fabric Orchestrator — Cross-Tenant Demo")
st.caption(
    "A Microsoft Agent Framework manager agent that calls a Fabric Data Agent "
    "in another tenant. Sign in with your Entra ID account — one sign-in for "
    "Fabric (Tenant A), and one for the Azure AI Foundry tenant."
)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
try:
    CONFIG = OrchestratorConfig.from_env()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()


# --------------------------------------------------------------------------- #
# Cached credential + orchestrator (browser opens only on the first call)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="\U0001F510 Opening browser for Tenant A sign-in (Fabric)…")
def _get_fabric_credential(tenant_id: str) -> InteractiveBrowserCredential:
    """Credential bound to Tenant A — used to call the Fabric Data Agent."""
    return InteractiveBrowserCredential(tenant_id=tenant_id)


@st.cache_resource(show_spinner="\U0001F510 Opening browser for home-tenant sign-in (Foundry)…")
def _get_llm_credential(tenant_id: str | None = None) -> InteractiveBrowserCredential:
    """Credential bound to the tenant that owns the Azure AI Foundry resource.

    Pass ``tenant_id`` when Foundry is in a *different* tenant from the
    Fabric workspace (cross-tenant case). When ``None``, MSAL resolves
    the user's home tenant. On Windows this typically completes silently
    via SSO if the user is already signed in to Edge.
    """
    if tenant_id:
        return InteractiveBrowserCredential(tenant_id=tenant_id)
    return InteractiveBrowserCredential()


@st.cache_resource(show_spinner="\U0001F6E0\uFE0F Building orchestrator…")
def _get_orchestrator(_fabric_credential, _llm_credential, config: OrchestratorConfig):
    # ``_get_last_result`` lives in session state so callbacks can write to
    # it without hashing the orchestrator instance itself.
    def _on_fabric_result(result: FabricToolResult) -> None:
        st.session_state["_last_fabric_result"] = result

    agent = build_orchestrator(
        config,
        _fabric_credential,
        llm_credential=_llm_credential,
        on_fabric_result=_on_fabric_result,
    )
    return agent


try:
    fabric_credential = _get_fabric_credential(CONFIG.tenant_id)
    llm_credential = _get_llm_credential(CONFIG.llm_tenant_id)
    orchestrator = _get_orchestrator(fabric_credential, llm_credential, CONFIG)
except Exception as exc:  # noqa: BLE001 — surface any setup error
    st.error(f"Initialization failed: {exc}")
    if st.button("\U0001F501 Retry sign-in"):
        _get_fabric_credential.clear()
        _get_llm_credential.clear()
        _get_orchestrator.clear()
        st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
if "thread_name" not in st.session_state:
    st.session_state.thread_name = f"orchestrator-{uuid.uuid4().hex[:8]}"
if "messages" not in st.session_state:
    st.session_state.messages = []

# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Session")
    st.write("**Tenant A ID**")
    st.code(CONFIG.tenant_id, language="text")
    st.write("**Data Agent URL**")
    st.code(CONFIG.data_agent_url, language="text")
    st.write("**Azure AI Foundry**")
    st.code(
        f"{CONFIG.azure_openai_endpoint}\nDeployment: {CONFIG.azure_openai_deployment}",
        language="text",
    )
    st.write("**Foundry tenant**")
    st.code(CONFIG.llm_tenant_id or "(home tenant — MSAL default)", language="text")
    st.write("**Conversation thread**")
    st.code(st.session_state.thread_name, language="text")

    if st.button("🆕 New conversation", use_container_width=True):
        st.session_state.thread_name = f"orchestrator-{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.rerun()

    if st.button("🚪 Sign out", use_container_width=True):
        _get_fabric_credential.clear()
        _get_llm_credential.clear()
        _get_orchestrator.clear()
        st.session_state.clear()
        st.rerun()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _run_orchestrator(prompt: str) -> str:
    """Block-wait for the async ``Agent.run`` and return its final text."""
    response = asyncio.run(orchestrator.run(prompt))
    return _response_to_text(response)


def _response_to_text(response) -> str:
    """Extract the assistant's final text from an ``AgentResponse``."""
    # AgentResponse exposes .messages — concat all text content blocks.
    parts: list[str] = []
    for message in getattr(response, "messages", []) or []:
        for block in getattr(message, "contents", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
    if parts:
        return "\n".join(parts)
    # Fallback for older response shapes.
    return str(response)


def _render_chart_block(msg_index: int, df: pd.DataFrame) -> None:
    with st.expander(f"📊 Chart ({len(df)} rows × {df.shape[1]} cols)", expanded=True):
        chart_type = st.selectbox(
            "Chart type",
            CHART_TYPES,
            key=f"chart_type_{msg_index}",
            help="Charts are rendered client-side from the data the Fabric Data Agent returned.",
        )
        render_chart(st, df, chart_type)
        with st.popover("Show data"):
            st.dataframe(df, use_container_width=True)


# --------------------------------------------------------------------------- #
# Chat history
# --------------------------------------------------------------------------- #
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("data_records"):
            df = pd.DataFrame(msg["data_records"])
            _render_chart_block(idx, df)

# --------------------------------------------------------------------------- #
# Chat input
# --------------------------------------------------------------------------- #
prompt = st.chat_input("Ask the orchestrator a question…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Orchestrator is thinking…"):
            # Reset any prior tool result so we only attach data from THIS turn.
            st.session_state.pop("_last_fabric_result", None)
            try:
                answer = _run_orchestrator(prompt)
            except Exception as exc:  # noqa: BLE001
                answer = f"❌ Error: {exc}"

        st.markdown(answer)

        df: pd.DataFrame | None = None
        last_result: FabricToolResult | None = st.session_state.get(
            "_last_fabric_result"
        )
        if last_result is not None:
            df = extract_dataframe(last_result.answer, last_result.run_details)
        if df is not None and len(df) > 0:
            _render_chart_block(len(st.session_state.messages), df)

    entry: dict = {"role": "assistant", "content": answer}
    if df is not None and len(df) > 0:
        entry["data_records"] = df.to_dict(orient="records")
    st.session_state.messages.append(entry)
