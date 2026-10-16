# Segurança e privacidade

## Modelo de ameaça (o que estamos protegendo e de quem)

| Ameaça | Proteção implementada | Teste |
|---|---|---|
| Alguém na rede acessar o Jarvis | Servidor escuta **só em 127.0.0.1**; nenhuma porta é aberta no firewall | `test_server_binds_loopback_only` |
| Site malicioso no seu navegador chamar a API local (CSRF) | Cookie `SameSite=Strict` + `Origin` deve ser exatamente igual ao `Host` em todo POST/PUT/DELETE e no WebSocket | `test_cross_origin_post_blocked`, `test_ws_rejects_foreign_origin` |
| DNS rebinding (domínio externo apontando para 127.0.0.1) | Cabeçalho `Host` precisa estar na lista `localhost`/`127.0.0.1`/`JARVIS_ALLOWED_HOSTS` | `test_foreign_host_blocked` |
| Força bruta na senha | 5 erros em 5 minutos bloqueiam o login por 5 minutos | `test_wrong_password_then_rate_limit` |
| Vazamento da senha | Guardada só como hash scrypt com sal; nunca vai para logs nem para a auditoria | `test_password_not_stored_in_plain_text` |
| Roubo de sessão | Token aleatório de 256 bits; o banco guarda só o SHA-256; cookie `HttpOnly`; `Secure` quando acessado por HTTPS; expira em 12 h | `test_login_sets_protected_cookie`, `test_expired_session_rejected` |
| Sessão esquecida em outro aparelho | Aba Segurança: lista sessões, "Encerrar outras sessões", "Sair"; trocar a senha derruba todas | `test_revoke_other_sessions`, `test_password_change_kills_sessions` |
| Sessão revogada continuar no WebSocket aberto | A sessão é revalidada a cada mensagem | `test_revoked_session_closes_ws` |
| XSS pela resposta do modelo | Todo HTML é escapado antes da formatação Markdown; CSP `default-src 'self'` sem scripts inline | `test_render_markdown_escapes_html`, `test_security_headers` |
| Clickjacking | `X-Frame-Options: DENY` e `frame-ancestors 'none'` | `test_security_headers` |
| Dados enviados para a nuvem sem querer | Modelos `*cloud*` do Ollama e URLs de LLM não locais são recusados na inicialização | `test_cloud_model_rejected`, `test_remote_llm_rejected` |
| Injeção de instruções via memória/arquivos/e-mails | O prompt de sistema marca esse conteúdo como dado; a partir da Fase 5, as ações perigosas exigem confirmação humana, independentemente do que o modelo "decidir" | parcial (Fase 5) |

## Microfone e voz

| Situação | Comportamento | Teste |
|---|---|---|
| Botão 🎤 | O navegador grava só até você parar ou haver silêncio; o áudio vai para `/api/stt`, é transcrito em memória e descartado. Nunca é salvo em disco. A transcrição vira uma mensagem normal do chat. | `test_speech_round_trip` + navegador |
| Respostas faladas | O texto vai para `/api/tts`, que devolve o WAV; nada é salvo. | `test_tts_returns_wav_and_204_for_symbols` |
| Escuta local (palmas/nome "Sarah") | **Desligada por padrão.** Quando ligada, abre o microfone do PC e analisa quadros de 80 ms em memória; trechos curtos de fala (até ~3 s) são transcritos só em memória para procurar o nome; uma fila limitada descarta quadros atrasados em vez de acumular áudio. Não grava, não envia pela rede. Indicador "Escuta local" sempre visível no topo. | `test_listener_cooldown_and_callback` |
| Celular tentando ligar o microfone do PC | Bloqueado (403): só sessões locais podem mudar a escuta. | `test_remote_session_cannot_enable_pc_mic` |
| Acionamento enviado ao celular | Não: o aviso de acionamento vai só para interfaces abertas no próprio PC. | `test_remote_ui_does_not_receive_wake` |
| "Sarah" sem página aberta (mãos livres) | Depois do nome, grava só a pergunta (até 15 s, para no silêncio), transcreve em memória e descarta o áudio. Ações perigosas continuam pedindo confirmação: ela avisa em voz alta e a confirmação aparece no celular ou numa página aberta (5 min; sem resposta = recusa). Cada acionamento fica na auditoria (`maos_livres`). | `test_handsfree.py` |
| Iniciar com o Windows | Desligado por padrão; só uma sessão no próprio PC liga (celular → 403). É um atalho na pasta Inicializar do usuário: sem administrador, sem serviço; desligar apaga o atalho. Auditado (`inicio_automatico`). | `test_autostart_toggle` |
| Limites | Áudio até 10 MB; texto para fala até 1000 caracteres; voz e velocidade validadas. | `test_stt_rejects_empty_and_oversized`, `test_tts_validation` |

