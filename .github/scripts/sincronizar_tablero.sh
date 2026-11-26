#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Refleja una issue en el proyecto de usuario "Parcela Intel" (users/<owner>/projects/<n>):
# - la añade si no está;
# - Status según su etiqueta estado:* (o Done si está cerrada) y Size según talla:*;
# - Assignees: el fundador mientras tenga estado:necesita-fundador (la vista "Me esperan");
# - Start date / Target date para el Roadmap, con fechas reales:
#     historia: Start = entró en estado:en-desarrollo (o se cerró, si nunca entró), Target = se cerró
#               (hoy mientras sigue abierta); sin empezar, sin fechas;
#     feature/épica (tiene sub-issues): de la primera Start a la última Target de sus descendientes.
#   Después recalcula las fechas de sus padres hasta la épica.
# Idempotente: se puede llamar con cualquier evento.
# Entradas por entorno: GH_TOKEN (permiso project), REPO_TOKEN (lectura y asignación en el repo;
# si falta, GH_TOKEN), OWNER, PROJECT_NUMBER, REPO, ISSUE (número).
# Opcionales: TABLERO_CACHE (carpeta de caché compartida), SIN_PADRES=1 (no recalcula los padres).
set -euo pipefail

if [ -z "${GH_TOKEN:-}" ]; then
  echo "Sin PROJECT_TOKEN: no se sincroniza el tablero (las etiquetas siguen mandando)."
  exit 0
fi

repo_gh() { GH_TOKEN="${REPO_TOKEN:-$GH_TOKEN}" gh "$@"; }
HOY=$(date -u +%F)
# TABLERO_CACHE permite compartir la caché entre llamadas de una pasada completa.
if [ -n "${TABLERO_CACHE:-}" ]; then CACHE="$TABLERO_CACHE"; else CACHE=$(mktemp -d); trap 'rm -rf "$CACHE"' EXIT; fi

# Datos de una issue (cacheados en esta ejecución).
issue() {
  local n="$1" f="$CACHE/issue-$1.json"
  if [ ! -s "$f" ]; then
    repo_gh api graphql -f query='
      query($o: String!, $r: String!, $n: Int!) {
        repository(owner: $o, name: $r) {
          issue(number: $n) {
            id state closedAt
            labels(first: 30) { nodes { name } }
            assignees(first: 10) { nodes { login } }
            parent { number }
            subIssues(first: 100) { nodes { number } }
            timelineItems(itemTypes: [LABELED_EVENT], first: 100) {
              nodes { ... on LabeledEvent { createdAt label { name } } }
            }
          }
        }
      }' -f o="${REPO%/*}" -f r="${REPO#*/}" -F n="$n" --jq '.data.repository.issue' >"$f"
  fi
  cat "$f"
}

# fechas <n> → "inicio fin" (YYYY-MM-DD) o vacío si aún no ha empezado.
fechas() {
  local n="$1" d subs inicio="" fin="" s e c
  d=$(issue "$n")
  subs=$(jq -r '.subIssues.nodes[].number' <<<"$d")
  if [ -n "$subs" ]; then
    for c in $subs; do
      s=""; e=""
      read -r s e <<<"$(fechas "$c")" || true
      [ -z "${s:-}" ] && continue
      if [ -z "$inicio" ] || [[ "$s" < "$inicio" ]]; then inicio="$s"; fi
      if [ -z "$fin" ] || [[ "$e" > "$fin" ]]; then fin="$e"; fi
    done
  else
    inicio=$(jq -r '[.timelineItems.nodes[] | select(.label.name == "estado:en-desarrollo") | .createdAt][0] // empty' <<<"$d")
    fin=$(jq -r '.closedAt // empty' <<<"$d")
    [ -z "$inicio" ] && inicio="$fin"
    [ -n "$inicio" ] && [ -z "$fin" ] && fin="$HOY"
  fi
  if [ -n "$inicio" ]; then echo "${inicio:0:10} ${fin:0:10}"; fi
}

proyecto=$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        id
        status: field(name: "Status") { ... on ProjectV2SingleSelectField { id options { id name } } }
        size: field(name: "Size") { ... on ProjectV2SingleSelectField { id options { id name } } }
        inicio: field(name: "Start date") { ... on ProjectV2Field { id } }
        fin: field(name: "Target date") { ... on ProjectV2Field { id } }
      }
    }
  }' -f owner="$OWNER" -F number="$PROJECT_NUMBER")
project_id=$(jq -r '.data.user.projectV2.id' <<<"$proyecto")

item_de() {  # item_de <n> → id del item en el proyecto (lo añade si no está)
  gh api graphql -f query='
    mutation($project: ID!, $content: ID!) {
      addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
    }' -f project="$project_id" -f content="$(issue "$1" | jq -r .id)" --jq '.data.addProjectV2ItemById.item.id'
}

