// ÚNICO módulo del sitio que usa la librería de mapas (historia #85, ADR 0037; rediseño #185,
// ADR 0051).
//
// Leaflet 1.9.4 se carga antes como script clásico (`vendor/leaflet/leaflet.js`) y deja su
// global. Cambiar a MapLibre GL es reescribir este fichero con la misma interfaz:
//
//   crearMapa(contenedor, { fondos, fondoInicial, encuadreInicial, alFallarTesela, tema,
//                           alPulsarFondo, relleno, animar }) -> Mapa
//   Mapa.ponerFondo(id)                                  // uno de `fondos`
//   Mapa.anadirCapa(id, geojson, { clave | claveDe, orden, alPulsar })
//        // clave: una de CLAVES; claveDe(propiedades) -> clave; alPulsar(propiedades, idRasgo)
//   Mapa.seleccionar(capaId, idRasgo) -> boolean         // resalta un trazado; false si no está
//   Mapa.deseleccionar()
//   Mapa.encuadrarRasgo(capaId, idRasgo)
//   Mapa.ponerCobertura(geojson, { etiqueta, zoomEtiqueta, alPulsarMunicipio, alPulsarEtiqueta })
//   Mapa.resaltarMunicipio(ine | null)
//   Mapa.ponerTema("claro" | "oscuro")
//   Mapa.quitarCapa(id)
//   Mapa.mostrarCapa(id, visible)
//   Mapa.encuadrar([oeste, sur, este, norte])           // lon/lat EPSG:4326
//   Mapa.ponerAtribuciones(textos)                      // lista completa, en texto plano
//
// Sin popups: al pulsar un trazado se llama a `alPulsar` y la ficha la pinta la vista en su
// panel (historia #185).

import { CLAVES, COBERTURA, estiloTrazado } from "./estilos-capas.js";

const esPoligono = (feature) =>
  ["Polygon", "MultiPolygon"].includes(feature?.geometry?.type);

// El control de atribución de Leaflet inserta su contenido como HTML: se escapa cada texto
// para que llegue como texto plano.
export function escaparTexto(texto) {
  return String(texto)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Anillos exteriores de los polígonos de una colección (para los huecos del velo).
export function anillosExteriores(geojson) {
  const anillos = [];
  for (const feature of geojson?.features ?? []) {
    const g = feature?.geometry;
    if (g?.type === "Polygon" && Array.isArray(g.coordinates?.[0])) anillos.push(g.coordinates[0]);
    if (g?.type === "MultiPolygon") {
      for (const poligono of g.coordinates ?? []) {
        if (Array.isArray(poligono?.[0])) anillos.push(poligono[0]);
      }
    }
  }
  return anillos;
}

// Velo: el mundo (en Web Mercator) con un hueco por municipio cubierto.
export function veloCobertura(geojson) {
  const mundo = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "Polygon", coordinates: [mundo, ...anillosExteriores(geojson)] },
  };
}

