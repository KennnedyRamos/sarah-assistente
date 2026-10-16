# Jarvis Local — Arquitetura

Documento vivo. Última revisão: 2026-10-16 (Fase 10).

## 1. Diagnóstico real do computador (medido em 2026-10-15)

| Item | Valor encontrado | Como foi medido |
|---|---|---|
| SO | Windows 11 Pro 10.0.26300, 64 bits | `Win32_OperatingSystem` |
| CPU | AMD Ryzen 7 5700X, 8 núcleos / 16 threads, AVX2 | `Win32_Processor` |
| RAM | 15,9 GB total, **3,8 GB livres** no momento da medição (Opera, VS Code e ChatGPT abertos) | `Win32_OperatingSystem` |
| GPU | AMD Radeon RX 6600 (RDNA2, gfx1032), **8,0 GB VRAM** (7,2 GiB disponíveis) | registro `qwMemorySize` + log do Ollama |
| Driver AMD | 32.0.21045.5002 (16/08/2026), Vulkan 1.4.315 | `vulkaninfo --summary` |
| Disco C: | **17,1 GB livres** (458,8 GB usados) — principal restrição | `Get-PSDrive` |
| Python | 3.11.9 (único instalado) | `py -0p` |
| Git / Node / npm | 2.55.0 / 24.13.0 / 11.6.2 | `--version` |
| Ollama | 0.40.5, escutando só em `127.0.0.1:11434`, **backend Vulkan ativo na RX 6600** | `server.log` |
| Modelos já baixados | `qwen2.5vl:7b` (6,0 GB, visão, **sem suporte a ferramentas**) | `ollama list` / `ollama show` |
| Docker | 29.7.2 instalado, daemon parado | `docker info` |
| Ausentes | ffmpeg, cmake, compilador C++, Tailscale, uv | `Get-Command` |
| Portas ocupadas | 11434 (Ollama), **8080 (Apache httpd)** | `Get-NetTCPConnection` |
| Privilégios | Sessão **sem** administrador (integridade média) | `WindowsPrincipal` |
| Firewall | Ativo nos perfis Domínio, Privado e Público | `Get-NetFirewallProfile` |
| Periféricos | Webcam "WEB CAMER", dispositivo de áudio USB | `Get-PnpDevice` |
| SQLite | 3.45.1 com FTS5 | teste em memória |

### Compatibilidade da RX 6600
- **Vulkan: funciona.** O log do Ollama mostra `library=Vulkan ... AMD Radeon RX 6600 total="8.0 GiB"`.
- **ROCm no Windows: não utilizável.** O Ollama avisa "AMD driver is too old", e a RX 6600 (gfx1032) não está na lista oficial de GPUs ROCm para Windows. Não vamos usar ROCm nem `HSA_OVERRIDE_GFX_VERSION`.
- **CUDA: não se aplica** (é exclusivo da NVIDIA).
- Consequência: o LLM roda na GPU via Vulkan. A voz (Whisper e Kokoro) roda na **CPU**, porque CTranslate2 e onnxruntime não têm aceleração AMD no Windows sem DirectML. Isso também mantém a VRAM livre para o LLM.

## 2. Alternativas de inferência avaliadas

| Opção | Windows nativo | AMD RX 6600 | Prós | Contras | Decisão |
|---|---|---|---|---|---|
| **Ollama 0.40.5** | Sim | Vulkan (verificado) | Já instalado e funcionando; API nativa com streaming, ferramentas e `think`; gerencia modelos | Menos ajuste fino que llama.cpp puro | **Escolhido** |
| Lemonade Server (AMD) | Sim | Vulkan via llama.cpp (documentado para dGPU AMD) | API compatível com OpenAI, foco em AMD | Mais uma instalação global; ganho não comprovado sobre Ollama+Vulkan nesta GPU | Alternativa |
| llama.cpp `llama-server` (Vulkan) | Sim (binários prontos) | Vulkan | Máximo controle, leve | Gerenciar GGUFs à mão | Plano B |
| OpenJarvis | **Não** ("Native Windows is not supported", exige WSL2) | via Ollama | Apache 2.0, ideias boas de memória/agentes | Alfa, WSL2 consome RAM e disco que faltam aqui | **Não usado como base** |

