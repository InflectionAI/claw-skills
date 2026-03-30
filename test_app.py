"""Tests for the CLAW app — backend endpoints and frontend HTML contract."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app, load_skills


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
    # Find the custom model select — Opus should come before Sonnet
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
    """Cmd+Enter shortcut should be wired up."""
    html = client.get("/").text
    assert "metaKey" in html or "ctrlKey" in html


# ── GET /skills ──


def test_skills_returns_dict(client):
    resp = client.get("/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_skills_contains_expected_skills(client):
    """The skills/ directory should have dbcd, office-hours, ceo-review."""
    data = client.get("/skills").json()
    assert "dbcd" in data
    assert "office-hours" in data
    assert "ceo-review" in data


def test_skills_content_is_non_empty(client):
    data = client.get("/skills").json()
    for name, content in data.items():
        assert len(content) > 0, f"Skill '{name}' should not be empty"


def test_load_skills_function():
    """Directly test the load_skills helper."""
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


# ── POST /run — with mocked Claude API ──


def _make_mock_message(text="Hello from Claude", model="claude-opus-4-6", input_tokens=10, output_tokens=20):
    """Create a mock Anthropic message response."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    msg = MagicMock()
    msg.content = [block]
    msg.model = model
    msg.usage = usage
    return msg


@patch("app.client")
def test_run_success(mock_client, client):
    mock_client.messages.create.return_value = _make_mock_message(
        text="Test response", model="claude-opus-4-6"
    )
    resp = client.post("/run", json={"input": "Hello", "skill": "Be helpful"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["output"] == "Test response"
    assert data["model"] == "claude-opus-4-6"
    assert data["usage"]["input_tokens"] == 10
    assert data["usage"]["output_tokens"] == 20


@patch("app.client")
def test_run_passes_skill_as_system_prompt(mock_client, client):
    mock_client.messages.create.return_value = _make_mock_message()
    client.post("/run", json={"input": "test", "skill": "You are a pirate"})
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["system"] == "You are a pirate"


@patch("app.client")
def test_run_empty_skill_uses_default_system(mock_client, client):
    mock_client.messages.create.return_value = _make_mock_message()
    client.post("/run", json={"input": "test", "skill": ""})
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["system"] == "You are a helpful assistant."


@patch("app.client")
def test_run_passes_model(mock_client, client):
    mock_client.messages.create.return_value = _make_mock_message()
    client.post("/run", json={"input": "test", "model": "claude-haiku-4-5-20251001"})
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


@patch("app.client")
def test_run_default_model_is_opus(mock_client, client):
    mock_client.messages.create.return_value = _make_mock_message()
    client.post("/run", json={"input": "test"})
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-opus-4-6"


@patch("app.client")
def test_run_passes_input_as_user_message(mock_client, client):
    mock_client.messages.create.return_value = _make_mock_message()
    client.post("/run", json={"input": "What is 2+2?"})
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is 2+2?"}]


@patch("app.client")
def test_run_multi_block_response(mock_client, client):
    """When Claude returns multiple text blocks, they should be concatenated."""
    block1 = MagicMock()
    block1.type = "text"
    block1.text = "Part 1. "
    block2 = MagicMock()
    block2.type = "text"
    block2.text = "Part 2."
    block3 = MagicMock()
    block3.type = "tool_use"  # non-text block, should be skipped

    msg = _make_mock_message()
    msg.content = [block1, block2, block3]
    mock_client.messages.create.return_value = msg

    resp = client.post("/run", json={"input": "test"})
    assert resp.json()["output"] == "Part 1. Part 2."


@patch("app.client")
def test_run_api_error_raises(mock_client, client):
    mock_client.messages.create.side_effect = Exception("API key invalid")
    with pytest.raises(Exception, match="API key invalid"):
        client.post("/run", json={"input": "test"}, timeout=5)


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
    # Check that the template uses the right ID patterns
    assert 'id="input-${name}"' in html or "`input-${name}`" in html
    assert 'id="model-${name}"' in html or "`model-${name}`" in html
    assert 'id="output-${name}"' in html or "`output-${name}`" in html
    assert "id=\"skill-${name}\"" in html or "`skill-${name}`" in html


def test_html_hash_state_saves_per_tab(client):
    """Hash state should save input-{tab} and model-{tab} for each tab."""
    html = client.get("/").text
    assert "`input-${name}`" in html
    assert "`model-${name}`" in html
    assert "'skill-custom'" in html
