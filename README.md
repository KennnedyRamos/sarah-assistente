# Sarah (projeto Jarvis Local)

A **Sarah** é uma assistente pessoal de IA que roda no seu PC (Windows 11 + AMD RX 6600), em português, sem mensalidade e sem API paga.
O modelo de linguagem roda localmente no [Ollama](https://ollama.com) via Vulkan; a interface é uma página web.
O nome técnico continua `jarvis` (pasta, pacote Python, comandos `python -m jarvis…` e variáveis `JARVIS_*`).

## Estado atual

| Recurso | Estado | Como foi verificado |
|---|---|---|
| Chat por texto com streaming | ✅ Pronto | testes automáticos + teste real com qwen3.5:4b + navegador (Edge headless) |
| Interromper resposta | ✅ Pronto | teste automático + teste real |
| Histórico de conversas (listar, abrir, excluir, apagar tudo) | ✅ Pronto | testes automáticos + navegador |
| Memória persistente (criar, editar, excluir; usada como contexto) | ✅ Pronto | testes automáticos + teste real ("qual é meu nome?") |
| Login, sessões, revogação, auditoria | ✅ Pronto | testes automáticos + navegador |
| Interface responsiva (celular e desktop) | ✅ Pronto | screenshots em 390×844 e 1280×800 |
| Voz: falar com o Jarvis (🎤, para sozinho no silêncio) | ✅ Pronto | testes automáticos + navegador com microfone simulado |
| Voz: respostas faladas em pt-BR, frase a frase, com interrupção | ✅ Pronto | testes automáticos + navegador |
| Escolha de microfone, saída de áudio, voz e velocidade | ✅ Pronto | navegador (sem microfone físico no teste) |
| Ativação por duas palmas (no PC, opcional) | ⚠️ Pronto, **falta você calibrar** na aba Voz | testes com áudio sintético + calibração pela interface; palmas reais de pessoa ainda não registradas |
| Ativação dizendo **"Sarah"** (no PC, opcional), inclusive com a pergunta junto ("Sarah, que horas são?") | ✅ Pronto; falta você testar com a sua voz | 17 frases sintéticas: 16 certas, nenhum falso positivo ("A Sara chegou", "Será que…", ruído, palmas); teste de ponta a ponta com os modelos reais |
| 31 ferramentas tipadas no chat (arquivos, apps, diagnósticos, scripts aprovados, memória, internet, e-mail, agenda, câmera, localização) + 8 de programação | ✅ Pronto | testes de segurança + modelo real escolhendo a ferramenta certa (TESTING.md) |
| Confirmação na tela para ações perigosas, modo simulação (padrão) e somente leitura | ✅ Pronto | testes automáticos + navegador |
| Acesso ao PC: criar e abrir pastas, abrir o navegador numa pesquisa ou site, apagar um arquivo específico (Lixeira, com confirmação), atualizar um pacote de um projeto (pip/npm, com confirmação), nas pastas que você liberar | ✅ Pronto | 9 testes + modelo real escolheu a ferramenta certa em 6/6 pedidos (sem abrir nada de verdade no teste) |
| Visual no formato do seu modelo (tela clara, menu ☰, rosto que encolhe quando a conversa começa); o rosto da Sarah (a sua imagem) é animado por uma malha deformável (WebGL, como nos avatares 2D de streamers): a boca abre por uma fenda entre os lábios com interior e dentes, alarga nos sons agudos (e/i/s) e arredonda nos graves (o/u); as pálpebras fecham sobre os olhos; os olhos olham em volta e voltam para você; as sobrancelhas sobem nas sílabas fortes; a boca sorri levemente quando ela está à toa; a cabeça gira em falso 3D, respira, acena, inclina ao ouvir e olha para cima ao pensar | ✅ Pronto | navegador headless no celular e no PC; a sincronia com o som real depende do seu teste com caixa de som |
| Abrir e fechar apps de verdade | ✅ Pronto | Paint aberto e fechado educadamente no PC real |
| Cancelar tarefa em execução (mata o processo) | ✅ Pronto | testes automáticos |
| Agente de programação (botão `</>`): analisar, explicar, corrigir, criar projetos, rodar testes/lint, diff, integrar e reverter | ✅ Pronto | 23 testes + modelo real corrigiu 2 projetos com bug e criou um projeto com 10 testes passando |
| Execução de código isolada (cópia do projeto, ambiente sem tokens, limite de memória/processos, árvore de processos encerrada) | ✅ Pronto, **sem bloqueio de rede** | testes automáticos |
| Acesso pelo celular via Tailscale (HTTPS, só sua tailnet) | ⚠️ Configurado; **falta o teste no 4G** | endereço HTTPS testado a partir do PC: login, chat, voz, tarefas entre aparelhos, bloqueios |
| Tarefas visíveis entre aparelhos: parar e responder confirmações de outro aparelho | ✅ Pronto | testes automáticos + teste pela tailnet |
| Gmail e Google Agenda: buscar, ler, resumir, rascunhos, enviar e criar eventos (com confirmação) | ✅ Conectado e testado com a sua conta | 18 testes simulados + testes reais (enviar e criar evento: só a confirmação, sem executar) |
| Internet: buscar com fontes e ler páginas (com proteção da rede interna) | ✅ Pronto, com a sua chave grátis da Tavily | testes + busca real (1,6 s) e leitura real de sites |
| Localização do celular ou do PC ("onde eu estou?") | ✅ Coordenadas e link do mapa; endereço com chave do Google Maps (opcional) | testes + navegador e modelo reais |
| Câmera ao vivo: PC → celular e celular → PC | ✅ Pronto | testes + servidor e navegador reais |
| SMS | ❌ Não implementado: só seria grátis com um Android sobrando como gateway ([INTEGRATIONS.md](INTEGRATIONS.md#sms-avaliação-2026-10-16)) | avaliação |
| WhatsApp | ❌ Não integrado: os termos da Meta proíbem assistentes de IA de uso geral ([INTEGRATIONS.md](INTEGRATIONS.md)) | avaliação documentada |
| Visão: analisa imagens enviadas pelo 📎 e, a pedido, uma foto da câmera do PC ou do celular ("olhe a câmera e me diga o que vê"), com o próprio qwen3.5:4b (sem modelo extra, sem custo) | ✅ Pronto | 6 testes + modelo real: foto da câmera descrita em 6,3 s, imagem com texto lida em 9,5 s |
| Sarah disponível **sem nenhuma página aberta** no PC: "Sarah, …" é respondido pelas caixas de som e vai para o histórico; confirmações no celular | ✅ Pronto; falta o seu teste com microfone e caixas de som | 7 testes automáticos |
| Iniciar com o Windows, sem janela (chave na aba Voz) | ✅ Pronto | teste automático + pythonw real: sem janela, log em `data\logs\servidor.log` |
| App Android (APK, sem navegador) | ⚠️ Compilado; **falta testar no seu celular** | instalado e aberto no emulador (que não entra na tailnet, então só mostrou a tela "sem conexão") |
| Reconhecimento facial e **fotos de quem está na câmera**, inclusive pelo celular (nunca usado como senha) | ✅ Ativado por você | 16 testes simulados + webcam real aberta (sem salvar); cadastro e foto reais ficam para você |

## Iniciar e encerrar

1. Garanta que o Ollama está instalado e que o modelo foi baixado: `ollama pull qwen3.5:4b` (~3,4 GB).
2. Dê dois cliques em **`iniciar.bat`** (ou no atalho **Sarah** da Área de Trabalho). Ele:
   - cria o ambiente Python em `.venv` (na primeira vez) e instala/atualiza as dependências;
   - avisa se o Ollama estiver fechado e oferece baixar os modelos de voz que faltarem;
   - pede para você definir a senha de acesso (mínimo de 10 caracteres);
   - abre http://127.0.0.1:8765 no navegador.
3. Para encerrar: **Ctrl+C** na janela do Jarvis, ou execute **`parar.bat`**.

Se a Sarah já estiver rodando (por exemplo, em segundo plano), o `iniciar.bat` só abre a página.

**Sempre disponível (segundo plano)**: na aba **Voz**, ligue **Iniciar com o Windows, sem janela**. Isso cria o atalho
"Sarah (segundo plano)" na pasta Inicializar do seu usuário (sem administrador, sem serviço; desligar a chave apaga o atalho).
Ela sobe sem janela no login, grava o log em `data\logs\servidor.log` e fica acessível pelo celular. Para encerrar: `parar.bat`.

Para trocar a senha: `.venv\Scripts\python.exe -m jarvis.setpass` (todas as sessões são encerradas).

## Escolher o modelo

Copie `.env.example` para `.env` e altere `JARVIS_MODEL`. O modelo precisa estar baixado (`ollama pull <nome>`) e ter suporte a ferramentas, para as fases seguintes. Opções testadas ou avaliadas estão em [ARCHITECTURE.md](ARCHITECTURE.md#3-modelo-inicial). Modelos de nuvem do Ollama são recusados de propósito.

## Voz e microfone

1. Baixe os modelos de voz uma vez (~600 MB; depois tudo funciona offline):
   `.venv\Scripts\python.exe -m jarvis.voice`
2. Na interface, aba **Voz**: escolha o microfone, a saída de áudio, a voz (Dora, Alex ou Santa) e a velocidade.
   Os nomes dos dispositivos aparecem depois que você autoriza o microfone uma vez no navegador.
   Use **Testar microfone**: se o sinal estiver baixo, mova a sensibilidade para a esquerda.
3. No chat, clique em 🎤 e fale. A gravação para sozinha após ~1,2 s de silêncio (ou clique de novo).
4. O botão 🔊/🔇 no topo liga e desliga as respostas faladas. **Parar** ou **Esc** interrompe a fala.

### Ativação sem as mãos (opcional, só no PC)
Na aba Voz, em "Escuta local": **Duas palmas**, **Nome "Sarah"** ou ambos. Funciona com ou sem a página aberta no PC:
- **Com a página aberta**, a conversa aparece nela, com o rosto e a voz do navegador.
- **Sem nenhuma página aberta** (por exemplo, com ela em segundo plano), o servidor faz tudo: bipe, ouve a pergunta, responde
  pelas caixas de som do PC, frase a frase, e a conversa vai para o histórico. Se a ação precisar de confirmação, ela avisa
  em voz alta e a confirmação aparece no celular (ou em qualquer página aberta), onde também dá para parar a tarefa.
- **Palmas** funcionam sem instalar nada. Calibre uma vez na própria aba Voz: escolha o **Microfone da escuta**
  (neste PC, o "High Definition Audio"; o "USB Audio" padrão não capta som), clique em **Calibrar palmas**, bata duas palmas,
  espere 2 s, bata mais duas e clique em **Aplicar ajuste**. Microfone e ajuste ficam salvos, assim como o modo escolhido.
- **Nome "Sarah"**: diga só "Sarah" e espere o bipe, ou fale tudo junto: "Sarah, abre o YouTube". O nome precisa vir no começo
  e a frase precisa ser curta (até ~3 s); conversa comum, TV e "a Sarah disse…" não acionam. Enquanto ela fala pelas caixas do PC,
  a escuta fica surda (ela diz o próprio nome). Usa o Whisper `base` (~145 MB, já baixado aqui; em outro PC:
  `.venv\Scripts\python.exe -m jarvis.listener`) e ~0,5 s de CPU por frase curta.
- Enquanto a escuta está ligada, aparece "Escuta local" no topo. Só uma sessão no próprio PC pode ligá-la; o celular não pode.

## Visual e logotipo

A tela inicial segue o modelo que você enviou: fundo claro com as linhas da imagem, **SARAH** no alto, o rosto animado no centro, as ondas de voz com o status ("Sarah está ouvindo…", "pensando…", "falando…") e embaixo a caixa de mensagem com 📎 (enviar arquivo), `</>` (modo programação) e o botão grande de voz. Ao enviar a primeira mensagem (digitada ou falada), o rosto encolhe para o topo e a conversa aparece embaixo. O menu **☰** (canto superior direito) tem Nova conversa, Conversas anteriores, Memória, Voz, Ferramentas, Segurança e Respostas faladas; a bolinha nele indica a conexão. Clicar no rosto também começa a ouvir.

**Histórico**: fica na lateral esquerda (no PC, o botão de relógio no canto superior esquerdo recolhe e mostra; no celular, abre
como gaveta). As conversas aparecem pela última atividade, agrupadas em Hoje, Ontem, Últimos 7 dias…, e dá para buscar pelo título.

**"Sarah" com ela parada**: com a escuta em "Sarah" (ou "Sarah ou palmas"), diga "Sarah" ou "Sarah, …".
Depois de 30 minutos sem conversar, ela começa uma conversa nova (o assunto antigo não se mistura). Enquanto ela fala, o nome é
ignorado. Se o microfone escolhido sumir do Windows, aparece um aviso e a escuta volta sozinha quando ele reaparecer.

**Enviar arquivo** (📎): o arquivo vai para `data\workspace\arquivos` (até 25 MB, sem sobrescrever; executáveis são recusados) e o caminho segue junto com a sua mensagem, então dá para pedir "resuma este arquivo". Ela lê arquivos de texto (txt, md, csv, código, json…) e **vê imagens** (jpg, png, webp, bmp): "o que tem nesta foto?", "leia o texto
deste print". PDF fica salvo, mas o conteúdo ainda não é lido.

**Visão**: é o próprio qwen3.5:4b (ele entende imagens), então não há modelo extra, memória extra nem custo. Para equilibrar
precisão e velocidade, cada imagem vai reduzida a no máximo 1024 px (o suficiente para ler texto de um print) e só as 2 imagens
mais recentes da conversa são reenviadas ao modelo. Também dá para pedir "olhe a câmera do PC/celular e me diga o que vê": ela
tira **uma** foto, analisa e descarta (a foto não é salva; fica registrado na auditoria). O aparelho que filma mostra o aviso
de câmera, de propósito.

Para usar a sua imagem como logotipo (página, ícone do app no celular e atalho **Sarah** da Área de Trabalho):
`.venv\Scripts\python.exe -m jarvis.icon C:\caminho\da\imagem.png` (PNG, JPG ou WEBP; o centro vira um quadrado). Depois, Ctrl+F5 na página.

## Ferramentas (controle do PC)

Peça em linguagem natural: "crie um arquivo notas.md com…", "que arquivos tenho na pasta de trabalho?", "abra a calculadora",
"verifique minha internet", "lembre que…". Cada ação aparece no chat como um cartão 🔧, com o resultado.

- **Modo inicial: simulação.** Ações perigosas (apagar, sobrescrever, fechar app, rodar script) são só descritas.
  Para executá-las de verdade, vá à aba **Ferramentas** → "Normal". Aí cada uma pede **Aprovar/Recusar** na tela.
- **Pastas autorizadas**: por padrão só `data\workspace`. Libere outras na aba **Ferramentas → Pastas autorizadas**: um clique em
  "+ Área de Trabalho", "+ Documentos", "+ Downloads"… ou digite o caminho de uma pasta. Vale na hora, sem reiniciar.
  Aí dá para pedir: "crie uma pasta Projetos na Área de Trabalho", "abra a pasta Downloads", "exclua o arquivo boleto.pdf dos Downloads"
  (vai para a Lixeira, com confirmação), "atualize o pacote requests do projeto C:\...\meuapp" (pip no `.venv` do projeto ou npm, com confirmação).
- **Navegador**: "abra o navegador e pesquise…", "abra o YouTube com…", "abra o site gov.br". Para perguntas, ela busca na internet sozinha e cita as fontes.
- **Apps**: lista em `"aplicativos"` (bloco de notas, calculadora, paint, explorador e VS Code, se instalado).
- **Scripts**: cadastre em `"scripts"`, por exemplo:
  `"backup": {"comando": ["robocopy", "C:\\origem", "D:\\destino", "/E"], "tempo_limite": 600, "descricao": "Backup"}`.
- Desative ferramentas individuais na aba Ferramentas. Detalhes de cada uma: [SECURITY.md](SECURITY.md#ferramentas-fase-5).

## Agente de programação

Clique em **`</>`** ao lado do microfone para ligar o modo programação. Exemplos:
- "O projeto em `C:\...\meuapp` tem testes falhando. Encontre o erro, corrija e rode os testes."
- "Crie um projeto Python novo em `projetos/conversor` que converte CSV em JSON, com testes."
- "Explique o que faz o arquivo `src/main.py` do projeto X." / "Que melhorias você sugere neste projeto?"

Como funciona:
1. O Jarvis copia o projeto para uma **área isolada** (`data\workspace\.areas\<id>`). Pastas geradas como `.git`, `node_modules`, `.venv` e `build` não são copiadas.
2. Ele escreve e testa **só na área**. O seu projeto original não muda.
3. Ele verifica com comandos de uma lista fixa: compilar/ruff/pytest (Python), `npm install/test/build`, `node --check` (JS) e `flutter analyze/test`.
   Compilar e lint rodam direto. **Tudo que executa código pede sua confirmação.**
4. Quando você pedir para aplicar, aparece um cartão com o **diff**. Ao aprovar, ele copia os arquivos e guarda backup em `data\backups`. Se você se arrepender: "reverta a integração".
5. Ele nunca faz commit, push ou deploy. Se o projeto for um repositório Git, as mudanças ficam pendentes para você revisar com `git diff`.

Para usar projetos fora de `data\workspace`, adicione a pasta em `"pastas"` no `data\permissoes.json`.
Ações perigosas precisam do modo **Normal** na aba Ferramentas; em **Simulação**, o Jarvis só descreve.
Áreas antigas ocupam disco (principalmente com `node_modules`): peça "descarte a área X" ou apague `data\workspace\.areas`.

## Acesso pelo celular

Com o Jarvis rodando no PC e o app Tailscale conectado no celular (mesma conta), abra **https://seu-pc.sua-tailnet.ts.net**.
O celular conversa, usa a voz, lê arquivos autorizados, acompanha e **para** tarefas, e **recusa** confirmações.
Por padrão, não altera nada no PC. Detalhes, checklist do teste no 4G e como desligar: [REMOTE_ACCESS.md](REMOTE_ACCESS.md).

### App Android (sem navegador)

O arquivo **`Sarah.apk`** (na pasta do projeto, ~15 MB, para celulares de 64 bits) abre a Sarah em tela cheia, com o ícone dela.
1. Copie o `Sarah.apk` para o celular (cabo, Google Drive ou e-mail para você mesmo) e toque nele.
2. O Android pede para permitir instalar apps desta fonte: permita só para esse app (Arquivos/Drive) e instale.
3. Com o **Tailscale conectado** no celular, abra **Sarah** e entre com a sua senha (uma vez; a sessão fica salva).
4. Microfone, câmera e localização são pedidos na primeira vez em que você usar cada um.

O app é só uma "janela" para a Sarah do PC: nada roda nele, e ele não fica ouvindo em segundo plano (o Android não permite
isso de forma invisível). Para recompilar: `cd android_app` e
`flutter build apk --release --split-per-abi --dart-define=SARAH_URL=https://<seu-pc>.<sua-tailnet>.ts.net/`
(o endereço da sua tailnet fica fora do código)
(o APK de 64 bits sai em `build\app\outputs\flutter-apk\app-arm64-v8a-release.apk`).

## Logs, auditoria e dados

| O quê | Onde |
|---|---|
| Banco (conversas, memórias, sessões, auditoria) | `data/jarvis.db` |
| Log técnico (rotativo, 5 × 1 MB) | `data/logs/jarvis.log` |
| Auditoria (logins, exclusões, ações) | aba **Segurança** da interface |

Os logs não registram senhas nem o conteúdo das conversas.

## Armazenamento

Medido em 16/10/2026: o modelo de IA (3,1 GB no Ollama), os modelos de voz e de rosto (~0,87 GB) e o ambiente Python (~525 MB)
são quase tudo; conversas e memórias ocupam KB. Em **Segurança → Armazenamento** você vê o tamanho de cada parte e pode
apagar áreas do agente de programação sem uso há 7+ dias, backups com 30+ dias e compactar o banco. A auditoria com mais de
180 dias sai sozinha ao iniciar. Conversas, memórias, arquivos enviados, anexos e fotos nunca são apagados pela limpeza.

## Backup e restauração

`.venv\Scripts\python.exe -m jarvis.backup` cria `backups\jarvis-backup-<data>.zip` (pode rodar com o Jarvis aberto; aceita outra pasta de destino como argumento).
Inclui conversas, memórias, senha, permissões, área de trabalho, fotos, token do Google e rostos cadastrados. Ficam de fora os modelos (baixam de novo) e os logs.
O token do Google e os rostos são cifrados pelo Windows: só voltam **neste PC, nesta conta**; em outro PC, reconecte o Google e cadastre os rostos de novo.

Restaurar: feche o Jarvis (`parar.bat`), extraia o .zip dentro da pasta `data\` e inicie. O backup tem seu histórico e suas memórias: guarde-o em local seguro.

## Atualizar

```
.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen3.5:4b
```
Depois, rode os testes (abaixo) antes de voltar a usar.

## Testes

```
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```
O `ruff` (verificador de código) usa as regras do `pyproject.toml`.
Os testes de integração com o Ollama real (`tests/test_ollama_integration.py`) são pulados automaticamente se o Ollama estiver fechado. Detalhes em [TESTING.md](TESTING.md).

## Desativar recursos

- Voz: desligue 🔊; o microfone só é usado quando você clica em 🎤.
- Escuta local: aba Voz → "Desligada" (ou `JARVIS_WAKE=off` no `.env`, que é o padrão).

## Integrações

- **Tailscale** (acesso pelo celular): [REMOTE_ACCESS.md](REMOTE_ACCESS.md).
- **Google** (Gmail e Agenda): aba Ferramentas → Integrações. Passo a passo, custos e como desconectar: [INTEGRATIONS.md](INTEGRATIONS.md).
  As ferramentas de e-mail e agenda só aparecem para o modelo com a conta conectada.

## Limitações conhecidas

- O modelo de 4B é bom para conversa, mas erra mais que modelos grandes de nuvem, principalmente em raciocínio longo e código.
- Internet: o Jarvis busca quando o assunto pede (notícias, preços, fatos recentes) e cita as fontes, mas resume com um modelo de 4B: confira os links em assuntos importantes. A cota grátis da Tavily é de 1.000 buscas por mês.
- O modelo de 4B escolhe bem a ferramenta em pedidos diretos (10/10 no teste), mas pode errar em pedidos ambíguos ou com vários passos. As regras de segurança não dependem dele.
- Programação: o modelo de 4B resolve bem tarefas pequenas (corrigir uma função, criar um módulo com testes), mas leva de 50 a 80 s por tarefa e erra detalhes nos resumos (ex.: número da linha). Projetos grandes ou mudanças em muitos arquivos passam do que ele faz com confiança. Confira sempre o diff antes de integrar.
- O código executado pelo agente roda com o seu usuário do Windows: ele **pode acessar a rede e ler arquivos** que você consegue ler. O isolamento esconde credenciais comuns (tokens no ambiente, `.npmrc`, `pip.ini`) e limita memória e processos, mas não é uma sandbox completa. Por isso, cada execução pede sua confirmação.
- Se o PC estiver desligado, suspenso ou sem rede, o Jarvis fica inacessível.
- Visão com um modelo de 4B: descreve bem cenas, objetos e textos grandes, mas pode errar detalhes finos (letras miúdas, números,
  contagens). Cada pergunta sobre imagem leva ~6–10 s.
- O app Android não ouve "Sarah" em segundo plano: abra o app e toque no microfone.
- O primeiro pedido após iniciar demora cerca de 10 s (carregamento do modelo na GPU). A primeira mensagem de cada conversa nova leva 4–7 s (o modelo lê as instruções das ferramentas do assunto); nas seguintes, a primeira palavra chega em ~0,7 s.
- Para ficar rápido, o chat só mostra ao modelo as ferramentas do assunto da conversa (arquivos, sistema, e-mail, agenda, câmera, localização, web). Se ele disser que não consegue algo que sabe fazer, peça de forma mais explícita: "no meu e-mail…", "abra o arquivo…".
- Voz roda na CPU: do fim da sua fala até o Jarvis começar a responder falando, ~3,5 s (medido), ou ~6 s no primeiro uso, quando os modelos de voz carregam.
- O Whisper `small` às vezes erra palavras (ex.: "sexta" → "a cesta"). Para mais precisão, use `JARVIS_WHISPER_MODEL=medium` no `.env`: mais lento, ~1,5 GB, depois `python -m jarvis.voice`.
- Pelo celular: sem acesso se o PC estiver desligado, suspenso, sem internet ou com o Jarvis fechado.
- Resumos de e-mail: com a temperatura recomendada e a instrução contra inferências, o teste real não inventou fatos, mas um modelo de 4B ainda pode errar. Cada e-mail tem um link **abrir** no cartão 🔧 para você conferir.
- Google em modo Testing: reconectar a cada 7 dias (ou publicar o app; ver INTEGRATIONS.md).

Mais documentos: [INTEGRATIONS.md](INTEGRATIONS.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [SECURITY.md](SECURITY.md) · [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) · [REMOTE_ACCESS.md](REMOTE_ACCESS.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · [TESTING.md](TESTING.md)
