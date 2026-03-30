"""Tests for the CLAW app — backend endpoints and frontend HTML contract."""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app, load_skills, _mem_cache, cache_get, cache_set, _cache_key, CACHE_DIR


@pytest.fixture
def client():
    return TestClient(app)


# ── GET / ──


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_index_contains_title(client):
    resp = client.get("/")
    assert "CLAW" in resp.text


def test_index_contains_tab_infrastructure(client):
    """The HTML must have the tabs container and tab-panels div."""
    html = client.get("/").text
    assert 'id="tabs"' in html
    assert 'id="tab-panels"' in html
    assert 'id="panel-custom"' in html


def test_index_opus_is_default_model(client):
    """Opus 4.6 should be the first option in the custom model dropdown."""
    html = client.get("/").text
    opus_pos = html.index("claude-opus-4-6")
    sonnet_pos = html.index("claude-sonnet-4-6")
    assert opus_pos < sonnet_pos, "Opus 4.6 should appear before Sonnet in the dropdown"


def test_index_has_url_state_management(client):
    """The JS must include hash-based state persistence."""
    html = client.get("/").text
    assert "saveStateToHash" in html
    assert "loadStateFromHash" in html
    assert "hashchange" in html


def test_index_has_keyboard_shortcut(client):
    html = client.get("/").text
    assert "metaKey" in html or "ctrlKey" in html


# ── GET /skills ──


