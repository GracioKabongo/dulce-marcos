# Convite Digital — Dulce Marcos, 50 anos

Website independente, feito com **HTML, CSS, JavaScript e Python/FastAPI**. Não utiliza Lovable, não tem selos de editores e pode ser publicado num domínio próprio.

## O que já funciona

- Convite responsivo em branco/marfim e dourado com três fotografias da aniversariante, optimizadas em WebP.
- Secções: apresentação, mensagem de convite, fotografias, data/local/dress code e confirmação de presença. **Sem botões de mapa ou calendário.**
- Formulário RSVP no próprio site: nome completo + «Confirmo presença»/«Não poderei comparecer», sem acompanhantes.
- Registo **real** das respostas em SQLite, com token anónimo por dispositivo para permitir alterar a própria resposta; limites de tentativas e campo anti-spam.
- Painel privado `/admin`: contagens, lista, pesquisa, exportação CSV, eliminação e tentativa de reenvio das notificações.
- Integração **preparada** para notificações pelo WhatsApp Business Cloud API. A resposta fica guardada mesmo que a notificação falhe; a falha é visível no painel.

## Iniciar no Windows 11

1. Instalar Python 3.11 ou superior.
2. Descompactar esta pasta, abrir PowerShell no directório do projecto e executar:

   ```powershell
   py -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Abrir o `.env` e substituir `ADMIN_PASSWORD` e `SESSION_SECRET` por valores fortes. Gerar um segredo com:

   ```powershell
   py -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

4. Iniciar:

   ```powershell
   py -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

5. Ver o convite em `http://127.0.0.1:8000/` e o painel em `http://127.0.0.1:8000/admin`.

Sem servidor, pode abrir o ficheiro `static/index.html` para ver o visual, **mas nesse modo as confirmações não serão gravadas**. Use o servidor para testar o RSVP.

## Configurar notificações automáticas para o WhatsApp da Dulce

**Importante:** este recurso só funciona após autenticação numa conta WhatsApp Business Platform, configuração de um número *remetente* autorizado e aprovação de um modelo de mensagem. O número da Dulce é o *destinatário*, não o remetente da API. Ela deve consentir em receber estes avisos.

1. Configurar no Meta Business o número da WhatsApp Cloud API e obter `WHATSAPP_PHONE_NUMBER_ID` e um `WHATSAPP_ACCESS_TOKEN` válido (idealmente token de utilizador do sistema com permissões mínimas).
2. Criar e submeter para aprovação um modelo de mensagem (nome proposto: `novo_rsvp_dulce`, idioma `pt_PT`) com este texto:

   ```
   Nova resposta ao aniversário de Dulce: {{1}} — {{2}}. Registado em {{3}}.
   ```

   O modelo deve conter exactamente três variáveis no corpo: nome do convidado, resposta, data/hora. A aprovação e categoria são determinadas pela Meta, não pelo website.
3. Preencher em `.env`:

   ```dotenv
   WHATSAPP_ACCESS_TOKEN=SEU_TOKEN_META
   WHATSAPP_PHONE_NUMBER_ID=SEU_ID_DO_REMETENTE
   WHATSAPP_TEMPLATE_NAME=novo_rsvp_dulce
   WHATSAPP_TEMPLATE_LANGUAGE=pt_PT
   WHATSAPP_GRAPH_VERSION=v27.0
   WHATSAPP_TO=258877697751
   ```

4. Reiniciar o servidor, fazer um RSVP de teste e verificar o painel `/admin`. «Aceite pela API» significa **aceite para processamento pela Meta**, não comprova entrega. A confirmação efectiva de entrega exige webhook de status, ainda não incluído.
5. Se a API estiver indisponível, a resposta mantém-se guardada; o painel assinala «Falhou» e permite tentar novamente. Os avisos pendentes são reenviados *manualmente* pela pessoa administradora; não existe reenvio periódico automático nesta versão.

> Podem existir custos por mensagem e regras de elegibilidade. Não use bibliotecas não oficiais para automatizar WhatsApp Web.

## Publicar com domínio próprio (sem Lovable)

O projecto requer um servidor Python. **GitHub Pages sozinho não serve** para o formulário, porque não executa a API de registo. Pode colocar o projecto num serviço que execute FastAPI (por exemplo, Render, Railway ou VPS) e associar um domínio próprio. Para arrancar num serviço Linux:

- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Persistência:** montar um volume durável e definir `DATABASE_PATH=/var/data/rsvps.sqlite3` (ajustar o caminho ao serviço). Sem um disco persistente, as respostas podem desaparecer após reinícios/deploys.
- **Segredos:** guardar `ADMIN_PASSWORD`, `SESSION_SECRET` e chaves WhatsApp nas variáveis de ambiente da hospedagem; nunca no código ou frontend.
- **HTTPS:** publicar obrigatoriamente por HTTPS para proteger o painel e os dados dos convidados.

Antes de enviar o convite a convidados reais, testar formulário, base de dados, credenciais de administrador, privacidade e **entrega efectiva** de um aviso no WhatsApp da Dulce.

## Detalhes do evento

- **Aniversariante:** Dulce Marcos
- **Ocasião:** 50 anos
- **Data e hora:** sexta-feira, 4 de Dezembro de 2026 às 18h00 (Maputo)
- **Local:** Salão do Kitanda, Cidade Baixa, Maputo
- **Dress code:** preto
- **Acompanhantes:** não existe campo de acompanhantes
- **Distribuição:** um link para todos

## Ficheiros

- `static/index.html` — convite público
- `static/styles.css` — identidade visual e responsividade
- `static/app.js` — interacções e confirmação de presenças
- `static/assets/` — fotografias optimizadas
- `static/admin.html`, `static/admin.js` — painel de administração
- `main.py` — registo, autenticação, exportação e WhatsApp Cloud API
- `.env.example` — parâmetros de configuração (sem chaves reais)
- `requirements.txt` — dependências Python

## Observações de segurança e limitações

Esta primeira versão usa SQLite e um limitador de pedidos em memória, adequados a um convite de pequena escala numa única instância. Para várias instâncias ou tráfego elevado, é necessário migrar para uma base de dados centralizada e controlo de pedidos partilhado. Um link público e a identificação apenas pelo nome não garantem que alguém não envie uma resposta com o nome de outra pessoa; o painel permite detectar e eliminar registos suspeitos. Não há confirmação de acompanhantes.

As fotografias utilizadas foram melhoradas a partir das imagens fornecidas. Confira se a aparência da Dulce foi preservada como pretende antes de publicar. Confirme também a autorização dela para publicar as fotografias.
