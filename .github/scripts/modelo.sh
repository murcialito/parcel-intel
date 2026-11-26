#!/usr/bin/env bash
# Elige el modelo de Claude según la fase y la talla de la historia (docs/proceso.md, "Modelos por tarea").
# Uso: modelo.sh <fase> [issue]   con fase en: refinar | diseno | desarrollo | revision
#      modelo.sh turnos-desarrollo <issue>   → tope de turnos del desarrollador según la talla
# Entorno: GH_TOKEN, REPO. Los modelos se pueden cambiar sin tocar código con las variables
# de repositorio MODELO_BARATO, MODELO_INTERMEDIO y MODELO_CAPAZ.
set -euo pipefail

BARATO="${MODELO_BARATO:-claude-haiku-5-5}"
INTERMEDIO="${MODELO_INTERMEDIO:-claude-sonnet-5-5}"
CAPAZ="${MODELO_CAPAZ:-claude-opus-5-5}"

fase="$1"
issue="${2:-}"

talla=""
if [ -n "$issue" ]; then
  talla=$(gh issue view "$issue" -R "$REPO" --json labels \
    --jq '[.labels[].name | select(startswith("talla:"))][0] // ""')
fi

case "$fase" in
  refinar) echo "$INTERMEDIO" ;;
  diseno) echo "$CAPAZ" ;;
  desarrollo)
    case "$talla" in
      talla:s) echo "$BARATO" ;;
      talla:l) echo "$CAPAZ" ;;
      *) echo "$INTERMEDIO" ;;
    esac ;;
  revision)
    case "$talla" in
      talla:l) echo "$CAPAZ" ;;
      *) echo "$INTERMEDIO" ;;
    esac ;;
  turnos-desarrollo)
    # Una historia L con Opus llegó a 173 turnos (#37): el tope sobra en S y se queda corto en L.
    case "$talla" in
      talla:s) echo 120 ;;
      talla:l) echo 350 ;;
      *) echo 250 ;;
    esac ;;
  *) echo "Fase desconocida: $fase" >&2; exit 1 ;;
esac
