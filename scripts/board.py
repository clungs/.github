"""Mantém o board do Project em dia a partir de eventos de PR e issue.

Roda dentro do workflow reutilizável .github/workflows/project-board.yml.
O que os workflows nativos do Project já fazem (item adicionado -> Todo,
fechado ou PR mergeado -> Done) não é repetido aqui.

  PR aberto como draft ou convertido em draft  -> issues do PR em In Progress
  PR aberto pronto, ready_for_review, review   -> issues do PR em In Review
  Lote começa (In Progress/In Review)          -> feature-mãe sai de Todo para In Progress
  Último lote de uma feature fecha             -> feature-mãe fecha

Nos mesmos eventos de PR, o PR herda o que falta nele:
  sem assignee   -> o autor do PR
  sem labels     -> as labels das issues do PR (menos as de triagem, como needs-spec)
  sem milestone  -> a milestone da primeira issue do PR que tiver uma
  fora do board  -> entra no Project (a view Board filtra is:issue, então não vira card)

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

    node = graphql("""
        query($id: ID!) {
          node(id: $id) {
            ... on PullRequest {
              id number
              author { __typename ... on User { id login } }
              assignees(first: 1) { totalCount }
              labels(first: 1) { totalCount }
              milestone { id }
              projectItems(first: 20) { nodes { project { id } } }
              closingIssuesReferences(first: 20) {
                nodes { id labels(first: 30) { nodes { id name } } milestone { id title } }
              }
            }
          }
        }""", id=pr["node_id"])["node"]
    issues = node["closingIssuesReferences"]["nodes"]
    for ref in issues:
        issue = issue_by_id(ref["id"])
        set_status(issue, project, target)
        start_parent(issue, project)
    try:
        fill_pull_request(node, issues, project)
    except RuntimeError as error:
        print(f"::warning::PR #{node['number']}: não deu para completar assignee/labels/milestone/project: {error}")


TRIAGE_LABELS = {"needs-spec", "good-first-issue", "good first issue", "help wanted"}


def fill_pull_request(pr: dict, issues: list[dict], project: dict) -> None:
    number = pr["number"]
    author = pr["author"]
    if pr["assignees"]["totalCount"] == 0 and author and author["__typename"] == "User":
        graphql("""
            mutation($pr: ID!, $user: ID!) {
              addAssigneesToAssignable(input: {assignableId: $pr, assigneeIds: [$user]}) { clientMutationId }
            }""", pr=pr["id"], user=author["id"])
        print(f"PR #{number}: assignee {author['login']}")

    if pr["labels"]["totalCount"] == 0:
        labels: dict[str, str] = {}
        for issue in issues:
            for label in issue["labels"]["nodes"]:
                if label["name"] not in TRIAGE_LABELS:
                    labels.setdefault(label["name"], label["id"])
        if labels:
            graphql("""
                mutation($pr: ID!, $labels: [ID!]!) {
                  addLabelsToLabelable(input: {labelableId: $pr, labelIds: $labels}) { clientMutationId }
                }""", pr=pr["id"], labels=list(labels.values()))
            print(f"PR #{number}: labels {', '.join(labels)}")

    milestone = next((issue["milestone"] for issue in issues if issue["milestone"]), None)
    if pr["milestone"] is None and milestone:
        graphql("""
            mutation($pr: ID!, $milestone: ID!) {
              updatePullRequest(input: {pullRequestId: $pr, milestoneId: $milestone}) { clientMutationId }
            }""", pr=pr["id"], milestone=milestone["id"])
        print(f"PR #{number}: milestone {milestone['title']}")

    if not any(item["project"]["id"] == project["id"] for item in pr["projectItems"]["nodes"]):
        graphql("""
            mutation($project: ID!, $content: ID!) {
              addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
            }""", project=project["id"], content=pr["id"])
        print(f"PR #{number}: ligado ao Project")


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
