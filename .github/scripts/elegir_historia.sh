#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Elige la siguiente historia de la cola de desarrollo y escribe su número en stdout (vacío si no hay).
# - Hasta HISTORIAS_EN_PARALELO historias a la vez en estado:en-desarrollo (por defecto 1). Las que
#   están en revisión no ocupan hueco, pero sus zonas cuentan para el solape. Con alguna en curso, solo se elige otra si las dos declaran su línea "Toca:" (zonas del
#   código que modifican) y no se solapan; una historia sin "Toca:" va sola.
# - Candidatas: historias abiertas con estado:lista.
# - Orden: Priority del tablero (P0, P1, P2, sin prioridad) y, dentro de cada una, la más antigua.
# - Salta las que tienen dependencias abiertas: solo cuentan las líneas que EMPIEZAN por "Depende de #N"
#   (o "Depende de: #a, #b"); "no depende de #N" o "#N depende de esta" no cuentan. Las épicas, features y
#   los ancestros de la propia historia no cuentan; una historia madre cuenta mientras tenga hijas abiertas.
# Entradas por entorno: GH_TOKEN (lectura del repo), REPO; para leer Priority, PROJECT_TOKEN, OWNER y
# PROJECT_NUMBER (sin PROJECT_TOKEN se ordena solo por antigüedad). IGNORAR_OCUPADAS=1 prueba el
# orden aunque haya una historia en curso. COLA_PAUSADA=1 solo deja retomar historias con PR abierta.
# Los mensajes van a stderr.
set -euo pipefail

log() { echo "$*" >&2; }

LIMITE=${HISTORIAS_EN_PARALELO:-1}

# toca <issue>: zonas de su línea "Toca:" (una por línea, sin comillas ni barra final); vacío si no la tiene.
toca() {
  gh issue view "$1" -R "$REPO" --json body --jq .body \
    | grep -m1 -iE '^[-*_ ]*Toca[*_ ]*:' | sed -E 's/^[^:]*:[*_ ]*//' \
    | tr ',;' '\n\n' | tr -d '`*' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s#/+$##' | grep -v '^$' || true
}

# Puntos calientes compartidos: casi toda historia los toca, sus conflictos son triviales (se añaden
# líneas) y los resuelve Actualizar rama; Fusionar exige además la PR al día con main antes de fusionar.
COMPARTIDAS='^(src/parcel_intel/cli/main\.py|src/parcel_intel/ports/errors\.py|src/parcel_intel/sources/REGISTRY\.md|NOTICE|CLAUDE\.md|docs/lessons/LESSONS\.md)$'

# solapan <zonas-a> <zonas-b>: 0 si alguna zona de una contiene a (o es) alguna de la otra.
solapan() {
  local a b
  while read -r a; do
    while read -r b; do
      [ -z "$a" ] || [ -z "$b" ] && continue
      [[ "$a" =~ $COMPARTIDAS ]] && continue
      [[ "$b" =~ $COMPARTIDAS ]] && continue
      if [ "$a" = "$b" ] || [[ "$a" == "$b"/* ]] || [[ "$b" == "$a"/* ]]; then return 0; fi
    done <<<"$2"
  done <<<"$1"
  return 1
}

en_desarrollo=""
en_curso=""
if [ -z "${IGNORAR_OCUPADAS:-}" ]; then
  en_desarrollo=$(gh issue list -R "$REPO" --state open --label tipo:historia --label estado:en-desarrollo --json number --jq '.[].number' | sort -un)
  # Las de revisión no ocupan hueco de desarrollo, pero sus zonas cuentan: su PR sigue abierta.
  en_curso=$( { echo "$en_desarrollo"
                gh issue list -R "$REPO" --state open --label tipo:historia --label estado:en-revision --json number --jq '.[].number'; } | grep . | sort -un || true)
fi
ocupadas=$(grep -c . <<<"$en_desarrollo" || true)
if [ "$ocupadas" -ge "$LIMITE" ]; then
  log "Hay $ocupadas historia(s) en desarrollo y el límite es $LIMITE: se espera."
  exit 0
fi
zonas_en_curso=""
for n in $en_curso; do
  z=$(toca "$n")
  if [ -z "$z" ]; then log "#$n está en curso sin línea Toca: va sola, se espera."; exit 0; fi
  zonas_en_curso+="$z"$'\n'
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

# Cola pausada (variable de repo COLA_PAUSADA=1): solo se retoman historias que ya tienen PR abierta.
con_pr=""
if [ -n "${COLA_PAUSADA:-}" ]; then
  con_pr=$(gh pr list -R "$REPO" --state open --json headRefName \
             --jq '.[].headRefName | capture("^claude/historia-(?<n>[0-9]+)-").n')
  log "Cola pausada: solo historias con PR abierta (${con_pr:-ninguna})."
fi

while read -r n prio; do
  [ -z "${n:-}" ] && continue
  if [ -n "${COLA_PAUSADA:-}" ] && ! grep -qx "$n" <<<"$con_pr"; then continue; fi
  deps=$(gh issue view "$n" -R "$REPO" --json body --jq .body \
           | sed -E 's|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(#[0-9]+)|\1|g' \
           | grep -iE '^[-*_ ]*Depende de[*_ :]*#' | sed -E 's/\. .*$//; s/;.*$//' \
           | grep -oE '#[0-9]+' | tr -d '#' | sort -un || true)
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
  if [ -n "$en_curso" ]; then
    z=$(toca "$n")
    if [ -z "$z" ]; then log "#$n no tiene línea Toca: no puede ir en paralelo."; continue; fi
    if solapan "$z" "$zonas_en_curso"; then log "#$n toca zonas de una historia en curso."; continue; fi
  fi
  log "Historia elegida: #$n (${prio:-sin prioridad})."
  echo "$n"
  exit 0
done <<<"$candidatas"

log "Historia elegida: ninguna."
