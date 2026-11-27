#!/usr/bin/env bash
# Lanza corregir.yml para cada PR de agente con `cambios-pedidos` que se quedó sin corrección.
# La corrección se dispara con el evento `labeled` (desarrollar.yml, job corregir). GitHub no crea
# runs de `pull_request` mientras la PR está en conflicto con main, así que una etiqueta puesta en
# ese momento se pierde y la PR se queda parada (#114, 2026-11-27).
#
# Una PR está pendiente si cumple todo esto:
#   - rama claude/*, abierta, no borrador, sin veto, con cambios-pedidos;
#   - no está en conflicto: primero la pone al día Actualizar rama;
#   - la etiqueta lleva puesta más de GRACIA_S segundos, el margen para que el disparo normal llegue antes;
#   - no hay ningún Corregir de esa PR en cola o en curso, ni ninguno lanzado después de la etiqueta.
#     Si ese intento acabó sin cambios, no se repite: lo deja anotado corregir.yml.
# Los runs de Corregir se reconocen por su nombre, «Corregir PR #<n>» (run-name de corregir.yml).
# Entradas por entorno: GH_TOKEN (pull-requests e issues: read, actions: write), REPO; opcional GRACIA_S.
set -euo pipefail

GRACIA_S="${GRACIA_S:-120}"
ahora=$(date -u +%s)
a_segundos() { python3 -c 'import sys,datetime;print(int(datetime.datetime.fromisoformat(sys.argv[1].replace("Z","+00:00")).timestamp()))' "$1"; }

runs=$(gh run list -R "$REPO" --workflow corregir.yml --limit 100 --json displayTitle,status,createdAt)
# Un Corregir en curso sin número (anterior al run-name) podría ser de cualquier PR: esta pasada no lanza nada.
if jq -e '.[] | select(.status != "completed") | select(.displayTitle | test("#[0-9]+") | not)' <<<"$runs" >/dev/null; then
  echo "Hay un Corregir en curso sin número de PR: se espera a la próxima pasada."
  exit 0
fi

for pr in $(gh pr list -R "$REPO" --state open --json number,headRefName,isDraft,labels \
              --jq '.[] | select(.headRefName | startswith("claude/")) | select(.isDraft | not)
                    | select([.labels[].name] | index("cambios-pedidos")) | select([.labels[].name] | index("veto") | not)
                    | .number'); do
  if [ "$(gh api "repos/$REPO/pulls/$pr" --jq .mergeable_state)" = "dirty" ]; then
    echo "PR #$pr: en conflicto; antes la pone al día Actualizar rama."
    continue
  fi
  etiqueta=$(gh api "repos/$REPO/issues/$pr/events" --paginate \
               --jq '.[] | select(.event == "labeled" and .label.name == "cambios-pedidos") | .created_at' | tail -1)
  [ -n "$etiqueta" ] || { echo "PR #$pr: sin evento de la etiqueta."; continue; }
  t_etiqueta=$(a_segundos "$etiqueta")
  if [ $((ahora - t_etiqueta)) -lt "$GRACIA_S" ]; then
    echo "PR #$pr: etiqueta reciente ($etiqueta); el disparo normal va primero."
    continue
  fi
  suyos=$(jq --arg t "Corregir PR #$pr" '[.[] | select(.displayTitle == $t)]' <<<"$runs")
  if jq -e '.[] | select(.status != "completed")' <<<"$suyos" >/dev/null; then
    echo "PR #$pr: ya hay un Corregir en cola o en curso."
    continue
  fi
  ultimo=$(jq -r 'map(.createdAt) | max // empty' <<<"$suyos")
  if [ -n "$ultimo" ] && [ "$(a_segundos "$ultimo")" -ge "$t_etiqueta" ]; then
    echo "PR #$pr: ya se intentó corregir después de la etiqueta ($ultimo)."
    continue
  fi
  echo "PR #$pr: cambios-pedidos desde $etiqueta sin corrección: se lanza Corregir."
  gh workflow run corregir.yml -R "$REPO" --ref main -f pr="$pr"
done