A voz não identifica **quem** está falando. Qualquer pessoa perto do microfone pode acionar a Sarah com palmas ou dizendo o nome dela. Por isso, as ações sensíveis (Fase 5) sempre vão exigir confirmação na tela.

## Acesso remoto (Fase 7)

| Ameaça | Proteção | Verificado |
|---|---|---|
| Alguém na internet achar o Jarvis | Nenhuma porta aberta; `tailscale serve` é tailnet only (sem Funnel). Só aparelhos da sua conta Tailscale chegam ao endereço | `serve status` = "tailnet only"; Jarvis fechado → 502 |
| Aparelho da tailnet sem senha | A senha do Jarvis continua obrigatória; o limite de tentativas vale para todos | testes de login |
| Interceptação | WireGuard de ponta a ponta + HTTPS com certificado válido (`*.ts.net`) | teste real: `isSecureContext` = true |
| Sessão roubada no celular | Cookie `Secure` (detectado por `X-Forwarded-Proto: https`) + `HttpOnly` + `SameSite=Strict`; expira em 12 h; revogável | teste real pela tailnet |
| CSRF / DNS rebinding pela tailnet | O `Host` real é preservado pelo serve; só o nome detectado do PC é aceito; `Origin` precisa ser igual ao `Host` | medido: `Host`/`Origin`/`X-Forwarded-*` reais; origem falsa → 403 |
| Falsificar identidade Tailscale | O serve descarta `Tailscale-User-*` enviados pelo cliente e põe os reais | medido: valor falso substituído |
| Celular comprometido ou perdido | Sessão remota: só ferramentas de leitura; não aprova ações perigosas, não liga o microfone do PC, não muda permissões; pode parar e recusar. Expulse o aparelho no painel do Tailscale e encerre as sessões | `test_remote.py` + teste real |
| Excesso de requisições | 240 por minuto por cliente na API (429 acima disso) | `test_rate_limit` |

`JARVIS_REMOTE_TOOLS_ALL=true` libera ações e aprovações pelo celular (sempre com o cartão de confirmação). Fica desligado até você decidir.

## Google: Gmail e Agenda (Fase 8)

| Ponto | Como é tratado | Teste |
|---|---|---|
| Senha do Google | Nunca passa pelo Jarvis (OAuth no site do Google; retorno em `localhost`, porta aleatória) | — |
| Token | `data/google/token.bin` cifrado com DPAPI (só seu usuário do Windows, neste PC); nunca em logs ou auditoria | `test_token_encrypted_with_dpapi` |
| Escopos | `gmail.readonly`, `gmail.compose` (rascunhos e envio), `calendar.events` (eventos), `calendar.calendarlist.readonly` (lista de agendas); nada de apagar e-mails | `test_refresh_uses_only_granted_scopes` |
| Anexos | Baixar: só para `data/workspace/anexos`, sem sobrescrever, executáveis recusados. Anexar: só de pastas autorizadas, nunca arquivos sensíveis, máx. 20 MB | `test_download_attachment`, `test_draft_refuses_sensitive_or_outside_attachments` |
| Alterar ou apagar evento | Confirmação com o evento atual e o que muda; ids de agenda e evento validados (sem `../`) | `test_change_event_keeps_duration_and_confirms`, `test_delete_event_confirms` |
| Enviar e-mail | Só envia **rascunho existente**, com confirmação que mostra destinatário, assunto e texto; simulado no modo Simulação | `test_send_needs_confirmation_with_preview` |
| Criar evento | Confirmação com título, data, hora e local; datas validadas | `test_create_event_validation_and_confirmation` |
| Injeção por e-mail | Conteúdo marcado como DADO; envio depende do seu clique; quebras de linha em destinatário ou assunto (injeção de `Bcc`) são recusadas | `test_draft_rejects_bad_addresses` |
| Conectar | Só no próprio PC (abre o navegador local); o celular recebe 403 | `test_remote_cannot_start_google_login` |
| Desconectar | Revoga no Google e apaga o token; auditado | `test_google_api_endpoints` |
| Expiração e falta de internet | Mensagens claras, sem travar o Jarvis | `test_expired_authorization_message`, `test_offline_message` |

