// ÚNICO módulo del sitio que usa la librería de mapas (historia #85, ADR 0037).
//
// Leaflet 1.9.4 se carga antes como script clásico (`vendor/leaflet/leaflet.js`) y deja su
// global. Cambiar a MapLibre GL es reescribir este fichero con la misma interfaz:
//
//   crearMapa(contenedor, { teselas, vistaInicial, atribucionesBase, alFallarTesela }) -> Mapa
//   Mapa.anadirCapa(id, geojson, { estilo, alPulsar })  // alPulsar(propiedades) -> Node
//   Mapa.quitarCapa(id)
//   Mapa.mostrarCapa(id, visible)
//   Mapa.encuadrar([oeste, sur, este, norte])           // lon/lat EPSG:4326
//   Mapa.ponerAtribuciones(textos)                      // lista completa, en texto plano

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
  const { teselas, vistaInicial, atribucionesBase = [], alFallarTesela } = opciones;

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

  function quitarCapa(id) {
    const capa = capas.get(id);
    if (!capa) return;
    if (mapa.hasLayer(capa)) mapa.removeLayer(capa);
    capas.delete(id);
  }

  function anadirCapa(id, geojson, { estilo, alPulsar }) {
    quitarCapa(id);
    // Un feature `Multi*` es un único layer con un único popup para todas sus partes (CA14).
    const capa = L.geoJSON(geojson, {
      style: () => ({ ...estilo }),
      onEachFeature: (feature, layer) => {
        // Se pasa un nodo construido con textContent, nunca una cadena HTML (CA6).
        layer.bindPopup(() => alPulsar(feature.properties ?? {}));
      },
    });
    capas.set(id, capa);
    capa.addTo(mapa);
  }

  function mostrarCapa(id, visible) {
    const capa = capas.get(id);
    if (!capa) return;
    const presente = mapa.hasLayer(capa);
    if (visible && !presente) mapa.addLayer(capa);
    if (!visible && presente) mapa.removeLayer(capa);
  }

  function encuadrar([oeste, sur, este, norte]) {
    mapa.fitBounds([
      [sur, oeste],
      [norte, este],
    ]);
  }

  ponerAtribuciones(atribucionesBase);
  return { anadirCapa, quitarCapa, mostrarCapa, encuadrar, ponerAtribuciones };
}
