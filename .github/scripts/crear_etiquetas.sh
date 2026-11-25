#!/usr/bin/env bash
# Crea (o actualiza) las etiquetas del proceso de docs/proceso.md. Idempotente.
# Uso: .github/scripts/crear_etiquetas.sh [owner/repo]
set -euo pipefail
REPO="${1:-murcialito/parcel-intel}"

etiqueta() { gh label create "$1" -R "$REPO" --color "$2" --description "$3" --force; }

etiqueta "tipo:epica"               "5319e7" "Objetivo de producto; se parte en features"
etiqueta "tipo:feature"             "1d76db" "Capacidad entregable; se parte en historias"
etiqueta "tipo:historia"            "0e8a16" "Incremento que cabe en una PR"
etiqueta "estado:refinar"           "fbca04" "El agente refinador debe trabajarla"
etiqueta "estado:necesita-fundador" "d93f0b" "Preguntas para el fundador en el último comentario"
etiqueta "estado:lista"             "0e8a16" "Cumple la Definición de Lista"
etiqueta "estado:en-desarrollo"     "c5def5" "Un agente la está programando"
etiqueta "estado:en-revision"       "bfdadc" "PR abierta"
etiqueta "cambios-pedidos"          "e99695" "La revisión encontró problemas bloqueantes"
etiqueta "veto"                     "b60205" "El fundador bloquea el merge automático"
