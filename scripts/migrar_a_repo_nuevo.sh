#!/usr/bin/env bash
# shellcheck disable=SC2016  # las variables $x de GraphQL van literales a propósito
# Migra Parcel Intel a un repo nuevo con el historial purgado, para hacerlo público sin depender
# de GitHub Support (ADR 0028, docs/runbook-publicacion.md). El repo actual queda privado como
# archivo de las PRs. Se ejecuta por fases, comprobando cada una antes de la siguiente:
#
#   scripts/migrar_a_repo_nuevo.sh <fase> <carpeta-de-trabajo> [--simular]
#
#   preparar   mirror de copia, purga, verificación, tests sobre el árbol purgado y foto de las
#              issues (padres, Priority). No toca GitHub.
#   archivar   desactiva Actions en el repo actual y lo renombra a parcel-intel-archivo.
#   crear      crea parcel-intel PRIVADO (no se pueden transferir issues de privado a público),
#              con Actions desactivado; sube main purgado y copia las etiquetas.
#   numerar    transfiere las issues conservando su número: los números que eran PRs se rellenan
#              con una issue de reserva que se borra al momento. Se puede reanudar.
#   restaurar  enlaza el proyecto, recompone sub-issues que falten, sincroniza el tablero y
#              repone Priority.
#   activar    (después de que el fundador guarde los secrets y dé acceso a la App de Claude)
#              activa Actions.
#   publicar   verifica la purga sobre un clon nuevo, hace público el repo, activa Pages y
#              protege main contra push forzado y borrado.
#
# --simular imprime lo que haría sin cambiar nada en GitHub.
# --ensayo (solo preparar) no exige que no haya PRs abiertas ni workflows en marcha.
#
# Qué se purga: las fixtures sintéticas (#45, #46) comparten ruta con las respuestas reales de
# Catastro, así que la purga es POR CONTENIDO. Se quitan del historial todas las versiones que
# alguna vez estuvieron en tests/fixtures/catastro/ o tests/fixtures/caminos/catastro_*, salvo
# las que hay en main al migrar (sintéticas, comprobadas antes de purgar).
# Además, toda referencia catastral real que aparezca en cualquier fichero o mensaje de commit del
# historial se sustituye por REFCAT-RETIRADA (decisión del fundador en #46: opción 1, también en el
# historial). main no debe contener ninguna al migrar.
set -euo pipefail

OWNER=murcialito
VIEJO=parcel-intel
ARCHIVO=parcel-intel-archivo
NUEVO=parcel-intel
PROYECTO=1
RAIZ=$(cd "$(dirname "$0")/.." && pwd -P)

[ "$#" -ge 2 ] || { sed -n '2,30p' "$0"; exit 2; }
FASE=$1
TRABAJO=$2
SIMULAR=""
ENSAYO=""
[ "${3:-}" = "--simular" ] && SIMULAR=1
[ "${3:-}" = "--ensayo" ] && ENSAYO=1  # preparar sin exigir que no haya PRs ni workflows en marcha
mkdir -p "$TRABAJO"
TRABAJO=$(cd "$TRABAJO" && pwd -P)

hacer() {  # hacer <comando...>: lo ejecuta o, con --simular, lo imprime
  if [ -n "$SIMULAR" ]; then printf '[simular]'; printf ' %q' "$@"; echo; else "$@"; fi
}
paso() { echo; echo "==> $*"; }
parar() { echo "ERROR: $*" >&2; exit 1; }

RUTAS_RE='^tests/fixtures/(catastro/|caminos/catastro_)'
# Referencia catastral de 14 caracteres con su sufijo opcional de 6 (20 en total): rústica de Madrid
# (28...) o urbana.
REFERENCIA_RE='\b28[0-9]{3}A[0-9]{8}([0-9]{4}[A-Z]{2})?\b|\b[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]([0-9]{4}[A-Z]{2})?\b'

referencias_reales() {  # stdin: contenido; stdout: referencias reales encontradas
  # No son reales las sintéticas del proyecto: urbanas con hoja ZZ (#45), rústicas con polígono
  # 99x (#46) o con parcela 99999 (casos "no encontrada"). Las de provincia 99 no casan con 28...
  grep -oE "$REFERENCIA_RE" | grep -vE '^[0-9]{7}ZZ|^28[0-9]{3}A99[0-9]|^28[0-9]{3}A[0-9]{3}99999' || true
}

tiene_referencia_real() {  # stdin: contenido. 0 si contiene una referencia catastral real.
  referencias_reales | grep -q .
}

