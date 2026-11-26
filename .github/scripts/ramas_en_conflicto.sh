#!/usr/bin/env bash
# Lanza actualizar-rama.yml para cada PR de agente (rama claude/*, no borrador) en conflicto con main.
# GitHub no ejecuta CI ni revisión en una PR con conflictos, así que sin esto se quedaría parada.
# Entradas por entorno: GH_TOKEN (pull-requests: read, actions: write), REPO.
set -euo pipefail

for pr in $(gh pr list -R "$REPO" --state open --json number,headRefName,isDraft \
              --jq '.[] | select(.headRefName | startswith("claude/")) | select(.isDraft | not) | .number'); do
  estado=""
  for _ in 1 2 3 4 5 6; do  # GitHub calcula "mergeable" en diferido tras cada cambio en main
    estado=$(gh api "repos/$REPO/pulls/$pr" --jq '.mergeable_state')
    [ "$estado" != "unknown" ] && break
    sleep 5
  done
  if [ "$estado" = "dirty" ]; then
    echo "PR #$pr en conflicto con main: se lanza Actualizar rama."
    gh workflow run actualizar-rama.yml -R "$REPO" --ref main -f pr="$pr"
  else
    echo "PR #$pr: $estado."
  fi
done
