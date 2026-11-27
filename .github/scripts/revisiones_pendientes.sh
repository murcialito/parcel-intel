#!/usr/bin/env bash
# Vuelve a pedir la revisión de las PRs de agente cuyo último commit se quedó sin revisar.
# Pasa cuando el agente hace push y `gh pr ready` casi a la vez (#115, PR #131, 2026-11-27):
#   - el evento `synchronize` del commit nuevo sale con la PR aún en borrador, y su revisión se salta;
#   - el `ready_for_review` sale con el commit anterior, porque GitHub aún no había movido la cabeza.
# El commit de cabeza se queda con `revision` en «skipped» (o sin ella) y Fusionar no lo fusiona nunca.
#
# Una PR está pendiente si cumple todo esto:
#   - rama claude/*, abierta, no borrador, sin veto;
#   - el CI (`checks`) de su commit de cabeza ya terminó: el mismo push lanzó las dos cosas;
#   - el último `revision` de ese commit no existe, o acabó en skipped o cancelled;
#   - no hay ningún run de Revisar en cola o en curso para su rama.
# Se pasa la PR a borrador y se vuelve a marcar lista con PROJECT_TOKEN, porque los eventos de
# GITHUB_TOKEN no disparan workflows. Así sale un `ready_for_review` con la cabeza actual.
# Entradas por entorno: GH_TOKEN (pull-requests y actions: read), PROJECT_TOKEN (repo), REPO.
set -euo pipefail

for pr in $(gh pr list -R "$REPO" --state open --json number,headRefName,isDraft,labels \
              --jq '.[] | select(.headRefName | startswith("claude/")) | select(.isDraft | not)
                    | select([.labels[].name] | index("veto") | not) | .number'); do
  datos=$(gh pr view "$pr" -R "$REPO" --json id,headRefName,statusCheckRollup)
  ultimo() {  # ultimo <check>: estado del último check de ese nombre en el commit de cabeza
    jq -r --arg c "$1" '[.statusCheckRollup[] | select(.name == $c)] | sort_by(.startedAt // "") | last
                        | if . == null then "NINGUNO" elif .status != "COMPLETED" then "EN_CURSO" else .conclusion end' <<<"$datos"
  }
  ci=$(ultimo checks)
  revision=$(ultimo revision)
  case "$ci" in
    NINGUNO|EN_CURSO) echo "PR #$pr: CI $ci en la cabeza; se espera."; continue ;;
  esac
  case "$revision" in
    NINGUNO|SKIPPED|CANCELLED) ;;
    *) echo "PR #$pr: revision $revision."; continue ;;
  esac
  rama=$(jq -r .headRefName <<<"$datos")
  if [ -n "$(gh run list -R "$REPO" --workflow revisar.yml --branch "$rama" --limit 20 \
               --json status --jq '.[] | select(.status != "completed") | .status')" ]; then
    echo "PR #$pr: hay un Revisar en cola o en curso."
    continue
  fi
  [ -n "${PROJECT_TOKEN:-}" ] || { echo "::error::Sin PROJECT_TOKEN no se puede volver a pedir la revisión de la PR #$pr."; exit 1; }
  echo "PR #$pr: CI $ci y revision $revision en la cabeza: se vuelve a pedir la revisión."
  id=$(jq -r .id <<<"$datos")
  GH_TOKEN="$PROJECT_TOKEN" gh api graphql --silent -f id="$id" \
    -f query='mutation($id: ID!) { convertPullRequestToDraft(input: {pullRequestId: $id}) { clientMutationId } }'
  GH_TOKEN="$PROJECT_TOKEN" gh api graphql --silent -f id="$id" \
    -f query='mutation($id: ID!) { markPullRequestReadyForReview(input: {pullRequestId: $id}) { clientMutationId } }'
done
