# Solução de problemas

## "Ollama offline" na interface
- Abra o Ollama pelo menu Iniciar (ou rode `ollama serve`).
- Teste: `curl http://127.0.0.1:11434/api/version`.

## "qwen3.5:4b não instalado"
`ollama pull qwen3.5:4b`, ou mude `JARVIS_MODEL` no `.env` para um modelo listado em `ollama list`.

## Modelo roda na CPU
1. `ollama ps`: a coluna PROCESSOR deve mostrar `100% GPU`.
2. Veja `%LOCALAPPDATA%\Ollama\server.log` e procure `inference compute`. O esperado é `library=Vulkan ... AMD Radeon RX 6600`.
3. O aviso `AMD driver is too old` refere-se ao ROCm, que não é usado nesta GPU. Pode ser ignorado se o Vulkan aparecer.
4. Se o Vulkan não aparecer: atualize o driver AMD Adrenalin e reinicie o Ollama.
5. Pouca VRAM livre (jogos ou outros apps usando a GPU) faz o Ollama dividir o modelo entre GPU e CPU.

## Primeira resposta demora ~10 s
É o carregamento do modelo na GPU. Ele fica carregado por `JARVIS_KEEP_ALIVE` (padrão 30 min) após o último uso.

## "Senha ainda não definida"
Execute `iniciar.bat` ou `.venv\Scripts\python.exe -m jarvis.setpass`.

## "Muitas tentativas"
Aguarde 5 minutos ou reinicie o Jarvis.

## "Já está rodando" ao iniciar
Com a Sarah já rodando (por exemplo, em segundo plano), o `iniciar.bat` só abre a página. Para reiniciar: `parar.bat` e depois
`iniciar.bat`. Se o Jarvis tiver travado, `iniciar.bat` detecta o processo morto e segue normalmente.

## Em segundo plano: onde ver o que aconteceu
Iniciada sem janela (com o Windows), a saída vai para `data\logs\servidor.log` (além do `jarvis.log`). Se ela não subir no login,
confira se o atalho "Sarah (segundo plano)" está em `shell:startup` (Win+R) e se a chave na aba Voz está ligada.

## "Sarah" sem página aberta não responde em voz alta
Confira a saída de áudio padrão do Windows (é por ela que a Sarah fala nesse modo) e os modelos de voz
(`.venv\Scripts\python.exe -m jarvis.voice`). Se ela disser "Responda na tela do celular", a ação precisa de confirmação:
abra a Sarah no celular ou no PC.

## Porta 8765 ocupada
Defina `JARVIS_PORT` no `.env` (a 8080 desta máquina já é usada pelo Apache).

## "Host não permitido" / "Origem não permitida"
Acesse por `http://127.0.0.1:8765` ou `http://localhost:8765`. Outros nomes precisam estar em `JARVIS_ALLOWED_HOSTS`.

## Voz: "Modelos de voz não encontrados"
`.venv\Scripts\python.exe -m jarvis.voice` (precisa de internet só nesse download).

## Voz: "Microfone indisponível"
- Verifique a permissão do site no navegador (ícone de cadeado → Microfone → Permitir).
- Windows: Configurações → Privacidade → Microfone → permitir apps da área de trabalho.
- No celular, o microfone só funciona por HTTPS (Fase 7).

## Voz: a gravação não para sozinha
O ruído ambiente está acima do limite. Na aba Voz, mova "Sensibilidade" para a direita, ou clique em 🎤 de novo para parar.

## Voz: "Não ouvi nada"
O sinal está baixo. Use "Testar microfone" e mova a sensibilidade para a esquerda, ou escolha o microfone certo.

## Escuta local: palmas não acionam
Aba Voz → **Microfone da escuta**: escolha o microfone de verdade. Neste PC, o padrão do Windows ("USB Audio") entrega silêncio;
o que capta é o "High Definition Audio". Depois clique em **Calibrar palmas**, bata duas palmas secas (0,2 a 1 s entre elas),
espere 2 s, bata mais duas e clique em **Aplicar ajuste**.
- "não captou som nenhum": o microfone escolhido está mudo ou desativado no Windows; escolha outro.
- "Nenhuma palma clara": bata mais perto do microfone ou mais forte, e evite falar durante os 12 s.

## Escuta local: "Sarah" não aciona
- Diga o nome **no começo** e numa frase curta: "Sarah" (espere o bipe) ou "Sarah, que horas são?". Frases com mais de ~3 s são ignoradas de propósito.
- Escolha o microfone certo em Voz → **Microfone da escuta** (o mesmo das palmas).
- Aviso "microfone não encontrado" e o indicador vermelho "Escuta local: sem microfone" no menu ☰: o microfone escolhido sumiu do Windows (desconectado ou desativado em Configurações → Som → Entrada). Religue-o: a escuta volta sozinha em até 20 s, sem reiniciar. Em 16/10/2026 o "High Definition Audio" sumiu da lista do Windows por volta das 12h e o "USB Audio" que sobrou não capta som (pico de 0,0009).
- Enquanto a Sarah fala pelas caixas do PC, a escuta fica surda; espere ela terminar.
- Aviso de modelo ausente: `.venv\Scripts\python.exe -m jarvis.listener` (baixa o Whisper `base`, ~145 MB).

## Celular: o endereço não abre
- O app Tailscale do celular está **conectado** e na mesma conta? O PC também? (ícone do Tailscale → Connected)
- O Jarvis está rodando no PC? Com ele fechado, o endereço responde 502.
- Confira a publicação: `"C:\Program Files\Tailscale\tailscale.exe" serve status` deve mostrar `proxy http://127.0.0.1:8765`.
  Se não mostrar: `"C:\Program Files\Tailscale\tailscale.exe" serve --bg 8765`.

## Celular: "Host não permitido"
O Jarvis libera o nome `*.ts.net` quando detecta o Tailscale (na inicialização e a cada minuto). Espere um minuto ou reinicie o Jarvis.

## Celular: o microfone não funciona
Use o endereço `https://...ts.net` (não um IP) e permita o microfone quando o navegador pedir.

## App Android: "Não consegui falar com a Sarah"
O app só alcança a Sarah pela tailnet: abra o Tailscale no celular e confira que está **conectado**, que o PC está ligado e que a
Sarah está rodando (com ela fechada, o endereço responde 502). Depois toque em **Tentar de novo**.
Microfone ou câmera recusados por engano: Configurações do Android → Apps → Sarah → Permissões.

## Google: "Falta client_secret.json"
Siga INTEGRATIONS.md e salve o arquivo como `data\google\client_secret.json`.

## Google: "Acesso bloqueado: o app … não concluiu o processo de verificação" (Erro 403: access_denied)
O app está em modo de teste e a conta escolhida não está em **Google Auth platform → Audience → Test users**.
Adicione o seu e-mail lá, clique em Save e, no Jarvis, em **Abrir login de novo**. Não é preciso verificar o app no Google.

## Google: "A autorização do Google expirou"
Modo Testing: ela dura 7 dias. Ferramentas → Integrações → Conectar. Para evitar: Audience → Publish app (INTEGRATIONS.md).

## Google: "O Google respondeu 403 … API has not been used / is disabled"
Ative a **Gmail API** e a **Google Calendar API** no projeto (APIs e serviços → Biblioteca).

## Onde ver erros
`data/logs/jarvis.log` e a janela do `iniciar.bat`.
