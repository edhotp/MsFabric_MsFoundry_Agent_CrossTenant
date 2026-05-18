"""Chart helpers for the Fabric Data Agent Streamlit demo.

The Fabric Data Agent does **not** generate chart images itself
(see https://learn.microsoft.com/fabric/data-science/concept-data-agent).
It returns natural-language answers plus the SQL/DAX/KQL it ran and a text
preview of the rows. We render charts on the client side from whichever
tabular form the agent gave us:

1. A GitHub-flavored markdown table inside the assistant's text answer
   (the most common shape for tabular Lakehouse / Warehouse questions).
2. As a fallback, the ``sql_data_previews`` list returned by
   ``FabricDataAgentClient.get_run_details()`` — each entry is already a
   list of markdown-table lines.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# -----------------------------------------------------------------------------
# Answer extraction
# -----------------------------------------------------------------------------
def extract_answer_text(run_details: dict) -> str:
    """Return the latest assistant text from a ``get_run_details()`` result.

    Mirrors the MS Learn sample
    (https://learn.microsoft.com/fabric/data-science/consume-data-agent-python#ask-the-data-agent-a-question)
    but unwraps OpenAI's typed content blocks down to a plain string.
    """
    messages = (run_details.get("messages") or {}).get("data") or []
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []):
            if block.get("type") == "text":
                value = (block.get("text") or {}).get("value") or ""
                if value:
                    return value
    return "(no answer returned)"


# -----------------------------------------------------------------------------
# Markdown-table parsing
# -----------------------------------------------------------------------------
_MD_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _split_row(line: str) -> list[str]:
    """Split a markdown table row on ``|``, stripping the outer pipes."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_markdown_table(text: str) -> Optional[pd.DataFrame]:
    """Parse the first well-formed markdown table found in ``text``.

    Returns ``None`` when no table with a header + separator + at least one
    body row is present.
    """
    lines = text.splitlines()
    n = len(lines)
    for i in range(n - 1):
        header_line = lines[i]
        if "|" not in header_line:
            continue
        if not _MD_SEP_RE.match(lines[i + 1]):
            continue

        header = _split_row(header_line)
        rows: list[list[str]] = []
        for body_line in lines[i + 2 :]:
            if body_line.strip() == "":
                break
            if "|" not in body_line:
                break
            cells = _split_row(body_line)
            # Tolerate trailing/leading empty cells from "| a | b |" style
            if len(cells) == len(header) + 1 and cells[-1] == "":
                cells = cells[:-1]
            if len(cells) == len(header) + 1 and cells[0] == "":
                cells = cells[1:]
            if len(cells) != len(header):
                continue
            rows.append(cells)

        if not rows:
            continue

        df = pd.DataFrame(rows, columns=header)
        _coerce_numeric_inplace(df)
        return df
    return None


def _coerce_numeric_inplace(df: pd.DataFrame) -> None:
    """Best-effort numeric coercion so charts have proper axes.

    A column is converted to numeric only if at least half of its non-empty
    values parse cleanly (after stripping commas, currency, and ``%``).
    """
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        stripped = (
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.replace("€", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.strip()
        )
        coerced = pd.to_numeric(stripped, errors="coerce")
        non_empty = df[col].astype(str).str.strip().ne("").sum()
        if non_empty > 0 and coerced.notna().sum() >= max(1, non_empty // 2):
            df[col] = coerced


# -----------------------------------------------------------------------------
# Public extraction API
# -----------------------------------------------------------------------------
def extract_dataframe(
    answer_text: str, run_details: Optional[dict] = None
) -> Optional[pd.DataFrame]:
    """Try to build a DataFrame from the agent's answer.

    Tries the assistant's inline markdown table first (most accurate, already
    formatted by the LLM), then falls back to the structured
    ``sql_data_previews`` if present.
    """
    df = _parse_markdown_table(answer_text)
    if df is not None and len(df) > 0:
        return df

    if not run_details:
        return None

    for preview in run_details.get("sql_data_previews") or []:
        if not preview:
            continue
        if isinstance(preview, list):
            candidate = "\n".join(str(line) for line in preview)
        else:
            candidate = str(preview)
        df = _parse_markdown_table(candidate)
        if df is not None and len(df) > 0:
            return df
    return None


# -----------------------------------------------------------------------------
# Chart rendering
# -----------------------------------------------------------------------------
CHART_TYPES: tuple[str, ...] = ("Auto", "Bar", "Line", "Area", "Scatter", "Table only")


def infer_chart_type(df: pd.DataFrame) -> str:
    """Pick a sensible default chart for ``df``."""
    if df.shape[1] < 2:
        return "Table only"
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    if not numeric_cols:
        return "Table only"
    if not non_numeric_cols and len(numeric_cols) >= 2:
        return "Scatter"
    return "Bar"


def render_chart(st_mod, df: pd.DataFrame, chart_type: str) -> None:
    """Render ``df`` to a Streamlit container.

    ``st_mod`` is the ``streamlit`` module (passed in so this file stays
    import-light and unit-testable).
    """
    if chart_type == "Auto":
        chart_type = infer_chart_type(df)

    if chart_type == "Table only" or df.shape[1] < 2:
        st_mod.dataframe(df, use_container_width=True)
        return

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    x_col = non_numeric_cols[0] if non_numeric_cols else df.columns[0]
    y_cols = numeric_cols if numeric_cols else [c for c in df.columns if c != x_col]

    if not y_cols:
        st_mod.dataframe(df, use_container_width=True)
        return

    chart_fn = {
        "Bar": st_mod.bar_chart,
        "Line": st_mod.line_chart,
        "Area": st_mod.area_chart,
        "Scatter": st_mod.scatter_chart,
    }.get(chart_type, st_mod.bar_chart)

    chart_fn(df, x=x_col, y=y_cols, use_container_width=True)
