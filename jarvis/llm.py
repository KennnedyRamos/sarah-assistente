"""Cliente do servidor de inferência. Único módulo acoplado ao Ollama; troque este arquivo para mudar de mecanismo."""
import json

import httpx

from . import config


class LLMError(Exception):
    pass


async def chat(messages: list[dict], tools: list[dict] | None = None):
    """Gera eventos {"type": "token", "text"} e {"type": "tool_calls", "calls"}."""
    body = {"model": config.MODEL, "messages": messages, "stream": True, "think": False,
            "keep_alive": config.KEEP_ALIVE,
            "options": {"num_ctx": config.NUM_CTX, "temperature": config.TEMPERATURE, "top_p": 0.8, "top_k": 20}}
    if tools:
        body["tools"] = tools
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5)) as client:
            async with client.stream("POST", f"{config.LLM_URL}/api/chat", json=body) as r:
                if r.status_code != 200:
                    detail = (await r.aread()).decode(errors="replace")[:300]
                    raise LLMError(f"O Ollama respondeu {r.status_code}: {detail}")
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        raise LLMError("O Ollama mandou uma resposta inválida.") from None
                    if "error" in chunk:
                        raise LLMError(f"Erro do modelo: {chunk['error']}")
                    msg = chunk.get("message", {})
                    if msg.get("content"):
                        yield {"type": "token", "text": msg["content"]}
                    if msg.get("tool_calls"):
                        yield {"type": "tool_calls", "calls": msg["tool_calls"]}
    except httpx.ConnectError:
        raise LLMError(f"Não consegui falar com o Ollama em {config.LLM_URL}. Ele está aberto?") from None
    except httpx.TimeoutException:
        raise LLMError("O modelo demorou demais para responder.") from None
    except httpx.HTTPError:  # ex.: o Ollama fechou ou reiniciou no meio da resposta
        raise LLMError("A conexão com o Ollama caiu no meio da resposta. Tente de novo.") from None


async def status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            tags = (await client.get(f"{config.LLM_URL}/api/tags")).json()
            ps = (await client.get(f"{config.LLM_URL}/api/ps")).json()
    except (httpx.HTTPError, ValueError):
        return {"online": False, "model": config.MODEL}
    loaded = next((m for m in ps.get("models", []) if m.get("name") == config.MODEL), None)
    return {
        "online": True,
        "model": config.MODEL,
        "installed": any(m.get("name") == config.MODEL for m in tags.get("models", [])),
        "loaded": loaded is not None,
        "gpu": bool(loaded and loaded.get("size_vram")),
    }
