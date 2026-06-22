"""Offline tests for the LLM-reply parsing (no CLI, no network).

Focus: _extract_ops must dig the real {"ops": [...]} object out of an *agentic* CLI's
reply (e.g. GitHub copilot), which interleaves tool-call transcript noise, "permission
denied" lines, and stray {...} fragments around the actual answer.
"""

from __future__ import annotations

import pytest

from okf_wiki import llm


def test_extract_ops_clean_reply():
    reply = '{"ops": [{"op": "skip", "type": "", "title": "", "rel_path": "", "description": "", "tags": [], "body": ""}]}'
    assert llm._extract_ops(reply)["ops"][0]["op"] == "skip"


def test_extract_ops_ignores_agentic_tool_noise():
    """A copilot-style reply: a failed shell tool-call (with a stray single-quoted
    {...}), a permission-denied line, THEN the real ops JSON at the end."""
    reply = (
        "✗ Evaluate ingest result (shell)\n"
        '│ python -c "\n'
        "│ result = { 'ops': [] }\n"
        "└ Permission denied and could not request permission from user\n"
        "\n"
        '{"ops": [{"op": "skip", "type": "", "title": "", "rel_path": "", '
        '"description": "", "tags": [], "body": ""}]}\n'
    )
    ops = llm._extract_ops(reply)["ops"]
    assert ops == [
        {"op": "skip", "type": "", "title": "", "rel_path": "",
         "description": "", "tags": [], "body": ""}
    ]


def test_extract_ops_prefers_last_real_object():
    """When several balanced {...} objects appear, the genuine final answer wins."""
    reply = (
        '{"ops": []}\n'
        "✗ placeholder (shell)\n"
        '{"ops": [{"op": "write", "type": "Concept", "title": "Espresso Milk Drinks", '
        '"rel_path": "concepts/espresso-milk-drinks.md", "description": "d", "tags": [], '
        '"body": "Body with a brace { and a quote \\" inside.[^s1]"}]}'
    )
    ops = llm._extract_ops(reply)["ops"]
    assert len(ops) == 1
    assert ops[0]["title"] == "Espresso Milk Drinks"
    assert "{" in ops[0]["body"]  # braces inside JSON strings handled correctly


def test_extract_ops_raises_when_no_ops():
    with pytest.raises(RuntimeError):
        llm._extract_ops("just some prose, no json here")


def test_json_object_spans_is_string_aware():
    # A '}' inside a JSON string must not close the object early.
    spans = llm._json_object_spans('prefix {"k": "a } b", "n": 1} suffix {"m": 2}')
    assert spans == ['{"k": "a } b", "n": 1}', '{"m": 2}']