## Reconhecimento facial (Fase 9, opcional e desligado)

| Ponto | Como é tratado | Teste |
|---|---|---|
| Padrão | Desligado; ferramenta e API inativas | `test_disabled_by_default` |
| Câmera | Abre só sob demanda. Pelo celular, só com `JARVIS_REMOTE_CAMERA=true` (sem a chave → 403) | `test_phone_cannot_use_pc_camera_but_can_delete`, `test_phone_camera_when_enabled` |
| Fotos | Só quando pedidas; servidas apenas com sessão válida, `Cache-Control: no-store`; nomes validados (sem `../`); auditadas com origem local ou remota; apagáveis | `test_photo_api`, `test_photos_need_session` |
| Armazenamento | Cadastro sem imagens: vetores e nomes cifrados com DPAPI. Fotos pedidas ficam em `data/workspace/fotos` (não cifradas, para você abrir) | `test_stored_encrypted_without_images` |
| Exclusão | Por pessoa ou tudo, sempre disponível | `test_remove_and_remove_all` |
| Uso em segurança | **Nunca** autoriza ações: não há prova de vida | por desenho |

## Internet, localização e câmeras ao vivo

| Ponto | Proteção | Teste |
|---|---|---|
| SSRF (usar o Jarvis para acessar a rede interna) | Só http/https públicos, portas 80/443; DNS checado (privado, loopback, link-local, CGNAT/Tailscale e metadados bloqueados), inclusive após cada redirecionamento | `test_internal_or_odd_urls_blocked`, `test_redirect_to_internal_blocked` + teste real com 9 endereços internos |
| Conteúdo da web | Marcado como DADO não confiável; só texto; até 1,5 MB; scripts e menus removidos | `test_page_text_extraction_and_limits` |
| Chaves (Tavily, Google Maps) | Só no `.env` (fora do Git), nunca em logs ou no modelo | — |
| Localização | Pedida ao navegador do aparelho, que exige permissão; consulta auditada; o modelo não deduz endereço sem geocodificação | `test_location_round_trip_over_websocket`, teste com o modelo real |
| Câmera do PC ao vivo | Exige sessão; pelo celular só com `JARVIS_REMOTE_CAMERA`; máximo de 10 min; auditada (quem viu, de onde) | `test_pc_camera_from_phone_needs_flag`, `test_camera_requires_session` |
| Foto para a Sarah analisar (`olhar_camera`) | Só quando você pede. Uma foto, analisada pelo modelo local e descartada (não é salva). Pelo celular, a foto do PC segue a regra `JARVIS_REMOTE_CAMERA`. Auditada (`camera_olhada`). O aparelho que fotografa **sempre mostra** que a câmera está em uso (luz da webcam no PC; aviso na página e indicador do Android no celular): esconder isso não é suportado, de propósito. | `test_vision.py` |
| Imagens enviadas pelo 📎 | Analisadas pelo modelo local; só arquivos de `data\workspace\arquivos` ou pastas autorizadas; nada sai do PC. | `test_vision.py` |
| Câmera do celular | Só com a página aberta; faixa vermelha com prévia e Parar sempre visíveis; para sozinha em 10 min ou sem espectadores; só aceita JPEG; nada é gravado | `test_phone_camera_reaches_pc` + navegador real |

## Onde ficam os dados

Tudo em `data/` (fora do Git): banco SQLite, logs, sessões. Não há telemetria. O Ollama roda localmente; o Jarvis não chama nenhum serviço externo.

## Segredos

- `.env` só guarda configurações, nunca senhas. `.env.example` não tem nenhum valor real.
- `.gitignore` exclui `data/`, `.env`, `*.db`, `credentials*.json`, `token*.json` e `client_secret*.json`.
- Tokens OAuth (Fase 8) ficarão em `data/`, nunca no Git, nos logs ou no contexto do modelo.

## Ferramentas (Fase 5)

Não há execução de comando livre. O modelo só pode chamar as ferramentas abaixo, com argumentos validados. Toda chamada vai para a auditoria (argumentos cortados em 200 caracteres; conteúdo de arquivos não é gravado na auditoria).

