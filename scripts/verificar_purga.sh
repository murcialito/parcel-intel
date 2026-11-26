#!/usr/bin/env bash
# Comprueba que en un repo no queda rastro de las rutas de un fichero de rutas.
#
# Uso: scripts/verificar_purga.sh <repo> <fichero-de-rutas>
#
# Comprueba, tras expirar el reflog y hacer `gc --prune=now` EN el repo indicado (úsalo sobre
# el clon purgado, nunca sobre un repo con trabajo sin publicar):
#   1. commits de todas las refs (`git log --all --name-only`);
#   2. tags (árbol de cada tag);
#   3. blobs alcanzables (`git rev-list --objects --all`);
#   4. objetos sueltos o inalcanzables que sobrevivan al gc.
#
# Salida 0 si no hay rastro; 1 si lo hay (lista ruta y commit/objeto); 2 si el uso es incorrecto.
# Entiende las líneas del fichero de rutas: ruta literal o de directorio, `literal:` y `glob:`.
set -euo pipefail

[ "$#" -eq 2 ] || { echo "Uso: $0 <repo> <fichero-de-rutas>" >&2; exit 2; }
repo=$1
rutas=$2
[ -f "$rutas" ] || { echo "Error: '$rutas' no es un fichero de rutas." >&2; exit 2; }
git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || {
    echo "Error: '$repo' no es un repositorio git." >&2
    exit 2
}

literales=()
globs=()
while IFS= read -r linea || [ -n "$linea" ]; do
    case "$linea" in
        ''|'#'*) continue ;;
        glob:*) globs+=("${linea#glob:}") ;;
        literal:*) literales+=("${linea#literal:}") ;;
        regex:*) echo "Error: las líneas 'regex:' no están soportadas: $linea" >&2; exit 2 ;;
        *) literales+=("$linea") ;;
    esac
done < "$rutas"

# coincide <ruta>: 0 si la ruta cae bajo alguna entrada del fichero de rutas.
coincide() {
    local ruta=$1 p
    for p in "${literales[@]+"${literales[@]}"}"; do
        p=${p%/}
        if [ "$ruta" = "$p" ] || [[ $ruta == "$p"/* ]]; then return 0; fi
    done
    for p in "${globs[@]+"${globs[@]}"}"; do
        # shellcheck disable=SC2053
        if [[ $ruta == $p ]]; then return 0; fi
    done
    return 1
}

git -C "$repo" reflog expire --expire=now --all
git -C "$repo" gc --prune=now --quiet

rastros=0
informar() {
    echo "RASTRO ($1): $2 en $3"
    rastros=$((rastros + 1))
}

# 1. Commits de todas las refs (incluye tags y cualquier otra ref, p. ej. refs/pull/*).
commit=""
while IFS= read -r linea; do
    if [[ $linea =~ ^COMMIT\ ([0-9a-f]+)$ ]]; then
        commit=${BASH_REMATCH[1]}
    elif [ -n "$linea" ] && coincide "$linea"; then
        informar "commit" "$linea" "commit $commit"
    fi
done < <(git -C "$repo" log --all --no-renames --name-only --format='COMMIT %H')

# 2. Tags: árbol completo al que apunta cada uno.
while IFS= read -r tag; do
    [ -n "$tag" ] || continue
    while IFS= read -r ruta; do
        if coincide "$ruta"; then informar "tag" "$ruta" "tag $tag"; fi
    done < <(git -C "$repo" ls-tree -r --name-only "refs/tags/$tag^{tree}" 2>/dev/null || true)
done < <(git -C "$repo" tag)

# 3. Blobs y árboles alcanzables.
while IFS= read -r linea; do
    ruta=${linea#* }
    [ "$ruta" != "$linea" ] || continue
    if coincide "$ruta"; then informar "objeto alcanzable" "$ruta" "objeto ${linea%% *}"; fi
done < <(git -C "$repo" rev-list --objects --all)

# 4. Objetos que sobreviven al gc sin ser alcanzables (sueltos, reflog ya expirado).
inalcanzables=$(git -C "$repo" fsck --unreachable --no-reflogs --no-progress 2>/dev/null | wc -l)
if [ "$inalcanzables" -ne 0 ]; then
    echo "RASTRO (objetos inalcanzables tras gc --prune=now): $inalcanzables"
    rastros=$((rastros + 1))
fi

if [ "$rastros" -ne 0 ]; then
    echo "FALLO: quedan $rastros rastros de las rutas purgadas." >&2
    exit 1
fi
echo "OK: sin rastro en commits de todas las refs, tags, blobs alcanzables, reflog ni objetos sueltos."
