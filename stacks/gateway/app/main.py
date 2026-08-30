from fastapi import FastAPI
from pydantic import BaseModel
import httpx

app = FastAPI()

class AskRequest(BaseModel):
    text: str
    image: str | None = None
    mode: str = "quick"

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.post("/v1/ask")
def ask(req: AskRequest):
    r = httpx.post(
        "http://ollama:11434/api/generate",
        json={
            "model": "qwen3-vl-atlas:latest",
            "prompt": req.text,
            "stream": False,
        },
        timeout=120,
    )
    data = r.json()
    return {"answer": data["response"]}
