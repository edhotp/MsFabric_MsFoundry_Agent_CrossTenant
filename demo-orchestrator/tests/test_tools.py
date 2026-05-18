"""Unit tests for the Fabric Data Agent tool wrapper."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from orchestrator import (
    FabricToolResult,
    build_fabric_data_agent_tool,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _make_run_details(answer_text: str = "Top product is Foo (USD 1,234).") -> dict:
    """Build a minimal ``get_run_details()``-shaped dict the tool can parse."""
    return {
        "question": "fake",
        "run_status": "completed",
        "messages": {
            "data": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": {"value": "fake"}}],
                },
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": {"value": answer_text}}
                    ],
                },
            ]
        },
    }


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.get_run_details.return_value = _make_run_details()
    return client


# --------------------------------------------------------------------------- #
# Tool metadata
# --------------------------------------------------------------------------- #


def test_tool_has_correct_name_and_description(mock_client: MagicMock) -> None:
    tool = build_fabric_data_agent_tool(mock_client)
    assert tool.name == "ask_fabric_data_agent"
    assert "Fabric Data Agent" in tool.description
    schema = tool.to_json_schema_spec()
    assert schema["function"]["name"] == "ask_fabric_data_agent"
    assert "question" in schema["function"]["parameters"]["properties"]
    assert "question" in schema["function"]["parameters"]["required"]


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_tool_returns_extracted_answer_text(mock_client: MagicMock) -> None:
    tool = build_fabric_data_agent_tool(mock_client)
    result = tool.func("What is the top product?")
    assert result == "Top product is Foo (USD 1,234)."
    mock_client.get_run_details.assert_called_once_with(
        "What is the top product?", thread_name="orchestrator"
    )


def test_tool_uses_custom_thread_name(mock_client: MagicMock) -> None:
    tool = build_fabric_data_agent_tool(mock_client, thread_name="my-thread")
    tool.func("question 1")
    mock_client.get_run_details.assert_called_once_with(
        "question 1", thread_name="my-thread"
    )


def test_tool_invokes_on_result_callback(mock_client: MagicMock) -> None:
    captured: list[FabricToolResult] = []

    tool = build_fabric_data_agent_tool(
        mock_client, on_result=captured.append
    )
    result = tool.func("any question")

    assert result == "Top product is Foo (USD 1,234)."
    assert len(captured) == 1
    assert isinstance(captured[0], FabricToolResult)
    assert captured[0].answer == "Top product is Foo (USD 1,234)."
    assert captured[0].run_details["run_status"] == "completed"


def test_tool_swallows_callback_errors(mock_client: MagicMock) -> None:
    """A broken UI callback must NEVER break the tool call."""

    def bad_callback(_: FabricToolResult) -> None:
        raise RuntimeError("UI broke")

    tool = build_fabric_data_agent_tool(mock_client, on_result=bad_callback)
    result = tool.func("any question")
    # Still got the agent's answer even though the callback exploded.
    assert result == "Top product is Foo (USD 1,234)."


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #


def test_tool_handles_empty_question(mock_client: MagicMock) -> None:
    tool = build_fabric_data_agent_tool(mock_client)
    result = tool.func("   ")
    assert "empty" in result.lower()
    mock_client.get_run_details.assert_not_called()


def test_tool_surfaces_error_from_run_details(mock_client: MagicMock) -> None:
    mock_client.get_run_details.return_value = {"error": "boom"}
    tool = build_fabric_data_agent_tool(mock_client)
    result = tool.func("anything")
    assert "boom" in result
    assert "Error" in result


def test_tool_returns_fallback_when_no_assistant_message(
    mock_client: MagicMock,
) -> None:
    mock_client.get_run_details.return_value = {
        "messages": {"data": []},
        "run_status": "completed",
    }
    tool = build_fabric_data_agent_tool(mock_client)
    result = tool.func("anything")
    assert result == "(no answer returned)"


# --------------------------------------------------------------------------- #
# Async invocation through FunctionTool.invoke (end-to-end framework call)
# --------------------------------------------------------------------------- #


def test_tool_invoke_through_framework_returns_content(
    mock_client: MagicMock,
) -> None:
    """Verify the tool plays nicely with the framework's invoke contract."""
    tool = build_fabric_data_agent_tool(mock_client)
    raw = asyncio.run(tool.invoke(arguments={"question": "Hello?"}))
    # invoke returns either str/Any (after parsing) or list[Content].
    # The Fabric tool returns a plain str, so the framework will wrap it.
    flattened: Any
    if isinstance(raw, list):
        flattened = "".join(getattr(c, "text", "") for c in raw)
    else:
        flattened = raw
    assert "Top product is Foo" in str(flattened)
    mock_client.get_run_details.assert_called_once()
