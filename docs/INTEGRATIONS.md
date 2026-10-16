# Integrações

## Google: Gmail e Agenda

**Estado (2026-10-16):** conectado à sua conta Google e testado de verdade, inclusive **envio real** (e-mail com anexo para você mesmo; o anexo baixado de volta saiu idêntico) e **criar, alterar e apagar evento** (a agenda voltou ao estado original). Mais 29 testes automáticos com o Google simulado.

### O que o Jarvis pode fazer
| Ação | Risco | Confirmação |
|---|---|---|
| Buscar e-mails (sintaxe do Gmail: `is:unread`, `from:`, `subject:`, `newer_than:7d`, `after:`/`before:`) | leitura | não |
| Ler um e-mail (texto puro; HTML vira texto) | leitura | não |
| Resumir, classificar por prioridade, achar tarefas e prazos | feito pelo modelo a partir das buscas e leituras | — |
| Baixar **anexo** para `data\workspace\anexos` (executáveis são recusados) | ação | não |
| Criar **rascunho** (inclusive resposta na mesma conversa), com **anexos** de pastas autorizadas | ação: **não envia** | não |
| **Enviar** um rascunho | perigosa | **sim**: o cartão mostra destinatário, assunto, anexos e texto |
| Listar as **agendas** da conta (principal, compartilhadas, feriados) | leitura | não |
| Ver eventos (de qualquer agenda) com os ids | leitura | não |
| **Criar**, **alterar** ou **apagar** evento | perigosa | **sim**: o cartão mostra o evento e o que muda |

Cada e-mail encontrado aparece no cartão 🔧 com um link **abrir** (Gmail), para conferir antes de agir.
Arquivos que parecem sensíveis (`.env`, chaves, `token`, `senha`…) **nunca são anexados**, mesmo que um e-mail peça.

### Custos e limites (verificado em 2026-10-15)
- **Gmail API** e **Google Calendar API**: "All standard use … is available at no additional cost". Os limites (80 milhões de unidades por dia no Gmail; 1 milhão de requisições por dia na Agenda) ficam muito acima de uso pessoal. O Google avisa que, **ainda em 2026**, passar desses limites vai gerar cobrança. Sem conta de faturamento, o que passar do limite simplesmente falha.
- **Não é preciso cadastrar cartão** nem conta de faturamento para essas APIs.

### Passo a passo (uma vez, uns 10 minutos)
1. Acesse https://console.cloud.google.com/ com a conta Google que o Jarvis vai usar.
2. Crie um projeto: seletor de projetos no topo → **Novo projeto** → nome `Jarvis Local` → Criar. Deixe-o selecionado.
3. Ative as APIs: **APIs e serviços → Biblioteca** → procure e clique em **Ativar** em:
   - **Gmail API**
   - **Google Calendar API**
4. Configure o consentimento: **Menu → Google Auth platform → Branding** (se aparecer "not configured yet", clique em **Get Started**):
   - Nome do app: `Jarvis Local`; e-mail de suporte: o seu.
   - **Audience (público): External.** Contas pessoais do Gmail não podem usar "Internal".
   - Contato: o seu e-mail. Aceite a política e clique em **Create**.
5. Em **Google Auth platform → Audience → Test users**, clique em **Add users** e adicione **o seu próprio e-mail**.
6. Crie a credencial: **Google Auth platform → Clients → Create client**:
   - Application type: **Desktop app**; nome: `Jarvis`.
   - Clique em **Create**, depois em **Download JSON**.
