#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Pone en el campo Status del proyecto de usuario la columna que corresponde a una etiqueta estado:*.
# Entradas por entorno: GH_TOKEN, OWNER, PROJECT_NUMBER, ISSUE_ID (node id), ETIQUETA.
set -euo pipefail

if [ -z "${GH_TOKEN:-}" ]; then
  echo "Sin PROJECT_TOKEN: no se sincroniza el tablero (las etiquetas siguen mandando)."
  exit 0
fi

case "$ETIQUETA" in
  estado:refinar) COLUMNA="Refinando" ;;
  estado:necesita-fundador) COLUMNA="Necesita al fundador" ;;
  estado:lista) COLUMNA="Lista" ;;
  estado:en-desarrollo) COLUMNA="En desarrollo" ;;
  estado:en-revision) COLUMNA="En revisión" ;;
  *) echo "Etiqueta $ETIQUETA sin columna asociada."; exit 0 ;;
esac

proyecto=$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        id
        field(name: "Status") {
          ... on ProjectV2SingleSelectField { id options { id name } }
        }
      }
    }
  }' -f owner="$OWNER" -F number="$PROJECT_NUMBER")

project_id=$(jq -r '.data.user.projectV2.id' <<<"$proyecto")
field_id=$(jq -r '.data.user.projectV2.field.id' <<<"$proyecto")
option_id=$(jq -r --arg c "$COLUMNA" '.data.user.projectV2.field.options[] | select(.name == $c) | .id' <<<"$proyecto")

if [ -z "$option_id" ]; then
  echo "::warning::El campo Status no tiene la opción '$COLUMNA'. Créala en el proyecto."
  exit 0
fi

item_id=$(gh api graphql -f query='
  mutation($project: ID!, $content: ID!) {
    addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
  }' -f project="$project_id" -f content="$ISSUE_ID" --jq '.data.addProjectV2ItemById.item.id')

gh api graphql -f query='
  mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
    updateProjectV2ItemFieldValue(input: {
      projectId: $project, itemId: $item, fieldId: $field,
      value: {singleSelectOptionId: $option}
    }) { projectV2Item { id } }
  }' -f project="$project_id" -f item="$item_id" -f field="$field_id" -f option="$option_id" >/dev/null

echo "Issue movida a '$COLUMNA'."
