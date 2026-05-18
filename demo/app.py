"""Streamlit chat UI for a Microsoft Fabric Data Agent.

This demo follows the official Microsoft Learn pattern:
https://learn.microsoft.com/en-us/fabric/data-science/consume-data-agent-python

The user signs in interactively with their own Microsoft Entra ID account
(via `InteractiveBrowserCredential`). Because the credential is created with
`tenant_id=TENANT_A`, the user can pick *any* account that has access to
Tenant A — including guest accounts from another tenant (Tenant B) — which
makes this a true cross-tenant scenario:

    [User in Tenant B]  →  sign in to Tenant A  →  call Fabric Data Agent in Tenant A
"""

from __future__ import annotations

import os
import uuid

import streamlit as st
from dotenv import load_dotenv

# Load TENANT_ID and DATA_AGENT_URL from .env next to this script.
load_dotenv()

from fabric_data_agent_client import FabricDataAgentClient

TENANT_ID = os.getenv("TENANT_ID", "").strip()
DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "").strip()

# -----------------------------------------------------------------------------
# Page chrome
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Fabric Data Agent — Cross-Tenant",
    page_icon="💬",
    layout="centered",
)
st.title("💬 Fabric Data Agent — Cross-Tenant Demo")
st.caption(
    "Sign in with your Entra ID account, then chat with a Microsoft Fabric "
    "Data Agent that lives in another tenant."
)

# -----------------------------------------------------------------------------
# Config validation
# -----------------------------------------------------------------------------
missing = [name for name, value in (("TENANT_ID", TENANT_ID), ("DATA_AGENT_URL", DATA_AGENT_URL)) if not value]
if missing:
    st.error(
        f"Missing required environment variable(s): {', '.join(missing)}.\n\n"
        "Copy `.env.example` to `.env` in the `demo/` folder and fill in the values, "
        "then restart the app."
    )
    st.stop()

# -----------------------------------------------------------------------------
# Cached client (browser opens only on the first call per Streamlit process)
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner="🔐 Opening browser for Entra ID sign-in…")
def get_client(tenant_id: str, data_agent_url: str) -> FabricDataAgentClient:
    return FabricDataAgentClient(tenant_id=tenant_id, data_agent_url=data_agent_url)


try:
    client = get_client(TENANT_ID, DATA_AGENT_URL)
except Exception as exc:  # noqa: BLE001 — surface any auth error to the UI
    st.error(f"Authentication failed: {exc}")
    if st.button("🔁 Retry sign-in"):
        get_client.clear()
        st.rerun()
    st.stop()

# -----------------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------------
if "thread_name" not in st.session_state:
    # Stable thread name → conversation context persists across turns in this session.
    st.session_state.thread_name = f"streamlit-{uuid.uuid4().hex[:8]}"
if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("Session")
    st.write("**Tenant A ID**")
    st.code(TENANT_ID, language="text")
    st.write("**Data Agent URL**")
    st.code(DATA_AGENT_URL, language="text")
    st.write("**Conversation thread**")
    st.code(st.session_state.thread_name, language="text")

    if st.button("🆕 New conversation", use_container_width=True):
        st.session_state.thread_name = f"streamlit-{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.rerun()

    if st.button("🚪 Sign out", use_container_width=True):
        # Clear cached client → next request will open the browser again.
        get_client.clear()
        st.session_state.messages = []
        st.rerun()

# -----------------------------------------------------------------------------
# Chat history
# -----------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -----------------------------------------------------------------------------
# Chat input
# -----------------------------------------------------------------------------
prompt = st.chat_input("Ask a question about your data…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Asking the data agent…"):
            try:
                answer = client.ask(prompt, thread_name=st.session_state.thread_name)
            except Exception as exc:  # noqa: BLE001 — surface tool errors to user
                answer = f"❌ Error: {exc}"
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