refs_historial() {  # refs_historial <repo>: referencias reales en cualquier blob o mensaje del historial
  local repo="$1"
  {
    git -C "$repo" rev-list --objects --all | while read -r id ruta; do
      [ -n "$ruta" ] || continue
      [ "$(git -C "$repo" cat-file -t "$id")" = blob ] || continue
      git -C "$repo" cat-file -p "$id" | referencias_reales
    done
    git -C "$repo" log --all --format=%B | referencias_reales
  } | sort -u
}

blobs_en_rutas() {  # blobs_en_rutas <repo> <commit>: blobs de main o de un commit en las rutas purgables
  git -C "$1" ls-tree -r "$2" | awk -v re="$RUTAS_RE" '$4 ~ re {print $3}'
}

blobs_reales() {  # todos los blobs que estuvieron en las rutas purgables, menos los de main
  local repo="$1"
  comm -23 \
    <(git -C "$repo" rev-list --all | while read -r c; do blobs_en_rutas "$repo" "$c"; done | sort -u) \
    <(blobs_en_rutas "$repo" main | sort -u)
}

verificar() {  # verificar <repo> <fichero-de-blobs>: 0 si no queda rastro
  local repo="$1" ids="$2" fallos=0 id sueltos
  git -C "$repo" reflog expire --expire=now --all
  git -C "$repo" gc -q --prune=now
  while read -r id; do
    if git -C "$repo" cat-file -e "$id" 2>/dev/null; then echo "RASTRO: blob real $id sigue en $repo"; fallos=$((fallos + 1)); fi
  done <"$ids"
  # Comprobación independiente: ninguna referencia real en ningún fichero ni mensaje del historial.
  local quedan
  quedan=$(refs_historial "$repo")
  if [ -n "$quedan" ]; then
    echo "RASTRO: referencias catastrales reales en el historial: $(tr '\n' ' ' <<<"$quedan")"; fallos=$((fallos + 1))
  fi
  sueltos=$(git -C "$repo" fsck --unreachable --no-reflogs --no-progress 2>/dev/null | wc -l | tr -d ' ')
  [ "$sueltos" = "0" ] || { echo "RASTRO: $sueltos objetos inalcanzables tras gc"; fallos=$((fallos + 1)); }
  [ "$fallos" = "0" ] && echo "OK: sin rastro de las $(wc -l <"$ids" | tr -d ' ') versiones reales ni referencias catastrales reales en el historial."
  return "$fallos"
}

visibilidad() { gh repo view "$OWNER/$1" --json visibility --jq .visibility 2>/dev/null || echo NO_EXISTE; }

