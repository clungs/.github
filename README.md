# clungs/.github

Padrões que todos os repos da org Clungs herdam.

| Arquivo | Para quê |
| --- | --- |
| `profile/README.md` | Página pública da org |
| `.github/ISSUE_TEMPLATE/` | Formulários de Feature, Bug e Chore (valem para todo repo sem templates próprios) |
| `.github/pull_request_template.md` | Template de PR padrão |
| `CONTRIBUTING.md` | Fluxo de trabalho, títulos, labels |
| `labels.json` + `scripts/sync_labels.py` | Labels da org; sincronizadas pelo workflow `Sincroniza labels` |
| `.github/workflows/project-board.yml` + `scripts/board.py` | Workflow reutilizável que move issues no Project conforme os PRs e completa assignee, labels, milestone e Project do PR |
| `workflow-templates/` | Workflow que cada jogo usa para chamar o de cima (aparece em Actions → New workflow) |

## Ligar um jogo ao board

1. Copie `workflow-templates/project-board.yml` para `.github/workflows/` do jogo.
2. No repo do jogo: Settings → Secrets and variables → Actions → **Variables** → `PROJECT_NUMBER` = número do Project dele.
3. O secret `PROJECT_TOKEN` é da org e já vale para todos os repos.
