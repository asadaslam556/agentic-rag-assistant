import pytest

from agentic_rag.agent.parser import ParserError, extract_first_json


def test_plain_json():
    assert extract_first_json('{"action": "finish"}') == {"action": "finish"}


def test_fenced_json_with_prose():
    text = 'Sure, here is my plan:\n```json\n{"action": "vector_search", "action_input": {"query": "x"}}\n```\nDone.'
    assert extract_first_json(text)["action"] == "vector_search"


def test_braces_inside_strings_are_handled():
    text = 'noise {"thought": "use {curly} braces", "action": "finish"} trailing'
    assert extract_first_json(text)["thought"] == "use {curly} braces"


def test_invalid_input_raises():
    with pytest.raises(ParserError):
        extract_first_json("no json here at all")
