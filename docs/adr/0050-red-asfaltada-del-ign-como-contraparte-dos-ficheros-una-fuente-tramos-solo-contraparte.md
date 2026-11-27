# ADR 0050 — Red asfaltada del IGN como contraparte: dos ficheros, una fuente, tramos solo contraparte

- Estado: aceptado
- Fecha: 2026-11-27
- Historias: #183 (sobre #27, #32, #84, #128)

## Contexto

La capa «camino actual» (#27, ADR 0034) solo pide a `roadlink` los tramos
`surfacecategory='unpaved'`. Una vía pecuaria o un camino histórico que hoy va
bajo una carretera asfaltada no encuentra contraparte en `ign_red_transporte`, y
`discrepancias` (ADR 0030) lo marca `AUSENTE_EN_FUENTE` o `SOLAPE`. En Colmenar
(2026-11-27), 3 de los 19 indicios publicados tienen entre un 57 % y un 82 % de su
zona a ≤ 15 m de un tramo asfaltado. El fundador decidió que un trazado bajo una
carretera asfaltada no es indicio: para saber si un trazado tiene equivalente hoy,
la red asfaltada del IGN cuenta igual que la sin asfaltar. La capa publicada
«camino actual» no cambia.

En el bbox de Colmenar, `roadlink` tiene 2.222 tramos `paved` y 1.774 `unpaved`,
que suman los 3.996 sin filtro: no hay un tercer valor. Lo mismo en los otros seis
términos del ámbito (REGISTRY.md, sección de #183). El filtro `paved` funciona en
el servidor igual que `unpaved` y pagina con `offset`.

## Decisión

1. `ign_red_transporte` sigue siendo una sola fuente lógica, con dos ficheros
   derivados por municipio en el formato común: `data/derived/camino_actual/<ine>.geojson`
   (`unpaved`, sin cambios de contenido, el que se publica) y
   `data/derived/camino_asfaltado/<ine>.geojson` (`paved`, no se publica). Los dos
   declaran `superficie` en la colección y en cada feature.
2. `RoadSegmentPort.query_roads(geometry, margin_m, surface)` con
   `RoadSurface = Literal["unpaved", "paved"]`. `query_unpaved_roads` queda como
   caso particular y conserva los mismos parámetros de petición, así que la caché
   cruda existente sigue valiendo. El adapter filtra en el servidor y comprueba la
   superficie de nuevo en el cliente; el caso de uso, otra vez (un tramo de otra
   superficie es un fallo del municipio).
3. `camino-actual-municipios` hace las dos consultas y, por municipio, escribe los
   dos ficheros o ninguno (`--salida-asfaltado`, por defecto
   `data/derived/camino_asfaltado`).
4. `GeoJsonTrailLayerReader` admite un fichero complementario por fuente. Para
   `discrepancias`, `ign_red_transporte` = `camino_actual` ∪ `camino_asfaltado`.
   Si solo existe uno de los dos ficheros, es un error (`IncompleteTrailLayerError`,
   subclase de `TrailLayerFormatError`) que pide regenerar; sin ninguno de los dos,
   la fuente consta como ausente. Una `superficie` cruzada, un identificador en los
   dos ficheros o nombres de municipio distintos también son errores de formato que
   nombran el fichero. La capa unida lleva la procedencia, el nombre y el límite del
   principal. `publicar-capas` lee solo `camino_actual` (sin complemento).
5. `Trail.counterpart_only` (por defecto `False`): los tramos asfaltados entran
   con `True`. `detect_municipal_discrepancies` no los evalúa como sujeto. Sirven
   de equivalente a vías pecuarias, Catastro y trazados históricos, pero no generan
   discrepancias propias, porque si no cada carretera paralela a una vereda daría
   un `DESPLAZAMIENTO` nuevo.
6. No cambian `SourceKind`, `ABSENCE_PAIRS`, `kinds_kept`, `CRITERION`,
   `BASE_COUNTERPARTS` ni `CUT_METHOD`. Lo que cambia es el contenido de la capa de
   contraparte, no el criterio ni el método. Los candidatos a corte heredan la
   contraparte al partir del informe interno de discrepancias.

### Umbrales y decisiones de producto a revisar con el fundador

- No se sube `CUT_METHOD.version`. Así solo caducan las aprobaciones de los
  candidatos cuyo tramo cambia, no las 40.
- `procedencia_b` de una ausencia cita la consulta `unpaved` aunque la ausencia
  dependa también de la `paved`. Cada contraparte asfaltada de un `SOLAPE` o
  `DESPLAZAMIENTO` lleva su propia procedencia con la URL `paved`.
- Los tramos `paved` `fictitious` cuentan como contraparte igual que los no
  ficticios, el mismo criterio que ya se aplica a los `unpaved` (casi todos
  `fictitious="true"`).
- Una vía con un tramo asfaltado paralelo a entre 11,18 m (tolerancia vía–IGN) y
  33,54 m (radio de búsqueda) no da ningún registro: `compare_trail` ve un
  `DESPLAZAMIENTO`, que el par vía → IGN no conserva, y el inverso no se evalúa
  porque el asfaltado es solo contraparte. Con un tramo sin asfaltar a esa
  distancia sigue saliendo el `DESPLAZAMIENTO` IGN → vía, como hasta ahora.
- **Se mantiene a propósito** (decisión del fundador en #183, «opción 1», que
  reescribe CA8): un `DESPLAZAMIENTO` cuyo sujeto es un camino **sin asfaltar** no
  cambia aunque discurra junto a una carretera, porque la red asfaltada no entra en
  esa comparación (su contraparte es la vía). En Colmenar, `415956c18feed794`
  (64,5 % de su zona a ≤ 15 m de asfalto) sigue publicándose: es un camino sin
  asfaltar en paralelo a una carretera (a 13–25 m), no va bajo asfalto, y su vía
  tampoco (1,9 % cubierto a ≤ 11,18 m). No se añade ninguna regla para suprimirlo.

## Alternativas descartadas

- **Una sola capa con las dos superficies y filtro al publicar**: obliga a
  `publicar-capas` a filtrar y cambia la procedencia (URL sin filtro) de la capa
  publicada. Una capa pública correcta pasaría a depender de un filtro nuevo.
- **Fuente nueva `ign_red_asfaltada` en `SourceKind`**: `compare_trail` compara
  contra una sola fuente, así que la ausencia «ni asfaltado ni sin asfaltar» no se
  podría expresar sin cambiar el criterio y la matriz `ABSENCE_PAIRS`.
- **Una consulta sin filtro partida en dos en el cliente**: invalida la caché
  `unpaved` existente y cambia la URL de procedencia publicada.
- **Ampliar `TrailRole` con un tercer papel**: el papel se serializa como `papel`
  en el formato común y ya tiene semántica (anejo = sujeto de `DESPLAZAMIENTO`
  pero no de ausencia). «Solo contraparte» es otra idea.

## Consecuencias

- Los ficheros derivados anteriores a esta historia hacen fallar `discrepancias`
  con un mensaje que pide regenerar. La primera regeneración necesita red, porque la
  caché no tiene las consultas `paved`.
- Unas 45 peticiones más y unos 150 MB más de caché cruda por pasada completa del
  ámbito (Aranjuez: 14.035 tramos `paved`, 29 páginas). Sin coste recurrente.
- `LayerSummary.trail_count` de `ign_red_transporte` cuenta las dos superficies.
- Los candidatos con parte bajo asfalto cambian de tramo, de id y de huella, y su
  revisión caduca o queda huérfana (ADR 0047). Hay que volver a revisarlos a mano.
- El visor no cambia: la red asfaltada no se publica (fuera de alcance de #183).
- Ninguna dependencia ni proveedor nuevo. Licencia CC BY 4.0 (#24), sin cambios en `NOTICE`.
