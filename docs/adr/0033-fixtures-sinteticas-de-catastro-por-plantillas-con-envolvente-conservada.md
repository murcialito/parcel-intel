# ADR 0033 — Fixtures sintéticas de Catastro por plantillas, con envolvente conservada

- Estado: aceptado
- Fecha: 2026-11-26
- Historia: #45 (feature #38, épica #2)

El diseño de la historia lo proponía como "ADR 0024 (previsiblemente)"; el siguiente número
libre al implementarla era el 0033.

## Contexto

Para hacer público el repo (#39) hay que sacar del árbol y del historial las respuestas crudas de
Catastro de `tests/fixtures/catastro/`. La licencia INSPIRE de Catastro (v1.0, 2016) prohíbe difundir
la información original sin transformarla y presentar lo derivado como cartografía catastral
(REGISTRY, historia 0021). El fundador descartó un repo privado de fixtures y las fixtures recortadas,
y eligió fixtures sintéticas del mismo formato, generadas por un script versionado (#2).

Las fixtures de Catastro no se usan solo en los tests de su adapter. Los tests de IDEM, DPH, vías
pecuarias, Red Natura, inundación, PNOA y Sentinel-2 parsean una parcela de Catastro y la cruzan con
respuestas reales de esas fuentes, grabadas para el bbox de esa parcela. Sentinel-2 incluso resuelve
lecturas por rango con claves exactas derivadas del bbox. Además, dos tests de dominio usan la
distancia entre la parcela de Villaconejos y un cauce real como oráculo exacto (ADR 0017).

## Decisión

1. Las fixtures se generan con plantillas por tipo de respuesta (CPMRC, WFS CP, WFS BU, GetCapabilities)
   en `tests/fixtures/generate_catastro.py`. Solo stdlib, sin `parcel_intel`, sin aleatoriedad, sin
   reloj y sin red. No se transforma la respuesta real, que no estará tras la purga.
2. Las plantillas copian la estructura del esquema real (namespaces, elementos, `srsName`
   EPSG:25830, codificación declarada), nunca sus datos. Omiten los enlaces a la sede y los comentarios
   de origen de la D.G. del Catastro, y llevan un comentario `FIXTURE SINTÉTICA` (constante
   `HEADER_COMMENT` del generador) justo tras la declaración XML.
3. Las referencias usan la provincia `99` y, en urbanas, la hoja `ZZ`, que no existen. Así ninguna
   puede coincidir con una parcela real.
4. De lo real solo se conservan las envolventes de las tres parcelas que otros tests cruzan con
   respuestas reales de otras fuentes. Dentro de cada envolvente, la geometría es un rombo con vértices
   en los puntos medios de los lados: conserva la envolvente exacta y da distancias no triviales.
5. Un test compara las huellas SHA-256 de las referencias y de los anillos (`posList` normalizado a 2
   decimales) de las fixtures generadas con las de los originales, calculadas una vez antes de borrarlos
   (`tests/fixtures/catastro_fingerprints.py`) y versionadas en
   `tests/fixtures/catastro_huellas_reales.json` (725 referencias y 703 anillos).
6. Otro test exige que los ficheros de `tests/fixtures/catastro/` sean exactamente los que produce el
   generador, byte a byte (además de un `README.md`).
7. Los tests que deben demostrar que no usan la red lo hacen dentro de `tests/network_guard.no_network()`,
   que sustituye `socket.getaddrinfo`, `socket.create_connection` y `socket.socket.connect(_ex)` por una
   función que lanza `NetworkBlockedError`. La historia #46 lo reutiliza.

### Notas de implementación

- `catastro_fingerprints` admite `--salida <fichero>` además de la salida estándar, y el generador
  admite `--destino <dir>`: el entorno de los agentes no permite redirecciones de shell, y el test de
  determinismo genera dos veces en directorios temporales.
- Oráculo de distancia al Barranco del Montero: `shapely` da `3.6847247041562987` m (estimación a mano
  del arquitecto: ≈ 3,686 m). La función de dominio da `3.684724704111723` m: difieren en ~4·10⁻¹¹ m
  por el orden de las operaciones en coma flotante. Los tests comparan con `pytest.approx(abs=1e-9)`
  contra el literal de `shapely` en vez de con `==`, que exigiría tomar el valor de la propia función
  bajo test (lección de la historia 0017).
- El test de aceptación CA2 de la historia #35 fijaba los centroides CPMRC reales. Ahora fija los
  centros de las envolventes conservadas (a pocos metros); su docstring, que copia el criterio, no se
  toca.

## Consecuencias

- Los tests de otras fuentes no cambian sus bbox ni sus fixtures. Los oráculos geométricos que
  dependían de la forma real (distancia al Barranco del Montero) se recalculan con `shapely` como
  control independiente.
- Las tres envolventes conservadas (12 números) derivan de geometría real. Se consideran
  transformación suficiente: no permiten reconstruir la parcela ni son la información original.
- Las huellas SHA-256 de referencias son fuerza-bruteables (espacio pequeño por municipio). Se acepta:
  una referencia catastral es un identificador público, no un dato de titularidad, y el objetivo es no
  redistribuir respuestas, no ocultar identificadores.
- Los tests ya no verifican el parser contra respuestas reales capturadas. La verificación real queda
  en REGISTRY con fecha (2026-10-15) y debe repetirse contra el servicio, con una petición real no
  versionada, si el adapter de Catastro cambia de parsing.
- Hay que regenerar las fixtures al cambiar una plantilla (`python -m tests.fixtures.generate_catastro`).
  `--check` y el test de CA1 detectan la deriva.
- La historia #46 reutiliza el generador para `tests/fixtures/caminos/catastro_*` y añade la
  plantilla DNPPP; los polígonos 991 y 992 del municipio 28043 quedan reservados para ella.
- Los literales de referencias reales en código que no lee fixtures, en REGISTRY y en los ADR
  quedaron fuera de #45; se resolvieron en #46, que los sustituyó por referencias sintéticas de
  provincia 99 (la misma real da siempre la misma sintética) y amplió el test de huellas.

## Alternativas descartadas

- Transformar las respuestas reales (desplazar y simplificar): exige tener los originales para
  regenerar, y desplazar rompe la coherencia con las fixtures reales de otras fuentes.
- Parcela objetivo = rectángulo envolvente: da distancia 0 al cauce de Villaconejos, que corta la
  franja inferior de la envolvente. Es un oráculo trivial (lección de la historia 0017).
- Reconstruir los tests de otras fuentes con geometrías a mano, sin Catastro: posible, pero multiplica
  el diff y pierde el recorrido completo parser de Catastro → adapter de otra fuente.

## Anexo (historia #46): fixtures de caminos de Catastro

### Contexto
`tests/fixtures/caminos/catastro_*` (una WFS de parcelas de 600×600 m con 51 parcelas y cinco `Consulta_DNPPP`) eran respuestas crudas de Catastro grabadas en la historia 0021. Ningún test las consumía aún; #37 y #28 iban a fijar sobre ellas oráculos con referencias y superficies reales.

### Decisión
- Se sustituyen por seis fixtures sintéticas generadas por plantilla con el mismo generador (módulo `tests/fixtures/generate_caminos.py`, función `generate(out_dir)`), sin leer las originales: un teselado de 20 rectángulos de 600×600 m con origen (469000, 4439000) en EPSG:25830, municipio 28043, polígonos 991 y 992, cuatro parcelas ≥9000 de clase `VT` y una de control `C-`.
- Los polígonos 991 y 992 de 28043 quedan reservados para estas fixtures; ningún otro generador los usa.
- Se conservan las propiedades del dato real que importan a los consumidores: numeración ≥9000 de los caminos, clase `VT` solo en DNPPP, `areaValue` del WFS distinto de `ssp` de DNPPP en dos caminos, un anillo exterior por parcela en sentido horario, codificación ISO-8859-1 de la WFS.
- Los nombres de fichero llevan `sintetica` y no codifican polígonos ni parcelas reales.
- Las huellas (hash) de las 51 referencias y de todos los vértices originales se añaden a `tests/fixtures/catastro_huellas_reales.json` (clave nueva `vertices`); un test recorre `tests/`, `docs/` y `src/` buscándolas.
- El punto de entrada de #45 (`python -m tests.fixtures.generate_catastro`) genera también `caminos/` cuando se usa el directorio por defecto; con `--destino` solo escribe `catastro/`.

### Consecuencias
- Los oráculos de #37 y #28 se expresan sobre las referencias sintéticas (20 parcelas, 4 caminos `28043A99109101`, `…09102`, `28043A99209201`, `…09202`).
- Los casos con `gml:interior`, multiparte o clase `HG` se añaden como filas nuevas del generador, no como respuestas grabadas.
- `REGISTRY.md` conserva las conclusiones de la verificación real (fecha 2026-11-25) sin citar referencias reales.