numero_mas_alto() {  # del repo dado, contando issues y PRs
  gh api graphql -f query='
    query($o: String!, $r: String!) {
      repository(owner: $o, name: $r) {
        issues(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) { nodes { number } }
        pullRequests(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) { nodes { number } }
      }
    }' -f o="$OWNER" -f r="$1" \
    --jq '[.data.repository.issues.nodes[0].number // 0, .data.repository.pullRequests.nodes[0].number // 0] | max'
}

case "$FASE" in

preparar)
  paso "Precondiciones"
  [ "$(visibilidad "$VIEJO")" = "PRIVATE" ] || parar "$OWNER/$VIEJO no es privado o no existe."
  [ "$(gh issue view 45 -R "$OWNER/$VIEJO" --json state --jq .state)" = "CLOSED" ] || parar "#45 (fixtures sintéticas) no está cerrada."
  if [ -z "$ENSAYO" ]; then
    abiertas=$(gh pr list -R "$OWNER/$VIEJO" --state open --json number --jq '[.[].number] | join(" ")')
    [ -z "$abiertas" ] || parar "Hay PRs abiertas: $abiertas. Ciérralas o espera a que se fusionen."
    curso=$(gh run list -R "$OWNER/$VIEJO" --status in_progress --json databaseId --jq length)
    [ "$curso" = "0" ] || parar "Hay $curso workflows en marcha en $OWNER/$VIEJO."
  fi
  git -C "$RAIZ" fetch -q origin main
  en_main=$(git -C "$RAIZ" ls-tree -r origin/main | awk '$2 == "blob" {print $3}' | while read -r id; do
              git -C "$RAIZ" cat-file -p "$id" | referencias_reales; done | sort -u)
  if [ -n "$en_main" ]; then
    aviso="main aún contiene referencias catastrales reales: $(tr '\n' ' ' <<<"$en_main")"
    if [ -n "$ENSAYO" ]; then echo "AVISO (ensayo): $aviso"; else parar "$aviso"; fi
  fi
  command -v git-filter-repo >/dev/null || parar "Falta git-filter-repo (uv tool install git-filter-repo)."
  [ ! -e "$TRABAJO/backup.git" ] || parar "$TRABAJO/backup.git ya existe: usa una carpeta de trabajo nueva."

  paso "Copia de seguridad completa (mirror)"
  git clone -q --mirror "git@github.com:$OWNER/$VIEJO.git" "$TRABAJO/backup.git"

  paso "Purga sobre un clon desechable"
  git clone -q --no-local "$TRABAJO/backup.git" "$TRABAJO/purga"
  git -C "$TRABAJO/purga" checkout -q main
  blobs_reales "$TRABAJO/purga" >"$TRABAJO/blobs_reales.txt"
  echo "$(wc -l <"$TRABAJO/blobs_reales.txt" | tr -d ' ') versiones a quitar del historial; las de main (sintéticas) se conservan."
  refs_historial "$TRABAJO/purga" | awk '{print length, $0}' | sort -rn | cut -d' ' -f2- \
    | sed 's/$/==>REFCAT-RETIRADA/' >"$TRABAJO/reemplazos.txt"  # las largas (20) antes que las cortas (14)
  echo "$(wc -l <"$TRABAJO/reemplazos.txt" | tr -d ' ') referencias reales a sustituir en ficheros y mensajes del historial."
  git -C "$TRABAJO/purga" filter-repo --force --strip-blobs-with-ids "$TRABAJO/blobs_reales.txt" \
    --replace-text "$TRABAJO/reemplazos.txt" --replace-message "$TRABAJO/reemplazos.txt"
  verificar "$TRABAJO/purga" "$TRABAJO/blobs_reales.txt"

  paso "El árbol purgado sigue en verde"
  # Los criterios de integración (PostGIS) los cubre CI en el repo nuevo.
  (cd "$TRABAJO/purga" && git checkout -q main && uv sync -q --frozen --extra dev \
     && uv run ruff check . && uv run mypy && uv run lint-imports \
     && uv run pytest -q && uv run pytest -q -m "acceptance and not integration" \
     && uv run python -m tests.fixtures.generate_catastro --check \
     && { [ ! -f tests/fixtures/generate_caminos.py ] || uv run python -m tests.fixtures.generate_caminos --check; })

  paso "Foto de las issues (padre y Priority) para restaurar después"
  gh api graphql --paginate -f query='
    query($endCursor: String) {
      repository(owner: "'"$OWNER"'", name: "'"$VIEJO"'") {
        issues(first: 100, after: $endCursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            number
            parent { number }
            projectItems(first: 5) {
              nodes { project { number } prioridad: fieldValueByName(name: "Priority") { ... on ProjectV2ItemFieldSingleSelectValue { name } } }
            }
          }
        }
      }
    }' --jq '.data.repository.issues.nodes[]
             | {number, parent: .parent.number,
                priority: ([.projectItems.nodes[] | select(.project.number == '"$PROYECTO"') | .prioridad.name] | map(select(. != null)) | first)}' \
    | jq -s 'sort_by(.number)' >"$TRABAJO/foto_issues.json"
  echo "$(jq length "$TRABAJO/foto_issues.json") issues en la foto; número más alto (issues y PRs): $(numero_mas_alto "$VIEJO")."
  numero_mas_alto "$VIEJO" >"$TRABAJO/numero_mas_alto"
  echo "Listo. Siguiente fase: archivar."
  ;;

archivar)
  [ -s "$TRABAJO/foto_issues.json" ] || parar "Falta la fase preparar."
  [ "$(visibilidad "$VIEJO")" = "PRIVATE" ] || parar "$OWNER/$VIEJO no es privado o no existe."
  paso "Actions desactivado en el repo actual (para agentes y crons)"
  hacer gh api -X PUT "repos/$OWNER/$VIEJO/actions/permissions" -F enabled=false
  paso "Renombrar $VIEJO → $ARCHIVO (sigue privado, con sus PRs)"
  hacer gh api -X PATCH "repos/$OWNER/$VIEJO" -f name="$ARCHIVO" --jq .full_name
  ;;

