#!/usr/bin/env bash
# Crea las épicas iniciales del backlog (docs/vision.md, docs/proceso.md).
# Las que llevan estado:refinar arrancan al agente refinador, que las parte en features e historias
# y pregunta al fundador lo que no pueda decidir. Las demás quedan como ideas, sin estado.
# Ejecutar una sola vez, después de crear_etiquetas.sh.
# Uso: .github/scripts/sembrar_backlog.sh [owner/repo]
set -euo pipefail
REPO="${1:-murcialito/paso-comun}"

epica() {
  local titulo="$1" cuerpo="$2"; shift 2
  gh issue create -R "$REPO" --title "$titulo" --body "$cuerpo" --label "tipo:epica" "$@"
}

epica "Épica: repo público y despliegue en GitHub Pages" "$(cat <<'EOF'
Objetivo: que el repo pueda ser público (código abierto) y que `main` se despliegue solo en GitHub Pages (ADR 0022).

Bloqueo conocido: `tests/fixtures/catastro/` y `tests/fixtures/caminos/catastro_*` contienen respuestas crudas de Catastro. Su licencia INSPIRE (2016) prohíbe difundirlas por Internet sin transformarlas (ver `REGISTRY.md`). Hay que sacarlas del repo **y de su historial** sin romper los ~260 tests que las usan. Opciones a valorar: fixtures en un repo privado aparte, fixtures sintéticas con el mismo formato, o fixtures reducidas y transformadas.

También: elegir la licencia del código y de los datos derivados (decisión abierta en `docs/vision.md`).
EOF
)" --label "estado:refinar"

epica "Épica: conjunto de validación de caminos cerrados" "$(cat <<'EOF'
Objetivo: reunir y congelar, antes de ajustar ningún umbral, los casos de caminos cerrados o usurpados que asociaciones u otras fuentes ya han documentado públicamente en el ámbito (Colmenar de Oreja, Aranjuez, Chinchón, Belmonte de Tajo, Villaconejos, Villarejo de Salvanés, Valdelaguna) o, si no hay suficientes, en la Comunidad de Madrid.

Cada caso: fuente pública, tramo afectado y fecha aproximada del cierre. Sin datos de propietarios aunque la fuente los nombre. Lección de la historia 0021: leer siempre el documento primario antes de atribuir un caso a un municipio.
EOF
)" --label "estado:refinar"

epica "Épica: mapa de trazados que deberían ser públicos" "$(cat <<'EOF'
Objetivo: una capa por municipio del ámbito con los trazados que deberían ser públicos, cada uno con su fuente y fecha, y con las discrepancias entre fuentes visibles en vez de resueltas en silencio.

Fuentes verificadas (historia 0021, `REGISTRY.md`): vías pecuarias de IDEM (CC BY 4.0, informativa), Catastro (parcelas 9xxx de clase `VT`, solo uso interno y producto transformado), planimetrías del IGN de 1870-1880 (hay que georreferenciarlas), MTN50 de 1881 y red de transporte del IGN.

Pendientes que vienen de la 0021: cómo salen los arroyos (`HG`) en Catastro; órdenes de clasificación y deslindes de vías pecuarias por municipio; solicitudes de transparencia a los 7 ayuntamientos pidiendo sus inventarios de caminos (acción externa: la decide y presenta el fundador).
EOF
)" --label "estado:refinar"

epica "Épica: candidatos a corte" "$(cat <<'EOF'
Objetivo: señalar los tramos donde un trazado que debería ser público desaparece en la ortofoto actual (PNOA 2023, 25 cm) o queda dentro de una finca cerrada, con confianza, imágenes de comparación (histórica frente a actual) y la regla que lo señaló. Se mide contra el conjunto de validación.

El método de detección está abierto y necesita ADR: a 25 cm un vallado apenas se ve, así que probablemente haya que combinar señales.
EOF
)"

epica "Épica: visor web estático" "$(cat <<'EOF'
Objetivo: un mapa estático, sin servidor de aplicación, con los trazados, los candidatos y una ficha de evidencia por candidato, desplegado en GitHub Pages. Con la atribución de cada fuente visible y lenguaje de indicio.
EOF
)"

epica "Épica: avisos ciudadanos con foto" "$(cat <<'EOF'
Idea posterior al primer hito: que alguien sobre el terreno confirme o desmienta un candidato con una foto. Es la primera funcionalidad que almacena datos de terceros (fotos, EXIF, contacto) y que puede tener coste recurrente: necesita análisis de privacidad y ADR de coste antes de diseñarse.
EOF
)"

epica "Épica: dossier para el ayuntamiento" "$(cat <<'EOF'
Idea posterior al primer hito: un documento generado para un tramo concreto, listo para presentar, con trazado, fuentes, serie de imágenes, normativa aplicable y lenguaje de indicio.
EOF
)"
