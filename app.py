from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

SKILLS_DIR = Path("skills")

# Pre-loaded skills: add .md files to the skills/ directory
def load_skills() -> dict[str, str]:
    skills = {}
    if SKILLS_DIR.is_dir():
        for f in sorted(SKILLS_DIR.glob("*.md")):
            skills[f.stem] = f.read_text()
    return skills


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

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_input}],
    )

    output_text = ""
    for block in message.content:
        if block.type == "text":
            output_text += block.text

    return {
        "output": output_text,
        "model": message.model,
        "usage": {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        },
    }
