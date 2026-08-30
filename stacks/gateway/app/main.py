from fastapi import FastAPI
from pydantic import BaseModel

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
    return {"message": "stub", "you_said": req.text, "mode": req.mode, "has_image": req.image is not None}