A troca de mecanismo fica isolada em `jarvis/llm.py`, o único arquivo que fala com o servidor de inferência.

## 3. Modelo inicial

| Modelo | Tamanho | Ferramentas | Observação |
|---|---|---|---|
| **qwen3.5:4b** | ~3,4 GB | Sim (+ thinking, visão) | 201 idiomas, contexto 256K, publicado no Ollama há 1 semana. **Padrão.** |
| qwen3:4b | 2,5 GB | Sim | Alternativa menor se faltar disco/VRAM |
| qwen2.5vl:7b (já instalado) | 6,0 GB | **Não** | Serve para chat/visão, não para agente |
| gemma4:e4b | 6,6–9,5 GB | Sim | Não cabe no orçamento de disco atual |

O modelo é configurável (`JARVIS_MODEL`). Modelos de nuvem do Ollama (`*cloud*`) são **recusados** pela configuração, para nada sair do PC sem querer.

## 4. Arquitetura

```
 Navegador (PC ou celular)                 PC Windows (tudo em 127.0.0.1)
 ┌──────────────────────┐   HTTPS/WSS   ┌──────────────────────────────────────────┐
 │ web/ (HTML+JS puro)  │──(Tailscale)──│ FastAPI  jarvis/main.py   :8765          │
 │ chat, voz, tarefas,  │   ou local    │  ├─ auth.py   login, sessões, Host/Origin│
 │ memória, aprovações  │               │  ├─ agent.py  laço do agente + ferramentas│
 └──────────────────────┘               │  ├─ llm.py ──HTTP──► Ollama :11434 (Vulkan)│
                                        │  ├─ db.py     SQLite (data/jarvis.db)    │
                                        │  ├─ tools/    ferramentas tipadas         │
                                        │  └─ voice/    Whisper (CPU), Kokoro (CPU) │
                                        └──────────────────────────────────────────┘
```

| Componente | Responsabilidade | Tecnologia |
|---|---|---|
| `web/` | Interface responsiva pt-BR, tema escuro, sem build | HTML + CSS + JS puro |
| `jarvis/main.py` | Rotas HTTP, WebSocket de chat, arquivos estáticos | FastAPI + Uvicorn |
| `jarvis/auth.py` | Senha (scrypt da stdlib), sessões com expiração, checagem de Host/Origin contra DNS rebinding/CSRF, limite de tentativas | stdlib |
| `jarvis/agent.py` | Prompt de sistema, injeção de memórias, laço de chamada de ferramentas, streaming | — |
| `jarvis/llm.py` | Cliente do servidor de inferência (único ponto de acoplamento) | httpx → API nativa do Ollama |
| `jarvis/db.py` | Conversas, mensagens, memórias (FTS5), sessões, auditoria | sqlite3 da stdlib |
| `jarvis/coding.py` | Agente de programação: áreas isoladas, verificações por lista fixa, diff, integração com backup e reversão | difflib, Job Objects do Windows (ctypes) |
| `jarvis/web.py` | Busca (Tavily ou Wikipédia) e leitura de páginas com proteção contra SSRF | httpx |
| `jarvis/devices.py` | Localização e câmera ao vivo via pedidos à página aberta no aparelho | Geolocation do navegador; Google Geocoding (opcional) |
| `jarvis/camera.py` | Dono único da webcam do PC (vídeo ao vivo e fotos) e repasse da câmera do celular (MJPEG) | OpenCV |
| `jarvis/face.py` | Reconhecimento facial opcional (YuNet + SFace); vetores cifrados; câmera só local | opencv-python-headless (extra) |
| `jarvis/secure.py` | Cifragem DPAPI compartilhada (token do Google, dados faciais) | ctypes |
| `jarvis/google_api.py` | Gmail e Agenda via REST com OAuth do usuário; token cifrado com DPAPI | google-auth-oauthlib (só o login) |
| `jarvis/remote.py` | Lê o estado do Tailscale e do `serve`; libera o nome `*.ts.net` como Host | CLI do Tailscale |
| `jarvis/tools.py` | 15 ferramentas tipadas, com níveis leitura/ação/perigosa, validação, tempo limite, pastas e apps autorizados (`data/permissoes.json`), modos simulação/normal/somente leitura | stdlib + ctypes (Lixeira do Windows) |
| `jarvis/voice.py` | STT e TTS na CPU, modelos em `data/models` | faster-whisper (CTranslate2 int8), kokoro-onnx (int8) |
| `jarvis/listener.py` | Escuta local opcional: palmas (numpy) e o nome "Sarah" (trechos curtos de fala → Whisper `base`) | sounddevice (PortAudio), faster-whisper |
| `jarvis/icon.py` | Logotipo: imagem → ícones da página/celular e `.ico` do atalho | OpenCV |
| `jarvis/storage.py` | Uso de disco, limpeza de áreas e backups antigos, compactação e manutenção do banco | SQLite |
| `web/app.js` | Interface: login, chat, voz, menu e páginas; avisos de erro no rodapé | sem bibliotecas externas |
| `web/avatar.js` | Rosto da Sarah deformado por malha em WebGL 2 (boca, pálpebras, olhar, sobrancelhas, sorriso e giro em falso 3D), guiado pelo som da fala e pelo estado | WebGL 2 |
| `data/` | Banco, logs, modelos de voz, segredos (fora do Git) | — |

