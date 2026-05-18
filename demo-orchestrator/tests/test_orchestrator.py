"""Unit tests for orchestrator config + factory wiring."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from agent_framework import Agent

from orchestrator import (
    MANAGER_INSTRUCTIONS,
    OrchestratorConfig,
    build_orchestrator,
)


# --------------------------------------------------------------------------- #
# OrchestratorConfig.from_env
# --------------------------------------------------------------------------- #


_ENV_VARS = (
    "TENANT_ID",
    "DATA_AGENT_URL",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe orchestrator env vars before each test so .env doesn't leak in."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_config_from_env_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_ID", "tenant-a")
    monkeypatch.setenv("DATA_AGENT_URL", "https://example/openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aoai.example")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

    cfg = OrchestratorConfig.from_env()
    assert cfg.tenant_id == "tenant-a"
    assert cfg.data_agent_url == "https://example/openai"
    assert cfg.azure_openai_endpoint == "https://aoai.example"
    assert cfg.azure_openai_deployment == "gpt-4o-mini"
    assert cfg.azure_openai_api_version == "2025-04-01-preview"


def test_config_from_env_uses_default_api_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TENANT_ID", "tenant-a")
    monkeypatch.setenv("DATA_AGENT_URL", "https://example/openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aoai.example")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    cfg = OrchestratorConfig.from_env()
    assert cfg.azure_openai_api_version == "2024-12-01-preview"


def test_config_from_env_reports_all_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TENANT_ID", "tenant-a")  # only this one set
    with pytest.raises(RuntimeError) as excinfo:
        OrchestratorConfig.from_env()
    msg = str(excinfo.value)
    assert "DATA_AGENT_URL" in msg
    assert "AZURE_OPENAI_ENDPOINT" in msg
    assert "AZURE_OPENAI_DEPLOYMENT" in msg
    assert "TENANT_ID" not in msg  # this one WAS set


def test_config_from_env_treats_whitespace_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TENANT_ID", "   ")
    monkeypatch.setenv("DATA_AGENT_URL", "https://example/openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aoai.example")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    with pytest.raises(RuntimeError) as excinfo:
        OrchestratorConfig.from_env()
    assert "TENANT_ID" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# build_orchestrator
# --------------------------------------------------------------------------- #


def _make_config() -> OrchestratorConfig:
    return OrchestratorConfig(
        tenant_id="tenant-a",
        data_agent_url="https://example/openai",
        azure_openai_endpoint="https://aoai.example",
        azure_openai_deployment="gpt-4o-mini",
        azure_openai_api_version="2024-12-01-preview",
    )


def test_build_orchestrator_returns_agent_with_fabric_tool() -> None:
    cfg = _make_config()
    fabric_client = MagicMock()
    chat_client = MagicMock()

    agent = build_orchestrator(
        cfg,
        credential=MagicMock(),
        fabric_client=fabric_client,
        chat_client=chat_client,
    )

    assert isinstance(agent, Agent)
    assert agent.name == "FabricOrchestrator"
    tools = agent.default_options.get("tools") or []
    tool_names = {t.name for t in tools if hasattr(t, "name")}
    assert "ask_fabric_data_agent" in tool_names


def test_build_orchestrator_uses_provided_instructions() -> None:
    cfg = _make_config()
    agent = build_orchestrator(
        cfg,
        credential=MagicMock(),
        fabric_client=MagicMock(),
        chat_client=MagicMock(),
        instructions="Custom system prompt.",
    )
    assert agent.default_options.get("instructions") == "Custom system prompt."


def test_build_orchestrator_default_instructions_mention_tool() -> None:
    # Sanity: the default system prompt actually tells the LLM about the tool.
    assert "ask_fabric_data_agent" in MANAGER_INSTRUCTIONS


def test_build_orchestrator_accepts_extra_tools() -> None:
    from agent_framework import tool

    @tool(name="echo", description="Echo the input.")
    def echo(text: str) -> str:
        return text

    cfg = _make_config()
    agent = build_orchestrator(
        cfg,
        credential=MagicMock(),
        fabric_client=MagicMock(),
        chat_client=MagicMock(),
        extra_tools=[echo],
    )
    tools = agent.default_options.get("tools") or []
    tool_names = {t.name for t in tools if hasattr(t, "name")}
    assert {"ask_fabric_data_agent", "echo"}.issubset(tool_names)
