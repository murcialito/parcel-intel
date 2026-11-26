#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Elige la siguiente historia de la cola de desarrollo y escribe su número en stdout (vacío si no hay).
# - Si ya hay una historia en estado:en-desarrollo o estado:en-revision, no elige ninguna.
# - Candidatas: historias abiertas con estado:lista.
# - Orden: Priority del tablero (P0, P1, P2, sin prioridad) y, dentro de cada una, la más antigua.
# - Salta las que tienen dependencias abiertas ("Depende de #N" en el cuerpo). Las épicas, features y
#   los ancestros de la propia historia no cuentan; una historia madre cuenta mientras tenga hijas abiertas.
# Entradas por entorno: GH_TOKEN (lectura del repo), REPO; para leer Priority, PROJECT_TOKEN, OWNER y
# PROJECT_NUMBER (sin PROJECT_TOKEN se ordena solo por antigüedad). IGNORAR_OCUPADAS=1 prueba el
# orden aunque haya una historia en curso. Los mensajes van a stderr.
set -euo pipefail

log() { echo "$*" >&2; }

for estado in estado:en-desarrollo estado:en-revision; do
  [ -n "${IGNORAR_OCUPADAS:-}" ] && break  # solo para probar el orden a mano
  if [ "$(gh issue list -R "$REPO" --state open --label tipo:historia --label "$estado" --json number --jq length)" -gt 0 ]; then
    log "Ya hay una historia en $estado; se espera a que termine."
    exit 0
  fi
done

prioridades='{}'
if [ -n "${PROJECT_TOKEN:-}" ]; then
  prioridades=$(GH_TOKEN="$PROJECT_TOKEN" gh api graphql --paginate -f query='
    query($owner: String!, $number: Int!, $endCursor: String) {
      user(login: $owner) {
        projectV2(number: $number) {
          items(first: 100, after: $endCursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              content { ... on Issue { number } }
              prioridad: fieldValueByName(name: "Priority") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
            }
          }
        }
      }
    }' -f owner="$OWNER" -F number="$PROJECT_NUMBER" \
    --jq '.data.user.projectV2.items.nodes[] | select(.content.number != null and .prioridad.name != null)
          | {key: (.content.number | tostring), value: .prioridad.name}' \
    | jq -s 'from_entries') || { log "::warning::No se pudo leer Priority del tablero; orden por antigüedad."; prioridades='{}'; }
else
  log "Sin PROJECT_TOKEN: orden por antigüedad."
fi

candidatas=$(gh issue list -R "$REPO" --state open --label tipo:historia --label estado:lista --limit 200 \
  --json number,createdAt \
  | jq -r --argjson p "$prioridades" '
      map(. + {prio: ($p[(.number | tostring)] // "")})
      | sort_by([({"P0": 0, "P1": 1, "P2": 2}[.prio] // 3), .createdAt])
      | .[] | "\(.number) \(.prio)"')

while read -r n prio; do
  [ -z "${n:-}" ] && continue
  deps=$(gh issue view "$n" -R "$REPO" --json body --jq .body \
           | grep -iE 'depende de' | grep -oE '#[0-9]+' | tr -d '#' | sort -un || true)
  abiertas=""
  ancestros=$(gh api graphql -f query='
    query($o: String!, $r: String!, $n: Int!) {
      repository(owner: $o, name: $r) {
        issue(number: $n) { parent { number parent { number parent { number } } } }
      }
    }' -f o="${REPO%/*}" -f r="${REPO#*/}" -F n="$n" \
    --jq '[.data.repository.issue | .. | objects | .number? // empty] | .[]' 2>/dev/null || true)
  for d in $deps; do
    [ "$d" = "$n" ] && continue
    grep -qx "$d" <<<"$ancestros" && continue  # "Parte de la historia #23": su madre no es dependencia
    # Una épica o feature citada no es dependencia. Una historia madre bloquea mientras tenga alguna
    # hija abierta (no se cierra sola al acabar sus hijas); una historia normal, mientras esté abierta.
    bloquea=$(gh api graphql -f query='
      query($o: String!, $r: String!, $n: Int!) {
        repository(owner: $o, name: $r) {
          issue(number: $n) {
            state labels(first: 20) { nodes { name } }
            subIssues(first: 100) { totalCount nodes { state } }
          }
        }
      }' -f o="${REPO%/*}" -f r="${REPO#*/}" -F n="$d" \
      --jq '.data.repository.issue
            | if ([.labels.nodes[].name] | index("tipo:epica") != null or index("tipo:feature") != null) then false
              elif .subIssues.totalCount > 0 then ([.subIssues.nodes[].state] | index("OPEN") != null)
              else .state == "OPEN" end' \
      2>/dev/null || echo false)
    [ "$bloquea" = "true" ] && abiertas="$abiertas #$d"
  done
  if [ -n "$abiertas" ]; then log "#$n ${prio:-sin prioridad} espera a$abiertas."; continue; fi
  log "Historia elegida: #$n (${prio:-sin prioridad})."
  echo "$n"
  exit 0
done <<<"$candidatas"

log "Historia elegida: ninguna."
