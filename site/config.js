// Configuración del visor (historia #85, ADR 0037). Solo datos: sin imports, sin DOM, sin Leaflet.
//
// Los textos de atribución se copian LITERALMENTE de `NOTICE` (fuente única). Un test
// (tests/acceptance/test_historia_85.py, CA4) los compara con `NOTICE`: si uno cambia sin el
// otro, CI falla. No se generan para no necesitar un paso de compilación ni un `.json` más.

export const CONFIG = Object.freeze({
  // Índice de municipios publicado por `publicar-capas` (#84). Rutas relativas al sitio.
  indice: "datos/indice.json",
  datos: "datos/",

  teselas: Object.freeze({
    // WMTS del IGN, solo KVP (verificado 2026-11-26, REGISTRY.md «PNOA», WMTS visor #85).
    url: "https://www.ign.es/wmts/pnoa-ma?service=WMTS&request=GetTile&version=1.0.0&layer=OI.OrthoimageCoverage&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}",
    minZoom: 6,
    maxZoom: 19,
  }),

  // Vista antes de leer el índice: entorno de Colmenar de Oreja (lat, lon).
  vistaInicial: Object.freeze({ centro: Object.freeze([40.09, -3.45]), zoom: 11 }),

  // Atribuciones del mapa base: siempre visibles (tabla de productos del SCNE, NOTICE).
  atribucionesBase: Object.freeze([
    "PNOA 2023 CC-BY 4.0 scne.es",
    "MosaicoSentinel2 2018-2026 CC-BY 4.0 ign.es",
  ]),

  capas: Object.freeze([
    Object.freeze({
      id: "vias_pecuarias",
      titulo: "Vías pecuarias (Comunidad de Madrid)",
      fuente: "Red de Vías Pecuarias, IDEM, Comunidad de Madrid",
      atribucion: "CC BY 4.0 Comunidad de Madrid",
      propiedadNombre: "nombre",
      tipo: "poligono",
      estilo: Object.freeze({
        color: "#c2410c",
        weight: 2,
        opacity: 1,
        fillColor: "#fb923c",
        fillOpacity: 0.35,
      }),
    }),
    Object.freeze({
      id: "camino_actual",
      titulo: "Camino actual (red de transporte del IGN, sin asfaltar)",
      fuente: "Red de transporte, IGN",
      atribucion: "Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional",
      propiedadNombre: null,
      tipo: "linea",
      estilo: Object.freeze({ color: "#fde047", weight: 3, opacity: 0.95 }),
    }),
  ]),

  textos: Object.freeze({
    sinTrazados: "sin trazados de esta capa en el municipio",
    errorCapa: "no se pudo cargar",
    cargando: "cargando…",
    mapaBaseNoDisponible:
      "Mapa base no disponible ahora mismo: las capas se dibujan sobre fondo neutro.",
    errorIndice: "No se pudo cargar la lista de municipios. Prueba a recargar la página.",
  }),
});
