"""Testes contra o Ollama real. São pulados se o Ollama ou o modelo não estiverem disponíveis."""
import asyncio

import pytest

from jarvis import config, llm

status = asyncio.run(llm.status())
pytestmark = pytest.mark.skipif(not (status["online"] and status["installed"]),
                                reason=f"Ollama offline ou modelo {config.MODEL} não instalado")


async def _collect(messages, tools=None):
    text, calls = "", []
    async for ev in llm.chat(messages, tools):
        if ev["type"] == "token":
            text += ev["text"]
        else:
            calls += ev["calls"]
    return text, calls


def test_real_model_answers_in_portuguese():
    text, _ = asyncio.run(_collect([{"role": "user", "content": "Responda só com a palavra: funcionando"}]))
    assert "funcionando" in text.lower()


def test_real_model_calls_tool():
    tools = [{"type": "function", "function": {
        "name": "obter_hora", "description": "Retorna a data e a hora atuais",
        "parameters": {"type": "object", "properties": {}}}}]
    _, calls = asyncio.run(_collect([{"role": "user", "content": "Que horas são agora?"}], tools))
    assert calls and calls[0]["function"]["name"] == "obter_hora"


def test_model_runs_on_gpu():
    asyncio.run(_collect([{"role": "user", "content": "oi"}]))
    assert asyncio.run(llm.status())["gpu"] is True