### Decisões principais
- **Rosto realista sem placa NVIDIA** (2026-10-16): modelos de IA que geram vídeo de rosto falando (MuseTalk, LivePortrait e similares) rodam em tempo real só em placas NVIDIA; não há versão para AMD no Windows. A alternativa usada é a dos avatares 2D animados: a imagem é deformada por uma malha (~15 mil pontos) com pesos por região do rosto, a ~175 quadros por segundo no navegador.
- **Visão com o mesmo modelo** (2026-10-16): o qwen3.5:4b já entende imagens, então não há segundo modelo na VRAM (o `qwen2.5vl:7b` foi removido). Para equilibrar precisão e velocidade: imagens reduzidas a ≤1024 px (JPEG 88), só as 2 mais recentes da conversa vão ao modelo, e a foto da câmera é analisada numa chamada à parte (`vision.describe`), sem as ferramentas. Medido: 6–10 s por imagem.
- **Sarah sem página aberta** (2026-10-16): se ninguém estiver com a página aberta no PC, o servidor trata o "Sarah" sozinho (`main.hands_free`): grava a pergunta pela própria escuta, transcreve, responde com o mesmo `agent.respond` e fala pelo `sounddevice`. Início com o Windows por atalho na pasta Inicializar (`autostart.py`), não por serviço: roda na sessão do usuário, que é onde estão o microfone, as caixas de som e o Tailscale.
- **App Android = WebView** (`android_app/`, Flutter): a mesma interface da página, sem duplicar código. Escuta contínua em segundo plano no celular exigiria um app nativo com serviço em primeiro plano e notificação fixa, e gastaria bateria; ficou de fora.
- **Prompt de sistema estável** (Fase 5): o qwen3.5 tem arquitetura híbrida e o Ollama só reaproveita o cache quando a nova requisição estende a anterior. Com a hora no prompt, toda mensagem reprocessava as ~1.900 instruções (~4 s). Agora o prompt só tem a data; a hora vem da ferramenta `data_hora`. Medido: 1º token em 0,6–0,9 s após o 1º turno.
- **Fase 6 sem Docker**: o Docker Desktop custaria ~2 GB dos 16 GB de RAM. O isolamento usa área copiada, ambiente limpo e Job Object (memória, processos, árvore encerrada). Rede e leitura de arquivos não ficam isoladas, então toda execução de código pede confirmação. Docker pode virar opção futura para `--network none`.
- **Contexto de 16K** (antes 8K): medido 3,4 GB de VRAM com 8K e 3,9 GB com 24K (o qwen3.5 tem KV cache pequeno). Código ocupa muito contexto.
- **Ferramentas por assunto** (Fase 10): com 31 ferramentas, a 1ª mensagem de cada conversa levava 17 s (3.968 tokens de instruções). Agora o chat comum só recebe as 3 básicas (hora, busca na web, memória) mais as dos assuntos das últimas 6 mensagens do usuário (`tools.TOPICS`: arquivos, sistema, e-mail, agenda, câmera, localização, web). Medido: 4–7 s. Se a palavra-chave não aparecer, o modelo não vê a ferramenta: aí basta pedir de forma mais explícita ("abra o arquivo…", "no meu e-mail…").
- **Modo programação separado**: outro prompt e outras 8 ferramentas, oferecidos só com o botão `</>`. Assim o chat comum não fica mais lento com mais instruções de ferramentas.
- **qwen3:4b testado e descartado**: mesmo com `think: false`, escrevia o raciocínio em inglês na resposta.
- **Sem framework de agente** (LangChain etc.): o laço de ferramentas tem ~50 linhas e fica auditável.
- **Sem build de frontend**: menos dependências, carrega rápido no celular.
- **Memória = recuperação, não treinamento**: tabela `memories` + busca FTS5 (BM25). Só o usuário ou o pedido explícito "lembre que..." grava memória. Embeddings via Ollama podem entrar depois se a busca por palavras não bastar.
- **Áudio capturado no navegador** (push-to-talk) e enviado ao backend: funciona igual no PC e no celular. Escuta contínua no PC (palavra-chave/palmas) é um módulo separado, opcional e desligado por padrão, que processa áudio só em memória.
- **Backend só em `127.0.0.1`**. O acesso pelo celular será via `tailscale serve` (HTTPS dentro da tailnet, sem abrir portas nem mexer no firewall).