poner_opcion() {  # poner_opcion <item> <campo: status|size> <opción>
  local item="$1" campo="$2" opcion="$3" field_id option_id
  field_id=$(jq -r --arg f "$campo" '.data.user.projectV2[$f].id // empty' <<<"$proyecto")
  option_id=$(jq -r --arg f "$campo" --arg o "$opcion" \
    '.data.user.projectV2[$f].options[]? | select(.name == $o) | .id' <<<"$proyecto")
  if [ -z "$field_id" ] || [ -z "$option_id" ]; then
    echo "::warning::El proyecto no tiene la opción '$opcion' en el campo '$campo'."
    return 0
  fi
  gh api graphql -f query='
    mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $project, itemId: $item, fieldId: $field,
        value: {singleSelectOptionId: $option}
      }) { projectV2Item { id } }
    }' -f project="$project_id" -f item="$item" -f field="$field_id" -f option="$option_id" >/dev/null
}

poner_fecha() {  # poner_fecha <item> <campo: inicio|fin> <YYYY-MM-DD o vacío para borrar>
  local item="$1" campo="$2" valor="$3" field_id
  field_id=$(jq -r --arg f "$campo" '.data.user.projectV2[$f].id // empty' <<<"$proyecto")
  [ -z "$field_id" ] && return 0
  if [ -n "$valor" ]; then
    gh api graphql -f query='
      mutation($project: ID!, $item: ID!, $field: ID!, $date: Date!) {
        updateProjectV2ItemFieldValue(input: {
          projectId: $project, itemId: $item, fieldId: $field, value: {date: $date}
        }) { projectV2Item { id } }
      }' -f project="$project_id" -f item="$item" -f field="$field_id" -f date="$valor" >/dev/null
  else
    gh api graphql -f query='
      mutation($project: ID!, $item: ID!, $field: ID!) {
        clearProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field}) {
          projectV2Item { id }
        }
      }' -f project="$project_id" -f item="$item" -f field="$field_id" >/dev/null
  fi
}

sincronizar_fechas() {  # sincronizar_fechas <n> <item> → imprime "inicio→fin" o "sin empezar"
  local s="" e=""
  read -r s e <<<"$(fechas "$1")" || true
  poner_fecha "$2" inicio "${s:-}"
  poner_fecha "$2" fin "${e:-}"
  if [ -n "${s:-}" ]; then echo "$s→$e"; else echo "sin empezar"; fi
}

# --- La issue pedida -------------------------------------------------------------------------
datos=$(issue "$ISSUE")
etiquetas=$(jq -r '.labels.nodes[].name' <<<"$datos")

columna="Backlog"
if [ "$(jq -r .state <<<"$datos")" = "CLOSED" ]; then
  columna="Done"
elif grep -qx 'estado:necesita-fundador' <<<"$etiquetas"; then
  columna="Necesita al fundador"
elif grep -qx 'estado:en-revision' <<<"$etiquetas"; then
  columna="In review"
elif grep -qx 'estado:en-desarrollo' <<<"$etiquetas"; then
  columna="In progress"
elif grep -qx 'estado:lista' <<<"$etiquetas"; then
  columna="Ready"
fi

talla=""
case "$(grep -m1 '^talla:' <<<"$etiquetas" || true)" in
  talla:s) talla="S" ;;
  talla:m) talla="M" ;;
  talla:l) talla="L" ;;
esac

item_id=$(item_de "$ISSUE")
poner_opcion "$item_id" status "$columna"
if [ -n "$talla" ]; then poner_opcion "$item_id" size "$talla"; fi

# El fundador, asignado solo mientras la issue le espera.
asignado=$(jq -r --arg o "$OWNER" '[.assignees.nodes[].login] | index($o) != null' <<<"$datos")
if [ "$columna" = "Necesita al fundador" ] && [ "$asignado" = "false" ]; then
  repo_gh issue edit "$ISSUE" -R "$REPO" --add-assignee "$OWNER" >/dev/null
elif [ "$columna" != "Necesita al fundador" ] && [ "$asignado" = "true" ]; then
  repo_gh issue edit "$ISSUE" -R "$REPO" --remove-assignee "$OWNER" >/dev/null
fi

rango=$(sincronizar_fechas "$ISSUE" "$item_id")
echo "Issue #$ISSUE → Status '$columna'${talla:+, Size '$talla'}, fechas $rango."

# --- Sus padres, hasta la épica --------------------------------------------------------------
# En una pasada completa (SIN_PADRES=1) cada padre se sincroniza en su propio turno.
padre=""
[ -z "${SIN_PADRES:-}" ] && padre=$(jq -r '.parent.number // empty' <<<"$datos")
while [ -n "$padre" ]; do
  echo "  padre #$padre → fechas $(sincronizar_fechas "$padre" "$(item_de "$padre")")."
  padre=$(issue "$padre" | jq -r '.parent.number // empty')
done
