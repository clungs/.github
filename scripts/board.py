"""Mantém o board do Project em dia a partir de eventos de PR e issue.

Roda dentro do workflow reutilizável .github/workflows/project-board.yml.
O que os workflows nativos do Project já fazem (item adicionado -> Todo,
fechado ou PR mergeado -> Done) não é repetido aqui.

  PR aberto como draft ou convertido em draft  -> issues do PR em In Progress
  PR aberto pronto, ready_for_review, review   -> issues do PR em In Review
  Lote começa (In Progress/In Review)          -> feature-mãe sai de Todo para In Progress
  Último lote de uma feature fecha             -> feature-mãe fecha

"Issues do PR" são as de "Closes #N" no corpo do PR.

Variáveis: GH_TOKEN, GITHUB_EVENT_NAME, GITHUB_EVENT_PATH, PROJECT_OWNER, PROJECT_NUMBER.
"""

import json
import os
import subprocess
import sys

TODO = "Todo"
IN_PROGRESS = "In Progress"
IN_REVIEW = "In Review"


def graphql(query: str, **variables) -> dict:
    body = json.dumps({"query": query, "variables": variables})
    result = subprocess.run(["gh", "api", "graphql", "--input", "-"], input=body,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    payload = json.loads(result.stdout)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload["data"]


def load_project(owner: str, number: int) -> dict:
    data = graphql("""
        query($owner: String!, $number: Int!) {
          organization(login: $owner) {
            projectV2(number: $number) {
              id
              field(name: "Status") { ... on ProjectV2SingleSelectField { id options { id name } } }
            }
          }
        }""", owner=owner, number=number)
    project = data["organization"]["projectV2"]
    if project is None or project["field"] is None:
        raise RuntimeError(f"Project {owner}/{number} sem campo Status")
    return {
        "id": project["id"],
        "field": project["field"]["id"],
        "options": {option["name"]: option["id"] for option in project["field"]["options"]},
    }


ISSUE_FIELDS = """
  id number state
  parent { id number state }
  projectItems(first: 20) {
    nodes { id project { id } fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } } }
  }
"""


def issue_by_id(node_id: str) -> dict:
    return graphql(f"query($id: ID!) {{ node(id: $id) {{ ... on Issue {{ {ISSUE_FIELDS} }} }} }}", id=node_id)["node"]


def project_item(issue: dict, project: dict) -> dict | None:
    for item in issue["projectItems"]["nodes"]:
        if item["project"]["id"] == project["id"]:
            return item
    return None


def current_status(issue: dict, project: dict) -> str | None:
    item = project_item(issue, project)
    if item is None or item["fieldValueByName"] is None:
        return None
    return item["fieldValueByName"]["name"]


def set_status(issue: dict, project: dict, status: str) -> None:
    option = project["options"].get(status)
    if option is None:
        print(f"::warning::Status '{status}' não existe no Project; crie a opção no campo Status.")
        return
    item = project_item(issue, project)
    if item is None:
        item_id = graphql("""
            mutation($project: ID!, $content: ID!) {
              addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
            }""", project=project["id"], content=issue["id"])["addProjectV2ItemById"]["item"]["id"]
    else:
        item_id = item["id"]
    graphql("""
        mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
          updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field,
                                                value: {singleSelectOptionId: $option}}) { clientMutationId }
        }""", project=project["id"], item=item_id, field=project["field"], option=option)
    print(f"#{issue['number']} -> {status}")


def start_parent(issue: dict, project: dict) -> None:
    parent_ref = issue["parent"]
    if parent_ref is None or parent_ref["state"] != "OPEN":
        return
    parent = issue_by_id(parent_ref["id"])
    if current_status(parent, project) in (None, TODO):
        set_status(parent, project, IN_PROGRESS)


def on_pull_request(event: dict, project: dict) -> None:
    action = event["action"]
    pr = event["pull_request"]
    if action == "converted_to_draft":
        target = IN_PROGRESS
    elif action in ("opened", "reopened"):
        target = IN_PROGRESS if pr["draft"] else IN_REVIEW
    elif action in ("ready_for_review", "review_requested"):
        target = IN_REVIEW
    else:
        return

    data = graphql("""
        query($id: ID!) {
          node(id: $id) { ... on PullRequest { closingIssuesReferences(first: 20) { nodes { id } } } }
        }""", id=pr["node_id"])
    for ref in data["node"]["closingIssuesReferences"]["nodes"]:
        issue = issue_by_id(ref["id"])
        set_status(issue, project, target)
        start_parent(issue, project)


def on_issue_closed(event: dict) -> None:
    parent_ref = issue_by_id(event["issue"]["node_id"])["parent"]
    if parent_ref is None or parent_ref["state"] != "OPEN":
        return
    summary = graphql("""
        query($id: ID!) { node(id: $id) { ... on Issue { subIssuesSummary { total completed } } } }
        """, id=parent_ref["id"])["node"]["subIssuesSummary"]
    if summary["total"] == 0 or summary["completed"] < summary["total"]:
        return
    graphql("""
        mutation($id: ID!) { closeIssue(input: {issueId: $id, stateReason: COMPLETED}) { clientMutationId } }
        """, id=parent_ref["id"])
    print(f"#{parent_ref['number']} fechada: todos os lotes concluídos")


def main() -> int:
    if not os.environ.get("GH_TOKEN"):
        print("::warning::PROJECT_TOKEN não configurado na org; board não atualizado.")
        return 0
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        event = json.load(handle)
    name = os.environ["GITHUB_EVENT_NAME"]

    if name == "issues" and event["action"] == "closed":
        on_issue_closed(event)
        return 0

    number = os.environ.get("PROJECT_NUMBER", "").strip()
    if name == "pull_request":
        if not number:
            print("::notice::Variável PROJECT_NUMBER não definida no repo; status não atualizado.")
            return 0
        on_pull_request(event, load_project(os.environ["PROJECT_OWNER"], int(number)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