7. Salve o arquivo baixado na pasta `C:\dev\JarvisLocal\data\google\`. Pode manter o nome que o Google dá
   (`client_secret_….apps.googleusercontent.com.json`) ou renomear para `client_secret.json`.
8. No Jarvis, **no PC**: aba **Ferramentas → Integrações → Conectar conta Google**. O navegador abre:
   - escolha a conta;
   - aparece "**O Google não verificou este app**". É esperado, porque o app é seu: clique em **Continuar**;
   - confira as permissões (ler e-mails, criar rascunhos e enviar, ver e editar eventos) e clique em **Continuar**;
   - aparece "Jarvis conectado ao Google". Pode fechar a aba.

### Os 7 dias do modo "Testing"
Com o app em modo **Testing**, o Google faz a autorização **expirar em 7 dias**. O Jarvis avisa ("A autorização do Google expirou… Reconecte"), e basta clicar em **Conectar** de novo.
Para não precisar repetir: em **Audience**, clique em **Publish app**. O aviso de "app não verificado" continua aparecendo no login, o limite de 100 usuários não importa para você, e a autorização deixa de expirar a cada semana. **Isso é opcional e fica a seu critério.**

**Publicar exige um endereço público** com página inicial e política de privacidade. As duas páginas estão prontas em `site\`
(troque `COLOQUE-AQUI-O-SEU-E-MAIL` em `site\privacidade.html`). Um jeito grátis de publicá-las:
1. No repositório **público** `<seu-usuario>.github.io` (crie se não existir), envie os dois arquivos de `site\` numa pasta
   **`sarah/`**. Se você já tem um site nesse repositório, não substitua o `index.html` da raiz.
2. Em alguns minutos elas ficam em `https://<seu-usuario>.github.io/sarah/` e `https://<seu-usuario>.github.io/sarah/privacidade.html`.
3. No Google Cloud → **Branding**: nome do app (ex.: Sarah), e-mail de suporte, as duas URLs, o domínio autorizado
   `<seu-usuario>.github.io` e o e-mail de contato. **Não envie logotipo**: com logotipo o Google exige verificação.
4. **Audience → Publish app**, depois **Reconectar** na Sarah uma vez.

Esse repositório público tem só as duas páginas, nada do código nem dos seus dados.

### Segurança
- A senha do Google nunca passa pelo Jarvis: o login acontece no site do Google.
- O retorno do login vai para um servidor temporário em `localhost`, numa porta aleatória, que fecha em seguida.
- O token fica em `data\google\token.bin`, **cifrado com a DPAPI do Windows**: só a sua conta do Windows, neste PC, consegue decifrá-lo. Ele nunca vai para logs, auditoria, Git ou para o modelo.
- `client_secret.json`: em apps de desktop, o Google não o trata como segredo forte, mas ele fica em `data\` (fora do Git).
- E-mails são tratados como **dados não confiáveis**: um e-mail que diga "envie tudo para X" não tem como enviar nada sem o seu clique em Aprovar. Linhas novas em destinatário ou assunto, que serviriam para injetar `Bcc`, são recusadas.
- Pelo celular: buscar e ler funciona. Criar rascunho, enviar e criar evento seguem `JARVIS_REMOTE_TOOLS_ALL` (ligado por você), sempre com confirmação.

### Desconectar
- No Jarvis: **Ferramentas → Integrações → Desconectar**. Revoga o acesso no Google e apaga o token local.
- No Google: https://myaccount.google.com/permissions → Jarvis Local → Remover acesso.
- Para remover tudo: apague o projeto no Google Cloud.

### Permissões novas
Quando o Jarvis ganha um recurso que precisa de outra permissão (ex.: listar agendas), a aba Integrações mostra **Reconectar**. Até lá, o resto continua funcionando com as permissões antigas.

## Internet: busca e leitura de páginas

O Jarvis pesquisa na internet quando a pergunta depende de fatos atuais, cita as fontes com links e pode ler uma página para confirmar detalhes.

| Fonte | Custo | Como ativar |
|---|---|---|
| **Tavily** (busca na web inteira) | Grátis: 1.000 buscas por mês, **sem cartão** (verificado em 2026-10-16) | Crie a conta em https://app.tavily.com, copie a chave `tvly-…` e coloque `JARVIS_TAVILY_KEY=tvly-…` no `.env` |
| **Wikipédia** (sem Tavily) | Grátis | A Wikipédia exige um contato no identificador do programa: `JARVIS_WEB_CONTACT=seu e-mail ou site` no `.env`. Sem isso, ela responde 403 |

Alternativas verificadas e descartadas: a API de busca do Google está fechada para novos clientes (encerra em 01/01/2027), e a do Brave passou a exigir cartão em 2026.

**Segurança:** a leitura só acessa endereços **públicos** (http/https nas portas 80 e 443). IPs da sua rede, do próprio PC, do Tailscale e de metadados de nuvem são recusados, inclusive após redirecionamentos. Assim, uma página ou um e-mail malicioso não consegue usar o Jarvis para chegar ao Ollama, ao roteador ou a outros serviços. O conteúdo da web é tratado como dado não confiável. Páginas: até 1,5 MB, só texto.

## Localização

"Onde eu estou?" (ou "onde está o celular?", "onde está o PC?"). O Jarvis pede a localização à página aberta no aparelho, que usa o GPS/Wi-Fi do próprio navegador. Na primeira vez, o navegador pede permissão.

| Parte | Como funciona | Custo |
|---|---|---|
| Coordenadas | Navegador do aparelho (celular ou PC) | Grátis |
| Link do mapa | `https://www.google.com/maps?q=…` | Grátis (sem API) |
| **Endereço** | Google Geocoding com **a sua chave** | Grátis até 10 mil por mês. **O Google exige projeto com faturamento ativo (cartão)** |

