import hashlib
import json
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse

app = FastAPI()

client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

SKILLS_DIR = Path("skills")
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

# In-memory cache: hash -> {"output": str, "model": str, "usage": dict}
_mem_cache: dict[str, dict] = {}


def _cache_key(skill: str, user_input: str, model: str) -> str:
    """Deterministic hash of (skill, input, model)."""
    raw = json.dumps({"skill": skill, "input": user_input, "model": model}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> dict | None:
    """Check memory, then disk."""
    if key in _mem_cache:
        return _mem_cache[key]
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text())
        _mem_cache[key] = data  # promote to memory
        return data
    return None


def cache_set(key: str, data: dict):
    """Write to memory and disk."""
    _mem_cache[key] = data
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(data))


# Pre-loaded skills: add .md files to the skills/ directory
# Explicit ordering; unlisted files appear at the end alphabetically
SKILL_ORDER = ["office-hours", "dbcd", "ceo-review"]


def load_skills() -> dict[str, str]:
    skills = {}
    if SKILLS_DIR.is_dir():
        for f in sorted(SKILLS_DIR.glob("*.md")):
            skills[f.stem] = f.read_text()
    # Return in explicit order
    ordered = {}
    for name in SKILL_ORDER:
        if name in skills:
            ordered[name] = skills.pop(name)
    for name in sorted(skills):
        ordered[name] = skills[name]
    return ordered


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("static/index.html").read_text()


@app.get("/skills")
async def list_skills():
    return load_skills()


@app.post("/run")
async def run(request: Request):
    body = await request.json()
    skill_content = body.get("skill", "")
    user_input = body.get("input", "")
    model = body.get("model", "claude-opus-4-6")

    if not user_input.strip():
        return {"error": "Input text is required"}

    system_prompt = skill_content if skill_content.strip() else "You are a helpful assistant."

    # Check cache
    key = _cache_key(system_prompt, user_input, model)
    cached = cache_get(key)
    if cached:
        def stream_cached():
            yield f"data: {json.dumps({'type': 'text', 'text': cached['output']})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'model': cached['model'], 'usage': cached['usage'], 'cached': True})}\n\n"

        return StreamingResponse(
            stream_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Call Claude API with streaming
    def stream_response():
        full_text = ""
        with client.messages.stream(
            model=model,
            max_tokens=16384,
            system=system_prompt,
            messages=[{"role": "user", "content": user_input}],
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"

            # Send final message with usage info
            final = stream.get_final_message()
            usage = {
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            }
            yield f"data: {json.dumps({'type': 'done', 'model': final.model, 'usage': usage})}\n\n"

            # Save to cache after successful completion
            cache_set(key, {"output": full_text, "model": final.model, "usage": usage})

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