## 5. Memória e armazenamento estimados

| Item | Disco | RAM | VRAM |
|---|---|---|---|
| qwen3.5:4b (Q4) | ~3,4 GB | ~0,5–1 GB (processo Ollama) | ~4–5 GB com contexto de 8K |
| Backend Python + deps base | ~60 MB | ~100 MB | — |
| faster-whisper `small` int8 + deps (medido) | 0,5 GB de modelo + parte dos 286 MB de pacotes | ~0,5–1 GB durante a transcrição | — |
| kokoro-onnx int8 + vozes (medido) | 120 MB | ~0,3–0,5 GB | — |
| Gatilho "Sarah" (Whisper `base`, medido) | ~145 MB de modelo | ~0,5 s de CPU por frase curta | — |
| **Total novo** | **~4,7 GB** (sobram ~12 GB) | **~2–2,5 GB** | **~5 GB de 8 GB** |

Com só 3,8 GB de RAM livre, recomenda-se fechar abas do navegador ao usar voz. O `qwen2.5vl:7b` (6 GB) foi removido com sua autorização em 16/10/2026: o qwen3.5:4b também tem visão.

## 6. Riscos e limitações conhecidos
1. **Modelo de 4B é limitado**: raciocínio, código e chamadas de ferramentas são menos confiáveis que em modelos de nuvem. O agente de programação (Fase 6) vai depender de testes automáticos e aprovação humana, não da "inteligência" do modelo.
2. **Disco apertado** (17 GB): evitar modelos grandes e acompanhar o espaço.
3. **RAM livre baixa**: voz e LLM juntos podem paginar se muitos apps estiverem abertos.
4. **Voz na CPU** (medido): Whisper `small` transcreve uma frase em ~2 s; Kokoro gera fala a 0,22× o tempo real; do fim da gravação até o Jarvis começar a falar, ~3,5 s.
5. **PC desligado, suspenso ou sem internet = Jarvis inacessível pelo celular.** Não há componente em nuvem.
6. **Microfone no celular exige HTTPS** (regra dos navegadores): por isso o `tailscale serve`, que fornece certificado válido.
7. Gatilho "Sarah" (2026-10-16): treinar um modelo de palavra-chave próprio (openWakeWord) exige milhares de áudios sintéticos e GPU de treino. Em vez disso, a escuta separa trechos curtos de fala pelo volume e confere o começo com o Whisper `base` (16/17 frases certas, nenhum falso positivo, ~0,5 s por frase; o `small` acerta igual, mas leva 1,3 s). Se vier uma pergunta junto, ela é transcrita de novo com o `small`.
8. A escuta local (palmas/nome) avisa a página aberta no PC, que grava a pergunta. Sem essa página aberta, o acionamento não tem efeito.

