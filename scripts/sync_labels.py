"""Cria ou atualiza as labels de labels.json em repos da org.

Uso:
    python scripts/sync_labels.py clungs/chombs clungs/pelvs
    python scripts/sync_labels.py --org clungs        # todos os repos não arquivados

Só cria e atualiza: nunca apaga labels que o repo já tenha.
Precisa do gh autenticado (ou GH_TOKEN) com escrita em issues.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

LABELS_FILE = Path(__file__).resolve().parent.parent / "labels.json"


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def org_repos(org: str) -> list[str]:
    out = gh("repo", "list", org, "--no-archived", "--limit", "200", "--json", "nameWithOwner", "--jq", ".[].nameWithOwner")
    return [line for line in out.splitlines() if line]


def sync(repo: str, labels: list[dict]) -> int:
    failures = 0
    for label in labels:
        try:
            gh("label", "create", label["name"], "--repo", repo, "--color", label["color"],
               "--description", label["description"], "--force")
        except RuntimeError as error:
            failures += 1
            print(f"  ! {repo} {label['name']}: {error}", file=sys.stderr)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repos", nargs="*")
    parser.add_argument("--org")
    args = parser.parse_args()

    repos = org_repos(args.org) if args.org else args.repos
    if not repos:
        parser.error("informe repos ou --org")

    labels = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
    failures = 0
    for repo in repos:
        failures += sync(repo, labels)
        print(f"{repo}: {len(labels)} labels sincronizadas")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
