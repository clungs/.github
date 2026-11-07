"""Abre uma issue quando alguém empurra commits direto no main, sem PR.

Roda dentro do workflow reutilizável .github/workflows/main-push-alert.yml, a cada push no main.
No plano Free não há proteção de branch em repo privado, então isto não impede o push:
só deixa ele visível para o time.

Um commit "veio de PR" quando a API o associa a um PR mergeado no main (merge, squash ou rebase).
Force push sempre gera alerta, porque pode ter apagado commits.

Variáveis: GH_TOKEN, GITHUB_EVENT_PATH, GITHUB_REPOSITORY. Com DRY_RUN=1 só imprime a issue.
"""

import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ZERO = "0" * 40


def gh(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def came_from_pr(repo: str, sha: str, branch: str) -> bool:
    pulls = json.loads(gh("api", f"repos/{repo}/commits/{sha}/pulls"))
    return any(pr.get("merged_at") and pr["base"]["ref"] == branch for pr in pulls)


def issue_body(event: dict, direct: list[dict], branch: str) -> str:
    who = event["sender"]["login"]
    lines = [f"@{who} empurrou direto no `{branch}`, sem PR." if direct else f"@{who} fez force push no `{branch}`.", ""]
    if event.get("forced"):
        lines += ["**Foi um force push**: commits que estavam no `main` podem ter sumido. "
                  f"O `main` antes do push estava em `{event['before'][:7]}`.", ""]
    if direct:
        lines += ["## Commits fora de PR", ""]
        for commit in direct:
            title = commit["message"].splitlines()[0] if commit["message"] else ""
            lines.append(f"- [`{commit['id'][:7]}`]({commit['url']}) {title} ({commit['author'].get('name', '?')})")
        lines.append("")
    lines += [f"Diferença: {event['compare']}", "",
              "## O que fazer",
              "- Se foi engano, confira com quem empurrou se o commit precisa de revisão e abra um PR de correção se for o caso.",
              "- Se foi combinado (hotfix, por exemplo), registre o motivo aqui e feche a issue.",
              "",
              "Mudanças no `main` passam por PR: veja o [CONTRIBUTING](https://github.com/clungs/.github/blob/main/CONTRIBUTING.md)."]
    return "\n".join(lines) + "\n"


def main() -> int:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        event = json.load(handle)
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = event["ref"].removeprefix("refs/heads/")

    if event.get("deleted") or event.get("before") == ZERO:
        print("branch criada ou apagada; nada a conferir")
        return 0

    commits = [commit for commit in event.get("commits", []) if commit.get("distinct", True)]
    direct = [commit for commit in commits if not came_from_pr(repo, commit["id"], branch)]
    if not direct and not event.get("forced"):
        print(f"{len(commits)} commit(s), todos de PR mergeado")
        return 0

    sender = event["sender"]["login"]
    kind = "Force push" if event.get("forced") else "Push direto"
    title = f"{kind} no {branch} por @{sender}"
    body = issue_body(event, direct, branch)
    if os.environ.get("DRY_RUN"):
        print(f"[dry-run] issue: {title}\n\n{body}")
        return 0

    payload = {"title": title, "body": body}
    if event["sender"].get("type") == "User":
        payload["assignees"] = [sender]
    issue = json.loads(gh("api", f"repos/{repo}/issues", "--input", "-", stdin=json.dumps(payload)))
    print(f"::warning::{title}: {issue['html_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