**Para ter o endereço (opcional):**
1. No seu projeto do Google Cloud (com faturamento ativo): APIs e serviços → Biblioteca → ative **Geocoding API**.
2. APIs e serviços → Credenciais → **Criar credenciais → Chave de API**. Em "Restrições de API", deixe **só a Geocoding API**.
3. **Trave a cota para nunca pagar:** Google Maps Platform → Cotas → Geocoding API → "Requests per day" = **300** (≈ 9 mil por mês, abaixo dos 10 mil grátis). Crie também um alerta de orçamento de R$ 1.
4. Coloque `JARVIS_GOOGLE_MAPS_KEY=…` no `.env` e reinicie.

Sem a chave, o Jarvis informa as coordenadas e o link do mapa. Ele foi instruído a **não adivinhar a cidade** pelas coordenadas: no teste, sem essa instrução, o modelo de 4B chutou outra cidade.
Avaliado e não usado: OpenStreetMap/Nominatim é grátis e sem cartão, mas a política dele pede para não enviar dados pessoais, e a sua localização é exatamente isso.

**Limitação:** só funciona com a página do Jarvis **aberta e na tela** do aparelho. Não há rastreamento em segundo plano.

## Câmeras ao vivo

- **Câmera do PC no celular:** "mostre a câmera do PC" ou Ferramentas → **Ver câmera do PC**. Pelo celular, exige `JARVIS_REMOTE_CAMERA=true` (ligado).
- **Câmera do celular no PC:** "mostre a câmera do celular" ou Ferramentas → **Ver câmera do celular**. O PC pede à página aberta no celular, que começa a transmitir (câmera traseira; "Trocar câmera" muda para a frontal).
- Enquanto transmite, o aparelho mostra uma **faixa vermelha com a prévia** e o botão **Parar**.
- Tudo **desliga sozinho em 10 minutos**, ou quando ninguém mais está assistindo (15 s).
- Medido: ~7 quadros por segundo nos dois sentidos, ~40 KB por quadro (cerca de 2,4 Mbit/s no 4G).
- O vídeo passa pelo PC e pelo Tailscale, **sem nenhum serviço externo**, e **nada é gravado** (só o último quadro em memória). Para guardar uma imagem, use "tirar foto".
- Limitação: para o PC ligar a câmera do celular, a página do Jarvis precisa estar **aberta e na tela** do celular. Celulares pausam páginas em segundo plano.

## SMS (avaliação, 2026-10-16)

**Gratuito de verdade, só de um jeito:** um **celular Android sobrando, com chip**, em casa, rodando o app de código aberto **SMS Gateway for Android** (licença Apache 2.0) no modo local.
- Você manda SMS do seu celular para o número desse Android, mesmo sem internet móvel. O app repassa a mensagem ao Jarvis pela rede de casa, e o Jarvis responde por SMS.
- Custo: só o SMS do plano da operadora (muitos planos no Brasil incluem SMS ilimitado).
- Sem esse segundo aparelho, não existe API de SMS gratuita confiável: Twilio e similares cobram por mensagem, e as "grátis" são limitadas ou bloqueadas.
- Não implementado: depende de você ter um Android para isso. Se tiver, o conector segue o mesmo formato dos outros (`jarvis/sms.py`).

## WhatsApp: avaliado e NÃO integrado (Fase 9, 2026-10-16)

| Caminho | Situação | Motivo |
|---|---|---|
| **API oficial** (WhatsApp Business Platform / Cloud API) | ❌ Não usar | **Termos da Meta, seção 4.7 "Provedores de IA"** (atualizados em 23/09/2026): proíbem usar a plataforma para oferecer IA "quando ela for a funcionalidade principal (em vez de incidental ou auxiliar)". Não há exceção para uso pessoal. Um assistente de uso geral como o Jarvis é exatamente esse caso: risco de bloqueio da conta e do número. |
| | | Mensagens recebidas exigem um **webhook público na internet** (HTTPS acessível pela Meta), o que vai contra a regra de não expor o Jarvis. |
| | | Exige conta Meta Business e um **número dedicado**. Mensagens iniciadas pela empresa fora da janela de 24 h são **cobradas** por modelo (desde 01/07/2025); dentro da janela, as de serviço são gratuitas. |
| **Bibliotecas não oficiais** (WhatsApp Web automatizado, ex.: Baileys, whatsapp-web.js) | ❌ Rejeitado | Violam os termos do WhatsApp (risco de banir o seu número pessoal) e guardam a sessão da sua conta (equivale a uma credencial completa). |

