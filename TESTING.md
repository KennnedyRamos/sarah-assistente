# Registro de testes

Legenda: **A** = automatizado (pytest) · **M** = manual/scriptado, executado de verdade · **N** = ainda não testado.

## Execução de 2026-10-15 (Fases 1–3)

`pytest -q` → **41 passed** (inclui 3 testes contra o Ollama real).

| Área | Tipo | Resultado |
|---|---|---|
| Inicialização e encerramento (lifespan, logs) | A | ✅ |
| Validação de configuração (modelo de nuvem, URL não local, porta, contexto) | A | ✅ |
| Ausência de senha configurada (503) | A | ✅ |
| Login, cookie protegido, expiração, logout, revogação, troca de senha | A | ✅ |
| Limite de tentativas de login | A | ✅ |
| Bloqueio de Host estranho (DNS rebinding) e de Origin estranha (CSRF), HTTP e WebSocket | A | ✅ |
| Cabeçalhos de segurança (CSP, X-Frame-Options) | A | ✅ |
| Chat em streaming, persistência, contexto com histórico e memória | A | ✅ |
| Interrupção da resposta (salva parcial com "[interrompido]") | A | ✅ |
| Falha do LLM e Ollama inacessível (mensagem clara) | A | ✅ |
| Limites de tamanho de mensagem e memória | A | ✅ |
| Memória: CRUD, persistência, busca FTS5, caracteres especiais | A | ✅ |
| Histórico: listar, excluir com cascata, apagar tudo + auditoria | A | ✅ |
| Renderização Markdown sem XSS | A | ✅ |
| Modelo real responde em pt-BR, chama ferramenta e roda 100% na GPU | A (integração) | ✅ |
| Servidor real + Ollama real: login, memória usada na resposta, contexto, interrupção, honestidade sobre a falta de ferramentas | M (script `httpx` + `websockets`) | ✅ 1º token em 1,0 s; 30,8 tokens/s |
| Interface no navegador (Edge headless via CDP): login errado/certo, envio, streaming, botão Parar, status GPU, gaveta no celular, memória, segurança, sem rolagem horizontal, sem erros de CSP | M (script) | ✅ após corrigir 3 defeitos de layout encontrados pelo próprio teste |
| **Fase 4: voz** (`pytest` → 65 passed no total) | | |
| STT/TTS exigem sessão; limites de tamanho; voz/velocidade inválidas | A | ✅ |
| Ida e volta fala → texto pela API ("previsão do tempo") | A | ✅ |
| Silêncio transcrito como vazio (sem alucinação) e áudio inválido → 400 | A | ✅ |
| Limpeza de Markdown/links/código antes de falar | A | ✅ |
| Detector de palmas: 2 palmas, 1 palma, longe/perto demais, fracas, tons, fala alta, espera de 3 s | A (áudio sintético) | ✅ |
| Estresse do detector: 80 variações de palma (intensidade, eco, intervalo) | M (script) | 72/80 detectadas; falhas só com eco extremo (40 ms) |
| Estresse do detector: 36 frases faladas no volume máximo, 3 vozes | M (script) | 0 falsos positivos |
| Palavra-chave: "Hey Jarvis" em inglês | A (áudio sintético) | ✅ score 0,99 |
| Palavra-chave: "Ei Jarvis" em português / frases comuns | M (script) | 0,04–0,06 (não aciona) / 0,00 |
| API de escuta: modo local, bloqueio para sessão remota (403), auditoria, aviso só para UI local | A | ✅ |
| Microfone real do PC (USB Audio) aberto a 16 kHz pela escuta local, 2 s, só nível | M | ✅ 24 quadros em 2 s, sem gravação |
| Navegador (Edge headless, microfone simulado com WAV): 🎤 → para no silêncio → transcreve "Jarvis, qual é a capital da Argentina?" → resposta → fala → Parar interrompe; acionamento inicia escuta; sem erros de console | M (script) | ✅ 3,5 s do fim da gravação até começar a falar (6,2 s no primeiro uso) |
| Palmas reais e "Hey Jarvis" falado por pessoa no microfone real | N | Depende de você: aba Voz → **Calibrar palmas** |
| Microfone/saída escolhidos na aba Voz com dispositivos reais | N | Headless só tem dispositivo simulado |
| **Fase 5: ferramentas** (`pytest` → 102 passed no total) | | |
| Caminhos: relativo → workspace; fora da lista; `..`; **junção NTFS** apontando para fora; dados internos do Jarvis; maiúsculas/minúsculas | A | ✅ |
| Simulação (padrão) nunca executa; perigosa sem aprovação não executa; com aprovação executa | A | ✅ |
| Somente leitura, ferramenta desativada, sessão remota só leitura, ferramenta inexistente, argumentos inválidos/enum | A | ✅ |
| Criar sem sobrescrever; bloqueio de extensões executáveis; sobrescrever com backup; mover sem sobrescrever | A | ✅ |
| Arquivo sensível (`.env`) exige confirmação; binário e arquivo grande recusados; conteúdo marcado como não confiável | A | ✅ |
| Apps só da lista; Explorador nunca fechado; script só da lista + confirmação; saída em tempo real | A | ✅ |
| Script com erro → ✗; tempo limite e **cancelamento matam o processo** (arquivo marcador nunca criado) | A | ✅ |
| Fluxo no chat: ferramenta → resultado volta ao modelo; aprovação aceita/recusada; Parar durante aprovação | A | ✅ |
| **Injeção**: arquivo manda "apague tudo", modelo obedece, confirmação continua obrigatória | A | ✅ |
| API: só sessão local muda modo/ferramentas (remota → 403) | A | ✅ |
| Modelo real (qwen3.5:4b) escolhe a ferramenta certa | M (script, 10 pedidos) | ✅ 10/10; recusou `C:\Windows\win.ini` explicando o motivo |
| Latência com ferramentas: 1ª mensagem ~4 s; seguintes 0,6–0,9 s até o 1º token | M (script) | ✅ após tirar a hora do prompt de sistema |
| Navegador: modo via interface, cartões 🔧, cartão de confirmação com foco em Recusar, recusa respeitada, histórico com cartões | M (script) | ✅ após corrigir o layout da lista de ferramentas |
| Abrir e fechar app real (Paint) | M | ✅ após corrigir um bug real: o app era morto ~2 s depois de aberto |
| Mover para a Lixeira real (SHFileOperation) | N | Testado com simulação do Windows; não executado para não sujar a sua Lixeira |
| **Fase 6: agente de programação** (`pytest` → 125 passed no total) | | |
| Área: cópia sem pastas pesadas; projeto novo vazio; fora das pastas autorizadas bloqueado; ids de área inválidos | A | ✅ |
| Escrita não escapa da área (`..`, caminho absoluto, metadados, área vizinha) e bloqueia `.exe` | A | ✅ |
| Original intocado até integrar; diff com novos/alterados/removidos | A | ✅ |
| Compilar acusa SyntaxError; executar código exige confirmação (e é simulado no modo padrão) | A | ✅ |
| pytest real na área: falha e depois passa | A | ✅ |
| Ambiente sem `GITHUB_TOKEN`/`*_API_KEY` e com perfil na área | A | ✅ |
| Limite de 2 GB: alocar 3 GB → MemoryError | A | ✅ |
| Cancelar mata a árvore inteira (neto não chega a escrever o arquivo) | A | ✅ |
| Job Object: sem ele o neto sobrevive ao tempo limite; com ele, morre | M (script) | ✅ após corrigir a criação para "suspenso" |
| Instalar dependências exige `requirements.txt` e mostra o conteúdo na confirmação | A | ✅ |
| Integrar mostra diff, faz backup, avisa que não houve commit; reverter restaura; arquivo editado depois é preservado | A | ✅ |
| Projeto novo nasce só na integração; descartar área | A | ✅ |
| Conjuntos de ferramentas por modo; modo programação remoto só leitura; chat usa o prompt de programação | A | ✅ |
| Modelo real: corrigir projeto com bug (desconto em %) e aplicar | M (script) | ✅ 54 s; testes passaram; original corrigido após aprovar |
| Modelo real: criar projeto novo (calculadora + testes) e aplicar | M (script) | ✅ 78 s; **10 testes passando fora do Jarvis**; achado: pasta duplicada `projetos/projetos` por causa de uma dica no prompt (removida) |
| Navegador: botão `</>`, aprovações clicadas, cartão de integração com diff colorido, recusa respeitada | M (script) | ✅ 52 s + 13 s; 2 bugs corrigidos; original intocado após recusar |
| npm e Flutter dentro da área | N | Comandos configurados; não testados com um projeto real |
| **Fase 7: acesso remoto** (`pytest` → 135 passed no total) | | |
| Tarefa do PC visível e interrompível pelo celular; confirmação respondida de outro aparelho | A | ✅ |
| Celular recusa, mas não aprova por padrão (403); aprova com `JARVIS_REMOTE_TOOLS_ALL` | A | ✅ |
| Limite de requisições (429); APIs novas exigem sessão; host da tailnet liberado após detecção | A | ✅ |
| Cabeçalhos reais do `tailscale serve` 1.104.1 (Host, Origin, X-Forwarded-*, identidade não falsificável) | M (servidor eco) | ✅ |
| Pela URL `https://seu-pc.sua-tailnet.ts.net` (a partir do PC): página, login, cookie Secure/HttpOnly, sessão remota, CSRF 403, microfone do PC 403, permissões 403, só ferramentas de leitura, chat por wss | M (script) | ✅ |
| Pela URL da tailnet: celular vê tarefa do PC, aprovar → 403, recusar → 200, PC recebe "recusado", auditoria registra | M (script) | ✅ |
| Pela URL da tailnet, navegador como celular: contexto seguro, microfone simulado → transcrição → resposta falada → Parar | M (script) | ✅ 10,9 s no primeiro uso (modelos carregando) |
| Jarvis fechado → URL da tailnet responde 502 | M | ✅ |
| **Celular real em rede externa (4G)** | N | **Pendente: checklist em REMOTE_ACCESS.md** |
| **Fase 8: Gmail e Agenda** (`pytest` → 152 passed no total) | | |
| Token cifrado com DPAPI (sem texto puro no arquivo); token corrompido avisa para reconectar | A | ✅ |
| Ferramentas só aparecem com a conta conectada | A | ✅ |
| Busca (limite de 20, snippet decodificado), leitura (texto puro preferido, HTML limpo sem script/style, id validado) | A (Google simulado) | ✅ |
| Rascunho de resposta: To, "Re:", In-Reply-To/References, threadId; destinatários inválidos e injeção de `Bcc` recusados | A | ✅ |
| Enviar: confirmação com prévia real do rascunho; recusa não envia; simulação não envia | A | ✅ |
| Agenda: listar; criar com validação de datas, duração padrão de 1 h e confirmação | A | ✅ |
| Sessão remota: lê, mas não cria rascunho (padrão); não inicia o login do Google | A | ✅ |
| Autorização expirada e falta de internet → mensagens claras | A | ✅ |
| Desconectar revoga no Google e apaga o token | A | ✅ |
| Conta Google real (2026-10-16): conectar pelo botão; token cifrado | M | ✅ após 2 correções: aceitar o nome de arquivo padrão do Google e permitir nova tentativa após login bloqueado |
| Conta real: buscar (5 em 3,1 s), ler, contar não lidos (16 em 3,3 s, antes 10,1 s), agenda, rascunho para si mesmo | M | ✅ |
| Conta real: enviar rascunho → cartão com destinatário, assunto e texto → recusado → nada enviado | M | ✅ |
| Modelo real resumindo e-mails não lidos por prioridade | M | ✅ após instrução contra inferências: a 1ª versão inventou "pagamento duplicado" |
| Temperatura 0,7 (recomendação da Qwen para respostas diretas): resumo real sem fatos inventados | M | ✅ |
| Modelo citando links "abrir" no texto | M | ✗ ignorou a instrução; os links ficam clicáveis no cartão 🔧 |
| **Envio real** para si mesmo com anexo: cartão listou o anexo → chegou em ~3 s → anexo baixado idêntico byte a byte | M | ✅ |
| **Agenda real**: criar → alterar (manteve 30 min) → apagar → agenda vazia de novo | M | ✅ |
| Anexos, agendas, alterar/apagar, links, renovação só com permissões concedidas (Google simulado) | A | ✅ 29 testes de Google; 164 no total |
| Conta real após reconectar: listar 4 agendas; eventos da agenda "Feriados no Brasil" (id com `#`) → 7 feriados até 31/12 | M | ✅ |
| **Fase 9: WhatsApp e reconhecimento facial** (`pytest` → 174 passed no total) | | |
| WhatsApp: termos da Meta (seção 4.7) lidos na fonte primária; custos e requisitos verificados | M (pesquisa) | ✅ conclusão: não integrar |
| Facial: desligado por padrão; cadastro exige exatamente 1 rosto; identificação acima e abaixo do limiar; limite de amostras | A (câmera e modelo simulados) | ✅ |
| Facial: dados cifrados e sem imagens; remover pessoa e apagar tudo; auditoria | A | ✅ |
| Facial: câmera só local (ferramenta e API); celular pode apagar | A | ✅ |
| Facial: modelos reais carregam (OpenCV 5); imagem vazia → nenhum rosto | A | ✅ |
| Facial: sanidade com imagens públicas do OpenCV (mesma pessoa 0,91–0,97; outra 0,13; limiar 0,363) | M (script) | ✅ |
| Fotos: JPEG válido, sem sobrescrever, marcador no cartão do chat, API (servir, 400/404, apagar uma e todas), sessão obrigatória | A | ✅ |
| Câmera pelo celular com `JARVIS_REMOTE_CAMERA`: cadastrar, identificar, foto, auditoria "remoto" | A | ✅ |
| Foto escura clareada automaticamente (brilho 3 → acima de 60) | A | ✅ |
| Webcam real (2026-10-16, com o módulo ativado por você): abre em 1,8 s, 640x480, detecta 1 rosto; sem salvar nem olhar a imagem | M | ✅, mas o **brilho medido foi 2–5 de 255** (ambiente escuro ou tampa) → clareamento adicionado |
| Cadastro e foto com a sua webcam | N | Para você fazer: Ferramentas → Reconhecimento facial |
| **Internet, localização e câmeras ao vivo** (`pytest` → 206 passed no total) | | |
| SSRF: 11 endereços internos ou estranhos bloqueados; redirecionamento para endereço interno bloqueado | A | ✅ |
| Real: leitura de gov.br, docs.python.org, example.com; 9 endereços internos reais bloqueados (Ollama, Tailscale, roteador, metadados…) | M | ✅ |
| Real: Wikipédia recusa sem contato no identificador (403) → mensagem explicando `JARVIS_WEB_CONTACT` | M | ✅ (não usei contato falso nem o seu e-mail) |
| Tavily (formato da chamada, limite mensal), Wikipédia (contato enviado), sem internet | A (simulado) | ✅ |
| Localização: ida e volta pelo WebSocket; com e sem chave do Maps; dados inválidos | A | ✅ |
| Navegador real + modelo real: "Onde eu estou agora?" | M | ✅ após corrigir: sem endereço, o modelo **inventava a cidade** (3/3 corretas depois) |
| Câmera do celular → PC e webcam do PC → celular, no servidor real | M | ✅ ~7 quadros/s nos dois sentidos (webcam real sem ver ou salvar imagens) |
| Navegador real: transmitir câmera (faixa, prévia, Parar) e ver o vídeo 640x480 | M | ✅ após corrigir: vídeo fora da página saía 2x2 |
| Modelo real escolhendo as ferramentas novas (câmera, busca, ler página, hora, sem ferramenta) | M | ✅ 5/5 |
| Busca real com Tavily | M | ✅ 1,6 s, com a sua chave (ver Fase 10) |
| Localização e câmera com o seu celular real | N | Para você testar |
| Desconexão da internet | N | O Jarvis não depende da internet; teste formal com o cabo desligado ainda não feito |
| Pouca memória RAM | N | Pendente |
| `iniciar.bat` / `parar.bat` | M | ✅ ver Fase 10 |
| **Fase 10: integração e acabamento** (`pytest` → 215 passed no total) | | |
| Instalação do zero numa cópia limpa (venv nova, só `requirements.txt`) e a bateria inteira nela | M | ✅ 206 passed; 1 defeito do próprio teste corrigido |
| Varredura de **todas** as rotas da API sem sessão → 401 | A | ✅ 40 rotas |
| Backup com o Jarvis aberto e restauração numa pasta nova (memórias e senha voltam; modelos ficam de fora) | A | ✅ |
| Modo da escuta local sobrevive a reinício | A | ✅ |
| Ferramentas por assunto (só as do tema da conversa vão ao modelo): 1ª mensagem de conversa nova | M (script, 13 pedidos, modelo real) | ✅ 1º token em 4–7 s (antes 17 s com as 31 ferramentas); 12/13 certas |
| Erro do teste acima: "Quanto é 15% de 240?" → o modelo inventou a ferramenta "calculadora" | M | recebeu erro e respondeu certo (36); sem efeito colateral |
| "Arquivos da pasta workspace" → o modelo pedia `workspace\workspace` (2 erros antes de acertar) | M | ✅ após corrigir a descrição do parâmetro: certo na 1ª |
| Busca real pelo chat com Tavily: Copa de 2022 e cotação do dólar | M | ✅ com fontes |
| Calibração de palmas: a sugestão pega palmas fracas que o ajuste padrão perde; microfone mudo; microfone escolhido pelo nome; só no PC; a escuta volta depois | A | ✅ |
| Navegador: aba Voz lista os microfones reais, salva a escolha, calibra (resultado simulado no teste) e aplica | M (script) | ✅ sem erros de JS e sem rolagem horizontal |
| `iniciar.bat` na cópia limpa: dependências, pergunta dos modelos de voz (20 s → Não), servidor no ar; 2ª execução → "Já está rodando"; `parar.bat` encerra; de novo → "Não está rodando" | M | ✅ após corrigir um defeito real: uma 2ª cópia apagava o PID da 1ª e o `parar.bat` deixava de funcionar |
| Palmas reais | M (você) | ✅ calibradas por você em 2026-10-16 |
| **Acesso ao PC e visual novo** (`pytest` → 225 passed no total) | | |
| Pastas do Windows pelo nome (Área de Trabalho, Downloads…) só valem depois de liberadas; criar e abrir pasta | A (pastas simuladas) | ✅ |
| Liberar pasta: recusa disco inteiro, Windows, Program Files, pasta do usuário, AppData e `data/`; sem duplicar; retirar; API só no PC (celular 403); auditoria | A | ✅ |
| Apagar arquivo específico depois de liberar a pasta: sem aprovação não apaga; com aprovação vai para a Lixeira | A | ✅ |
| Navegador: Google/YouTube/sites https abrem direto; `file:`, `javascript:`, `ms-settings:`, espaços recusados; IP/rede interna pede confirmação | A | ✅ após corrigir: no modo simulação, um endereço inválido passava como "simulado" |
| Atualizar dependência: recusa sem `.venv` (nunca no Python global), exige aprovação, comando exato, nomes e versões com `;`/`&&`/opções recusados; npm com `@escopo/pacote` | A | ✅ |
| Modelo real com as ferramentas novas (criar pasta, pesquisar no navegador, YouTube, excluir arquivo, atualizar pacote, abrir pasta), tudo interceptado | M (script) | ✅ 6/6; 1ª versão do prompt fazia toda resposta começar com "Estou pronta!" (corrigido) |
| Ícones: imagem retangular com transparência e caminho com acento → PNG 192/512 e `.ico` válido com 7 tamanhos | A | ✅ |
| Atalho da Área de Trabalho usando `web\jarvis.ico` | M | ✅ |
| Navegador headless, celular e PC: rosto no login e no início, sugestões, estados pensando → respondendo → pronta numa pergunta real, modo compacto no celular, gaveta de conversas, pastas, sem rolagem horizontal | M (script) | ✅ |
| Boca acompanhando o volume (áudio sintético de 1,6 s) | M (script) | ✅ 80 quadros de volume; abre até 11 e fecha no fim. Sem placa de som no headless, o áudio termina antes: a sincronia com som real fica para você ver |
| **Sarah: novo nome, rosto da imagem e gatilho pelo nome** (`pytest` → 230 passed no total) | | |
| Whisper base × tiny × small para achar "Sarah" em 17 frases sintéticas (6 com o nome, 9 sem, ruído, palmas) | M (script) | base: 16/17, nenhum falso positivo, ~0,5 s por frase (escolhido); tiny: 14/17; small: 1,3 s por frase |
| Gatilho: só trechos curtos são transcritos; fala longa e estalos não; o nome precisa abrir a frase ("A Sarah chegou", "Será que…" não acionam) | A (transcritor simulado) | ✅ |
| Gatilho de ponta a ponta com os modelos reais: "Sarah, que horas são?" → aciona e a pergunta chega transcrita | A | ✅ |
| Pergunta junto com o nome vai para a página; fala da Sarah pelas caixas do PC deixa a escuta surda (pelo celular, não) | A | ✅ |
| Rosto da sua imagem sem o fundo branco: queixo descendo com o volume, boca abrindo, piscada, brilho dos olhos | M (navegador + montagem em resolução cheia) | ✅ após trocar o recorte duro (aparecia um "V" no pescoço) por máscara suave no contorno do queixo |
| Ícones da imagem (página, celular, atalho "Sarah" da Área de Trabalho) | M | ✅ |
| Sincronia da boca com o som real e "Sarah" dito pela sua voz | N | Para você testar |
| **Tela no formato do modelo enviado** (`pytest` → 232 passed no total) | | |
| Enviar arquivo: salva em `arquivos\`, nunca sobrescreve, nome com `..`/caminho absoluto/`CON` neutralizado, executável e vazio recusados, limite de tamanho (413), auditoria; a Sarah lê pelo caminho da mensagem | A | ✅ |
| Navegador, celular e PC: rosto grande no início (354 px) → 112 px ao enviar; menu ☰ abre e fecha ao tocar fora; páginas com voltar; sem rolagem horizontal | M (script) | ✅ após corrigir: a gaveta escondida criava rolagem no PC e o texto da caixa quebrava em 2 linhas no celular |
| Arquivo enviado pela interface + pergunta real ("resuma em uma frase") → `ler_arquivo` → resumo correto | M (modelo real) | ✅ |
| Rosto realista com a voz real da Sarah (Kokoro, frase de 5 s) no navegador: queixo 0–13, largura da boca 0,95–1,05 pelo agudo do som, dentes, lábio de cima, cabeça balançando parada (±0,7°), inclinada ao ouvir (3,3°), olhando para cima e com olhos semicerrados ao pensar, 3 piscadas irregulares em 7 s | M (script) | ✅ após escurecer o interior da boca (aberta, parecia lábio claro) e aumentar a abertura |
| Rosto em malha (WebGL 2): 12 poses fixadas e fotografadas (boca aberta, "e", "o", olhos fechados, olhar para os lados e para cima, sorriso, sobrancelhas, giro para os dois lados, pensando) e 10 quadros durante fala real | M (script) | ✅ após 3 ajustes: interior da boca preto e dentes brancos demais (parecia recorte), brilho dos olhos atravessando as pálpebras fechadas, fresta brilhante com o olho fechado |
| Desempenho do rosto em malha no Edge | M | ~175 quadros por segundo parada e falando |
| **Revisão geral de código** (`pytest` → 239 passed; `ruff check .` sem pendências) | | |
| Falha inesperada numa ferramenta (ex.: `PermissionError`) volta ao modelo como erro, sem derrubar a resposta | A | ✅ (antes: "Erro interno" e resposta perdida) |
| Acesso à web conecta no IP conferido, com o nome no Host e no SNI (DNS rebinding não passa); sites reais com HTTPS e redirecionamentos; 7 endereços internos bloqueados | A + M | ✅ |
| WebSocket do chat: JSON inválido e mensagem que não é objeto não derrubam a conexão; a resposta em andamento é cancelada em qualquer desconexão | A | ✅ |
| Ollama caindo no meio da resposta → mensagem clara | A | ✅ |
| Rodada só de ferramenta não grava balão vazio no histórico | A | ✅ |
| `.env` com valores entre aspas | A | ✅ |
| Busca de arquivos ignora `node_modules`, `.git` e afins | A | ✅ |
| Anexo de e-mail executável recusado antes de baixar (regressão pega pelo teste durante a revisão) | A | ✅ |
| Navegador: avisos no rodapé (erro sem tratamento, conversa ocupada, sem conexão mantendo o anexo); layout, envio de arquivo, menu e rosto falando depois da separação do `avatar.js` | M (script) | ✅ |
| Modelo real com as ferramentas de acesso ao PC depois da revisão | M (script) | ✅ 6/6 |
| **Histórico na lateral, armazenamento e "Sarah" robusta** (`pytest` → 247 passed) | | |
| Conversas pela última atividade; lateral fixa no PC (recolher lembrado), gaveta pela esquerda no celular, grupos por data, busca | A + M (navegador) | ✅ |
| Armazenamento: só áreas sem uso há 7+ dias e backups com 30+ dias saem (inclusive arquivos somente leitura do .git); arquivos do usuário ficam; auditoria antiga sai; VACUUM com o banco em uso; hardlinks contados uma vez; só no PC | A | ✅ após corrigir a soma dos modelos (2,1 GB → 0,87 GB: hardlinks contados duas vezes) |
| Microfone escolhido some do Windows: aviso, pílula vermelha, e volta sozinho quando reaparece; microfone travado (sem áudio por 5 s) detectado | A | ✅ causa real encontrada no log: "High Definition Audio" sumiu às 12h18 e a escuta desistia |
| "Sarah" com a Sarah parada (navegador + modelo real): falando → ignorado; parada há 31 min → conversa nova; logo depois → mesma conversa | M (script) | ✅ |
| Pacotes do "Hey Jarvis" removidos da .venv (openwakeword, scikit-learn, scipy, threadpoolctl) | M | ✅ 709 → 524 MB; `pip check` sem pendências |
| **Visão, Sarah em segundo plano e app Android** (`pytest` → 260 passed; `ruff check .` sem pendências) | | |
| Imagem enviada pelo 📎 vai ao modelo reduzida (≤1024 px, JPEG); só as 2 mais recentes; caminhos fora das pastas autorizadas e não-imagens ignorados | A | ✅ |
| `olhar_camera`: celular devolve JPEG validado (tamanho, base64), foto não é salva, auditoria; PC respeita a regra de câmera remota | A | ✅ |
| Modelo real (qwen3.5:4b): foto da webcam capturada e descrita | M (script) | ✅ 17 s a captura com o modelo frio; descrição em 6,3 s; print com texto lido corretamente em 9,5 s |
| Mãos livres (sem página aberta no PC): pergunta junto com o nome, só o nome → bipe → grava → transcreve, silêncio não faz nada, resposta falada frase a frase sem markdown, conversa continua dentro de 30 min, acionamento sem página vai para o modo mãos livres | A | ✅ (microfone e caixas de som reais: para você testar) |
| Iniciar com o Windows: atalho real criado e apagado pelo Windows; só no PC (celular → 403); auditoria | A | ✅ |
| `pythonw -m jarvis` (como no início automático): sem janela, log em `data\logs\servidor.log`, sem registro de cada requisição | M | ✅ |
| `iniciar.bat` com a Sarah já rodando abre a página e sai sem erro | M | ✅ |
| APK (Flutter, `flutter build apk --release --split-per-abi`): compila; instalado e aberto no emulador Pixel 7 Pro | M | ✅ abre com o ícone e mostra a tela "Não consegui falar com a Sarah": o emulador não resolve o nome da tailnet (MagicDNS), nem com `-dns-server 100.100.100.100` |
| APK num celular real com Tailscale (login, voz, câmera, 📎, localização) | N | Para você testar |