## 7. Custos e serviços externos (verificado em 2026-10-15)
| Serviço | Situação | Observação |
|---|---|---|
| Ollama, qwen3.5, faster-whisper, Kokoro, FastAPI | Gratuitos, licenças Apache 2.0/MIT | 100% offline após o download |
| Tailscale (Personal) | Gratuito: até 6 usuários, dispositivos ilimitados (mudança de 08/04/2026, segundo fontes de terceiros) | Conta e app de terceiros; o plano pode mudar |
| Gmail/Calendar API | Gratuito para uso pessoal, com cota | Exige projeto no Google Cloud + OAuth. Apps em modo "Testing" têm refresh token que expira em 7 dias (confirmar na Fase 8) |
| WhatsApp Business Platform | **Não é gratuito em geral**: preço por mensagem desde 01/07/2025; mensagens de serviço na janela de 24 h são gratuitas | Exige conta Meta Business, número dedicado e **webhook público**, o que conflita com "não expor portas". Fica desacoplado (Fase 9) |
| OpenJarvis | Não usado | — |

## 8. Plano de implementação

| Fase | Entrega | Depende de você? | Estado |
|---|---|---|---|
| 1 | Diagnóstico e esta arquitetura | Não | ✅ |
| 2 | Backend, login, UI web, chat por texto com streaming via Ollama | Não (só baixa o qwen3.5:4b, ~3,4 GB) | ✅ |
| 3 | Histórico de conversas, memória persistente com consulta/edição/exclusão | Não | ✅ |
| 4 | Voz: Whisper (STT), Kokoro pt-BR (TTS), interrupção, palavra-chave/palmas opcionais | Não (downloads de ~1 GB) | ✅ (palmas: calibração na aba Voz, falta a sua) |
| 5 | Ferramentas tipadas, permissões, confirmações, simulação, auditoria, cancelamento | Não | ✅ |
| 6 | Agente de programação em área de trabalho isolada, com diff e aprovação | Não | ✅ (sem isolamento de rede) |
| 7 | Acesso remoto via Tailscale | **Sim**: instalar Tailscale (software global) e criar conta | ✅ configurado; teste no 4G pendente |
| 8 | Gmail/Calendar: ler, buscar, rascunhos, enviar e criar eventos com confirmação | **Sim**: criar projeto Google Cloud e autorizar OAuth | ✅ conectado e testado |
| 9 | Avaliação de WhatsApp e reconhecimento facial (módulo desligado) | Sim, para qualquer ativação | ✅ WhatsApp rejeitado (termos da Meta); facial pronto e desligado |
| 10 | Testes integrados, documentação final, scripts de inicialização | Não | ✅ (TESTING.md) |

## 9. Se a GPU deixar de funcionar
1. O Ollama cai automaticamente para CPU. O Ryzen 5700X roda o qwen3.5:4b em CPU, porém mais lento (estimativa: 5–10 tokens/s, a medir).
2. Trocar para `qwen3:4b` ou `qwen3.5:2b` para ganhar velocidade.
3. Testar `llama-server` (Vulkan) ou Lemonade e apontar `JARVIS_LLM_URL` para eles. Isso exige adaptar `llm.py` para a API compatível com OpenAI.
4. Atualizar o driver Adrenalin, se a falha for de driver.