| Ferramenta | Risco | O que acessa | Confirmação |
|---|---|---|---|
| `data_hora` | leitura | Relógio do sistema | não |
| `info_sistema` | leitura | Nome da CPU (registro), RAM, espaço em disco, tempo ligado | não |
| `listar_arquivos` | leitura | Nomes e tamanhos numa pasta **autorizada** | não |
| `buscar_arquivos` | leitura | Nomes de arquivos em pastas autorizadas (máx. 100 resultados / 50 mil arquivos varridos) | não |
| `ler_arquivo` | leitura → **perigosa** se o nome parecer sensível (`.env`, chaves, `token`, `senha`, `credential`…) | Texto de até 1 MB numa pasta autorizada; o resultado é marcado como DADO não confiável | só se sensível |
| `criar_arquivo` | ação | Cria arquivo **novo** numa pasta autorizada; nunca sobrescreve; bloqueia extensões executáveis (`.exe .bat .ps1 .vbs .lnk .reg`…) | não |
| `mover_arquivo` | ação | Move/renomeia dentro das pastas autorizadas, sem sobrescrever | não |
| `salvar_memoria` | ação | Grava uma memória (visível e apagável na aba Memória) | não |
| `abrir_aplicativo` | ação | Abre só apps da lista em `data/permissoes.json` (sem shell) | não |
| `abrir_projeto` | ação | Abre uma pasta autorizada no VS Code ou no Explorador | não |
| `criar_pasta` | ação | Cria uma pasta nova dentro de uma pasta autorizada | não |
| `abrir_pasta` | ação | Abre uma pasta autorizada no Explorador | não |
| `abrir_no_navegador` | ação → **perigosa** se o endereço não for `https` ou for de rede interna (IP, `localhost`, nome sem ponto) | Abre o navegador padrão numa pesquisa do Google, YouTube ou Maps, ou num link `http(s)`; `file:`, `javascript:` e outros esquemas são recusados | só nesses casos |
| `atualizar_dependencia` | **perigosa** | `pip install --upgrade` **no ambiente virtual do projeto** (nunca no Python global) ou `npm install pacote@versão` numa pasta com `package.json`; nome do pacote e versão validados (sem espaços, `;`, `&&` ou opções); o cartão mostra o comando exato | **sim** |
| `executar_diagnostico` | leitura | Só `ipconfig`, `ping 1.1.1.1` ou `tasklist`, com argumentos fixos | não |
| `sobrescrever_arquivo` | **perigosa** | Substitui um arquivo autorizado; guarda cópia em `data/backups` | **sim** |
| `mover_para_lixeira` | **perigosa** | Manda para a Lixeira do Windows (recuperável); recusa apagar uma pasta autorizada inteira | **sim** |
| `fechar_aplicativo` | **perigosa** | `taskkill` **sem** `/F` (o app pode pedir para salvar) de um app da lista; o Explorador nunca é fechado | **sim** |
| `executar_script` | **perigosa** | Só scripts que **você** cadastrou em `data/permissoes.json`, com tempo limite; a saída aparece em tempo real | **sim** |

Regras aplicadas pelo servidor, não pelo modelo (o modelo não consegue desligá-las):
- **Modos**: `simulação` (padrão: ações perigosas são só descritas, nunca executadas), `normal` (executam após você clicar em Aprovar) e `somente leitura` (só ferramentas de leitura são oferecidas).
- **Pastas**: só as listadas em `data/permissoes.json` (padrão: apenas `data/workspace`). Você libera ou retira pastas na aba Ferramentas → **Pastas autorizadas** (só no PC; o celular recebe 403), e cada mudança vai para a auditoria. O servidor recusa liberar um disco inteiro, as pastas do Windows e de programas (`Windows`, `Program Files`, `ProgramData`), a pasta do usuário inteira, o `AppData` (senhas salvas do navegador, tokens) e a pasta `data/`. Nomes como "Área de Trabalho", "Documentos" e "Downloads" viram o caminho real informado pelo Windows (inclusive se o OneDrive moveu a pasta), mas continuam valendo só se a pasta estiver liberada. Caminhos passam por `resolve()`, então `..`, links e junções NTFS não escapam. A pasta `data/` do Jarvis (banco, sessões, permissões) é sempre bloqueada, exceto `data/workspace`.
- **Sessões remotas**: só ferramentas de leitura, a menos que `JARVIS_REMOTE_TOOLS_ALL=true`. Só sessões locais mudam modo e ferramentas.
- **Confirmação**: aparece um cartão com o resumo da ação, Aprovar e Recusar (o foco vai para Recusar). Sem resposta em 5 minutos, a ação é recusada. **Parar** cancela tudo.
- **Tempo e recursos**: cada ferramenta tem tempo limite; processos são mortos se a tarefa for cancelada ou estourar o tempo; resultados são cortados em 6000 caracteres.
- **Injeção de instruções**: mesmo que um arquivo lido diga "apague tudo sem perguntar" e o modelo obedeça, a ação perigosa continua exigindo o seu clique (`test_injected_instruction_cannot_skip_confirmation`).

