# Instalação no Windows 11

Requisitos verificados nesta máquina: Windows 11 Pro, Python 3.11.9, Ollama 0.40.5, driver AMD com Vulkan 1.4.

## 1. Ollama
1. Instale pelo site oficial (https://ollama.com/download). Ele roda como app do usuário e escuta só em `127.0.0.1:11434`.
2. Baixe o modelo: `ollama pull qwen3.5:4b` (~3,4 GB).
3. Confirme a GPU: depois de usar o modelo uma vez, `ollama ps` deve mostrar `100% GPU`.
   Se mostrar CPU, veja [TROUBLESHOOTING.md](TROUBLESHOOTING.md#modelo-roda-na-cpu).

## 2. Python
Python 3.11 (https://www.python.org/downloads/windows/). Nenhum pacote é instalado no Python global: tudo vai para `.venv` dentro do projeto.

## 3. Jarvis
1. Execute `iniciar.bat`. Ele cria a `.venv`, instala `requirements.txt`, pede a senha e abre o navegador.
2. (Opcional) Copie `.env.example` para `.env` para mudar modelo, porta etc.

## 4. Voz (opcional, recomendado)
`.venv\Scripts\python.exe -m jarvis.voice` baixa o Whisper e o Kokoro para `data/models` (~580 MB).
A fonética do português vem embutida no pacote `espeakng-loader`; não é preciso instalar o eSpeak no Windows.

## Espaço em disco
| Item | Tamanho |
|---|---|
| qwen3.5:4b | 3,4 GB |
| `.venv` completa (voz, OpenCV, Google, testes) | ~525 MB (medido em 16/10/2026) |
| Modelos de voz (Whisper small + Kokoro int8) | ~580 MB |
| Gatilho "Sarah" (Whisper base) | ~145 MB |

## O que o Jarvis NÃO faz na instalação
- Não instala serviço do Windows nem inicialização automática.
- Não altera o firewall nem abre portas.
- Não precisa de administrador.
- Não instala nada fora da pasta do projeto (exceto o que você instalar à mão: Ollama e Python).

## Desinstalar
`parar.bat`, depois apague a pasta do projeto (inclui `data/` com o histórico). Para remover o modelo: `ollama rm qwen3.5:4b`.
