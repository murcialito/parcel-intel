# ADR 0052 — Vuelos históricos de la Comunidad de Madrid en la serie de imágenes de comparación: franjas 1975 y 1991, política v2 y despacho por vuelo

- Estado: aceptada
- Fecha: 2026-11-28
- Historia: #208 (feature #194). Continúa el ADR 0042 (§3, §5) y el ADR 0049 (§1, §2, §4, §5, §8). Usa el adapter de #207 y la verificación de #206.
- Número: el diseño lo dejaba como «el siguiente libre»; al crearlo, el último era el 0051.

## Contexto

La serie de imágenes de comparación (ADR 0042 §3) solo tenía vuelos del WMS histórico del IGN y declaraba un hueco de 1957 a 1997. #206 verificó que la IDEM de la Comunidad de Madrid sirve, por WMS `GetMap` en EPSG:25830 a 0,5 m, ortofotos de 1956, 1975 y 1991 sobre los 7 municipios del ámbito, con licencia CC BY 4.0 y la atribución literal de su aviso legal. #207 dejó `IdemVuelosWindowAdapter` (`OrthophotoWindowPort`, PNG, blanco = sin cobertura). El fundador decidió dejar fuera `CM_1956` hasta confirmar la licencia del CECAF.

Faltaba decidir cómo entran 1975 y 1991 en la serie, cómo se elige servidor por vuelo y cómo se amplían la lista blanca de URL, la atribución, la procedencia y la ficha del visor, que daban por hecho un único servidor (el IGN).

## Decisión

1. **Dos franjas nuevas, un vuelo cada una.** `COMPARISON_SLOTS` pasa a siete franjas en orden cronológico: `1956-1957`, `1975` (`CM_1975`), `1991` (`CM_1991`), `1997-2003`, `2006-2011`, `2014-2020`, `reciente`. Los vuelos de Madrid no son alternativas de una franja del IGN: son años distintos. `CM_1956` queda fuera de `FLIGHTS` y de las franjas (el adapter lo sigue sabiendo pedir).
2. **`FLIGHTS` declara la fuente y el aviso de cada vuelo.** `FlightInfo` gana `source` (la `Provenance.source` del adapter: `pnoa-historico` o `idem-vuelos-historicos`) y `notice` (aviso obligatorio de la fuente o `None`). Para 1975 y 1991: periodo `"1975"`/`"1991"`, 0,5 m, atribución literal del aviso legal de la IDEM («Información geográfica de la Comunidad de Madrid. Acceso público y gratuito en CC BY 4.0 Comunidad de Madrid .»), que se publica precedida de «Obra derivada de», y aviso «Cartografía de carácter informativo, sin valor vinculante en procedimientos administrativos.».
3. **Política v2 y huecos.** `COMPARISON_POLICY = imagenes_comparacion v2`. Se declara todo intervalo de más de 10 años sin vuelo de la serie: de 1958 a 1974 y de 1976 a 1990. Un manifiesto v1 no se publica: hay que volver a ejecutar `imagenes-comparacion`.
4. **Despacho por vuelo en un adapter compuesto.** `adapters/comparison_windows/router.py`: `FlightRoutedWindowAdapter` (implementa `OrthophotoWindowPort`; `CM_*` a la IDEM y el resto al IGN) y `comparison_window_url(ventana, vuelo)`, la URL canónica en el servidor del vuelo. El caso de uso no cambia de port; el composition root (`build_comparison_use_case`) inyecta los dos adapters sobre un único `CachedRawFetcher`.
5. **Lista blanca de URL por servidor** (amplía ADR 0049 §2). El lector del manifiesto exige que la URL de cada imagen sea exactamente `comparison_window_url(ventana, vuelo)`. El dominio exige que la fuente de cada imagen sea la de su vuelo en `FLIGHTS` (amplía ADR 0049 §5), con licencia `CC BY 4.0`, publicable, y la atribución de `attribution_for`.
6. **Publicación** (amplía ADR 0049 §1 y §8). Una imagen cuyo vuelo tiene aviso lleva además `aviso_fuente` en la feature; las del IGN no cambian. En el `.procedencia.json`, una fuente por vuelo `(origen, servidor, periodo)` con `periodo` (1975 y 1991 comparten atribución), y el bloque `imagenes_comparacion` pasa de `servidor` a `servidores` (los de las imágenes publicadas). La nota de la colección dice que las imágenes las sirven el IGN y la Comunidad de Madrid y que el sitio no aloja ninguna.
7. **Visor.** La ficha muestra `aviso_fuente` como texto bajo la atribución de cada imagen que lo lleve.

### Umbrales y decisiones de producto a revisar con el fundador

No bloquean; cambiarlos solo toca este ADR, el dominio y sus tests.

- La regla «hueco = más de 10 años sin vuelo» y sus textos («De 1958 a 1974: la serie no tiene ninguna ortofoto de esos años sobre el ámbito.», etc.). 1992–1996 no se declara.
- El texto de la nota «Las imágenes de comparación las sirven el Instituto Geográfico Nacional y la Comunidad de Madrid al abrir la ficha; este sitio no aloja ninguna.», fijo aunque un municipio no tenga imágenes de Madrid.
- La redacción del aviso de la IDEM en la ficha (resumen del aviso legal, tal como está en `NOTICE`).
- PNG de la IDEM: hasta ~1,5 MB por imagen de 1024 px que carga el visitante (el IGN sirve JPEG). Pedir JPEG obligaría a cambiar la detección de blanco de #207.

### Alternativas descartadas

- **Meter 1975 y 1991 como alternativas de una franja «1957-1997»**: mostraría solo uno de los dos años y escondería el otro si el primero cubre.
- **Despachador en `cli/main.py`**: el lector del manifiesto (adapter) también necesita la tabla de enrutado para la URL canónica, y un adapter no puede importar `cli/`. Dos tablas divergirían.
- **Un port por servidor en el caso de uso**: el caso de uso tendría que saber qué vuelo es de qué proveedor; esa es una decisión de composición.
- **Atribución por vuelo inventada («… vuelo 1975»)**: la atribución exigida es la literal del aviso legal; el vuelo se distingue por el periodo.
- **Incluir `CM_1956` como respaldo de `1956-1957`**: descartado por el fundador hasta confirmar la licencia del CECAF.

## Consecuencias

- `imagenes-comparacion` hace dos peticiones más por ventana (sin alternativas), contra la IDEM, con la misma caché y pausa. Un fallo de la IDEM es un `fallo` de franja y el comando sale con 1 sin escribir, como con el IGN.
- Todo manifiesto v1 deja de publicarse; los tests de #121, #122, #168, #170, #172 y #178 se actualizan a la v2 sin relajarse.
- `NOTICE` y `REGISTRY.md` dicen que 1975 y 1991 ya se enlazan en las fichas y 1956 no.
- Sin dependencias nuevas, sin proveedor nuevo (IDEM ya registrada), sin coste recurrente y sin LLM.
- Riesgo residual: la IDEM cambia la capa, la URL o deja de responder. CA10 de #208 lo vigila en `red-externa`; el visor dice «Imagen no disponible».
- Riesgo residual: la reserva de licencia de 1956 sigue abierta; incluir `CM_1956` exige su propia historia, subir la política a v3 y revisar los huecos.
