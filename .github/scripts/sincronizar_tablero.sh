#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Refleja una issue en el proyecto de usuario "Parcela Intel" (users/<owner>/projects/<n>):
# la añade si no está, pone Status según su etiqueta estado:* (o Done si está cerrada)
# y Size según su etiqueta talla:*. Idempotente: se puede llamar con cualquier evento.
# Entradas por entorno: GH_TOKEN, OWNER, PROJECT_NUMBER, REPO, ISSUE (número).
set -euo pipefail

if [ -z "${GH_TOKEN:-}" ]; then
  echo "Sin PROJECT_TOKEN: no se sincroniza el tablero (las etiquetas siguen mandando)."
  exit 0
fi

datos=$(gh issue view "$ISSUE" -R "$REPO" --json id,state,labels)
issue_id=$(jq -r '.id' <<<"$datos")
estado_issue=$(jq -r '.state' <<<"$datos")
etiquetas=$(jq -r '.labels[].name' <<<"$datos")

columna="Backlog"
if [ "$estado_issue" = "CLOSED" ]; then
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

proyecto=$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        id
        status: field(name: "Status") { ... on ProjectV2SingleSelectField { id options { id name } } }
        size: field(name: "Size") { ... on ProjectV2SingleSelectField { id options { id name } } }
      }
    }
  }' -f owner="$OWNER" -F number="$PROJECT_NUMBER")

project_id=$(jq -r '.data.user.projectV2.id' <<<"$proyecto")

item_id=$(gh api graphql -f query='
  mutation($project: ID!, $content: ID!) {
    addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
  }' -f project="$project_id" -f content="$issue_id" --jq '.data.addProjectV2ItemById.item.id')

poner() {  # poner <campo: status|size> <opción>
  local campo="$1" opcion="$2" field_id option_id
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
    }' -f project="$project_id" -f item="$item_id" -f field="$field_id" -f option="$option_id" >/dev/null
}

poner status "$columna"
if [ -n "$talla" ]; then poner size "$talla"; fi

echo "Issue #$ISSUE → Status '$columna'${talla:+, Size '$talla'}."