crear)
  [ "$(visibilidad "$ARCHIVO")" = "PRIVATE" ] || parar "Falta la fase archivar."
  [ "$(visibilidad "$NUEVO")" = "NO_EXISTE" ] || parar "$OWNER/$NUEVO ya existe."
  paso "Crear $OWNER/$NUEVO privado y vacío"
  hacer gh repo create "$OWNER/$NUEVO" --private --disable-wiki \
    --description "Mapa abierto de caminos públicos y vías pecuarias con indicios de cortes"
  hacer gh api -X PUT "repos/$OWNER/$NUEVO/actions/permissions" -F enabled=false
  hacer gh api -X PATCH "repos/$OWNER/$NUEVO" -F has_projects=true -F allow_squash_merge=true \
    -F allow_merge_commit=true -F allow_rebase_merge=true -F delete_branch_on_merge=true --silent
  paso "Subir main purgado"
  hacer git -C "$TRABAJO/purga" push "git@github.com:$OWNER/$NUEVO.git" main:main
  paso "Copiar etiquetas"
  hacer gh label clone "$OWNER/$ARCHIVO" -R "$OWNER/$NUEVO" --force
  ;;

numerar)
  maximo=$(cat "$TRABAJO/numero_mas_alto")
  hecho="$TRABAJO/numerado_hasta"
  desde=$(( $(cat "$hecho" 2>/dev/null || echo 0) + 1 ))
  paso "Numerar del #$desde al #$maximo"
  for n in $(seq "$desde" "$maximo"); do
    tipo=$(gh api graphql -f query='
      query($o: String!, $r: String!, $n: Int!) {
        repository(owner: $o, name: $r) { issueOrPullRequest(number: $n) { __typename } }
      }' -f o="$OWNER" -f r="$ARCHIVO" -F n="$n" --jq '.data.repository.issueOrPullRequest.__typename // "Nada"' 2>/dev/null) \
      || tipo=Nada  # número inexistente: gh sale con error
    if [ "$tipo" = "Issue" ]; then
      if [ -n "$SIMULAR" ]; then echo "[simular] #$n: transferir issue"; continue; fi
      url=$(gh issue transfer "$n" "$OWNER/$NUEVO" -R "$OWNER/$ARCHIVO")
      nuevo=${url##*/}
      [ "$nuevo" = "$n" ] || parar "#$n se transfirió como #$nuevo ($url). Para y revisa antes de seguir."
      echo "#$n: issue transferida."
    else
      if [ -n "$SIMULAR" ]; then echo "[simular] #$n: $tipo → reserva y borrado"; continue; fi
      url=$(gh issue create -R "$OWNER/$NUEVO" --title "Número reservado" \
              --body "Reserva el número de la PR #$n, que se conserva en el repo archivado.")
      nuevo=${url##*/}
      [ "$nuevo" = "$n" ] || parar "La reserva de #$n salió como #$nuevo ($url). Para y revisa antes de seguir."
      gh issue delete "$n" -R "$OWNER/$NUEVO" --yes >/dev/null
      echo "#$n: era $tipo, número reservado."
    fi
    echo "$n" >"$hecho"
    sleep 1  # sin ráfagas: GitHub limita la creación de contenido
  done
  ;;

restaurar)
  paso "Enlazar el proyecto al repo nuevo"
  pid=$(gh api graphql -f query='query($o: String!, $n: Int!) { user(login: $o) { projectV2(number: $n) { id } } }' \
          -f o="$OWNER" -F n="$PROYECTO" --jq .data.user.projectV2.id)
  rid=$(gh repo view "$OWNER/$NUEVO" --json id --jq .id)
  hacer gh api graphql -f query='mutation($p: ID!, $r: ID!) { linkProjectV2ToRepository(input: {projectId: $p, repositoryId: $r}) { clientMutationId } }' \
    -f p="$pid" -f r="$rid" --silent
  paso "Sub-issues: recomponer las que falten"
  jq -r '.[] | select(.parent != null) | "\(.number) \(.parent)"' "$TRABAJO/foto_issues.json" | while read -r hija madre; do
    actual=$(gh api graphql -f query='query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { issue(number: $n) { parent { number } } } }' \
               -f o="$OWNER" -f r="$NUEVO" -F n="$hija" --jq '.data.repository.issue.parent.number // empty')
    [ "$actual" = "$madre" ] && continue
    echo "#$hija → madre #$madre (ahora: ${actual:-ninguna})"
    ids=$(gh api graphql -f query='query($o: String!, $r: String!, $a: Int!, $b: Int!) { repository(owner: $o, name: $r) { a: issue(number: $a) { id } b: issue(number: $b) { id } } }' \
            -f o="$OWNER" -f r="$NUEVO" -F a="$madre" -F b="$hija" --jq '.data.repository | "\(.a.id) \(.b.id)"')
    hacer gh api graphql -f query='mutation($m: ID!, $h: ID!) { addSubIssue(input: {issueId: $m, subIssueId: $h}) { clientMutationId } }' \
      -f m="${ids% *}" -f h="${ids#* }" --silent
  done
  paso "Tablero: Status, Size, assignee y fechas de todas las issues"
  if [ -z "$SIMULAR" ]; then
    export TABLERO_CACHE="$TRABAJO/cache_tablero" SIN_PADRES=1
    mkdir -p "$TABLERO_CACHE"
    for n in $(gh issue list -R "$OWNER/$NUEVO" --state all --limit 500 --json number --jq '.[].number'); do
      GH_TOKEN=$(gh auth token) OWNER="$OWNER" PROJECT_NUMBER="$PROYECTO" REPO="$OWNER/$NUEVO" ISSUE="$n" \
        "$RAIZ/.github/scripts/sincronizar_tablero.sh"
    done
  else
    echo "[simular] sincronizar_tablero.sh para cada issue de $OWNER/$NUEVO"
  fi
  paso "Priority"
  campo=$(gh api graphql -f query='query($o: String!, $n: Int!) { user(login: $o) { projectV2(number: $n) { field(name: "Priority") { ... on ProjectV2SingleSelectField { id options { id name } } } } } }' \
            -f o="$OWNER" -F n="$PROYECTO" --jq .data.user.projectV2.field)
  jq -r '.[] | select(.priority != null) | "\(.number) \(.priority)"' "$TRABAJO/foto_issues.json" | while read -r n prio; do
    opcion=$(jq -r --arg p "$prio" '.options[] | select(.name == $p) | .id' <<<"$campo")
    item=$(gh api graphql -f query='mutation($p: ID!, $c: ID!) { addProjectV2ItemById(input: {projectId: $p, contentId: $c}) { item { id } } }' \
             -f p="$pid" -f c="$(gh issue view "$n" -R "$OWNER/$NUEVO" --json id --jq .id)" --jq .data.addProjectV2ItemById.item.id)
    hacer gh api graphql -f query='mutation($p: ID!, $i: ID!, $f: ID!, $o: String!) { updateProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f, value: {singleSelectOptionId: $o}}) { clientMutationId } }' \
      -f p="$pid" -f i="$item" -f f="$(jq -r .id <<<"$campo")" -f o="$opcion" --silent
    echo "#$n → $prio"
  done
  ;;

activar)
  secretos=$(gh secret list -R "$OWNER/$NUEVO" --json name --jq '[.[].name] | sort | join(" ")')
  [ "$secretos" = "CLAUDE_CODE_OAUTH_TOKEN PROJECT_TOKEN" ] || parar "Faltan secrets en $OWNER/$NUEVO (hay: '${secretos}')."
  paso "Activar Actions con permisos por defecto de solo lectura"
  hacer gh api -X PUT "repos/$OWNER/$NUEVO/actions/permissions" -F enabled=true -f allowed_actions=all
  hacer gh api -X PUT "repos/$OWNER/$NUEVO/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
  echo "Comprueba que la App de Claude tiene acceso a $OWNER/$NUEVO antes de lanzar ningún agente."
  ;;

publicar)
  paso "Verificar la purga sobre un clon recién bajado del repo nuevo"
  rm -rf "$TRABAJO/verificacion"
  git clone -q "git@github.com:$OWNER/$NUEVO.git" "$TRABAJO/verificacion"
  verificar "$TRABAJO/verificacion" "$TRABAJO/blobs_reales.txt"
  [ "$(gh api "repos/$OWNER/$NUEVO/forks" --jq length)" = "0" ] || parar "El repo nuevo tiene forks."
  paso "Hacer público"
  hacer gh repo edit "$OWNER/$NUEVO" --visibility public --accept-visibility-change-consequences
  paso "GitHub Pages desde Actions"
  hacer gh api -X POST "repos/$OWNER/$NUEVO/pages" -f build_type=workflow --silent
  paso "Proteger main: sin push forzado ni borrado"
  if [ -z "$SIMULAR" ]; then
    jq -n '{name: "main protegida", target: "branch", enforcement: "active",
            conditions: {ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}},
            rules: [{type: "non_fast_forward"}, {type: "deletion"}]}' \
      | gh api -X POST "repos/$OWNER/$NUEVO/rulesets" --input - --jq '"Ruleset \(.id): \(.name)"'
  else
    echo "[simular] ruleset non_fast_forward + deletion sobre main"
  fi
  hacer gh workflow run desplegar.yml -R "$OWNER/$NUEVO" --ref main
  echo "Hecho. Re-apunta tu clon local (docs/runbook-publicacion.md, sección 'Clon local')."
  ;;

*) parar "Fase desconocida: $FASE" ;;
esac
