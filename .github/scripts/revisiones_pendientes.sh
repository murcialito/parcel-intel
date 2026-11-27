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
#
# También saca de borrador las PRs que el agente dejó así al terminar (#216, #217, #183, 2026-11-27):
# el desarrollador pasa la historia a `estado:en-revision` pero no ejecuta `gh pr ready`. La revisión se
# salta los borradores, el barrido de arriba solo mira PRs listas y «devolver a la cola» solo actúa si la
# historia sigue en desarrollo: nadie la movía. Una PR así está pendiente si cumple todo esto:
#   - rama claude/historia-<n>-*, abierta, en borrador, sin veto;
#   - la historia <n> está en estado:en-revision desde hace más de GRACIA_S segundos (el agente pudo
#     poner la etiqueta y estar a punto de ejecutar `gh pr ready`);
#   - no hay ningún run de Corregir en cola o en curso para esa PR.
# Se marca lista con PROJECT_TOKEN, y el revisor la juzga contra la issue: si está a medias, pide cambios.
# Entradas por entorno: GH_TOKEN (pull-requests, issues y actions: read), PROJECT_TOKEN (repo), REPO.
set -euo pipefail
GRACIA_S=${GRACIA_S:-600}
recien=" "  # PRs que este barrido acaba de marcar listas: el segundo bucle no las toca

for fila in $(gh pr list -R "$REPO" --state open --json number,headRefName,isDraft,labels \
                --jq '.[] | select(.isDraft) | select([.labels[].name] | index("veto") | not)
                      | select(.headRefName | test("^claude/historia-[0-9]+-"))
                      | "\(.number):\(.headRefName | capture("^claude/historia-(?<n>[0-9]+)-").n)"'); do
  pr=${fila%%:*}
  historia=${fila#*:}
  desde=$(gh api "repos/$REPO/issues/$historia/timeline" --paginate \
            --jq '.[] | select(.event == "labeled" and .label.name == "estado:en-revision") | .created_at' | tail -1)
  if [ -z "$desde" ] || ! gh issue view "$historia" -R "$REPO" --json labels \
       --jq '[.labels[].name] | index("estado:en-revision")' | grep -q '[0-9]'; then
    continue  # la historia no está en revisión: el agente sigue o la devolvieron a la cola
  fi
  edad=$(( $(date -u +%s) - $(date -u -d "$desde" +%s) ))
  if [ "$edad" -lt "$GRACIA_S" ]; then
    echo "PR #$pr: borrador con #$historia en revisión desde hace ${edad}s; se espera."
    continue
  fi
  if [ -n "$(gh run list -R "$REPO" --workflow corregir.yml --limit 30 --json status,displayTitle \
               --jq ".[] | select(.status != \"completed\") | select(.displayTitle == \"Corregir PR #$pr\") | .status")" ]; then
    echo "PR #$pr: hay un Corregir en cola o en curso."
    continue
  fi
  [ -n "${PROJECT_TOKEN:-}" ] || { echo "::error::Sin PROJECT_TOKEN no se puede sacar de borrador la PR #$pr."; exit 1; }
  echo "PR #$pr: en borrador con #$historia en estado:en-revision desde hace ${edad}s: se marca lista."
  GH_TOKEN="$PROJECT_TOKEN" gh pr ready "$pr" -R "$REPO"
  recien="$recien$pr "
done

for pr in $(gh pr list -R "$REPO" --state open --json number,headRefName,isDraft,labels \
              --jq '.[] | select(.headRefName | startswith("claude/")) | select(.isDraft | not)
                    | select([.labels[].name] | index("veto") | not) | .number'); do
  case "$recien" in *" $pr "*) echo "PR #$pr: recién sacada de borrador; su revisión ya está pedida."; continue ;; esac
  datos=$(gh pr view "$pr" -R "$REPO" --json id,headRefName,statusCheckRollup,mergeStateStatus)
  if [ "$(jq -r .mergeStateStatus <<<"$datos")" = "DIRTY" ]; then
    echo "PR #$pr: en conflicto con main; la actualiza Actualizar rama (ramas_en_conflicto.sh)."
    continue  # GitHub no crea runs de pull_request en una PR con conflictos: pedir la revisión no sirve
  fi
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
