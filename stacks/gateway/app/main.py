from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel
import httpx
import os
import secrets

app = FastAPI()

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-vl-atlas:latest")
GATEWAY_TOKEN = os.environ["GATEWAY_TOKEN"]

class AskRequest(BaseModel):
    text: str
    image: str | None = None
    mode: str = "quick"

@app.get("/healthz")
def health():
    return {"status": "ok"}

def require_token(authorization: str = Header(default="")):
    expected = f"Bearer {GATEWAY_TOKEN}"
    if not secrets.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid or missing token")

@app.post("/v1/ask", dependencies=[Depends(require_token)])
def ask(req: AskRequest):
    if req.mode == "chat":
        num_predict = 600
    else:
        num_predict = 120

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": req.text,
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": num_predict},
    }
    if req.image:
        payload["images"] = [req.image]

    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="ollama unreachable")
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=503, detail="ollama rejected the request")

    data = r.json()
    return {
        "answer": data["response"],
        "total_ms": data["total_duration"] // 1_000_000,
        "load_ms": data["load_duration"] // 1_000_000,
        "prompt_eval_ms": data["prompt_eval_duration"] // 1_000_000,
        "eval_ms": data["eval_duration"] // 1_000_000,
        "prompt_tokens": data["prompt_eval_count"],
        "output_tokens": data["eval_count"],
        }
