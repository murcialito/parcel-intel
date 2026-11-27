// ÚNICO módulo del sitio que usa la librería de mapas (historia #85, ADR 0037).
//
// Leaflet 1.9.4 se carga antes como script clásico (`vendor/leaflet/leaflet.js`) y deja su
// global. Cambiar a MapLibre GL es reescribir este fichero con la misma interfaz:
//
//   crearMapa(contenedor, { teselas, vistaInicial, atribucionesBase, alFallarTesela, tema }) -> Mapa
//   Mapa.anadirCapa(id, geojson, { clave | claveDe, orden, alPulsar })
//        // clave: una de CLAVES; claveDe(propiedades) -> clave; alPulsar(propiedades) -> Node
//   Mapa.ponerTema("claro" | "oscuro")
//   Mapa.quitarCapa(id)
//   Mapa.mostrarCapa(id, visible)
//   Mapa.encuadrar([oeste, sur, este, norte])           // lon/lat EPSG:4326
//   Mapa.ponerAtribuciones(textos)                      // lista completa, en texto plano

import { CLAVES, estiloTrazado } from "./estilos-capas.js";

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

export function crearMapa(contenedor, opciones) {
  const L = globalThis.L;
  if (!L) throw new Error("La librería de mapas no está cargada");
  const { teselas, vistaInicial, atribucionesBase = [], alFallarTesela, tema: temaInicial = "claro" } = opciones;

  const mapa = L.map(contenedor, { attributionControl: false });
  if (vistaInicial) mapa.setView(vistaInicial.centro, vistaInicial.zoom);
  const control = L.control.attribution({ prefix: false });
  control.addTo(mapa);

  const base = L.tileLayer(teselas.url, {
    minZoom: teselas.minZoom,
    maxZoom: teselas.maxZoom,
    tileSize: 256,
    crossOrigin: false,
  });
  // Un fallo de tesela no toca las capas vectoriales: solo se avisa (CA10).
  base.on("tileerror", () => {
    if (typeof alFallarTesela === "function") alFallarTesela();
  });
  base.addTo(mapa);

  const capas = new Map();
  let atribucionesActuales = [];

  function ponerAtribuciones(textos) {
    for (const texto of atribucionesActuales) control.removeAttribution(texto);
    atribucionesActuales = textos.map(escaparTexto);
    for (const texto of atribucionesActuales) control.addAttribution(texto);
  }

  // Selección única de todo el mapa: estado del cierre, no de módulo.
  let tema = temaInicial;
  let seleccionado = null;

  function pintar(trazado, estado) {
    trazado.estado = estado;
    const estilos = estiloTrazado(trazado.clave, estado, tema, trazado.poligono);
    trazado.halo.setStyle(estilos.halo);
    trazado.linea.setStyle(estilos.linea);
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
    // Un pane por capa: el apilado no depende del orden en que terminan de cargar (CA8).
    const pane = "pc-capa-" + id;
    const elemento = mapa.getPane(pane) ?? mapa.createPane(pane);
    elemento.style.zIndex = String(400 + orden);

    const halos = new Map();
    const trazados = [];
    const capaHalo = L.geoJSON(geojson, {
      pane,
      interactive: false,
      style: (feature) =>
        estiloTrazado(claveDeFeature(feature), "normal", tema, esPoligono(feature)).halo,
      onEachFeature: (feature, layer) => halos.set(feature, layer),
    });
    // Un feature `Multi*` es un único layer con un único popup para todas sus partes (CA14).
    const capaLinea = L.geoJSON(geojson, {
      pane,
      style: (feature) =>
        estiloTrazado(claveDeFeature(feature), "normal", tema, esPoligono(feature)).linea,
      onEachFeature: (feature, layer) => {
        const trazado = {
          capaId: id,
          clave: claveDeFeature(feature),
          poligono: esPoligono(feature),
          estado: "normal",
          halo: halos.get(feature),
          linea: layer,
        };
        trazados.push(trazado);
        layer.on("mouseover", () => {
          if (seleccionado !== trazado) pintar(trazado, "hover");
        });
        layer.on("mouseout", () => {
          if (seleccionado !== trazado) pintar(trazado, "normal");
        });
        layer.on("click", () => {
          if (seleccionado && seleccionado !== trazado) pintar(seleccionado, "normal");
          seleccionado = trazado;
          pintar(trazado, "seleccionado");
          trazado.halo.bringToFront();
          layer.bringToFront();
        });
        layer.on("popupclose", () => {
          if (seleccionado !== trazado) return;
          seleccionado = null;
          pintar(trazado, "normal");
        });
        // Se pasa un nodo construido con textContent, nunca una cadena HTML (CA6).
        layer.bindPopup(() => alPulsar(feature.properties ?? {}));
      },
    });
    const grupo = L.layerGroup([capaHalo, capaLinea]);
    capas.set(id, { grupo, trazados });
    grupo.addTo(mapa);
  }

  function ponerTema(nuevo) {
    tema = nuevo;
    for (const { trazados } of capas.values()) {
      for (const trazado of trazados) pintar(trazado, trazado.estado);
    }
  }

  function mostrarCapa(id, visible) {
    const capa = capas.get(id);
    if (!capa) return;
    const presente = mapa.hasLayer(capa.grupo);
    if (visible && !presente) mapa.addLayer(capa.grupo);
    if (!visible && presente) mapa.removeLayer(capa.grupo);
  }

  function encuadrar([oeste, sur, este, norte]) {
    mapa.fitBounds([
      [sur, oeste],
      [norte, este],
    ]);
  }

  ponerAtribuciones(atribucionesBase);
  return { anadirCapa, ponerTema, quitarCapa, mostrarCapa, encuadrar, ponerAtribuciones };
}