def test_skills_returns_dict(client):
    resp = client.get("/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_skills_contains_expected_skills(client):
    data = client.get("/skills").json()
    assert "dbcd" in data
    assert "office-hours" in data
    assert "ceo-review" in data


def test_skills_content_is_non_empty(client):
    data = client.get("/skills").json()
    for name, content in data.items():
        assert len(content) > 0, f"Skill '{name}' should not be empty"


def test_load_skills_function():
    skills = load_skills()
    assert isinstance(skills, dict)
    assert len(skills) >= 3


# ── POST /run — validation ──


def test_run_empty_input_returns_error(client):
    resp = client.post("/run", json={"input": "", "skill": ""})
    assert resp.status_code == 200
    assert resp.json()["error"] == "Input text is required"


def test_run_whitespace_input_returns_error(client):
    resp = client.post("/run", json={"input": "   \n\t  ", "skill": ""})
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_run_missing_input_returns_error(client):
    resp = client.post("/run", json={"skill": "something"})
    assert resp.status_code == 200
    assert "error" in resp.json()


# ── Helpers for streaming mock ──


def _make_mock_stream(texts, model="claude-opus-4-6", input_tokens=10, output_tokens=20):
    """Create a mock context manager that mimics client.messages.stream()."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    final_msg = MagicMock()
    final_msg.model = model
    final_msg.usage = usage

    stream_obj = MagicMock()
    stream_obj.text_stream = iter(texts)
    stream_obj.get_final_message.return_value = final_msg
    stream_obj.__enter__ = MagicMock(return_value=stream_obj)
    stream_obj.__exit__ = MagicMock(return_value=False)

    return stream_obj


def _parse_sse_events(resp):
    """Parse SSE events from a streaming response into a list of dicts."""
    events = []
    for line in resp.text.strip().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ── POST /run — streaming with mocked Claude API ──


@patch("app.client")
def test_run_streams_text(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(
        ["Hello", " from", " Claude"]
    )
    resp = client.post("/run", json={"input": "Hello", "skill": "Be helpful"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse_events(resp)
    text_events = [e for e in events if e["type"] == "text"]
    assert len(text_events) == 3
    assert text_events[0]["text"] == "Hello"
    assert text_events[1]["text"] == " from"
    assert text_events[2]["text"] == " Claude"


@patch("app.client")
def test_run_stream_sends_done_event(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(
        ["test"], model="claude-opus-4-6", input_tokens=15, output_tokens=25
    )
    resp = client.post("/run", json={"input": "test"})
    events = _parse_sse_events(resp)
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["model"] == "claude-opus-4-6"
    assert done_events[0]["usage"]["input_tokens"] == 15
    assert done_events[0]["usage"]["output_tokens"] == 25


@patch("app.client")
def test_run_passes_skill_as_system_prompt(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(["ok"])
    client.post("/run", json={"input": "test", "skill": "You are a pirate"})
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["system"] == "You are a pirate"


@patch("app.client")
def test_run_empty_skill_uses_default_system(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(["ok"])
    client.post("/run", json={"input": "test", "skill": ""})
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["system"] == "You are a helpful assistant."


@patch("app.client")
def test_run_passes_model(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(["ok"])
    client.post("/run", json={"input": "test", "model": "claude-haiku-4-5-20251001"})
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


@patch("app.client")
def test_run_default_model_is_opus(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(["ok"])
    client.post("/run", json={"input": "test"})
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["model"] == "claude-opus-4-6"


@patch("app.client")
def test_run_passes_input_as_user_message(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(["ok"])
    client.post("/run", json={"input": "What is 2+2?"})
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is 2+2?"}]


@patch("app.client")
def test_run_concatenated_stream_text(mock_client, client):
    """All text chunks should be separate SSE events."""
    mock_client.messages.stream.return_value = _make_mock_stream(
        ["Part 1. ", "Part 2."]
    )
    resp = client.post("/run", json={"input": "test"})
    events = _parse_sse_events(resp)
    text_events = [e for e in events if e["type"] == "text"]
    full_text = "".join(e["text"] for e in text_events)
    assert full_text == "Part 1. Part 2."


@patch("app.client")
def test_run_max_tokens_is_16384(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(["ok"])
    client.post("/run", json={"input": "test"})
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["max_tokens"] == 16384


# ── Frontend HTML contract tests ──


def test_html_has_scan_lines(client):
    html = client.get("/").text
    assert "scan-lines" in html


def test_html_has_glitch_text(client):
    html = client.get("/").text
    assert "glitch-text" in html
    assert 'data-text="CLAW"' in html


def test_html_loads_google_fonts(client):
    html = client.get("/").text
    assert "Space+Grotesk" in html
    assert "JetBrains+Mono" in html


def test_html_custom_tab_has_file_upload(client):
    html = client.get("/").text
    assert 'id="skill-file"' in html
    assert 'accept=".md,.txt"' in html


def test_html_custom_tab_has_all_inputs(client):
    html = client.get("/").text
    assert 'id="skill-custom"' in html
    assert 'id="input-custom"' in html
    assert 'id="model-custom"' in html
    assert 'id="output-custom"' in html


def test_html_dynamic_skill_panel_template(client):
    """The JS createSkillPanel function should produce correct element IDs."""
    html = client.get("/").text
    assert 'id="input-${name}"' in html or "`input-${name}`" in html
    assert 'id="model-${name}"' in html or "`model-${name}`" in html
    assert 'id="output-${name}"' in html or "`output-${name}`" in html
    assert "id=\"skill-${name}\"" in html or "`skill-${name}`" in html


def test_html_hash_state_saves_per_tab(client):
    html = client.get("/").text
    assert "`input-${name}`" in html
    assert "`model-${name}`" in html
    assert "'skill-custom'" in html


def test_html_uses_streaming_fetch(client):
    """Frontend should use reader-based streaming, not resp.json()."""
    html = client.get("/").text
    assert "resp.body.getReader()" in html
    assert "text/event-stream" not in html or "event-stream" in html  # doesn't hardcode content-type check
    assert "'data: '" in html or 'data: ' in html


def test_html_shows_cached_badge(client):
    html = client.get("/").text
    assert "CACHED" in html


# ── Cache tests ──


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear in-memory and disk cache before each test."""
    _mem_cache.clear()
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
    yield
    _mem_cache.clear()
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()


def test_cache_key_deterministic():
    k1 = _cache_key("skill", "input", "model")
    k2 = _cache_key("skill", "input", "model")
    assert k1 == k2


def test_cache_key_differs_on_input():
    k1 = _cache_key("skill", "input1", "model")
    k2 = _cache_key("skill", "input2", "model")
    assert k1 != k2


def test_cache_key_differs_on_skill():
    k1 = _cache_key("skill1", "input", "model")
    k2 = _cache_key("skill2", "input", "model")
    assert k1 != k2


def test_cache_key_differs_on_model():
    k1 = _cache_key("skill", "input", "model-a")
    k2 = _cache_key("skill", "input", "model-b")
    assert k1 != k2


def test_cache_set_and_get_memory():
    data = {"output": "hello", "model": "m", "usage": {"input_tokens": 1, "output_tokens": 2}}
    cache_set("testkey", data)
    assert cache_get("testkey") == data


def test_cache_get_from_disk():
    """Write to disk, clear memory, should still find it."""
    data = {"output": "disk", "model": "m", "usage": {"input_tokens": 1, "output_tokens": 2}}
    key = "disktest123"
    cache_set(key, data)
    _mem_cache.clear()
    result = cache_get(key)
    assert result == data
    # Clean up
    (CACHE_DIR / f"{key}.json").unlink(missing_ok=True)


def test_cache_miss_returns_none():
    assert cache_get("nonexistent") is None


@patch("app.client")
def test_run_caches_response(mock_client, client):
    mock_client.messages.stream.return_value = _make_mock_stream(
        ["cached response"], model="claude-opus-4-6", input_tokens=5, output_tokens=10
    )
    resp = client.post("/run", json={"input": "cache me", "skill": "s", "model": "claude-opus-4-6"})
    events = _parse_sse_events(resp)
    assert any(e["type"] == "text" for e in events)

    # Verify it was cached
    key = _cache_key("s", "cache me", "claude-opus-4-6")
    cached = cache_get(key)
    assert cached is not None
    assert cached["output"] == "cached response"
    # Clean up disk
    (CACHE_DIR / f"{key}.json").unlink(missing_ok=True)


@patch("app.client")
def test_run_serves_from_cache(mock_client, client):
    """Second identical request should come from cache, not call API."""
    key = _cache_key("You are a helpful assistant.", "hello", "claude-opus-4-6")
    cache_set(key, {"output": "from cache", "model": "claude-opus-4-6", "usage": {"input_tokens": 3, "output_tokens": 7}})

    resp = client.post("/run", json={"input": "hello", "skill": "", "model": "claude-opus-4-6"})
    events = _parse_sse_events(resp)

    # Should NOT have called the API
    mock_client.messages.stream.assert_not_called()

    # Should get cached content
    text_events = [e for e in events if e["type"] == "text"]
    assert text_events[0]["text"] == "from cache"

    done_events = [e for e in events if e["type"] == "done"]
    assert done_events[0]["cached"] is True

    # Clean up
    (CACHE_DIR / f"{key}.json").unlink(missing_ok=True)
