// Configuración del visor (historia #85, ADR 0037). Solo datos: sin imports, sin DOM, sin Leaflet.
//
// Los textos de atribución se copian LITERALMENTE de `NOTICE` (fuente única). Un test
// (tests/acceptance/test_historia_85.py, CA4) los compara con `NOTICE`: si uno cambia sin el
// otro, CI falla. No se generan para no necesitar un paso de compilación ni un `.json` más.

export const CONFIG = Object.freeze({
  // Índice de municipios publicado por `publicar-capas` (#84). Rutas relativas al sitio.
  indice: "datos/indice.json",
  datos: "datos/",

  // Fondos del mapa (historia #185, ADR 0051). WMTS del IGN, solo KVP. Cada fondo lleva sus
  // atribuciones, visibles mientras está activo (NOTICE). «mapa» para ver España y la
  // cobertura; «ortofoto» para leer el terreno en un municipio.
  fondos: Object.freeze([
    Object.freeze({
      id: "mapa",
      titulo: "Mapa",
      // Verificado 2026-11-27, REGISTRY.md «WMTS IGN-Base gris».
      url: "https://www.ign.es/wmts/ign-base?service=WMTS&request=GetTile&version=1.0.0&layer=IGNBase-gris&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}",
      minZoom: 5,
      maxZoom: 19,
      atribuciones: Object.freeze(["IGNBase-gris CC BY 4.0 scne.es"]),
    }),
    Object.freeze({
      id: "ortofoto",
      titulo: "Ortofoto",
      // Verificado 2026-11-26, REGISTRY.md «PNOA», WMTS visor #85.
      url: "https://www.ign.es/wmts/pnoa-ma?service=WMTS&request=GetTile&version=1.0.0&layer=OI.OrthoimageCoverage&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}",
      minZoom: 5,
      maxZoom: 19,
      // Rótulos y carreteras del IGN sobre la ortofoto, para no perder la orientación al entrar
      // en un municipio (PNG transparente; verificado 2026-11-27, REGISTRY.md «IGN-Base»).
      rotulos:
        "https://www.ign.es/wmts/ign-base?service=WMTS&request=GetTile&version=1.0.0&layer=IGNBaseOrto&style=default&tilematrixset=GoogleMapsCompatible&format=image/png&tilematrix={z}&tilerow={y}&tilecol={x}",
      atribuciones: Object.freeze([
        "PNOA 2023 CC-BY 4.0 scne.es",
        "MosaicoSentinel2 2018-2026 CC-BY 4.0 ign.es",
        "IGNBaseOrto CC BY 4.0 scne.es",
      ]),
    }),
  ]),
  // Fondo de la vista de España; al entrar en un municipio se pasa a `fondoMunicipio` salvo que
  // la persona haya elegido uno (decisión del fundador, 2026-11-27).
  fondoInicial: "mapa",
  fondoMunicipio: "ortofoto",

  // Vista de España (peninsular y Baleares) como [oeste, sur, este, norte], lon/lat.
  espana: Object.freeze([-9.6, 35.9, 4.4, 43.9]),

  // Cobertura (historia #185): contornos de los municipios con datos, de `publicar-cobertura`.
  cobertura: Object.freeze({
    ruta: "datos/cobertura.geojson",
    atribucion: "CC BY 4.0 ign.es",
    // Por debajo de este zoom se ve la etiqueta del primer hito en lugar de los contornos.
    zoomEtiqueta: 9,
  }),

  capas: Object.freeze([
    Object.freeze({
      id: "vias_pecuarias",
      titulo: "Vías pecuarias (Comunidad de Madrid)",
      nombre: "Vía pecuaria",
      fuente: "Red de Vías Pecuarias, IDEM, Comunidad de Madrid",
      atribucion: "CC BY 4.0 Comunidad de Madrid",
      propiedadNombre: "nombre",
      tipo: "poligono",
      // Los colores y trazos viven en estilos-capas.js (#165); aquí solo se nombra la clave.
      estilo: Object.freeze({ clave: "viasPecuarias" }),
      orden: 10,
    }),
    Object.freeze({
      id: "camino_actual",
      titulo: "Camino actual (red de transporte del IGN, sin asfaltar)",
      nombre: "Camino actual",
      fuente: "Red de transporte, IGN",
      atribucion: "Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional",
      propiedadNombre: null,
      tipo: "linea",
      estilo: Object.freeze({ clave: "caminoActual" }),
      orden: 30,
    }),
    // Historia #95: indicios de discrepancia publicados por #94 (ADR 0044). Nace apagada: un
    // indicio no debe ser lo primero que se lea del mapa. Su trazo punteado la distingue
    // de una vía pecuaria y del camino actual.
    Object.freeze({
      id: "discrepancias",
      titulo: "Indicios a verificar (no son un dictamen)",
      nombre: "Indicio a verificar",
      fuente: "Parcel Intel, indicios de discrepancia entre trazados",
      atribucion: "Indicios elaborados por Paso Común a partir de las fuentes que cita cada ficha",
      propiedadNombre: null,
      tipo: "indicio",
      visibleInicial: false,
      // Confianza ausente o desconocida: el nivel menos enfático, no se oculta el indicio.
      estilo: Object.freeze({
        porPropiedad: "confianza",
        claves: Object.freeze({
          baja: "indicioBaja",
          media: "indicioMedia",
          alta: "indicioAlta",
        }),
        defecto: "indicioBaja",
      }),
      orden: 40,
    }),
    // Historia #171: tramos a verificar aprobados a mano y publicados por #170 (ADR 0048). Nace
    // apagada, como los indicios; su ficha es la de los indicios (misma forma, ADR 0044).
    Object.freeze({
      id: "candidatos",
      titulo: "Tramos a verificar (no son un dictamen)",
      nombre: "Tramo a verificar",
      fuente: "Paso Común, tramos a verificar revisados a mano",
      atribucion: "Tramos a verificar elaborados por Paso Común a partir de las fuentes que cita cada ficha",
      propiedadNombre: null,
      tipo: "candidato",
      visibleInicial: false,
      estilo: Object.freeze({ clave: "candidato" }),
      orden: 50,
    }),
  ]),

  textos: Object.freeze({
    sinIndicios: "sin indicios publicados",
    sinCandidatos: "sin tramos a verificar publicados",
    anioNoDeclarado: "año no declarado",
    // Historia #178: rótulos del visor para las imágenes de comparación. Los demás textos
    // (atribución, huecos, omitidas, «no disponible») vienen del fichero publicado.
    tituloComparacion: "Imágenes de comparación",
    mostrarTrazo: "Mostrar el trazo sobre las imágenes",
    imagenNoDisponible: "Imagen no disponible",
    fichaNoDisponible: "ficha no disponible",
    // Copia literal del aviso de #16 (ficha pública; también en cada feature y en el sidecar de
    // `datos/discrepancias/`). Un test lo compara con el fichero publicado.
    avisoIndicio:
      "Esto no es un dictamen ni afirma que haya ninguna irregularidad. Es un indicio automático, con la confianza indicada, que debe contrastarse con la administración competente.",
    sinTrazados: "sin trazados de esta capa en el municipio",
    errorCapa: "no se pudo cargar",
    cargando: "cargando…",
    mapaBaseNoDisponible:
      "Mapa base no disponible ahora mismo: las capas se dibujan sobre fondo neutro.",
    errorIndice: "No se pudo cargar la lista de municipios. Prueba a recargar la página.",
    // Historia #185: rediseño (buscador, cobertura, ficha en panel).
    sinMunicipio: "elige un municipio",
    espana: "España",
    // «{n}» es el número de municipios con datos.
    resumenCobertura:
      "{n} municipios con datos; el resto de España, aún sin cobertura. Elige uno en el buscador o en el mapa.",
    etiquetaHito: "Primer hito · {n} municipios",
    sinCoincidencias: "Aún sin cobertura. Por ahora hay datos de {n} municipios del sureste de Madrid.",
    tramoNoPublicado: "Ese tramo ya no está publicado en este municipio.",
    enlaceCopiado: "Enlace copiado",
    errorCobertura: "No se pudo cargar el mapa de cobertura.",
    // Rótulos de la ficha.
    fuentes: "Fuentes",
    comoSeCalcula: "Cómo se ha calculado",
    comoSeMide: "Cómo se ha medido",
    abrirConsulta: "Abrir la consulta original",
    acercar: "Acercar",
    copiarEnlace: "Copiar enlace",
    cerrar: "Cerrar la ficha",
    fuente: "Fuente",
  }),
});
