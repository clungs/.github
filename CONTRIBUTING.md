# Como trabalhamos na Clungs

Vale para todos os jogos da org. O `CLAUDE.md` de cada jogo traz as regras de código daquele projeto.

## Do pedido ao merge

1. **Ideia** → issue do tipo *Feature* com a label `needs-spec` (pelo formulário "Ideia de feature" ou pedindo ao agente).
2. **Spec** → a feature passa pela skill `tlc-spec-driven` (Specify → Design → Tasks). Cada fase é aprovada por uma pessoa.
3. **Publicação** → com as Tasks aprovadas, o agente roda `gh-tasks publish`. Isso cria a issue da feature e um sub-issue por lote de worker, com bloqueio entre lotes dependentes, e grava os números no `tasks.md`.
4. **Trabalho** → alguém pega um lote livre (`gh-tasks start <n>`), trabalha numa branch `feat/<n>-<slug>`, com commits `Refs #<n>`.
5. **PR** → corpo com `Closes #<n>` do lote. O board move sozinho para *In Review*.
6. **Merge** → feito por uma pessoa. O lote fecha e vai para *Done*; quando o último lote fecha, a feature fecha junto.

Bugs e chores pequenos pulam a spec: issue → branch `fix/<n>-<slug>` ou `chore/<n>-<slug>` → PR com `Closes #<n>`.

## Títulos

| Tipo | Formato | Exemplo |
| --- | --- | --- |
| Feature | `[Área] Nome da feature` | `[Player] Dash do player` |
| Lote | `[Área] Nome da feature · Lote N: foco` | `[Player] Dash do player · Lote 1: mecânica` |
| Bug | `[Área] bug: o que acontece` | `[UI] bug: menu de pause não fecha com Esc` |
| Chore | `[Área] o que fazer` | `[Tooling] atualizar GUT para 9.8` |

## Onde fica cada informação

| O quê | Onde |
| --- | --- |
| Tipo (Feature, Lote, Bug, Chore) | Issue type |
| Estado, tamanho, prioridade | Campos do Project |
| Área, disciplina, contexto | Labels ([`labels.json`](labels.json)) |
| Requisitos, design, decisões | `.specs/` no repo do jogo (fonte da verdade) |

A issue aponta para a spec, não copia. Se divergirem, vale a spec.

## Commits e PRs

- Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`, `build:`, `ci:`) com `Refs #<n>` no corpo.
- Um PR por lote. `Closes` só no lote, nunca na feature.
- Ninguém faz merge do próprio PR sem uma segunda olhada, quando houver mais alguém no time.

## Labels

Mude [`labels.json`](labels.json) por PR. No merge, o workflow `Sincroniza labels` aplica em todos os repos. Labels que só um jogo usa podem ser criadas direto no repo dele.
