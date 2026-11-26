#!/usr/bin/env bash
# Desbloquea las issues con estado:bloqueada cuyas dependencias ya están cerradas como completadas.
# Cada issue bloqueada declara en su cuerpo una línea así:
#   Desbloqueo: estado:diseno cuando se cierren #18, #19
# Al desbloquear pone ese estado, quita estado:bloqueada, comenta y lanza el workflow que le toca
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
    estado=$(gh issue view "$d" -R "$REPO" --json state,stateReason --jq '"\(.state) \(.stateReason)"')
    [ "$estado" = "CLOSED COMPLETED" ] || pendientes="$pendientes #$d"
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
