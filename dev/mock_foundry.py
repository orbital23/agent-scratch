"""Mock local de Foundry (API v1 compatible con OpenAI) para desarrollar sin cuenta de Azure.

Uso:  uv run python dev/mock_foundry.py
.env: FOUNDRY_ENDPOINT=http://127.0.0.1:8100  y  FOUNDRY_API_KEY=<cualquier valor>

Chat: responde {"intent", "answer"} detectando la intención por palabras clave.
Embeddings: vectores determinísticos por bolsa de palabras; textos con palabras en común quedan cerca.
"""

import base64
import hashlib
import json
import math
import os
import re
import struct
import time
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

# ponytail: heurística naive por palabras clave, suficiente para probar el flujo
RULES = [
    ("sensitive_action", ("bloque", "robaron", "robo", "perdí", "registrar reclamo")),
    ("data_query", ("mis movimientos", "estado de mi reclamo", "estado del reclamo")),
    ("product_question", ("fraude", "contracargo", "plazo", "reclamo", "no reconozco")),
    ("greeting", ("hola", "buenos", "buenas", "gracias", "adiós")),
]

DIM = 1536  # igual que text-embedding-3-small

app = FastAPI(title="mock-foundry")


def _authorize(authorization: str) -> None:
    if not authorization.removeprefix("Bearer ").strip():
        raise HTTPException(401, {"error": {"code": "401", "message": "Falta la API key"}})


@app.post("/openai/v1/chat/completions")
async def chat_completions(request: Request, authorization: str = Header(default="")) -> dict:
    _authorize(authorization)

    body = await request.json()
    text = body["messages"][-1]["content"].lower()
    intent = next((name for name, words in RULES if any(word in text for word in words)), "out_of_scope")
    content = json.dumps({"intent": intent, "answer": f"[mock] intención detectada: {intent}"}, ensure_ascii=False)
    prompt_tokens = sum(len(str(message["content"]).split()) for message in body["messages"])
    completion_tokens = len(content.split())
    return {
        "id": f"mock-{uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body["model"],
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content, "refusal": None},
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@app.post("/openai/v1/embeddings")
async def embeddings(request: Request, authorization: str = Header(default="")) -> dict:
    _authorize(authorization)
    body = await request.json()
    texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
    # el SDK de openai pide base64 por defecto y lo decodifica solo
    as_base64 = body.get("encoding_format") == "base64"
    data = [{"object": "embedding", "index": position, "embedding": _encode(_embed(text), as_base64)} for position, text in enumerate(texts)]
    tokens = sum(len(text.split()) for text in texts)
    return {"object": "list", "data": data, "model": body["model"], "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}


def _embed(text: str) -> list[float]:
    # ponytail: bolsa de palabras con hash, sin semántica real; alcanza para probar el flujo sin Azure
    vector = [0.0] * DIM
    for word in re.findall(r"\w+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / magnitude for value in vector]


def _encode(vector: list[float], as_base64: bool) -> str | list[float]:
    return base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode() if as_base64 else vector


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("MOCK_HOST", "127.0.0.1"), port=8100)