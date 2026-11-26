#!/usr/bin/env bash
# Reescribe el historial de un CLON eliminando las rutas de un fichero de rutas.
#
# Uso: scripts/purgar_historial.sh <clon> <fichero-de-rutas> --copia-desechable
#
# - <clon>: raíz de un clon git (no un subdirectorio ni un directorio sin git).
# - <fichero-de-rutas>: formato de `git filter-repo --paths-from-file`
#   (ver scripts/rutas_purga.txt).
# - --copia-desechable: confirmación explícita de que <clon> es una copia de trabajo que se
#   puede perder. La reescritura es irreversible sobre ese directorio.
#
# Códigos de salida: 0 ok; 2 uso incorrecto; 3 falta git-filter-repo; 4 no es un clon.
# No hace push: `git filter-repo` elimina el remoto `origin` del clon a propósito.
set -euo pipefail

uso() {
    echo "Uso: $0 <clon> <fichero-de-rutas> --copia-desechable" >&2
    exit 2
}

[ "$#" -eq 3 ] || uso
clon=$1
rutas=$2
confirmacion=$3

if [ "$confirmacion" != "--copia-desechable" ]; then
    echo "Error: falta --copia-desechable (el tercer argumento debe ser exactamente ese)." >&2
    echo "Indica explícitamente que <clon> es una copia de trabajo desechable." >&2
    exit 2
fi

if [ ! -d "$clon" ]; then
    echo "Error: '$clon' no es un directorio." >&2
    exit 4
fi
if [ ! -f "$rutas" ]; then
    echo "Error: '$rutas' no es un fichero de rutas." >&2
    exit 2
fi

clon_abs=$(cd "$clon" && pwd -P)
rutas_abs=$(cd "$(dirname "$rutas")" && pwd -P)/$(basename "$rutas")

raiz=$(git -C "$clon_abs" rev-parse --show-toplevel 2>/dev/null || true)
if [ -z "$raiz" ] || [ "$(cd "$raiz" && pwd -P)" != "$clon_abs" ]; then
    echo "Error: '$clon' no es la raíz de un clon git." >&2
    exit 4
fi
if [ "$(git -C "$clon_abs" rev-parse --is-bare-repository)" != "false" ]; then
    echo "Error: '$clon' es un repositorio bare; se espera un clon con árbol de trabajo." >&2
    exit 4
fi
if [ -n "$(git -C "$clon_abs" status --porcelain)" ]; then
    echo "Error: el clon tiene cambios sin confirmar; usa un clon limpio." >&2
    exit 4
fi

if ! git -C "$clon_abs" filter-repo --version >/dev/null 2>&1; then
    echo "Error: git-filter-repo no está instalado (p. ej. 'pip install git-filter-repo')." >&2
    exit 3
fi

echo "Purgando de $clon_abs las rutas de $rutas_abs ..."
# --force: filter-repo exige un clon "recién hecho"; aquí las salvaguardas son las de arriba.
git -C "$clon_abs" filter-repo --invert-paths --paths-from-file "$rutas_abs" --force
echo "Purga terminada. El remoto 'origin' se ha eliminado del clon; no se ha hecho push."
echo "Siguiente paso: scripts/verificar_purga.sh '$clon' '$rutas'"
