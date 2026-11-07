"""Monta o board de um jogo: copia o Project template da org, liga o repo e define PROJECT_NUMBER.

Uso:
    python scripts/new_game_board.py clungs/pelvs
    python scripts/new_game_board.py clungs/qibs-bombs --title "Qibs Bombs" --dry-run

O que faz (pode rodar de novo; o que já está feito é pulado):
  1. Acha o Project do jogo: o da variável PROJECT_NUMBER do repo, um aberto com o mesmo título,
     ou uma cópia nova do Project marcado como template na org (campos, views e workflows vêm juntos).
  2. Liga o repo ao Project.
  3. Define a variável PROJECT_NUMBER no repo.
  4. Liga "Automatically delete head branches" no repo (repos criados por template não herdam).
  5. Confere o que só dá para fazer à mão e diz como: workflow Auto-add, secret PROJECT_TOKEN
     e os workflows do board e do alerta de push no main no repo.

Precisa do gh autenticado com escopos project, repo e read:org, e admin no repo (para a variável).
"""

import argparse
import json
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

GAME_WORKFLOWS = [".github/workflows/project-board.yml", ".github/workflows/main-push-alert.yml"]


def gh(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh {' '.join(args)} falhou")
    return result.stdout


def graphql(query: str, **variables) -> dict:
    payload = json.loads(gh("api", "graphql", "--input", "-", stdin=json.dumps({"query": query, "variables": variables})))
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
    return payload["data"]


def org_context(org: str, repo: str) -> dict:
    data = graphql("""
        query($org: String!, $repo: String!) {
          organization(login: $org) {
            id
            projectsV2(first: 100) { nodes { id number title url template closed } }
          }
          repository(owner: $org, name: $repo) { id }
        }""", org=org, repo=repo)
    if data["repository"] is None:
        raise RuntimeError(f"repo {org}/{repo} não encontrado")
    return {"org_id": data["organization"]["id"], "repo_id": data["repository"]["id"],
            "projects": data["organization"]["projectsV2"]["nodes"]}


def repo_variable(full_repo: str, name: str) -> str | None:
    try:
        return gh("variable", "get", name, "-R", full_repo).strip()
    except RuntimeError:
        return None


def find_project(ctx: dict, full_repo: str, title: str) -> tuple[dict | None, str]:
    number = repo_variable(full_repo, "PROJECT_NUMBER")
    if number and number.isdigit():
        match = next((p for p in ctx["projects"] if p["number"] == int(number)), None)
        if match:
            return match, f"da variável PROJECT_NUMBER={number}"
        print(f"aviso: PROJECT_NUMBER={number} não aponta para um Project da org; vou procurar pelo título.")
    match = next((p for p in ctx["projects"] if p["title"] == title and not p["closed"] and not p["template"]), None)
    return match, "com o mesmo título"


def pick_template(ctx: dict, number: int | None) -> dict:
    if number is not None:
        template = next((p for p in ctx["projects"] if p["number"] == number), None)
        if template is None:
            raise RuntimeError(f"Project {number} não existe na org")
        return template
    templates = [p for p in ctx["projects"] if p["template"] and not p["closed"]]
    if not templates:
        raise RuntimeError("nenhum Project da org está marcado como template; use --template <número>")
    if len(templates) > 1:
        names = ", ".join(f"{p['number']} ({p['title']})" for p in templates)
        raise RuntimeError(f"mais de um template na org: {names}; escolha com --template <número>")
    return templates[0]


def project_details(project_id: str, repo_id: str) -> dict:
    node = graphql("""
        query($id: ID!) {
          node(id: $id) {
            ... on ProjectV2 {
              repositories(first: 50) { nodes { id } }
              workflows(first: 30) { nodes { name enabled } }
            }
          }
        }""", id=project_id)["node"]
    return {
        "linked": any(r["id"] == repo_id for r in node["repositories"]["nodes"]),
        "auto_add": any(w["name"] == "Auto-add to project" and w["enabled"] for w in node["workflows"]["nodes"]),
    }


def has_secret(full_repo: str, name: str) -> bool | None:
    try:
        out = gh("secret", "list", "-R", full_repo, "--json", "name", "--jq", ".[].name")
    except RuntimeError:
        return None
    return name in out.split()


def has_file(full_repo: str, path: str) -> bool:
    try:
        gh("api", f"repos/{full_repo}/contents/{path}", "--silent")
        return True
    except RuntimeError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(prog="new_game_board")
    parser.add_argument("repo", help="org/repo do jogo, por exemplo clungs/pelvs")
    parser.add_argument("--title", help="título do Project (padrão: nome do repo com iniciais maiúsculas)")
    parser.add_argument("--template", type=int, help="número do Project template (padrão: o único marcado como template)")
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria")
    args = parser.parse_args()

    if "/" not in args.repo:
        parser.error("use org/repo, por exemplo clungs/pelvs")
    org, repo = args.repo.split("/", 1)
    title = args.title or " ".join(word.capitalize() for word in repo.replace("_", "-").split("-"))
    dry = "(dry-run) " if args.dry_run else ""

    ctx = org_context(org, repo)
    project, how = find_project(ctx, args.repo, title)
    if project:
        print(f"Project #{project['number']} \"{project['title']}\" já existe ({how}): {project['url']}")
    else:
        template = pick_template(ctx, args.template)
        print(f"{dry}copiando o template #{template['number']} \"{template['title']}\" como \"{title}\"")
        if args.dry_run:
            project = None
        else:
            project = graphql("""
                mutation($project: ID!, $owner: ID!, $title: String!) {
                  copyProjectV2(input: {projectId: $project, ownerId: $owner, title: $title, includeDraftIssues: false}) {
                    projectV2 { id number title url }
                  }
                }""", project=template["id"], owner=ctx["org_id"], title=title)["copyProjectV2"]["projectV2"]
            print(f"Project #{project['number']} criado: {project['url']}")

    details = project_details(project["id"], ctx["repo_id"]) if project else {"linked": False, "auto_add": False}

    if details["linked"]:
        print(f"repo {args.repo} já ligado ao Project")
    else:
        print(f"{dry}ligando {args.repo} ao Project")
        if not args.dry_run:
            graphql("""
                mutation($project: ID!, $repo: ID!) {
                  linkProjectV2ToRepository(input: {projectId: $project, repositoryId: $repo}) { repository { id } }
                }""", project=project["id"], repo=ctx["repo_id"])

    number = str(project["number"]) if project else "<novo>"
    if repo_variable(args.repo, "PROJECT_NUMBER") == number:
        print(f"variável PROJECT_NUMBER={number} já definida")
    else:
        print(f"{dry}definindo a variável PROJECT_NUMBER={number} em {args.repo}")
        if not args.dry_run:
            gh("variable", "set", "PROJECT_NUMBER", "-R", args.repo, "--body", number)

    if gh("api", f"repos/{args.repo}", "--jq", ".delete_branch_on_merge").strip() == "true":
        print("branch do PR já é apagada no merge")
    else:
        print(f"{dry}ligando \"apagar a branch do PR no merge\" em {args.repo}")
        if not args.dry_run:
            gh("api", "-X", "PATCH", f"repos/{args.repo}", "-F", "delete_branch_on_merge=true", "--silent")

    todo = []
    if not details["auto_add"]:
        url = f"{project['url']}/workflows" if project else f"https://github.com/orgs/{org}/projects/<novo>/workflows"
        todo.append(f"Ligue o workflow Auto-add to project em {url}: Edit → repo {repo}, filtro is:issue → "
                    "Save and turn on workflow (o GitHub nunca copia o Auto-add).")
    secret = has_secret(args.repo, "PROJECT_TOKEN")
    if secret is None:
        todo.append(f"Não consegui listar os secrets de {args.repo}; confira se PROJECT_TOKEN existe.")
    elif not secret:
        todo.append(f"Crie o secret do token do board (cole o mesmo PAT dos outros jogos): gh secret set PROJECT_TOKEN -R {args.repo}")
    for path in GAME_WORKFLOWS:
        if not has_file(args.repo, path):
            name = path.rsplit("/", 1)[1]
            todo.append(f"O repo não tem {path}: copie workflow-templates/{name} deste repo para lá.")

    if todo:
        print("\nFalta fazer à mão:")
        for index, item in enumerate(todo, 1):
            print(f"  {index}. {item}")
    else:
        print("\nBoard pronto.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"erro: {error}", file=sys.stderr)
        sys.exit(1)