export function crearMapa(contenedor, opciones) {
  const L = globalThis.L;
  if (!L) throw new Error("La librería de mapas no está cargada");
  const {
    fondos,
    fondoInicial,
    encuadreInicial,
    alFallarTesela,
    tema: temaInicial = "claro",
    alPulsarFondo,
    relleno = () => ({ arriba: 0, derecha: 0, abajo: 0, izquierda: 0 }),
    animar = true,
  } = opciones;

  const mapa = L.map(contenedor, {
    attributionControl: false,
    zoomControl: false,
    zoomAnimation: animar,
    fadeAnimation: animar,
    markerZoomAnimation: animar,
  });
  L.control?.zoom?.({ position: "bottomright" })?.addTo(mapa);
  const control = L.control.attribution({ prefix: false, position: "bottomright" });
  control.addTo(mapa);
  if (typeof alPulsarFondo === "function") mapa.on?.("click", () => alPulsarFondo());

  const opcionesEncuadre = () => {
    const r = relleno();
    return {
      paddingTopLeft: [r.izquierda + 16, r.arriba + 16],
      paddingBottomRight: [r.derecha + 16, r.abajo + 16],
      animate: animar,
    };
  };

  // --- fondos ---------------------------------------------------------------------------
  const teselas = new Map();
  let fondoActual = null;
  for (const fondo of fondos) {
    const capa = L.tileLayer(fondo.url, {
      minZoom: fondo.minZoom,
      maxZoom: fondo.maxZoom,
      tileSize: 256,
      crossOrigin: false,
      className: `pc-fondo pc-fondo--${fondo.id}`,
    });
    // Un fallo de tesela no toca las capas vectoriales: solo se avisa (CA10 de #85).
    capa.on("tileerror", () => {
      if (typeof alFallarTesela === "function") alFallarTesela();
    });
    teselas.set(fondo.id, capa);
  }

  function ponerFondo(id) {
    const nueva = teselas.get(id);
    if (!nueva) throw new Error(`Fondo desconocido: ${id}`);
    if (fondoActual === id) return;
    if (fondoActual !== null) mapa.removeLayer(teselas.get(fondoActual));
    nueva.addTo(mapa);
    fondoActual = id;
  }

  // --- atribuciones ---------------------------------------------------------------------
  let atribucionesActuales = [];
  function ponerAtribuciones(textos) {
    for (const texto of atribucionesActuales) control.removeAttribution(texto);
    atribucionesActuales = textos.map(escaparTexto);
    for (const texto of atribucionesActuales) control.addAttribution(texto);
  }

  // --- capas de trazados ----------------------------------------------------------------
  const capas = new Map();
  let tema = temaInicial;
  let seleccionado = null; // selección única de todo el mapa

  function pintar(trazado, estado) {
    trazado.estado = estado;
    const estilos = estiloTrazado(trazado.clave, estado, tema, trazado.poligono);
    trazado.halo.setStyle(estilos.halo);
    trazado.linea.setStyle(estilos.linea);
  }

  function deseleccionar() {
    if (seleccionado === null) return;
    const anterior = seleccionado;
    seleccionado = null;
    pintar(anterior, "normal");
  }

  function marcar(trazado) {
    if (seleccionado && seleccionado !== trazado) pintar(seleccionado, "normal");
    seleccionado = trazado;
    pintar(trazado, "seleccionado");
    trazado.halo.bringToFront();
    trazado.linea.bringToFront();
  }

  function quitarCapa(id) {
    const capa = capas.get(id);
    if (!capa) return;
    if (seleccionado && seleccionado.capaId === id) seleccionado = null;
    if (mapa.hasLayer(capa.grupo)) mapa.removeLayer(capa.grupo);
    capas.delete(id);
  }

  function anadirCapa(id, geojson, { clave, claveDe, orden = 0, alPulsar }) {
    if ((clave === undefined) === (claveDe === undefined)) {
      throw new Error("anadirCapa necesita exactamente uno de «clave» o «claveDe»");
    }
    if (clave !== undefined && !CLAVES.includes(clave)) {
      throw new Error(`Clave de estilo desconocida: ${clave}`);
    }
    quitarCapa(id);
    const claveDeFeature = (feature) => clave ?? claveDe(feature.properties ?? {});
    // Un pane por capa: el apilado no depende del orden en que terminan de cargar (CA8 de #165).
    const pane = "pc-capa-" + id;
    const elemento = mapa.getPane(pane) ?? mapa.createPane(pane);
    elemento.style.zIndex = String(400 + orden);

    const halos = new Map();
    const trazados = [];
    const porId = new Map();
    const capaHalo = L.geoJSON(geojson, {
      pane,
      interactive: false,
      style: (feature) =>
        estiloTrazado(claveDeFeature(feature), "normal", tema, esPoligono(feature)).halo,
      onEachFeature: (feature, layer) => halos.set(feature, layer),
    });
    // Un feature `Multi*` es un único layer: una sola selección para todas sus partes.
    const capaLinea = L.geoJSON(geojson, {
      pane,
      style: (feature) =>
        estiloTrazado(claveDeFeature(feature), "normal", tema, esPoligono(feature)).linea,
      onEachFeature: (feature, layer) => {
        const trazado = {
          capaId: id,
          id: feature.id === undefined || feature.id === null ? null : String(feature.id),
          clave: claveDeFeature(feature),
          poligono: esPoligono(feature),
          estado: "normal",
          halo: halos.get(feature),
          linea: layer,
        };
        trazados.push(trazado);
        if (trazado.id !== null) porId.set(trazado.id, trazado);
        layer.on("mouseover", () => {
          if (seleccionado !== trazado) pintar(trazado, "hover");
        });
        layer.on("mouseout", () => {
          if (seleccionado !== trazado) pintar(trazado, "normal");
        });
        layer.on("click", (evento) => {
          // Que el clic no llegue al mapa (que cerraría la ficha recién abierta).
          if (evento && L.DomEvent?.stopPropagation) L.DomEvent.stopPropagation(evento);
          marcar(trazado);
          if (typeof alPulsar === "function") alPulsar(feature.properties ?? {}, trazado.id);
        });
      },
    });
    const grupo = L.layerGroup([capaHalo, capaLinea]);
    capas.set(id, { grupo, trazados, porId });
    grupo.addTo(mapa);
  }

  const trazadoDe = (capaId, idRasgo) => capas.get(capaId)?.porId.get(String(idRasgo)) ?? null;

  function seleccionar(capaId, idRasgo) {
    const trazado = trazadoDe(capaId, idRasgo);
    if (!trazado) return false;
    marcar(trazado);
    return true;
  }

  function encuadrarRasgo(capaId, idRasgo) {
    const trazado = trazadoDe(capaId, idRasgo);
    if (!trazado || typeof trazado.linea.getBounds !== "function") return;
    mapa.fitBounds(trazado.linea.getBounds(), { ...opcionesEncuadre(), maxZoom: 17 });
  }

  function ponerTema(nuevo) {
    tema = nuevo;
    for (const { trazados } of capas.values()) {
      for (const trazado of trazados) pintar(trazado, trazado.estado);
    }
    pintarCobertura();
  }

  function mostrarCapa(id, visible) {
    const capa = capas.get(id);
    if (!capa) return;
    const presente = mapa.hasLayer(capa.grupo);
    if (visible && !presente) mapa.addLayer(capa.grupo);
    if (!visible && presente) {
      if (seleccionado && seleccionado.capaId === id) deseleccionar();
      mapa.removeLayer(capa.grupo);
    }
  }

  function encuadrar([oeste, sur, este, norte]) {
    mapa.fitBounds(
      [
        [sur, oeste],
        [norte, este],
      ],
      opcionesEncuadre(),
    );
  }

  // --- cobertura ------------------------------------------------------------------------
  const cobertura = {
    velo: null,
    halo: null,
    grupoBordes: null,
    bordes: new Map(),
    etiqueta: null,
    alZoom: null,
    activo: null,
  };

  // Deja el mapa sin cobertura: `ponerCobertura` es idempotente.
  function quitarCobertura() {
    for (const capa of [cobertura.velo, cobertura.halo, cobertura.grupoBordes, cobertura.etiqueta]) {
      if (capa && mapa.hasLayer(capa)) mapa.removeLayer(capa);
    }
    if (cobertura.alZoom) mapa.off?.("zoomend", cobertura.alZoom);
    Object.assign(cobertura, { velo: null, halo: null, grupoBordes: null, etiqueta: null, alZoom: null });
    cobertura.bordes.clear();
  }

  function pintarCobertura() {
    const c = COBERTURA[tema];
    cobertura.velo?.setStyle({ stroke: false, fill: true, fillColor: c.velo.color, fillOpacity: c.velo.opacity });
    cobertura.halo?.setStyle({ color: c.halo.color, weight: c.halo.weight, opacity: c.halo.opacity, fill: false });
    for (const [ine, capa] of cobertura.bordes) {
      const estilo = ine === cobertura.activo ? c.activo : c.borde;
      capa.setStyle({ color: estilo.color, weight: estilo.weight, opacity: estilo.opacity, fill: true, fillOpacity: 0 });
    }
  }

  function ponerCobertura(geojson, { etiqueta, zoomEtiqueta = 9, alPulsarMunicipio, alPulsarEtiqueta } = {}) {
    for (const nombre of ["pc-cobertura-velo", "pc-cobertura"]) {
      const pane = mapa.getPane(nombre) ?? mapa.createPane(nombre);
      pane.style.zIndex = nombre === "pc-cobertura-velo" ? "350" : "390";
    }
    quitarCobertura();
    cobertura.velo = L.geoJSON(veloCobertura(geojson), { pane: "pc-cobertura-velo", interactive: false });
    cobertura.halo = L.geoJSON(geojson, { pane: "pc-cobertura", interactive: false });
    const bordes = L.geoJSON(geojson, {
      pane: "pc-cobertura",
      onEachFeature: (feature, layer) => {
        const ine = String(feature?.properties?.ine ?? feature?.id ?? "");
        cobertura.bordes.set(ine, layer);
        layer.on("click", (evento) => {
          if (evento && L.DomEvent?.stopPropagation) L.DomEvent.stopPropagation(evento);
          if (typeof alPulsarMunicipio === "function") alPulsarMunicipio(ine);
        });
      },
    });
    cobertura.grupoBordes = bordes;
    for (const capa of [cobertura.velo, cobertura.halo, bordes]) capa.addTo(mapa);
    pintarCobertura();

    if (etiqueta && L.marker && L.divIcon) {
      const anillos = anillosExteriores(geojson).flat();
      if (anillos.length > 0) {
        const lons = anillos.map((p) => p[0]);
        const lats = anillos.map((p) => p[1]);
        const centro = [(Math.min(...lats) + Math.max(...lats)) / 2, (Math.min(...lons) + Math.max(...lons)) / 2];
        cobertura.etiqueta = L.marker(centro, {
          icon: L.divIcon({ html: etiqueta, className: "pc-hito", iconSize: null }),
          keyboard: true,
          title: etiqueta.textContent,
          alt: etiqueta.textContent,
        });
        cobertura.etiqueta.on("click", (evento) => {
          if (evento && L.DomEvent?.stopPropagation) L.DomEvent.stopPropagation(evento);
          if (typeof alPulsarEtiqueta === "function") alPulsarEtiqueta();
        });
        const actualizar = () => {
          const ver = mapa.getZoom() < zoomEtiqueta;
          const presente = mapa.hasLayer(cobertura.etiqueta);
          if (ver && !presente) mapa.addLayer(cobertura.etiqueta);
          if (!ver && presente) mapa.removeLayer(cobertura.etiqueta);
        };
        cobertura.alZoom = actualizar;
        mapa.on("zoomend", actualizar);
        actualizar();
      }
    }
  }

  function resaltarMunicipio(ine) {
    cobertura.activo = ine;
    pintarCobertura();
  }

  // --- arranque -------------------------------------------------------------------------
  // La atribución del fondo se pone antes de pedir ninguna tesela (CA4 de #85).
  const inicial = fondos.find((f) => f.id === fondoInicial) ?? fondos[0];
  ponerAtribuciones([...(inicial.atribuciones ?? [])]);
  if (encuadreInicial) encuadrar(encuadreInicial);
  ponerFondo(inicial.id);
  return {
    anadirCapa,
    ponerTema,
    quitarCapa,
    mostrarCapa,
    encuadrar,
    encuadrarRasgo,
    ponerAtribuciones,
    ponerFondo,
    seleccionar,
    deseleccionar,
    ponerCobertura,
    resaltarMunicipio,
  };
}