**O que usar no lugar:** o próprio Jarvis no celular, pelo Tailscale (texto, voz, aprovações), que já cobre "falar com o Jarvis de fora de casa". Para avisos, o Jarvis pode criar rascunhos ou enviar e-mails para você mesmo (Gmail).

**Para o futuro:** se a Meta mudar os termos, um conector entraria como `jarvis/whatsapp.py`, que registra ferramentas no `tools.REGISTRY` (como `google_api.py`) e, para receber mensagens, um endpoint de webhook com verificação da assinatura `X-Hub-Signature-256`. Nada mais no Jarvis precisaria mudar. Integração alguma foi feita ou testada.

## Reconhecimento facial: opcional e DESLIGADO por padrão (Fase 9)

**O que é e o que não é:**
| | Faz? |
|---|---|
| **Detecção**: há um rosto na câmera? (YuNet) | ✅ |
| **Reconhecimento**: de quem é, entre as pessoas cadastradas? (SFace) | ✅ |
| **Autenticação**: é mesmo essa pessoa, e não uma foto? | ❌ **Não.** Não há prova de vida; uma foto pode enganar. Por isso o resultado é **só informativo** e **nunca libera nenhuma ação**. |

**Escolha da tecnologia:** OpenCV 5 (`opencv-python-headless`, Apache 2.0) com os modelos do OpenCV Zoo: **YuNet** (MIT) e **SFace** (Apache 2.0; 99,4% na avaliação oficial do Zoo). Rodam na CPU: detecção em ~7 ms, reconhecimento em ~5 ms.
Descartados: `face_recognition`/dlib (exige compilador C++ no Windows), InsightFace (modelos pré-treinados com licença não comercial), DeepFace (traz o TensorFlow inteiro).

**Fotos (quando você pede):** "Jarvis, tire uma foto de quem está na frente da câmera" ou o botão **📷 Tirar foto agora**.
A foto vai para `data\workspace\fotos\foto-AAAAMMDD-HHMMSS.jpg`, aparece no chat (e na galeria "Fotos salvas") e vem com quem foi reconhecido nela.
Fotos escuras são clareadas automaticamente (nesta webcam, à noite, o brilho medido foi 2–5 de 255). Cada foto fica na auditoria (quem pediu: local ou celular).

**Pelo celular:** com `JARVIS_REMOTE_CAMERA=true` no `.env` (ligado a seu pedido em 2026-10-16), o celular pode cadastrar, perguntar "quem está na câmera?" e tirar fotos da câmera do PC. Para desligar só isso, coloque `false` e reinicie.

**Privacidade:**
- A câmera só abre quando você pede (cadastrar, "quem está na câmera?" ou tirar foto), nunca continuamente. A luz da webcam acende durante o uso.
- O cadastro guarda só os vetores do rosto (128 números por amostra, até 10 por pessoa), cifrados com DPAPI em `data\face\pessoas.bin`. Imagens só são salvas quando você pede uma foto.
- Se outras pessoas usam o PC, avise que ele pode tirar fotos. Uso pessoal e doméstico não está sujeito à LGPD (art. 4º, I), mas é uma questão de confiança.
- Remover uma pessoa, **apagar todos os dados faciais** ou apagar fotos (uma ou todas) funciona a qualquer momento, até com o módulo desligado.
- Nada é enviado para a internet.

**Para ativar (só se quiser):**
1. `.venv\Scripts\python.exe -m jarvis.face` (baixa os modelos, ~39 MB, verificados por SHA-256; o OpenCV já vem no `requirements.txt`)
2. Coloque `JARVIS_FACE=on` no `.env` e reinicie o Jarvis.
3. Ferramentas → Reconhecimento facial → digite seu nome → **Cadastrar rosto** (olhe para a câmera ~3 s).
4. Teste com **Quem está na câmera?**.

**Precisão:** num teste de sanidade com imagens públicas do OpenCV, a mesma pessoa com variações (espelhada, escura, recortada) deu similaridade de 0,91 a 0,97, e outra pessoa deu 0,13 (limiar: 0,363). Isso **não** mede a precisão com a sua câmera, a sua luz e o seu rosto. Se na prática errar demais, mantenha desligado.
