# Plano de execução — Nível 1–3 do backlog de paridade

Deriva de `docs/backlog/paridade-manus.md` (a especificação completa, com Gherkin e contratos
de backend/frontend por tarefa). Este plano só reordena essas 15 tarefas em passos de build,
uma por commit.

## Correção descoberta durante a investigação (antes de codar)

**BUG-2 não reproduz.** Consulta direta ao Mongo do stack de dev (`docker exec ai-manus-mongodb-1
mongosh`) mostrou que **todo** arquivo em `session.files[].size` já está correto — inclusive dois
`.zip` de ~30MB e ~13MB. `LibraryFileCard.vue` e `SessionFileList.vue` (os componentes que o
backlog aponta como exibindo "0 B") **não renderizam tamanho nenhum**. A causa raiz que eu tinha
escrito no backlog (`execution.py:118-120`) está incompleta: existe um passo de enriquecimento em
`agent_task_runner.py` (`_sync_file_to_storage`/`_sync_message_attachments_to_storage`) que já
resolve isso antes de persistir. `formatFileSize()` (`utils/fileType.ts`) trata `null`/`undefined`
como `'0 B'`, mas só é chamada de `ChatAttachmentList.vue`/`TaskLogsDrawer.vue`/`ChatBoxFiles.vue`
— não da Biblioteca. Escopo ajustado: T1 vira um hardening pequeno dessa função (não um bugfix), e
`docs/backlog/paridade-manus.md` será corrigido para não afirmar uma causa raiz que não se sustenta.

## Ordem de execução (dependência crescente)

1. **T1** — hardening `formatFileSize` (BUG-2)
2. **T3** — Menu do usuário completo (17.3)
3. **T4** — Filtros de tipo da Biblioteca (6.1)
4. **T5** — Chips da Home (2.1)
5. **T6** — Favoritar no preview (5.3)
6. **T7** — Menu "+" completo (3.1)
7. **T8** — Arquivar tarefa: backend + sidebar (1.5)
8. **T9** — Menu "..." → Arquivar em ChatPage (4.3, depende de T8)
9. **T11** — Sugestões de follow-up (5.2)
10. **T12** — Atalhos editáveis (17.2)
11. **T13** — Controles de dados: compartilhados + arquivados (12.1, depende de T8)
12. **T14** — Painel de métricas de uso (4.1)
13. **T15** — Busca global server-side (16.1)
14. **T16** — Página "Agente" (1.1)
15. **T17** — Verificação final + atualização da documentação

## Verificação por tarefa

- Backend: `docker exec ai-manus-backend-1` já roda com hot-reload; toda rota nova é testada com
  `curl` autenticado contra `http://localhost:8000` e, quando fizer sentido, um teste em
  `backend/tests/` seguindo o padrão existente (`uv run pytest tests/test_x.py`).
- Frontend: o Vite dev server já roda em `:5173` com hot-reload; cada componente novo/editado
  passa por `npm run type-check` naquele momento; suíte completa (`test`, `type-check`, `lint`,
  `build`) roda uma vez ao final (T17), não a cada tarefa — o volume de páginas Vue tornaria isso
  redundante e lento.
- Cada tarefa concluída vira 1 commit no branch `feature/paridade-manus-backlog`.
