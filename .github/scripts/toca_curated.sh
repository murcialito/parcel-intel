#!/usr/bin/env bash
# Guardia de curated/** (ADR 0024, enmienda). Lee rutas de stdin, una por línea.
# Salida: 0 = alguna ruta empieza por "curated/" (requiere revisión del fundador); 1 = ninguna.
# No cuentan rutas como docs/curated/x ni curated-notas.md.
set -u

while IFS= read -r ruta; do
  case "$ruta" in
    curated/*) exit 0 ;;
  esac
done
exit 1
