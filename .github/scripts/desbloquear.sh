#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Desbloquea las issues con estado:bloqueada cuyas dependencias ya están cerradas como completadas
# (o, si la dependencia es una historia madre, cuando todas sus hijas están cerradas).
# Cada issue bloqueada declara en su cuerpo una línea así:
#   Desbloqueo: estado:diseno cuando se cierren #18, #19
# Al desbloquear pone ese estado, quita estado:bloqueada, comenta y lanza el workflow que le toca.
# Además cierra los contenedores (épica, feature, historia madre) con todas sus sub-issues cerradas.
# (las etiquetas puestas con GITHUB_TOKEN no disparan workflows por sí solas).
# Entradas por entorno: GH_TOKEN (issues y actions), REPO; opcional PROJECT_TOKEN para el tablero.
set -euo pipefail

for n in $(gh issue list -R "$REPO" --state open --label estado:bloqueada --limit 200 --json number --jq '.[].number'); do
  linea=$(gh issue view "$n" -R "$REPO" --json body --jq .body | grep -m1 -iE '^\**Desbloqueo:' || true)
  destino=$(grep -oE 'estado:[a-z-]+' <<<"$linea" | head -1 || true)
  deps=$(grep -oE '#[0-9]+' <<<"$linea" | tr -d '#' | sort -un || true)
  if [ -z "$destino" ] || [ -z "$deps" ]; then
    echo "::warning::#$n está bloqueada sin una línea 'Desbloqueo: estado:<x> cuando se cierren #a, #b'."
    continue
  fi

  pendientes=""
  for d in $deps; do
    # Hecha si se cerró como completada, o si es una historia madre con todas sus hijas cerradas
    # (una madre no se cierra sola al terminar sus hijas).
    hecha=$(gh api graphql -f query='
      query($o: String!, $r: String!, $n: Int!) {
        repository(owner: $o, name: $r) {
          issue(number: $n) { state stateReason subIssues(first: 100) { totalCount nodes { state } } }
        }
      }' -f o="${REPO%/*}" -f r="${REPO#*/}" -F n="$d" \
      --jq '.data.repository.issue
            | (.state == "CLOSED" and .stateReason == "COMPLETED")
              or (.subIssues.totalCount > 0 and ([.subIssues.nodes[].state] | index("OPEN") == null))')
    [ "$hecha" = "true" ] || pendientes="$pendientes #$d"
  done
  if [ -n "$pendientes" ]; then echo "#$n sigue bloqueada por$pendientes."; continue; fi

  lista=$(sed 's/^/#/' <<<"$deps" | paste -sd, - | sed 's/,/, /g')
  gh issue edit "$n" -R "$REPO" --remove-label estado:bloqueada --add-label "$destino" >/dev/null
  gh issue comment "$n" -R "$REPO" --body "Dependencias cerradas ($lista): pasa a \`$destino\`." >/dev/null
  case "$destino" in
    estado:diseno)  gh workflow run disenar.yml -R "$REPO" --ref main -f issue="$n" ;;
    estado:refinar) gh workflow run refinar.yml -R "$REPO" --ref main -f issue="$n" ;;
    estado:lista)   gh workflow run desarrollar.yml -R "$REPO" --ref main || true ;;
  esac
  if [ -n "${PROJECT_TOKEN:-}" ]; then
    GH_TOKEN="$PROJECT_TOKEN" REPO_TOKEN="$GH_TOKEN" OWNER="${REPO%/*}" PROJECT_NUMBER=1 ISSUE="$n" \
      .github/scripts/sincronizar_tablero.sh || echo "::warning::No se pudo sincronizar #$n con el tablero."
  fi
  echo "#$n desbloqueada → $destino."
done

# Contenedores terminados: una épica, feature o historia madre con todas sus sub-issues cerradas se
# cierra (GitHub no lo hace solo). Si luego se le añade trabajo, el refinador la reabre.
for n in $(gh api graphql --paginate -f query='
    query($o: String!, $r: String!, $endCursor: String) {
      repository(owner: $o, name: $r) {
        issues(first: 100, after: $endCursor, states: OPEN) {
          pageInfo { hasNextPage endCursor }
          nodes { number subIssuesSummary { total completed } }
        }
      }
    }' -f o="${REPO%/*}" -f r="${REPO#*/}" \
    --jq '.data.repository.issues.nodes[] | select(.subIssuesSummary.total > 0 and .subIssuesSummary.completed == .subIssuesSummary.total) | .number'); do
  gh issue close "$n" -R "$REPO" --reason completed --comment "Todas sus sub-issues están cerradas: se cierra." >/dev/null
  echo "#$n cerrada: contenedor terminado."
done
