#!/usr/bin/env bash
# Decide si una PR que toca curated/** tiene la aprobación del fundador sobre su último commit.
# Entrada: JSON de `gh pr view --json headRefOid,reviews` por stdin. Entorno: FUNDADOR (por defecto murcialito).
# Salida: 0 = hay una review APPROVED del fundador cuyo commit es headRefOid; 1 = no.
# Una aprobación sobre un commit anterior no vale: hay que volver a aprobar tras cada push.
set -u

fundador="${FUNDADOR:-murcialito}"
jq -e --arg f "$fundador" '
  .headRefOid as $cabeza
  | any(.reviews[]?; .state == "APPROVED" and .author.login == $f and .commit.oid == $cabeza)
' >/dev/null