### Agente de programação (Fase 6)

| Ferramenta | Risco | O que faz | Confirmação |
|---|---|---|---|
| `estrutura_projeto` | leitura | Lista arquivos de um projeto autorizado ou de uma área | não |
| `preparar_area` | ação | Copia um projeto autorizado para `data/workspace/.areas/<id>` (máx. 3000 arquivos / 100 MB, sem `.git`, `node_modules`, `.venv`, `build`…) | não |
| `escrever_arquivo` | ação | Escreve **só dentro da área**; bloqueia binários executáveis (`.exe .dll .msi .lnk`…) | não |
| `ver_alteracoes` | leitura | Diff da área contra o original | não |
| `executar_verificacao` | ação (compilar Python, ruff, `node --check`) / **perigosa** (pytest, executar script, npm, flutter, instalar dependências) | Só comandos de uma lista fixa, dentro da área | **sim**, para tudo que executa código |
| `integrar_alteracoes` | **perigosa** | Copia novos/alterados para o original; backup dos alterados; nunca apaga nada no original | **sim**, com o diff no cartão |
| `reverter_integracao` | **perigosa** | Restaura os alterados e remove os criados, exceto arquivos que você editou depois | **sim** |
| `descartar_area` | ação | Apaga a área (o original não é tocado) | não |

Isolamento da execução (sem administrador e sem Docker):
- **Ambiente limpo**: só variáveis essenciais (PATH, SYSTEMROOT…); nada com `TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `AUTH`…; `USERPROFILE`, `APPDATA`, `LOCALAPPDATA` e `TEMP` apontam para a área, então ferramentas não acham `.npmrc`, `pip.ini`, `.git-credentials` etc. pelo caminho padrão (`test_clean_environment`). Os caches de pacotes (pip, npm, pub) são reaproveitados e não contêm credenciais.
- **Job Object do Windows**: o processo nasce suspenso, entra no Job e só então roda. Limite de 2 GB de memória e 64 processos. Ao terminar, cancelar ou estourar o tempo, **toda a árvore de processos é encerrada** (`test_memory_limit`, `test_cancel_kills_whole_process_tree`).
- **Tempo limite**: 5 min por verificação; 10 min para instalar dependências.
- **Sem shell**: comandos montados como lista; `cmd /c` só com argumentos fixos (npm/flutter são `.cmd`).
- **Sem Git destrutivo**: o agente não tem ferramenta de commit, push, reset ou deploy.

**O que NÃO é isolado**: rede e leitura de arquivos do seu usuário. Para isso seria preciso Docker (`--network none`), Windows Sandbox ou outro usuário do Windows, o que exige administrador ou ~2 GB de RAM. Por isso todo código executado passa pela sua confirmação.

Para liberar uma pasta pessoal (ex.: Documentos), adicione o caminho em `"pastas"` no `data/permissoes.json`. Esse é um passo consciente seu: o Jarvis nunca altera esse arquivo.

## Limitações honestas

- Qualquer programa rodando com o seu usuário do Windows pode ler `data/jarvis.db`. A proteção é a do seu perfil do Windows; o banco não é criptografado.
- A sessão local e a remota usam a mesma senha; as permissões diferem pelo tipo de sessão (remota = só leitura por padrão).
- "Remota" é detectada pelos cabeçalhos do `tailscale serve`. Um programa rodando no próprio PC poderia se passar por remoto, mas isso só reduz as permissões dele.
- O limite de tentativas de login fica em memória e é zerado ao reiniciar o Jarvis.
