# Acesso remoto pelo celular

**Estado (2026-10-15):** configurado e testado neste PC pelo endereço HTTPS da tailnet. **Falta o teste final a partir de uma rede externa** (celular no 4G, com o Wi-Fi desligado), que só você pode fazer. Ver o [checklist](#teste-final-pelo-celular-4g) abaixo.

Endereço: **https://seu-pc.sua-tailnet.ts.net** (só abre em aparelhos logados na sua conta Tailscale).

## Como funciona
```
Celular (app Tailscale, sua conta) ──WireGuard criptografado──► PC: tailscaled
   https://seu-pc.sua-tailnet.ts.net                              │ tailscale serve (HTTPS, certificado válido)
                                                                  ▼
                                                    Jarvis em http://127.0.0.1:8765 (só local)
```
- Nenhuma porta aberta no roteador e nenhuma regra de firewall criada pelo Jarvis.
- `tailscale serve` é **tailnet only**: quem não está na sua conta Tailscale não alcança o endereço. **Não** usamos `tailscale funnel`, que seria público.
- Mesmo dentro da tailnet, é preciso a **senha do Jarvis**.

## O que foi instalado e configurado (com sua autorização, em 2026-10-15)
| Item | Detalhe |
|---|---|
| Tailscale 1.104.1 | `winget install Tailscale.Tailscale` (pacote oficial, BSD-3, MSI verificado por SHA256). Instala o serviço "Tailscale", que inicia com o Windows, e o ícone na bandeja |
| Conta | a sua conta Tailscale; MagicDNS ligado; HTTPS habilitado por você no painel |
| Publicação | `tailscale serve --bg 8765` → `https://seu-pc.sua-tailnet.ts.net/` → `http://127.0.0.1:8765`. Persiste entre reinicializações |

## Uso no dia a dia
1. No PC: `iniciar.bat`. A janela mostra `[Jarvis] Pelo celular (Tailscale): https://...`.
2. No celular: app Tailscale **conectado** → abra o endereço no navegador → senha do Jarvis.
   Ou instale o app **Sarah** (`Sarah.apk`, ver README → "App Android"): abre direto, sem navegador.
   O app é só uma janela para o endereço da tailnet: não abre portas, não fala com outros servidores e não funciona sem o Tailscale.
3. O microfone funciona no celular porque o endereço é HTTPS. Na primeira vez, o navegador pede permissão.

## O que o celular pode fazer
| Pode | Não pode (por padrão) |
|---|---|
| Conversar por texto e voz; ver e apagar histórico; gerenciar memórias | Ferramentas que alteram algo (criar, mover, apagar arquivos; abrir ou fechar apps; scripts; programação com escrita) |
| Ferramentas de leitura: hora, sistema, listar, buscar e ler arquivos autorizados, diagnósticos | **Aprovar** ações perigosas iniciadas no PC |
| Ver tarefas em andamento no PC, **parar** e **recusar** confirmações | Ligar a escuta do microfone do PC; mudar modo ou permissões de ferramentas |
| Câmera do PC: "quem está aí?", cadastrar rosto, **tirar foto** (com `JARVIS_REMOTE_CAMERA=true`, ligado) | |
| Ver sessões, encerrar outras sessões, ver a auditoria | |

Para liberar ações e aprovações pelo celular (sempre com confirmação na tela), coloque `JARVIS_REMOTE_TOOLS_ALL=true` no `.env` e reinicie. Como você é o único usuário e a tailnet é sua, é uma escolha razoável, mas fica desligado até você decidir.

## Teste final pelo celular (4G)
Com o Jarvis rodando no PC (`iniciar.bat`):
- [ ] Wi-Fi do celular **desligado**, dados móveis ligados, app Tailscale **conectado**
- [ ] Abrir https://seu-pc.sua-tailnet.ts.net → tela de login aparece
- [ ] Entrar com a senha → aba Segurança mostra a sessão como **Remota**
- [ ] Mandar uma mensagem de texto e receber resposta
- [ ] Tocar em 🎤, permitir o microfone, falar e receber resposta falada (ligue 🔊)
- [ ] Desconectar o Tailscale no celular e recarregar → a página **não abre** (prova que não está exposto na internet)

## Desligar ou desfazer
| Objetivo | Como |
|---|---|
| Tirar o Jarvis da tailnet | `tailscale serve reset` |
| Desconectar a VPN | ícone do Tailscale → Disconnect |
| Remover tudo | Configurações do Windows → Aplicativos → Tailscale → Desinstalar |
| Expulsar um aparelho | https://login.tailscale.com/admin/machines |
| Encerrar sessões do Jarvis | aba Segurança → "Encerrar outras sessões", ou trocar a senha |

## Limitações
- **PC desligado, suspenso, sem internet ou com o Jarvis fechado = sem acesso.** O endereço responde 502 quando o Jarvis está fechado.
- O Tailscale no Windows só fica conectado enquanto sua sessão do Windows está aberta, a menos que você ative "Run unattended" no app. O Jarvis também roda na sua sessão.
- Depende da coordenação do Tailscale (empresa terceira). O tráfego é criptografado de ponta a ponta (WireGuard), mas o plano gratuito pode mudar: Personal, até 6 usuários, segundo fontes de 2026.
- Voz pelo celular: a transcrição e a fala rodam no PC; a latência inclui a rede móvel.
- Alternativa sem terceiros: WireGuard puro, que exige abrir uma porta UDP no roteador. Não é a primeira opção.
- Para ficar disponível sem você abrir nada: ligue "Iniciar com o Windows, sem janela" (aba Voz) e o "Run unattended" do Tailscale.

## Hospedar fora do PC? (avaliação de 2026-10-16)
Não recomendado. Opções grátis de nuvem (ex.: Oracle Cloud Always Free, 4 núcleos ARM e 24 GB de RAM, sem GPU) rodariam o
qwen3.5:4b só na CPU, várias vezes mais lento que a RX 6600, e o Whisper/Kokoro também; contas grátis podem ser suspensas e
pedem cartão. Suas conversas, e-mails e fotos passariam a ficar num servidor de terceiros, exposto à internet. E as ferramentas
do PC (arquivos, apps, câmera, escuta) precisam do PC ligado de qualquer jeito. O desenho atual (tudo no PC + Tailscale) já é
grátis, rápido e não expõe portas.
