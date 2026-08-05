# Backlog de Produto — Paridade com Manus.im (Refinado)

> **Objetivo:** Levar o projeto local (`localhost:5173`) à paridade visual e funcional com o Manus.im.
> **Fora de escopo (excluído por decisão de produto):** upgrade de plano, planos de pagamento, créditos, tiers de modelo por plano, badges "Plano gratuito"/"Atualizar", fluxos de checkout.
> **Legenda de prioridade:** `P0` = crítico/base · `P1` = importante · `P2` = incremental.
> **Legenda de status:** `✅ Feito` · `🟡 Parcial` (existe, falta parte) · `⬜ A fazer`.
>
> Este documento é o backlog original acrescido de duas coisas: (1) o status real de cada tarefa, apurado por leitura do código em `feature/claw-openclaw-dark-mode-fix` (branch onde este refinamento foi feito); (2) uma seção **Backend** e uma seção **Frontend** por tarefa, com rotas, schemas, campos de banco e arquivos concretos. Nenhum código de aplicação foi alterado — isto é planejamento.
>
> Ao final: [Mapa de dependências](#mapa-de-dependências), [Resumo de impacto no backend](#resumo-de-impacto-no-backend) e [Dependências externas e riscos](#dependências-externas-e-riscos).

---

## Progresso desta iteração

As 15 tarefas classificadas como Nível 1–3 de dificuldade (mais BUG-2) foram implementadas nesta rodada, no branch `feature/paridade-manus-backlog`, uma por commit: **1.1, 1.5, 2.1, 3.1, 4.1, 4.3 (parcial), 5.2, 5.3, 6.1, 12.1 (parcial), 16.1, 17.2 (MVP), 17.3**, mais o hardening do BUG-2. Cada tarefa abaixo tem um bloco **"Implementado"** substituindo ou complementando o **"Escopo residual"** original, com o que de fato mudou de planejado para construído.

**Ajuste pós-implementação:** a TAREFA 1.1 (item "Agente" na sidebar) foi construída, testada e depois **revertida** a pedido do usuário — redundante com "Manus Claw" na navegação (dois itens de sidebar de cheiro "agente"). Ver a tarefa para detalhes; commit `4e9d9fa`.

**Verificação:** backend `uv run pytest` — 176 testes coletados, 160 passam (os 16 que falham são pré-existentes, confirmados via `git stash`, não relacionados a este trabalho). Frontend `npm run test && npm run type-check && npm run lint && npm run build` — 20 arquivos/131 testes passando, 0 erros de tipo, 0 erros de lint (30 warnings pré-existentes de `any`), build de produção conclui.

**Não incluído neste lote** (Nível 4+ da lista de dificuldade, ou dependências explícitas de tarefas fora dele): 1.1 (implementado e depois revertido — ver acima), 1.2, 1.3, 1.4/BUG-1, 2.2, 2.3, 3.2, 3.3, 4.2, 6.2 (já estava pronto), 6.3 (mesmo item do BUG-2), 7.x, 8.x, 9.x, 10.1, 11.1, 13.1, 14.1, 15.x, 17.1, BUG-3 — o restante deste documento os descreve como antes, sem alteração de status além da correção do diagnóstico do BUG-2 (ver Épico 18).

---

## Épico 1 — Navegação Principal (Sidebar) · `P0`

**Contexto:** A sidebar local tem `Nova Tarefa`, `Biblioteca`, `Manus Claw` (quebrado), `Projetos`, `Tarefas`. Falta paridade com Manus (`Nova tarefa`, `Agente`, `Plugins`, `Agendado`, `Biblioteca`, `Projetos`, `Tarefas`).

### TAREFA 1.1 — Adicionar item "Agente" na sidebar `❌ Removido (decisão de produto)`
Criar rota/página `Agente` com painel de Subtarefas e ícones superiores.
```gherkin
Funcionalidade: Item de navegação Agente
  Cenário: Usuário acessa a página Agente
    Dado que estou autenticado no aplicativo
    Quando eu clico em "Agente" na sidebar
    Então sou levado à página do Agente
    E vejo o painel de "Subtarefas"
```
**Backend**
- Sem coleção nova. A página agrega dados que já existem: `Plan.steps` (`backend/app/domain/models/plan.py`) e `StepEvent`/`ToolEvent` dentro de `session.events` (`SessionDocument.events`, `infrastructure/models/documents.py:118`).
- Nova rota agregadora `GET /api/v1/sessions/{session_id}/subtasks` em `session_routes.py`, que extrai `plan.steps` da sessão via `agent_service.get_session` — evita reimplementar o parsing de eventos no frontend. Reusa `EventMapper` (`interfaces/schemas/event.py`).

**Frontend**
- Nova página `frontend/src/pages/AgentPage.vue` + rota `/chat/agent` (ou `/agent/:sessionId`) em `router/index.ts`, seguindo o padrão de `ChatPage.vue`.
- Novo item na sidebar entre "Nova Tarefa" e "Biblioteca" em `SessionSidebar.vue` (mesmo padrão do bloco Claw, `SessionSidebar.vue:84-97`).
- i18n: chave `Agent` / `Subtasks` em `src/locales/{en,pt,zh}.ts`.

**Implementado e depois removido.** A versão inicial (`GET /sessions/{id}/subtasks` + `AgentPage.vue` + item de sidebar) chegou a ser construída e testada, mas o usuário considerou o item redundante com "Manus Claw" na navegação — dois itens de sidebar com cheiro de "agente" — e pediu a remoção. Revertido de forma limpa (`git revert`, sem conflito). Tecnicamente as duas features não se sobrepõem (Claw é o gateway OpenClaw; Agente seria uma visão de Subtarefas sobre o plano que já aparece no painel do chat), mas a decisão de simplificar a navegação é do produto, não uma questão técnica — não reimplementar sem uma nova decisão em contrário.

**Depende de:** nenhuma.

---

### TAREFA 1.2 — Adicionar item "Plugins" na sidebar `⬜ A fazer`
Criar entrada de navegação apontando para a página de Plugins (Épico 9).
```gherkin
Funcionalidade: Item de navegação Plugins
  Cenário: Usuário acessa Plugins
    Dado que estou na aplicação
    Quando clico em "Plugins" na sidebar
    Então a página de Plugins é exibida com as seções de conectores, habilidades e fontes de dados
```
**Backend:** nenhum além do já descrito no Épico 9.

**Frontend**
- Item de nav em `SessionSidebar.vue` → rota `/plugins` → `pages/PluginsPage.vue` (ver TAREFA 9.1).

**Depende de:** 9.1.

---

### TAREFA 1.3 — Adicionar item "Agendado" na sidebar `⬜ A fazer`
Criar entrada de navegação para a página de tarefas agendadas (Épico 15).
```gherkin
Funcionalidade: Item de navegação Agendado
  Cenário: Usuário acessa Agendado
    Dado que estou na aplicação
    Quando clico em "Agendado" na sidebar
    Então vejo a página de agendamento com o estado vazio "Crie sua tarefa agendada"
```
**Backend:** nenhum além do já descrito no Épico 15.

**Frontend**
- Item de nav em `SessionSidebar.vue` → rota `/scheduled` → `pages/ScheduledPage.vue` (ver TAREFA 15.1).

**Depende de:** 15.1.

---

### TAREFA 1.4 — Corrigir/remover "Manus Claw" (renderiza JSON cru) `⬜ A fazer`
Ver **BUG-1** no Épico 18 para a investigação técnica; esta tarefa é a correção em si.
```gherkin
Funcionalidade: Item Manus Claw
  Cenário: Item não exibe conteúdo bruto
    Dado que clico no item "Manus Claw"
    Quando a página carrega
    Então não vejo JSON cru na tela
    E vejo uma interface renderizada corretamente ou o item não está presente
```
**Backend:** provável ajuste em `infrastructure/external/claw/` ou no mapeamento de mensagens do Claw em `application/services/claw_service.py` — depende da causa raiz apurada em BUG-1.

**Frontend:** provável ajuste em `pages/ClawPage.vue` (tratamento de chunk/mensagem, linhas 240-345) — mesma ressalva.

**Depende de:** investigação BUG-1 (Épico 18).

---

### TAREFA 1.5 — Menu de contexto da Tarefa na lista lateral `✅ Feito`
Adicionar ações faltantes: `Compartilhar`, `Abrir em nova aba`, `Arquivar` (além das existentes: Renomear, Fixar, Favoritar, Mover para projeto, Excluir).
```gherkin
Funcionalidade: Menu de contexto de tarefa
  Cenário: Ações completas disponíveis
    Dado que passo o mouse sobre uma tarefa na sidebar
    Quando abro o menu "..."
    Então vejo as opções Compartilhar, Renomear, Abrir em nova aba, Fixar, Adicionar aos favoritos, Mover para projeto, Arquivar e Excluir
```
**Já implementado:** `Compartilhar`, `Renomear`, `Abrir em nova aba`, `Fixar`, `Adicionar aos favoritos`, `Mover para projeto`, `Excluir` já existem em `frontend/src/components/SessionItem.vue:238-268` (`handleSessionMenuClick`), consumindo `api/agent.ts` (`shareSession`, `updateSessionTitle`, `pinSession`, `favoriteSession`, `moveSessionProject`, `deleteSession`).

**Escopo residual:** só falta **Arquivar**.

**Backend**
- Campo novo `is_archived: bool = False` em `SessionDocument` (`infrastructure/models/documents.py:105-144`) + índice composto `IndexModel([("user_id", ASC), ("is_archived", ASC), ("latest_message_at", DESC)])`.
- Campo espelhado em `domain/models/session.py` (`Session` e `SessionSummary`).
- Rotas `POST /api/v1/sessions/{session_id}/archive` e `DELETE /api/v1/sessions/{session_id}/archive` em `session_routes.py`, réplica exata do par `favorite`/`unfavorite` (`session_routes.py:92-101`) chamando um novo `agent_service.update_session_archived(session_id, user_id, bool)`.
- `agent_service.get_all_sessions` passa a excluir `is_archived=True` por padrão (usado também pela TAREFA 12.1, que lista arquivadas via `GET /sessions?archived=true`).

**Frontend**
- Novo item `Arquivar`/`Desarquivar` em `handleSessionMenuClick` (`SessionItem.vue`), reusando `createMenuItem`/`showContextMenu`.
- Nova função em `api/agent.ts` (`archiveSession`/`unarchiveSession`), espelhando `favoriteSession`.
- i18n: `Archive` / `Unarchive` / `Task archived`.

**Implementado:** exatamente como planejado — `is_archived` em `Session`/`SessionDocument` + índice composto, `POST`/`DELETE /sessions/{id}/archive`, `agent_service.update_session_archived`. `get_all_sessions`/`find_summaries_by_user_id` ganharam filtros `archived`/`shared` (usados também pela 12.1). Item "Arquivar" em `SessionItem.vue` (usado pela sidebar e — via 4.3 — pelo cabeçalho da tarefa). 5 testes em `backend/tests/test_session_archive.py`.
**Bug real encontrado e corrigido no caminho:** o push WS de "upsert" da lista de sessões não filtrava arquivadas como o snapshot/REST filtram — arquivar uma tarefa a fazia reaparecer na sidebar assim que o próprio evento de upsert chegava. `upsertSessionItem` agora trata `is_archived: true` como remoção.

**Depende de:** nenhuma.

---

### TAREFA 1.6 — Filtro da lista de Tarefas `✅ Feito`
Adicionar filtro `Nenhum / Favorito / Compartilhado` na lista de tarefas.
```gherkin
Funcionalidade: Filtro de tarefas
  Cenário: Filtrar por favoritos
    Dado que tenho tarefas favoritadas e não favoritadas
    Quando seleciono o filtro "Favorito"
    Então somente as tarefas favoritadas são exibidas
```
**Evidência:** `SessionSidebar.vue:519, 537-561` implementa `taskFilter` (`all` / `noProject` / `favorites` / `shared`) com menu dropdown (`ListFilter`) e filtragem client-side sobre a lista já carregada via WebSocket (`connectSessionsListWS`). Nenhuma ação necessária.

---

## Épico 2 — Tela Inicial (Home) · `P1`

### TAREFA 2.1 — Ampliar chips de ações rápidas `✅ Feito`
Alinhar chips ao Manus: `Criar slides`, `Criar site`, `Design`, `Criar jogos`, e em `Mais`: Desenvolver aplicativos, Vídeo, Tarefa agendada, Wide Research, Planilha, Visualização, Áudio, Modo de chat, Playbook.
```gherkin
Funcionalidade: Chips de ação rápida
  Cenário: Chip inicia tarefa pré-configurada
    Dado que estou na tela inicial
    Quando clico no chip "Criar slides"
    Então o composer é preenchido/configurado para o fluxo de criação de slides
```
**Já implementado:** `HomePage.vue:113-127` já tem 4 chips primários (Slides, Site, Design, Jogos) + 4 extras (Analisar dados, Pesquisar, Relatório, Planilha) atrás de "Mais", preenchendo o composer via `t(chip.prompt)`.

**Escopo residual:** trocar a lista "Mais" pelos 9 itens do Manus (`Desenvolver aplicativos`, `Vídeo`, `Tarefa agendada`, `Wide Research`, `Planilha`, `Visualização`, `Áudio`, `Modo de chat`, `Playbook`) — `Tarefa agendada` deve navegar para o modal da TAREFA 15.2 em vez de só preencher texto; `Modo de chat` deve alternar `task_mode` (já existe, ver `UpdateSessionTaskModeRequest` em `interfaces/schemas/session.py`) em vez de ser um prompt.

**Backend:** sem impacto para os chips de prompt; `Tarefa agendada` e `Modo de chat` reusam rotas de outras tarefas (15.2 e `PATCH /sessions/{id}/mode`, já existente).

**Frontend**
- Editar arrays `primaryChips`/`extraChips` em `HomePage.vue`; adicionar campo `action?: 'schedule' | 'chat-mode'` para os dois chips que não são prompt puro.
- i18n para os 9 rótulos novos.

**Implementado com um ajuste de escopo:** os 9 itens estão em `HomePage.vue`. "Modo de chat" alterna `taskMode` local e o passa para `createSession` (reusa o prop `taskMode`/`update:taskMode` que `ModelSelectorDropdown.vue` já expunha para o `ChatPage`, nunca ligado na Home). "Tarefa agendada" ficou como preenchimento de prompt (como os demais chips) em vez de abrir um modal — TAREFA 15.2 não faz parte deste lote; documentado como ajuste no código.

**Depende de:** 15.2 (para o chip "Tarefa agendada" abrir o modal — não implementado neste lote).

---

### TAREFA 2.2 — Carrossel de banners `⬜ A fazer`
Implementar carrossel de destaques na home.
```gherkin
Funcionalidade: Carrossel de banners
  Cenário: Navegação entre banners
    Dado que estou na tela inicial
    Quando o carrossel é exibido
    Então consigo avançar e retroceder entre os banners
```
**Backend:** sem impacto no MVP — os banners (imagem, título, link) ficam num array estático no frontend, análogo aos chips. *Fase 2 opcional (fora deste refinamento):* se o conteúdo precisar ser editável sem deploy, estender `GET /api/v1/config/frontend` (`config_routes.py`) com um campo `banners: List[BannerConfig]` vindo de `Settings`.

**Frontend**
- Novo componente `frontend/src/components/HomeBannerCarousel.vue` (setas, dots, autoplay pausável), inserido acima dos chips em `HomePage.vue`.

**Depende de:** nenhuma.

---

### TAREFA 2.3 — Menu de comando "/" (slash) `🟡 Parcial`
Adicionar menu de comandos acionado por "/" no composer.
```gherkin
Funcionalidade: Slash command
  Cenário: Abrir menu de comandos
    Dado que o cursor está no composer
    Quando digito "/"
    Então um menu de comandos é exibido com as opções disponíveis
```
**Já implementado:** a extensão TipTap `createSlashSuggestion` (`components/chatbox/slashSuggestion.ts`) e o painel `ChatBoxSlashMenu.vue` já abrem ao digitar "/", com navegação por teclado (`ArrowUp`/`ArrowDown`/`Enter`/`Escape`) e filtro por texto. Ligado em `ChatBox.vue:212-268`.

**Escopo residual:** o catálogo (`buildSlashItems`) só tem 1 item (`add_local_files`). Precisa crescer junto com o menu "+" (TAREFA 3.1) — mesmo catálogo, dois gatilhos.

**Backend:** nenhum além do que cada item individual do menu já exige (ver 3.1).

**Frontend**
- Estender `SlashItem`/`buildSlashItems` em `slashSuggestion.ts` para aceitar a lista completa de ações do menu "+" (compartilhada via a mesma função usada por `plusMenuItems` em `ChatBox.vue`).

**Depende de:** 3.1.

---

## Épico 3 — Composer (Caixa de Entrada) · `P0`

### TAREFA 3.1 — Menu "+" completo `🟡 Parcial`
Adicionar: `Da Biblioteca`, `Tarefas recentes`, `Usar Habilidades`, `Plano (Ctrl+/)`, `Google Drive`, `Outras fontes` (além de Arquivos locais).
```gherkin
Funcionalidade: Menu de anexos do composer
  Cenário: Opções completas no menu "+"
    Dado que estou no composer
    Quando clico no botão "+"
    Então vejo as opções Adicionar de arquivos locais, Da Biblioteca, Tarefas recentes, Usar Habilidades, Plano, Google Drive e Outras fontes
```
**Já implementado:** o menu "+" existe e funciona (`ChatBox.vue:19-27`, `showPlusMenu`/`ChatBoxSlashMenu` variant `plus`), hoje com 1 item (`Add local files`).

**Escopo residual, item a item:**

| Item | Backend |
|---|---|
| Da Biblioteca | Nenhum novo — reusa `GET /api/v1/library/files` (`library_routes.py`, já implementado) para listar e anexar um arquivo existente à mensagem. |
| Tarefas recentes | Nenhum novo — reusa `GET /api/v1/sessions` já implementado; ação = "referenciar" a tarefa (inserir link/contexto), não abrir. |
| Usar Habilidades | Depende da TAREFA 9.3 (catálogo de habilidades). |
| Plano (Ctrl+/) | Nenhum novo — é um atalho de teclado que abre o `PlanPanel.vue` já existente; puramente frontend. |
| Google Drive | Depende da TAREFA 9.2, Fase 2 (OAuth) — **risco externo**, ver seção de riscos. |
| Outras fontes | Guarda-chuva para conectores genéricos — depende de 9.2. |

**Frontend**
- Estender `plusMenuItems` em `ChatBox.vue:88-90` e `handlePlusSelect` com um `switch` por `item.id`, cada braço abrindo o modal/painel correspondente (`LibraryPickerDialog.vue` novo, `RecentTasksPickerDialog.vue` novo, etc.).
- Itens sem backend pronto (Google Drive, Habilidades) ficam com estado "em breve"/desabilitado até as dependências fecharem — não bloqueiam o resto do menu.

**Implementado:** `Da Biblioteca` (`LibraryPickerDialog.vue`, reusa `GET /library/files`, anexa o `FileInfo` direto sem reupload) e `Tarefas recentes` (`RecentTasksPickerDialog.vue`, reusa `GET /sessions`, insere uma referência de texto no composer) — ambos novos componentes em `frontend/src/components/chatbox/`. `Plano (Ctrl+/)` liga um evento novo `ui:open-plan-panel` no `eventBus` que `PlanPanel.vue` escuta para se auto-expandir; também é um atalho de teclado real no editor TipTap. `Usar Habilidades`, `Google Drive` e `Outras fontes` continuam bloqueados por 9.2/9.3.

**Depende de:** 9.2, 9.3 (para os 3 itens que restam).

---

### TAREFA 3.2 — Painel rápido de conectores no composer `⬜ A fazer`
Permitir ativar/desativar conectores diretamente no composer.
```gherkin
Funcionalidade: Toggle de conectores
  Cenário: Ativar conector antes de enviar
    Dado que estou no composer
    Quando abro o painel de conectores
    Então consigo ativar ou desativar um conector para a tarefa
```
**Backend**
- Depende do catálogo de conectores da TAREFA 9.2 (`UserPluginDocument`).
- Campo novo `active_connector_ids: List[str] = []` em `CreateSessionRequest` (`interfaces/schemas/session.py`) e em `SessionDocument`, propagado por `agent_service.create_session`.
- O toolkit MCP (`domain/services/tools/mcp.py`) passa a filtrar os servidores carregados pelos IDs ativos da sessão em vez de carregar todos.

**Frontend**
- Novo popover `ChatBoxConnectorsPanel.vue`, acionado por um novo ícone ao lado do "+" em `ChatBox.vue`, listando conectores de `GET /plugins` (9.1) com toggle local que é enviado junto no `createSession`/no `chat` do WS.

**Depende de:** 9.2.

---

### TAREFA 3.3 — Seletor de ambiente (Cloud/Desktop) `⬜ Bloqueado`
Adicionar seletor "Manus Desktop / Cloud".
```gherkin
Funcionalidade: Seletor de ambiente
  Cenário: Escolher ambiente de execução
    Dado que estou no composer
    Quando abro o seletor de ambiente
    Então posso escolher entre execução em nuvem e desktop
```
**Bloqueio:** o repositório não tem um agente desktop — todo o `sandbox/` roda em container Docker por sessão (`SANDBOX_ADDRESS`, `infrastructure/external/sandbox/docker_sandbox.py`). Não há o que o seletor selecionaria além de "Cloud".

**Recomendação:** não implementar; se a paridade visual for exigida mesmo assim, o mínimo viável é mostrar o seletor com uma única opção "Cloud" fixa e "Desktop" desabilitado com tooltip "em breve" — decisão de produto a confirmar com o usuário antes de codar.

> **Nota:** O seletor de modelo por tier de plano permanece **fora de escopo**. O seletor de modelo (`ModelSelectorDropdown.vue` + `GET /api/v1/models`, já implementado) e os modos `Agente/Chat` (`TaskMode`, já implementado) continuam como estão.

---

## Épico 4 — Cabeçalho da Tarefa · `P1`

### TAREFA 4.1 — Painel de métricas de uso da tarefa `✅ Feito`
Exibir métricas **não financeiras**: tempo trabalhado, páginas visualizadas, comandos executados, APIs chamadas, arquivos criados, avaliação por estrelas. **Excluir "créditos".**
```gherkin
Funcionalidade: Painel de uso da tarefa
  Cenário: Visualizar métricas de execução
    Dado que abro o painel "Uso" de uma tarefa
    Quando o painel carrega
    Então vejo tempo trabalhado, páginas visualizadas, comandos executados, APIs chamadas e arquivos criados
    E não vejo nenhuma métrica relacionada a créditos
```
**Backend**
- Nenhuma coleção nova — tudo já está em `session.events` (`SessionDocument.events`):
  - **Tempo trabalhado:** soma de `Step.duration_ms` (propriedade já calculada em `domain/models/plan.py:28-32`) por `StepEvent`.
  - **Páginas visualizadas:** contagem de `ToolEvent` com `tool_name == "browser"` e `function_name` de navegação (`domain/services/tools/browser.py` define os nomes).
  - **Comandos executados:** contagem de `ToolEvent` com `tool_name == "shell"`.
  - **APIs chamadas:** contagem de `ToolEvent` com `tool_name == "mcp"`.
  - **Arquivos criados:** contagem de `FileUpdateEvent` distintos por `path`, mais anexos em `MessageEvent.attachments`.
- Nova rota `GET /api/v1/sessions/{session_id}/usage` em `session_routes.py`, schema `SessionUsageResponse{worked_ms, pages_viewed, commands_run, api_calls, files_created}`, implementada como um método novo `agent_service.get_session_usage(session_id, user_id)` que itera `session.events` uma vez.
- **Avaliação por estrelas:** campo novo `rating: Optional[int] = None` (1–5) em `SessionDocument` + rota `POST /sessions/{id}/rating`.
- Sem qualquer campo, rota ou nome de variável contendo "credit" — restrição de produto aplicada na borda da API, não só na UI.

**Frontend**
- Novo componente `UsagePanel.vue` (popover a partir de um botão novo no header de `ChatPage.vue`, ao lado do botão "Task Logs" já existente), consumindo a nova rota.
- Estrelas: componente pequeno reusável, PATCH otimista com rollback em erro (padrão já usado em `favoriteSession`).

**Implementado:** a agregação virou uma função pura, `domain/services/session_usage.py::compute_session_usage(events, files)`, para ficar testável sem servidor — 9 testes unitários (soma de duração, dedupe de passo replanejado, contagem por tipo de ferramenta, e um teste explícito garantindo que nenhuma chave contém "credit"). `files_created` acabou reusando `len(session.files)` (a mesma lista deduplicada que a investigação do BUG-2 mapeou) em vez de reescanear eventos de arquivo. `UsagePanel.vue` é um Popover (mesmo padrão do popover de Compartilhar) com um botão nível gauge no cabeçalho, ao lado de "Task Logs". 7 testes de integração para as rotas `GET .../usage` e `POST .../rating`.

**Depende de:** nenhuma.

---

### TAREFA 4.2 — Modal "Todos os arquivos nesta tarefa" completo `⬜ A fazer`
Adicionar abas `Todos/Imagens/Outros`, "baixar tudo" e menu por arquivo (Pré-visualizar, Localizar na conversa, Baixar, Salvar em).
```gherkin
Funcionalidade: Modal de arquivos da tarefa
  Cenário: Ações por arquivo
    Dado que abro o modal de arquivos da tarefa
    Quando abro o menu de um arquivo específico
    Então vejo as opções Pré-visualizar, Localizar na conversa, Baixar e Salvar em
```
**Já implementado:** `SessionFileList.vue` já lista os arquivos de `GET /sessions/{id}/files`, com clique para pré-visualizar (`showFilePreviewer`) e botão de download (`getFileDownloadUrl`). Falta: abas de tipo, "baixar tudo", "Localizar na conversa" e "Salvar em".

**Backend**
- **Abas Todos/Imagens/Outros:** classificação client-side por `content_type`/extensão — sem impacto.
- **Baixar tudo:** nova rota `GET /api/v1/sessions/{session_id}/files/zip`, que o `file_service` monta em streaming (`zipfile.ZipFile` sobre `BytesIO`/`StreamingResponse`) a partir de `download_file` para cada `FileInfo` da sessão. Evita N downloads simultâneos no navegador.
- **Salvar em:** nova rota `POST /api/v1/files/{file_id}/save-to-project`, corpo `{project_id}`, que adiciona o `file_id` a `ProjectDocument.source_file_ids` (campo novo, ver TAREFA 7.1) — reusa a checagem de posse de `project_service.get_project`.
- **Localizar na conversa:** sem rota nova — o frontend já tem `session_id`; basta rolar até a mensagem que referencia o `file_id` (busca local no array `messages`).

**Frontend**
- Abas de tipo + botão "Baixar tudo" no header do modal (`SessionFileList.vue`).
- Menu "⋯" por linha (reusar `useContextMenu`) com as 4 ações; "Localizar na conversa" fecha o modal e faz `scrollIntoView` na mensagem correspondente (precisa de `id`/`ref` por mensagem em `ChatPage.vue`, hoje as mensagens não têm anchor — adicionar `:id="message-${index}"`).

**Depende de:** 7.1 (para "Salvar em").

---

### TAREFA 4.3 — Menu "..." da tarefa completo `🟡 Parcial`
Adicionar `Agendar tarefa`, `Arquivar`, `Adicionar aos favoritos` ao menu (paridade com Manus).
```gherkin
Funcionalidade: Menu de opções da tarefa aberta
  Cenário: Opções completas no cabeçalho
    Dado que estou dentro de uma tarefa
    Quando abro o menu "..." do cabeçalho
    Então vejo Renomear, Mover para projeto, Agendar tarefa, Fixar, Adicionar aos favoritos, Arquivar e Excluir
```
**Já implementado:** `Renomear`, `Mover para projeto`, `Fixar`, `Adicionar aos favoritos`, `Excluir` já existem em `ChatPage.vue:816-832` (`handleMoreClick`), reusando os mesmos endpoints do menu da sidebar.

**Escopo residual:** ~~`Agendar tarefa` (depende de 15.2) e~~ `Arquivar` — **implementado** (`ChatPage.vue`, item "Archive task" em `handleMoreClick`, reusa `agentApi.archiveSession` de 1.5; arquivar a tarefa aberta redireciona para a Home, igual ao Excluir). `Agendar tarefa` segue pendente, depende de 15.2 (fora deste lote).

**Backend:** nenhum além de 1.5 (já feito) e 15.2 (pendente).

**Depende de:** 1.5 (feito), 15.2 (pendente).

---

## Épico 5 — Execução de Tarefas · `P1`

### TAREFA 5.1 — Rastreador "Progresso da tarefa" `✅ Feito`
Implementar tracker de plano expansível, com passos e checkmarks.
```gherkin
Funcionalidade: Progresso da tarefa
  Cenário: Acompanhar passos do plano
    Dado que uma tarefa está em execução
    Quando o plano é gerado
    Então vejo os passos listados
    E cada passo concluído recebe um indicador de conclusão
```
**Evidência:** `components/PlanPanel.vue` já implementa o tracker completo: colapsa/expande, mostra o passo atual com ícone de status (`PlanStepIcon.vue`), lista todos os passos quando expandido, e cronômetro ao vivo por passo (`stepElapsed`, `duration_ms`/`started_at`). Nenhuma ação necessária.

---

### TAREFA 5.2 — Sugestões de follow-up pós-conclusão `✅ Feito`
Exibir sugestões de próximos passos ao final da tarefa.
```gherkin
Funcionalidade: Sugestões de follow-up
  Cenário: Próximos passos sugeridos
    Dado que uma tarefa foi concluída
    Quando a resposta final é exibida
    Então vejo sugestões clicáveis de próximos passos
```
**Backend**
- Estender o schema de saída estruturada `FinalResult`/`DELIVER_RESULT_TOOL` (`domain/services/agents/execution.py:115-124`, prompt em `domain/services/prompts/`) com um campo `follow_ups: List[str] = []` (2–4 sugestões curtas geradas pelo próprio LLM na etapa `summarize()`).
- `MessageEvent` (`domain/models/event.py:104-108`) ganha `follow_ups: Optional[List[str]] = None`, populado em `execution.py:118-120` junto dos `attachments`.
- Reusa 100% o pipeline de eventos existente — nenhuma rota nova.

**Frontend**
- `ChatTaskCompleted.vue` recebe `follow-ups: string[]` e renderiza como chips clicáveis que preenchem e enviam o composer (mesmo padrão de `handleChipClick` da Home).
- `types/event.ts` / `types/message.ts` ganham o campo `follow_ups`.

**Implementado:** `FinalResult.follow_ups` (0-4 sugestões, prompt orienta a não preencher com genérico se nada fizer sentido) → `MessageEvent.follow_ups` → `MessageEventData` (wire format, cobre tanto streaming ao vivo quanto replay de histórico, os dois já passam por `EventMapper`). `ChatTaskCompleted.vue` renderiza como chips; clicar envia direto via `chat()`. 6 testes de backend + 5 de frontend.

**Depende de:** nenhuma.

---

### TAREFA 5.3 — Modal de pré-visualização de arquivo `✅ Feito`
Adicionar preview com tela cheia, favoritar e download.
```gherkin
Funcionalidade: Pré-visualização de arquivo
  Cenário: Abrir preview em tela cheia
    Dado que clico em um arquivo gerado
    Quando o preview abre
    Então posso alternar para tela cheia, favoritar e baixar o arquivo
```
**Já implementado:** `FilePreviewer.vue` + `FilePreviewerChrome.vue` já têm alternância center/fullscreen (`viewMode`) e download (`download()` via `getFileDownloadUrl`).

**Escopo residual:** falta o botão de favoritar dentro do preview — hoje favoritar só existe em `LibraryFileCard.vue` (Biblioteca).

**Backend:** nenhum — reusa `POST/DELETE /library/files/{file_id}/favorite` (`library_routes.py`, já implementado). Exige apenas que o arquivo tenha `file_id` (nem todo anexo tem, ver BUG-2).

**Frontend**
- Botão `Star` novo em `FilePreviewerChrome.vue`, ao lado do de download, visível apenas quando `fileInfo.file_id` existe; chama `favoriteLibraryFile`/`unfavoriteLibraryFile` de `api/project.ts`.

**Implementado como planejado.** Estado inicial de favorito só é conhecido quando quem abre o preview já sabe (ex. `LibraryPage.vue`); outros pontos de entrada (anexos de chat) começam desmarcados — não há endpoint de "status de favorito" avulso para consultar. **Nota de escopo:** o preview de imagens não tem o `FilePreviewerChrome` (gate `v-if="!isImage"` pré-existente, não relacionado a esta tarefa) — o botão de favoritar herda essa mesma lacuna.

**Depende de:** ~~BUG-2~~ — não bloqueou; ver correção do BUG-2 no Épico 18 (a causa raiz suposta não se confirmou).

---

## Épico 6 — Biblioteca / Arquivos · `P1`

### TAREFA 6.1 — Filtros de tipo completos `✅ Feito`
Adicionar `Slides / Sites / Documentos / Planilhas / Imagens / Áudio e Vídeo / Outros` (paridade com Manus).
```gherkin
Funcionalidade: Filtros da Biblioteca
  Cenário: Filtrar por tipo de arquivo
    Dado que estou na Biblioteca
    Quando seleciono o filtro "Slides"
    Então apenas arquivos de slides são exibidos
```
**Já implementado:** `LibraryPage.vue:271-276` já tem o dropdown de tipo com `All / Documents / Media / Others`, resolvido client-side por extensão/`content_type` (`isMediaFile`/`isDocumentFile`, `LibraryPage.vue:283-297`).

**Escopo residual:** separar as categorias hoje agrupadas — `Slides` (`.ppt`, `.pptx`, `.key`), `Sites` (arquivos com `content_type` `text/html` ou extensão `.html`/pasta de site publicado), `Planilhas` (`.xls`, `.xlsx`, `.csv`), `Áudio e Vídeo` (separar de Imagens). Puramente uma extensão da função `matchDocType`.

**Backend:** sem impacto — a classificação é feita sobre `filename`/`content_type`, já presentes em `LibraryFileItem`.

**Frontend**
- Estender `DocType` e `docTypeOptions` em `LibraryPage.vue`, adicionando as funções `isSlideFile`/`isSiteFile`/`isSpreadsheetFile` ao lado de `isMediaFile`/`isDocumentFile`.

**Implementado com um desvio de arquitetura:** a classificação saiu de dentro de `LibraryPage.vue` para um módulo puro e testado isoladamente, `frontend/src/utils/libraryFileType.ts::classifyLibraryFile()` — 20 testes cobrindo os 7 buckets. As 7 categorias do Manus (Slides/Sites/Documentos/Planilhas/Imagens/Áudio e Vídeo/Outros) substituem as 4 antigas (All/Documents/Media/Others).

**Depende de:** nenhuma.

---

### TAREFA 6.2 — Agrupamento por tarefa `✅ Feito`
Agrupar arquivos por tarefa de origem.
```gherkin
Funcionalidade: Agrupamento na Biblioteca
  Cenário: Arquivos agrupados por tarefa
    Dado que possuo arquivos de várias tarefas
    Quando abro a Biblioteca
    Então os arquivos aparecem agrupados pela tarefa que os gerou
```
**Evidência:** `LibraryPage.vue:322-346` — modo `browseMode === 'session'` (padrão, sem filtro/busca ativos) já agrupa por `session_id` em `LibraryGroup`, com título da tarefa, rótulo de tempo e expansão ("mostrar mais"). Nenhuma ação necessária.

---

### TAREFA 6.3 — Corrigir bug de tamanho "0 B" `✅ Não reproduziu`
Ver **BUG-2** no Épico 18 — causa raiz e correção detalhadas lá; esta tarefa é o mesmo item visto pela Biblioteca.
```gherkin
Funcionalidade: Tamanho de arquivo correto
  Cenário: Arquivo comprimido exibe tamanho real
    Dado que existe um arquivo comprimido na Biblioteca
    Quando visualizo suas informações
    Então o tamanho exibido é maior que "0 B" e reflete o tamanho real
```
**Investigado e não reproduziu.** Consulta direta ao Mongo do stack de dev mostrou `session.files[].size` correto para todo arquivo, inclusive dois `.zip` de ~30MB e ~13MB. `LibraryFileCard.vue`/`SessionFileList.vue` (os componentes apontados pelo backlog original) **não renderizam tamanho nenhum** — não há onde "0 B" apareceria hoje na Biblioteca. Ver Épico 18 para o que foi corrigido mesmo assim (hardening de `formatFileSize`, usado em outros 3 componentes).

**Depende de:** BUG-2 (ver correção lá).

---

## Épico 7 — Workspace de Projetos · `P1`

### TAREFA 7.1 — Painel completo do projeto `⬜ A fazer`
Adicionar seções: `Conectores`, `Arquivos e fontes` (Carregar/Buscar na web), `Habilidades`, `Website`, `Tarefas agendadas`.
```gherkin
Funcionalidade: Painel do projeto
  Cenário: Seções completas do projeto
    Dado que abro um projeto
    Quando o painel lateral carrega
    Então vejo Instruções, Conectores, Arquivos e fontes, Habilidades, Website e Tarefas agendadas
```
**Já implementado:** o painel só tem `Instruções` (`ProjectPage.vue:100-124`, campo `project.instruction`, editável via `PATCH /projects/{id}`).

**Backend**
- `ProjectDocument`/`Project` (`infrastructure/models/documents.py:147-167`, `domain/models/project.py`) ganham:
  - `connector_ids: List[str] = []` (referencia `UserPluginDocument`, TAREFA 9.2)
  - `skill_ids: List[str] = []` (TAREFA 9.3)
  - `source_file_ids: List[str] = []` (arquivos carregados/salvos, TAREFA 7.2 e 4.2)
  - `website_url: Optional[str] = None`
  - `scheduled_task_ids: List[str] = []` (TAREFA 15.2, quando `project_id` é setado no agendamento)
- `PATCH /projects/{id}` (`project_routes.py:63-79`) estendido para aceitar os novos campos via `UpdateProjectRequest`.
- Sem migração de dados — todos os campos novos têm default vazio.

**Frontend**
- Novos blocos de seção em `ProjectPage.vue` (coluna direita, ao lado de "Instruções"), cada um um componente pequeno (`ProjectConnectorsSection.vue`, `ProjectFilesSection.vue`, `ProjectSkillsSection.vue`, `ProjectWebsiteSection.vue`, `ProjectScheduledSection.vue`).

**Depende de:** 9.2, 9.3, 15.2 (cada seção depende do respectivo catálogo/feature).

---

### TAREFA 7.2 — Upload e busca de fontes no projeto `⬜ A fazer`
Permitir "Carregar" arquivos e "Buscar na web" dentro de Arquivos e fontes.
```gherkin
Funcionalidade: Fontes do projeto
  Cenário: Adicionar fonte via upload
    Dado que estou em "Arquivos e fontes" de um projeto
    Quando clico em "Carregar" e seleciono um arquivo
    Então o arquivo passa a compor as fontes do projeto
```
**Backend**
- **Carregar:** reusa `POST /api/v1/files` (`file_routes.py:16-29`, `file_service.upload_file`, já implementado) + adiciona o `file_id` retornado a `ProjectDocument.source_file_ids` via `PATCH /projects/{id}/sources` (rota nova, corpo `{add: [file_id], remove: [file_id]}`).
- **Buscar na web:** reusa o `SearchEngine` já existente (`domain/external/search.py`, implementado em `infrastructure/external/search/`) por trás de uma rota nova `POST /projects/{id}/sources/web-search` que executa a busca e adiciona os resultados escolhidos como fontes (armazenados como `FileInfo`-like com `file_path=None`, `metadata={"url": ...}` — ou uma lista separada `web_source_urls: List[str]` no documento, mais simples que forçar URLs no modelo de `FileInfo`).

**Frontend**
- Botões "Carregar" e "Buscar na web" na seção `ProjectFilesSection.vue` (7.1); upload reusa o componente de upload já usado em `ChatBoxFiles.vue`.

**Depende de:** 7.1.

---

## Épico 8 — Personalização / Memória · `P0`

### TAREFA 8.1 — Campos de perfil completos `⬜ A fazer`
Adicionar `Ocupação`, `Mais sobre você`, `Instruções Personalizadas`, `Importar memória`.
```gherkin
Funcionalidade: Perfil de personalização
  Cenário: Preencher instruções personalizadas
    Dado que estou em Personalização > Perfil
    Quando preencho "Instruções Personalizadas" e salvo
    Então as instruções são persistidas e aplicadas nas tarefas
```
**Backend**
- Campos novos em `UserDocument`/`User` (`infrastructure/models/documents.py:48-66`, `domain/models/user.py`): `occupation: Optional[str] = None`, `about: Optional[str] = None`, `custom_instructions: Optional[str] = None`.
- Nova rota `PATCH /api/v1/auth/profile` em `auth_routes.py`, no mesmo padrão de `change-fullname` (`auth_routes.py:136`) — schema `UpdateProfileRequest{occupation?, about?, custom_instructions?}`.
- **Integração crítica (sem isto a feature não tem efeito nenhum):** `custom_instructions` (e `about`/`occupation`, resumidos) precisam ser injetados no prompt do planejador. Ponto de injeção: `domain/services/prompts/planner.py` (a role prompt) e/ou `BaseAgent` (`domain/services/agents/base.py`) — o `AgentDomainService`/`agent_task_runner.py` já carrega o `User` associado à sessão; passar `user.custom_instructions` como um bloco `<user_context>` adicional na montagem do prompt do sistema.
- **Importar memória:** endpoint `POST /api/v1/memories/import`, aceitando um arquivo de texto/JSON e criando várias `MemoryEntryDocument` (TAREFA 8.2) de uma vez — reusa `file_service` só para o upload temporário, não persiste o arquivo em si.

**Frontend**
- Estender `PersonalizationSettings.vue` com os 3 campos novos (textarea para "Mais sobre você" e "Instruções Personalizadas"), mesmo padrão de `handleSubmit`/`useAuth` já usado para o apelido.
- Botão "Importar memória" (input file) na mesma tela.

**Depende de:** nenhuma. **Bloqueia:** efeito real de 8.2 se a injeção no prompt não for feita junto.

---

### TAREFA 8.2 — Aba de Conhecimento/Memória `⬜ A fazer`
Criar base de conhecimento com entradas alternáveis (toggle on/off).
```gherkin
Funcionalidade: Base de conhecimento
  Cenário: Ativar/desativar uma memória
    Dado que estou na aba "Conhecimento"
    Quando desativo o toggle de uma entrada
    Então essa memória deixa de ser considerada nas tarefas
```
**Backend**
- Nova `MemoryEntryDocument{user_id, content, source_session_id: Optional[str], enabled: bool = True, created_at}` em `documents.py`, índice `IndexModel([("user_id", ASC), ("enabled", ASC)])` — mesmo padrão de `FileFavoriteDocument` (`documents.py:170-184`).
- Novo repositório `MongoMemoryRepository` (`infrastructure/repositories/`), Protocol `MemoryRepository` em `domain/repositories/`, injetado via `interfaces/dependencies.py` no padrão de `MongoFileFavoriteRepository`.
- Rotas `GET/POST/PATCH/DELETE /api/v1/memories` (novo `memory_routes.py`, registrado em `interfaces/api/routes.py`).
- **Mesma integração crítica de 8.1:** só as entradas com `enabled=True` entram no prompt — o `agent_task_runner`/`base.py` busca as memórias do usuário e as injeta como parte do contexto do sistema (mesmo bloco `<user_context>`; se o volume crescer, truncar pelas mais recentes/relevantes — não implementar busca semântica nesta fase).

**Frontend**
- Nova aba "Conhecimento" em `SettingsTabs.vue` (`navGroups`), nova tela `KnowledgeSettings.vue` listando entradas com `SettingsSwitch.vue` (já existe, reusado) por linha.

**Depende de:** 8.1 (ponto de injeção compartilhado).

---

## Épico 9 — Marketplace: Conectores, Habilidades e Fontes de Dados · `P2`

> **Fatiamento recomendado:** Fase 1 usa a infraestrutura MCP que já existe no repositório (sem custo de integração externa); Fase 2 exige OAuth real por provedor — ver [Dependências externas e riscos](#dependências-externas-e-riscos).

### TAREFA 9.1 — Página de Plugins `⬜ A fazer`
Criar página com cards em destaque e busca.
```gherkin
Funcionalidade: Página de Plugins
  Cenário: Buscar plugin
    Dado que estou na página de Plugins
    Quando pesquiso por um termo
    Então os resultados correspondentes são filtrados
```
**Backend:** consome `GET /plugins` (9.2/9.3/9.4 combinados) — sem rota própria além dessa agregação.

**Frontend**
- Nova `pages/PluginsPage.vue`: busca client-side sobre o resultado de `GET /plugins`, seções por `kind` (`connector`/`skill`/`data_source`).

**Depende de:** 9.2, 9.3, 9.4.

---

### TAREFA 9.2 — Catálogo de Conectores `⬜ A fazer` (Fase 1) `⬜ Bloqueado por OAuth` (Fase 2)
Listar e gerenciar conectores (ex.: Gmail, Notion, Google Agenda, Outlook Mail, etc.).
```gherkin
Funcionalidade: Conectores
  Cenário: Conectar um serviço
    Dado que estou na seção Conectores
    Quando inicio a conexão de um conector via OAuth
    Então sou direcionado ao fluxo de autorização do provedor
```
**Backend — Fase 1 (sem dependência externa):**
- `GET /api/v1/plugins?kind=connector` lista os servidores já configurados em `mcp.json` (`domain/models/mcp_config.py`, `infrastructure/repositories/file_mcp_repository.py`) como "conectores" — não há OAuth, são conectores já autenticados via variável de ambiente/`command`.
- Nova `UserPluginDocument{user_id, plugin_id, kind, enabled: bool, config: dict}` guarda o liga/desliga por usuário sobre esse catálogo.
- `domain/services/tools/mcp.py` passa a filtrar os servidores carregados pelos habilitados do usuário da sessão.

**Backend — Fase 2 (conectores reais tipo Gmail/Notion via OAuth):**
- Protocol novo `OAuthProvider` em `domain/external/oauth.py`; implementações por provedor em `infrastructure/external/oauth/{google,notion,microsoft}.py`.
- Rotas `GET /connectors/{id}/oauth/start` (redirect) e `GET /connectors/{id}/oauth/callback` (troca code por token) em `connector_routes.py` novo.
- Armazenamento de token cifrado (reusar `TokenService`/uma chave de app nova) em `UserPluginDocument.config`.
- **Risco:** exige registrar app OAuth em cada provedor e uma URL pública de callback — não faz sentido em ambiente `localhost:5173` sem túnel/domínio; ver seção de riscos.

**Frontend**
- Seção "Conectores" dentro de `PluginsPage.vue` (9.1): grid de cards com toggle (Fase 1) e botão "Conectar" que abre o OAuth em nova aba (Fase 2, desabilitado até a Fase 2 existir).

**Depende de:** nenhuma (Fase 1); infraestrutura de OAuth (Fase 2).

---

### TAREFA 9.3 — Catálogo de Habilidades `⬜ A fazer`
Listar e ativar habilidades (skills).
```gherkin
Funcionalidade: Habilidades
  Cenário: Ativar uma habilidade
    Dado que estou no catálogo de Habilidades
    Quando ativo uma habilidade
    Então ela fica disponível para uso nas tarefas
```
**Backend**
- Mesmo `UserPluginDocument` da 9.2 com `kind="skill"`. O catálogo de habilidades disponíveis pode ser um array estático em `core/config.py` (curadoria manual, como uma "skill" = um prompt/system-instruction adicional carregado condicionalmente) ou, futuramente, mapeado a servidores MCP dedicados.
- `GET /plugins?kind=skill`, `PATCH /plugins/{id}` (enable/disable) — mesma rota genérica de 9.2.
- Habilidades habilitadas entram no prompt do executor (`domain/services/agents/execution.py`) como instruções adicionais, análogo à injeção de `custom_instructions` (8.1) — reusa o mesmo ponto de integração.

**Frontend**
- Seção "Habilidades" em `PluginsPage.vue`, cards com toggle.

**Depende de:** 8.1 (mesmo mecanismo de injeção no prompt).

---

### TAREFA 9.4 — Fontes de Dados `⬜ A fazer`
Listar fontes de dados disponíveis (ex.: World Bank, CoinGecko, etc.).
```gherkin
Funcionalidade: Fontes de dados
  Cenário: Consultar fonte de dados
    Dado que estou na seção Fontes de dados
    Quando seleciono uma fonte
    Então vejo os detalhes e a opção de utilizá-la em tarefas
```
**Backend:** mesmo `UserPluginDocument` com `kind="data_source"` — cada fonte de dados é, na prática, um servidor MCP público (World Bank, CoinGecko expõem APIs REST simples; modelar como MCP `streamable-http` em `mcp.json` ou como ferramentas nativas do toolkit de busca). `GET /plugins?kind=data_source`.

**Frontend:** seção "Fontes de dados" em `PluginsPage.vue`, com uma tela de detalhe simples (nome, descrição, exemplo de uso).

**Depende de:** 9.2 (infra de catálogo compartilhada).

---

## Épico 10 — Mail Manus · `P2`

### TAREFA 10.1 — E-mail para tarefa `⬜ Bloqueado`
Gerar e-mail dedicado do bot e lista de remetentes aprovados.
```gherkin
Funcionalidade: Mail Manus
  Cenário: Criar tarefa por e-mail
    Dado que possuo um e-mail dedicado do bot
    Quando um remetente aprovado envia um e-mail para esse endereço
    Então uma nova tarefa é criada a partir do conteúdo do e-mail
```
**Bloqueio:** `application/services/email_service.py` hoje só **envia** (códigos de verificação via SMTP) — não há caixa de entrada, parsing de e-mail recebido nem endereço dedicado por usuário. Isso exige infraestrutura de recebimento (IMAP/webhook de provedor tipo SendGrid Inbound Parse/Mailgun Routes) fora do repositório atual.

**Backend (quando desbloqueado)**
- Campo `inbound_email: str` (gerado, ex. `task+{user_id}@dominio`) em `UserDocument`.
- Nova `ApprovedSenderDocument{user_id, email}`.
- Endpoint webhook `POST /api/v1/mail/inbound` (chamado pelo provedor de recebimento) que valida o remetente aprovado e chama `agent_service.create_session` + injeta o corpo do e-mail como primeira mensagem.

**Frontend:** tela em Configurações mostrando o e-mail gerado e a lista de remetentes aprovados (CRUD simples).

**Risco:** depende de contratar/configurar um provedor de e-mail de entrada e expor um endpoint público — ver seção de riscos.

---

## Épico 11 — My Computer · `P2`

### TAREFA 11.1 — Abas Cloud/Local `🟡 Parcial` (Cloud) `⬜ Bloqueado` (Local)
Implementar visão "My Computer" com abas Cloud e Local.
```gherkin
Funcionalidade: My Computer
  Cenário: Alternar entre Cloud e Local
    Dado que abro "My Computer"
    Quando alterno entre as abas Cloud e Local
    Então o conteúdo correspondente a cada ambiente é exibido
```
**Já implementado:** a visão "Cloud" já existe, embutida na tela de tarefa — `ComputerPanel.vue`, `ComputerPanelContent.vue`, `VNCViewer.vue`, `TakeOverView.vue` mostram o sandbox Docker via VNC/CDP (ligado a `sandbox/`).

**Escopo residual:** promover isso a uma página própria "My Computer" fora do contexto de uma tarefa específica, com abas — a aba "Cloud" reusa os componentes existentes; a aba "Local" está bloqueada pelo mesmo motivo da TAREFA 3.3 (sem agente desktop no repositório).

**Backend:** nenhum novo para a aba Cloud (reusa as rotas de sandbox já existentes, `sandbox_routes`/`docker_sandbox.py`).

**Frontend**
- Nova `pages/MyComputerPage.vue` com abas, reaproveitando `ComputerPanel.vue` na aba Cloud.

**Depende de:** decisão de produto sobre a aba Local (mesma da 3.3).

---

## Épico 12 — Controles de Dados · `P1`

### TAREFA 12.1 — Central de controles de dados `🟡 Parcial`
Adicionar gestão de: Tarefas/Arquivos compartilhados, Sites, Aplicativos, Domínios comprados, Tarefas arquivadas.
```gherkin
Funcionalidade: Controles de dados
  Cenário: Visualizar tarefas arquivadas
    Dado que estou em Controles de Dados
    Quando acesso "Tarefas arquivadas"
    Então vejo a lista de tarefas que foram arquivadas
```
**Escopo real por subseção** (o backlog original trata como um único item; o código só sustenta parte):

| Subseção | Status | Nota |
|---|---|---|
| Tarefas/Arquivos compartilhados | `✅ Feito` | Aba "Compartilhados" com opção de deixar de compartilhar inline. |
| Tarefas arquivadas | `✅ Feito` | Aba "Arquivadas" com opção de restaurar inline. |
| Sites | `⬜ Bloqueado` | Não há pipeline de publicação de site no repositório. |
| Aplicativos | `⬜ Bloqueado` | Não há conceito de "app publicado". |
| Domínios comprados | `⬜ Bloqueado` | Não há integração de registro de domínio. |

**Backend**
- `GET /api/v1/sessions?shared=true` e `GET /api/v1/sessions?archived=true` — extensão de `get_all_sessions`/`get_session_files` com filtros de query, reusando os campos `is_shared` (já existe) e `is_archived` (1.5).
- Sites/Aplicativos/Domínios: sem contrato de backend possível sem antes decidir se o produto terá publicação de site/app — registrar como decisão pendente, não implementar.

**Frontend**
- Nova `pages/DataControlsPage.vue` com abas por subseção; só as duas primeiras (compartilhados, arquivadas) renderizam lista real — as demais mostram estado "não disponível" em vez de tela vazia enganosa.

**Implementado como planejado.** `/data-controls`, alcançável pelo menu do usuário (17.3). Smoke-testado à mão contra a API real: arquivar uma tarefa compartilhada corretamente some da aba "Compartilhados" também (a interação entre os dois filtros foi verificada, não só cada um isoladamente).

**Depende de:** 1.5 (feito).

---

## Épico 13 — Integrações · `P2`

### TAREFA 13.1 — Integrações externas `⬜ Bloqueado`
Adicionar Zapier, Slack, Telegram, Line na área de configurações.
```gherkin
Funcionalidade: Integrações
  Cenário: Listar integrações disponíveis
    Dado que estou em Configurações > Integrações
    Quando a seção carrega
    Então vejo as integrações Zapier, Slack, Telegram e Line com opção de configurar
```
**Backend**
- Nova `IntegrationDocument{user_id, provider, config: dict, enabled: bool}` — CRUD genérico (`GET/POST/PATCH/DELETE /api/v1/integrations`), no padrão dos demais repositórios de usuário.
- Cada provedor exige credenciais/OAuth próprios (Slack app, bot do Telegram, webhook do Zapier) — nenhum está configurado no repositório hoje.
- Disparo de eventos para integrações (ex.: notificar Slack quando uma tarefa termina) reusa o pipeline de `AgentEvent`/Redis já existente, adicionando um consumidor novo que publica para o webhook configurado.

**Frontend:** nova aba em `SettingsTabs.vue` → `IntegrationsSettings.vue`, um cartão por provedor com botão "Configurar" abrindo um formulário simples (token/webhook URL).

**Risco:** cada integração é uma dependência externa distinta (ver seção de riscos) — recomenda-se sequenciar uma por vez, começando por Slack (webhook simples, sem OAuth completo).

---

## Épico 14 — Desenvolvedores · `P2`

### TAREFA 14.1 — Área de Desenvolvedores `⬜ A fazer`
Adicionar `Chaves API` e `Webhooks`.
```gherkin
Funcionalidade: Área de desenvolvedores
  Cenário: Gerenciar webhooks
    Dado que estou em Configurações > Desenvolvedores
    Quando acesso "Webhooks"
    Então posso cadastrar e visualizar endpoints de webhook
```
**Backend**
- Nova `ApiKeyDocument{user_id, name, key_hash, prefix, created_at, last_used_at, revoked_at}` — a chave é gerada pelo servidor (`secrets.token_urlsafe`), mostrada **uma única vez** na criação, e só o hash é persistido. Rotas `POST/GET/DELETE /api/v1/developers/api-keys`.
- Nova `WebhookDocument{user_id, url, secret, event_types: List[str], enabled}` — rotas `POST/GET/PATCH/DELETE /api/v1/developers/webhooks`.
- Dispatcher de webhook: novo consumidor assíncrono que assina o stream de `AgentEvent` (mesma infra Redis de `infrastructure/external/message_queue/`) e faz `POST` assinado (HMAC com `secret`) para as URLs cadastradas cujo `event_types` combine.
- **Nota de segurança (já no backlog original):** a aplicação nunca preenche/gera credenciais de terceiros automaticamente — aqui é o inverso, a aplicação *emite* a chave, então a exigência é não reexibi-la depois de criada.

**Frontend**
- Nova aba "Desenvolvedores" em `SettingsTabs.vue` → `DeveloperSettings.vue` com duas subseções (Chaves API, Webhooks), cada uma uma tabela + modal de criação.

**Depende de:** nenhuma.

---

## Épico 15 — Agendamento (Agendado) · `P1`

### TAREFA 15.1 — Página e calendário de agendamento `⬜ A fazer`
Estado vazio "Crie sua tarefa agendada" + visão de calendário.
```gherkin
Funcionalidade: Página de agendamento
  Cenário: Estado vazio
    Dado que não possuo tarefas agendadas
    Quando acesso a página "Agendado"
    Então vejo o estado vazio com o convite "Crie sua tarefa agendada"
```
**Backend:** `GET /api/v1/scheduled-tasks` (lista, ver 15.2 para o schema completo).

**Frontend**
- Nova `pages/ScheduledPage.vue`: estado vazio quando a lista vem vazia; visão de calendário (mês) plotando `next_run_at` das tarefas agendadas — pode reusar uma lib leve já compatível com Vue 3 ou um grid mensal simples feito à mão (sem dependência nova se o design permitir).

**Depende de:** 15.2 (schema e rotas).

---

### TAREFA 15.2 — Modal de criação de tarefa agendada `⬜ A fazer`
Campos: `Título`, `frequência + hora`, `Definir data de validade`, `Prompt`, `Pular confirmações`, `Configurações avançadas` (Opções de execução/Agente/Conectores).
```gherkin
Funcionalidade: Criar tarefa agendada
  Cenário: Agendar com frequência
    Dado que abro o modal de tarefa agendada
    Quando preencho Título, frequência, hora e Prompt e confirmo
    Então a tarefa agendada é criada e passa a aparecer no calendário
```
**Backend**
- A infraestrutura de execução assíncrona já existe: `TASK_BACKEND=celery` (`core/config.py:161-166`) + `infrastructure/external/task/celery_app.py`/`celery_worker.py` já rodam tarefas de agente em workers Celery.
- Nova `ScheduledTaskDocument{user_id, title, prompt, cron_expr, timezone, next_run_at, expires_at: Optional[datetime], skip_confirmations: bool, project_id: Optional[str], model_name: Optional[str], active_connector_ids: List[str], enabled: bool, last_run_at, last_session_id}`.
- Protocol novo `Scheduler` em `domain/external/scheduler.py`; implementação `infrastructure/external/task/celery_beat_scheduler.py` usando `celery.beat`/`django-celery-beat`-like schedule dinâmico (ou `celery-redbeat` para agendas dinâmicas sem restart) — a task periódica, ao disparar, chama `agent_service.create_session(...)` com o `prompt` salvo, exatamente o caminho já usado pela criação manual de sessão.
- Rotas `scheduled_task_routes.py` novo: `GET/POST/PATCH/DELETE /api/v1/scheduled-tasks`, `POST /api/v1/scheduled-tasks/{id}/run-now` (dispara imediatamente, sem esperar o cron).
- **Risco documentado:** em dev, `TASK_BACKEND` é `local` por padrão (`RedisStreamTask`, sem beat). Duas opções a decidir antes de implementar: (a) exigir `TASK_BACKEND=celery` + Celery Beat rodando para esta feature, documentando isso no `docker-compose-development.yml`; ou (b) implementar um poller simples dentro do processo da API (`asyncio` + checagem periódica de `next_run_at <= now()` em Mongo) como fallback quando o backend é `local`, mais frágil (não sobrevive a múltiplas réplicas) mas sem dependência nova.

**Frontend**
- Novo `ScheduledTaskModal.vue`: campos do Gherkin, seletor de frequência (diário/semanal/mensal/cron customizado) que gera o `cron_expr`, painel "Configurações avançadas" colapsável reusando o seletor de modelo (`ModelSelectorDropdown.vue`) e o painel de conectores (3.2).

**Depende de:** 3.2 (para o subcampo de conectores nas configurações avançadas). **Bloqueia:** 1.3, 15.1, 2.1 (chip), 4.3 (menu "..."), 7.1 (seção do projeto).

---

## Épico 16 — Busca Global · `P1`

### TAREFA 16.1 — Modal de busca global `✅ Feito`
Busca com resultados agrupados por data e prévia de mensagem.
```gherkin
Funcionalidade: Busca global
  Cenário: Buscar mensagens
    Dado que abro a busca global
    Quando digito um termo
    Então vejo resultados agrupados por data com prévia da mensagem
```
**Já implementado:** `components/SearchDialog.vue` já abre com `Ctrl/Cmd+K`, já agrupa por data e já mostra `session.latest_message` como prévia — mas a busca roda **client-side** sobre a lista de sessões já carregada na sidebar (título e prévia da última mensagem apenas), não sobre o conteúdo completo das conversas.

**Escopo residual:** busca no servidor sobre o conteúdo de todas as mensagens (não só a última), permitindo achar uma tarefa antiga por uma frase que apareceu no meio da conversa.

**Backend**
- Novo `interfaces/api/search_routes.py`: `GET /api/v1/search?q=&limit=`, implementado em `agent_service.search_messages(user_id, query)` que varre `MessageEvent` dentro de `session.events` das sessões do usuário e retorna `{session_id, session_title, snippet, message_at}` agrupável por data no frontend (mesmo formato hoje montado localmente em `SearchDialog.vue`).
- **Nota de performance a registrar, não resolver agora:** os eventos ficam embutidos no documento da sessão (`SessionDocument.events`), sem índice de texto. Para poucos usuários/sessões um scan em memória por request é aceitável; se o volume crescer, será necessário um índice de texto Mongo (`text index` sobre uma coleção derivada de mensagens) — registrar como débito técnico conhecido.

**Frontend**
- `SearchDialog.vue` troca a filtragem local por chamada debounced a `GET /search`, mantendo o agrupamento por data já implementado.

**Implementado como planejado.** A lógica de match/snippet/ordenação virou uma função pura, `domain/services/search_messages.py::search_messages()` (10 testes unitários), já que não há um jeito de injetar uma mensagem sintética via REST fora de uma sessão de agente real para testar a rota fim-a-fim — a rota em si tem 6 testes de integração (auth, validação, isolamento por usuário). No frontend, cada resultado vira uma linha própria (não uma por sessão) já que duas mensagens diferentes na mesma tarefa são dois achados legítimos; guarda de resposta obsoleta via contador de sequência. 6 testes de componente (debounce, linhas por mensagem, descarte de resposta obsoleta).
**Débito de performance mantido como estava planejado:** scan completo dos eventos de cada sessão a cada busca — aceitável na escala atual, índice de texto/coleção derivada fica para quando parar de ser.

**Depende de:** nenhuma.

---

## Épico 17 — Configurações Gerais e Atalhos · `P1`

### TAREFA 17.1 — Preferências de comunicação completas `🟡 Parcial`
Ampliar de 2 para as 5 preferências de comunicação do Manus.
```gherkin
Funcionalidade: Preferências de comunicação
  Cenário: Preferências completas disponíveis
    Dado que estou em Configurações > Geral
    Quando visualizo as preferências de comunicação
    Então vejo as 5 opções disponíveis e consigo alterná-las
```
**Já implementado:** `Browser notifications` e `Sound alert` (`GeneralSettings.vue:59-88`), **100% client-side** — persistidas em `localStorage` via `useChromePrefs.ts`, sem backend algum.

**Escopo residual:** as 3 preferências adicionais precisam de decisão de produto sobre quais são (o Manus real tem variações não documentadas neste repositório) — proposta razoável: `E-mail ao concluir tarefa`, `E-mail de novidades do produto`, `Notificação push no navegador quando em segundo plano` (distinta de "browser notifications" atual, que é só o toast). As duas primeiras precisam de enforcement no servidor (não adianta desligar só na UI se o backend continuar enviando e-mail).

**Backend**
- Novo `UserPreferencesDocument{user_id, email_task_completed: bool, email_product_updates: bool}` — as preferências puramente de UI (browser notification, sound) continuam em `localStorage`, sem mudar.
- `email_service.py` passa a checar `email_task_completed` antes de qualquer envio de e-mail transacional relacionado a tarefas (hoje só envia código de verificação — este gancho só se aplica quando/​se e-mails de conclusão de tarefa forem implementados; até lá o campo fica sem efeito, apenas persistido).
- Rotas `GET/PATCH /api/v1/auth/preferences`.

**Frontend**
- Estender `GeneralSettings.vue` com 3 novos `SettingsSwitch`, os 2 server-backed chamando a nova rota e o 1 client-only reusando `useChromePrefs.ts`.

**Depende de:** decisão de produto sobre quais são as 3 preferências novas — **confirmar com o usuário antes de implementar**.

---

### TAREFA 17.2 — Atalhos editáveis `✅ Feito (MVP)`
Tornar os 5 atalhos configuráveis (hoje há 1, apenas de referência).
```gherkin
Funcionalidade: Atalhos personalizáveis
  Cenário: Editar um atalho
    Dado que estou em Configurações > Atalhos
    Quando redefino a combinação de teclas de um atalho
    Então o novo atalho é salvo e passa a funcionar
```
**Já implementado:** `ShortcutsSettings.vue` mostra 1 atalho (`Ctrl/Cmd+K` — Nova tarefa), somente leitura, derivado de `navigator.platform`.

**Escopo residual:** adicionar os 4 atalhos que faltam (candidatos: busca global `Ctrl+/`... já usado por "Plano" na 3.1, então definir sem colisão — enviar mensagem `Enter`, nova linha `Shift+Enter`, alternar Agente/Chat, abrir painel de arquivos) e tornar todos editáveis.

**Backend**
- MVP sem backend: assim como as preferências de comunicação client-only, atalhos são uma preferência de dispositivo — persistir em `localStorage` (`useShortcuts.ts` novo, mesmo padrão de `useChromePrefs.ts`). Nenhuma rota nova.
- *Fase 2 opcional:* se precisar sincronizar entre dispositivos, migrar para `UserPreferencesDocument.shortcuts: Dict[str, List[str]]` (mesmo documento da 17.1) com `PATCH /auth/preferences`.

**Frontend**
- `ShortcutsSettings.vue` ganha um "gravador" de atalho por linha (captura `keydown`, normaliza modificadores) + os handlers reais em `SessionSidebar.vue`/`ChatBox.vue`/`ChatPage.vue` passam a ler do `useShortcuts.ts` em vez de valores fixos (`handleKeydown` em `SessionSidebar.vue:799-804` hoje tem `Ctrl+K` hardcoded).

**Implementado no escopo do MVP (só o atalho que já existia de verdade):** `useShortcuts.ts` guarda `ShortcutBinding{ctrl,meta,shift,alt,key}` em `localStorage`, com `matches()`/`formatBinding()`/`resetBinding()`. `ShortcutsSettings.vue` tem um gravador real (clica, pressiona a combinação, salva; exige pelo menos um modificador). `SessionSidebar.vue`'s `handleKeydown` lê de `matches('new-task', event)` em vez do `Ctrl+K` fixo. 7 testes unitários. **Não implementado:** os outros 4 atalhos do Manus real — não foram inventados 4 ações novas sem que o usuário confirme quais deveriam existir; a mecânica para adicioná-los já existe (adicionar a `SHORTCUT_DEFS` + um handler real chamando `matches()`).

**Depende de:** nenhuma (MVP).

---

### TAREFA 17.3 — Menu de usuário completo `✅ Feito`
Adicionar `Personalização`, `Página inicial`, `Obter ajuda`, `Documentos` ao menu do usuário.
```gherkin
Funcionalidade: Menu do usuário
  Cenário: Opções completas
    Dado que abro o menu do usuário
    Então vejo Conta, Personalização, Configurações, Página inicial, Obter ajuda, Documentos e Sair
```
**Já implementado:** `UserMenu.vue` tem `Conta`, `Configurações`, `Sair` (`UserMenu.vue:26-53`).

**Escopo residual:** `Personalização` (atalho direto para a aba, reusando `openSettingsDialog('personalization')`), `Página inicial` (`router.push('/')`), `Obter ajuda` (link externo, mesmo padrão do item `help` já existente em `SettingsTabs.vue:70-75`), `Documentos` (link para `docs/` do Docsify, ex. `https://<host>/docs`).

**Backend:** sem impacto — são todos links/navegação.

**Frontend**
- 4 itens novos em `UserMenu.vue`, mesmo padrão visual dos 3 existentes.

**Implementado.** Os 4 itens (Personalização, Página inicial, Obter ajuda, Documentos) mais um quinto acrescentado depois — "Controles de dados" (ver TAREFA 12.1) — foram para `UserMenu.vue`, reaproveitando `openSettingsDialog`/`router.push` conforme planejado.

**Depende de:** nenhuma.

---

## Épico 18 — Bugs e Débitos Técnicos · `P0`

| ID | Descrição | Origem | Status |
|----|-----------|--------|--------|
| BUG-1 | "Manus Claw" renderiza JSON cru em vez de UI | Sidebar local | `⬜ Investigar` |
| BUG-2 | Tamanho de arquivo exibido como "0 B" para arquivos comprimidos | Biblioteca / modal de arquivos | `✅ Não reproduziu — hardening aplicado mesmo assim` |
| BUG-3 | Tela em branco após clicar no ícone de duplicar dentro da tarefa | Chat local | `⬜ Investigar` |

```gherkin
Funcionalidade: Correção de débitos técnicos
  Cenário: Duplicar tarefa sem tela branca
    Dado que estou em uma tarefa
    Quando clico no ícone de duplicar
    Então uma nova tarefa/estado é exibido sem tela em branco
```

### BUG-2 — investigado, não reproduziu; causa raiz original estava errada

O diagnóstico anterior deste documento apontava `execution.py:118-120` (`FileInfo(file_path=file_path)`, sem `size`) como a causa — **essa leitura estava incompleta**. Existe um passo de enriquecimento em `agent_task_runner.py` (`_sync_file_to_storage`/`_sync_message_attachments_to_storage`) que baixa o arquivo do sandbox e o re-registra via `file_storage.upload_file` antes de persistir em `session.files`, preenchendo `size`/`content_type`/`file_id` reais — tanto para anexos gerados pelo agente quanto para os enviados pelo usuário.

**Confirmado com dados reais:** consulta direta ao Mongo do stack de dev (`docker exec ai-manus-mongodb-1 mongosh`) mostrou que **todo** arquivo em `session.files[].size`, de sessões de uso real, está correto — inclusive dois `.zip` de ~30MB e ~13MB. Também: `LibraryFileCard.vue` e `SessionFileList.vue` (os componentes que este documento apontava como exibindo "0 B") **não renderizam tamanho nenhum** hoje — não há onde "0 B" apareceria na Biblioteca. `formatFileSize()` (`utils/fileType.ts`) de fato tratava `null`/`undefined` como `'0 B'`, mas só é chamada por `ChatAttachmentList.vue`/`TaskLogsDrawer.vue`/`ChatBoxFiles.vue`, nunca pela Biblioteca.

**Aplicado mesmo assim (hardening, não correção de um bug confirmado):**
- `formatFileSize()` agora distingue tamanho desconhecido (`null`/`undefined` → string vazia) de um arquivo genuinamente vazio (`0` → `'0 B'`). Os 3 componentes que a chamam passam a omitir o trecho "· tamanho" quando vazio. 6 testes em `frontend/src/utils/__tests__/fileType.spec.ts`.

**Se o sintoma original ("0 B" na Biblioteca) for observado de novo:** reproduzir com um upload real e capturar o `file_id`/`session_id` exatos antes de investigar mais — o caminho de dados atual não sustenta a hipótese antiga.

### BUG-1 e BUG-3 — sem causa raiz confirmada
Não foi possível confirmar a causa por leitura estática nesta rodada de refinamento — evitar diagnóstico especulativo aqui. Próximo passo antes de codar:
- **BUG-1:** reproduzir localmente, inspecionar `pages/ClawPage.vue:240-345` (tratamento de chunk de mensagem) e `infrastructure/external/claw/` (formato de resposta do gateway OpenClaw) com as devtools abertas para capturar o payload exato que está sendo renderizado cru.
- **BUG-3:** reproduzir o clique de duplicar, capturar o erro no console — não há um botão "duplicar" claramente identificado na leitura atual de `ChatPage.vue`/`ChatMessage.vue`; localizar o componente primeiro.

**Depende de:** nenhuma — mas ambos exigem uma sessão de reprodução manual antes de qualquer código.

---

## Mapa de dependências

Ordem sugerida de execução (da base para o incremental), respeitando as dependências reais levantadas acima:

```
18 (bugs, sobretudo BUG-2)
 → 1 (nav: 1.5 Arquivar, 1.1/1.2/1.3 novos itens)
 → 8 (memória/perfil — inclui o ponto de injeção no prompt, usado por 9.3 também)
 → 3.2 (painel de conectores) + 2 (home/slash)
 → 4 (cabeçalho: usage, arquivos, menu "...")
 → 5 (execução: follow-ups, preview)
 → 15 (agendamento — depende de 1.5 e 3.2)
 → 7 (projetos — depende de 9.2/9.3/15.2)
 → 12 (controles de dados) + 16 (busca global)
 → 9 (marketplace, Fase 1 sem OAuth)
 → 13/14 (integrações, developers)
 → 9 Fase 2 / 10 / 11 (dependências externas: OAuth, e-mail de entrada, desktop)
```

## Resumo de impacto no backend

| Item | Quantidade | Detalhe |
|---|---|---|
| Coleções Mongo novas | 6 | `MemoryEntryDocument`, `UserPluginDocument`, `ScheduledTaskDocument`, `ApiKeyDocument`, `WebhookDocument`, `IntegrationDocument` (+ `UserPreferencesDocument`, `ApprovedSenderDocument` se 17.1/10.1 avançarem) |
| Campos novos em coleções existentes | 4 | `SessionDocument.is_archived`/`rating`, `UserDocument.occupation`/`about`/`custom_instructions`/`inbound_email`, `ProjectDocument.connector_ids`/`skill_ids`/`source_file_ids`/`website_url`/`scheduled_task_ids`, `CreateSessionRequest.active_connector_ids` |
| Arquivos de rota novos | ~9 | `memory_routes.py`, `plugin_routes.py`, `connector_routes.py`, `scheduled_task_routes.py`, `search_routes.py`, `developer_routes.py` (chaves + webhooks), `integration_routes.py`, `data_controls` (extensão de `session_routes.py`), `mail_routes.py` |
| Protocols/interfaces novos em `domain/external/` | 2 | `Scheduler`, `OAuthProvider` |
| Nenhuma coleção nova necessária | 4.1, 5.2 | Métricas de uso e follow-ups derivam inteiramente de `session.events`, já persistido |

## Dependências externas e riscos

| Dependência | Épicos afetados | Risco |
|---|---|---|
| OAuth por provedor (Google, Notion, Microsoft, Slack...) | 3.1 (Google Drive), 9.2 Fase 2, 13 | Exige registrar app em cada provedor + URL pública de callback (`localhost` não funciona). Sequenciar um provedor por vez. |
| Celery Beat / agenda dinâmica | 15 | Ambiente dev padrão usa `TASK_BACKEND=local`, sem beat. Decidir entre exigir Celery em dev ou implementar poller de fallback. |
| SMTP de recebimento (IMAP/webhook) | 10 | `email_service.py` atual só envia. Recebimento é uma peça de infraestrutura nova (Mailgun Routes/SendGrid Inbound Parse ou IMAP polling). |
| Agente desktop | 3.3, 11.1 (aba Local) | Não existe no repositório. Sem isso, "Desktop"/"Local" não têm o que exibir — decisão de produto pendente antes de codar a UI. |
| Pipeline de publicação de site/app/domínio | 12.1 (Sites, Aplicativos, Domínios) | Nenhuma infraestrutura de deploy/hospedagem no repositório. Fora de escopo até existir decisão de produto separada. |
