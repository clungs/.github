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
| `scripts/new_game_board.py` | Monta o Project de um jogo novo a partir do template da org |
| `workflow-templates/` | Workflow que cada jogo usa para chamar o de cima (aparece em Actions → New workflow) |

## Ligar um jogo ao board

Rode, na raiz deste repo:

```
python scripts/new_game_board.py clungs/<jogo>
```

O script copia o Project marcado como template na org (campos, views e workflows vêm juntos), liga o repo do jogo e define a variável `PROJECT_NUMBER`. No fim ele lista o que só dá para fazer à mão:

1. Ligar o workflow **Auto-add to project** do Project novo (repo do jogo, filtro `is:issue`): o GitHub nunca copia esse workflow.
2. Criar o secret `PROJECT_TOKEN` no repo do jogo (`gh secret set PROJECT_TOKEN -R clungs/<jogo>`, colando o mesmo PAT). No plano Free, secrets de org não chegam a repos privados, então é um por repo.
3. Se o jogo não veio do `godot-template`, copiar `workflow-templates/project-board.yml` para `.github/workflows/` do jogo.

Pode rodar de novo a qualquer momento: o que já está feito é pulado. Use `--dry-run` para só ver o que ele faria.
