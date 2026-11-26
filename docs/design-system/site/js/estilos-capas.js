/* Paso Común · Estilos de capas para Leaflet 1.9.4 · CC BY 4.0
   Cada capa se dibuja dos veces: un halo oscuro debajo y la línea encima,
   para que se lea sobre la ortofoto PNOA (campo ocre, verde, casco urbano, sombras).
   La diferencia entre capas nunca depende solo del color: también grosor y patrón. */
(function (global) {
  'use strict';

  var BASE = {
    claro: {
      // 1. Vías pecuarias: banda ancha continua (cartografía informativa, no deslinde)
      viasPecuarias:    { color: '#e69f00', weight: 6,   opacity: 0.9, dashArray: null,    lineCap: 'butt',  halo: { color: '#1b1408', extra: 3, opacity: 0.55 } },
      // 2. Camino actual (IGN, sin asfaltar): línea fina continua, clara
      caminoActual:     { color: '#fdf3c4', weight: 2.5, opacity: 1,   dashArray: null,    lineCap: 'round', halo: { color: '#1b1b17', extra: 3, opacity: 0.75 } },
      // 3. Trazado histórico (planimetrías 1870-1880): discontinua
      trazadoHistorico: { color: '#e3a6d0', weight: 3,   opacity: 1,   dashArray: '10 7',  lineCap: 'butt',  halo: { color: '#2a1424', extra: 3, opacity: 0.6 } },
      // 4. Indicios de corte: punteado; la confianza sube con el tamaño y la densidad del punto
      indicioBaja:      { color: '#56b4e9', weight: 5,   opacity: 0.85, dashArray: '1 12', lineCap: 'round', halo: { color: '#0b2433', extra: 3, opacity: 0.55, dashArray: '1 12' } },
      indicioMedia:     { color: '#56b4e9', weight: 7,   opacity: 0.95, dashArray: '1 11', lineCap: 'round', halo: { color: '#0b2433', extra: 3, opacity: 0.65, dashArray: '1 11' } },
      indicioAlta:      { color: '#56b4e9', weight: 9,   opacity: 1,   dashArray: '1 10',  lineCap: 'round', halo: { color: '#0b2433', extra: 3, opacity: 0.75, dashArray: '1 10' } }
    },
    seleccionHalo: { claro: '#ffffff', oscuro: '#e8ebe8' }
  };
  // Modo oscuro: la ortofoto se atenúa (ver --map-tiles-filter); las líneas suben un punto de luminosidad
  BASE.oscuro = clonar(BASE.claro);
  BASE.oscuro.viasPecuarias.color = '#f2b33d';
  BASE.oscuro.caminoActual.color = '#fff6d6';
  BASE.oscuro.trazadoHistorico.color = '#edb9dd';
  ['indicioBaja', 'indicioMedia', 'indicioAlta'].forEach(function (k) { BASE.oscuro[k].color = '#7cc8f0'; });

  function clonar(o) { return JSON.parse(JSON.stringify(o)); }

  /* Devuelve { halo, linea } listos para L.Path#setStyle.
     estado: 'normal' | 'hover' | 'seleccionado' */
  function estilo(capa, estado, tema) {
    tema = tema || temaActual();
    var b = BASE[tema][capa];
    if (!b) throw new Error('Capa desconocida: ' + capa);
    var linea = { color: b.color, weight: b.weight, opacity: b.opacity, dashArray: b.dashArray, lineCap: b.lineCap, lineJoin: 'round' };
    var halo = { color: b.halo.color, weight: b.weight + b.halo.extra, opacity: b.halo.opacity, dashArray: b.halo.dashArray || null, lineCap: b.lineCap, lineJoin: 'round', interactive: false };
    if (estado === 'hover') {
      linea.weight += 2; linea.opacity = 1;
      halo.weight += 2; halo.opacity = Math.min(1, halo.opacity + 0.15);
    } else if (estado === 'seleccionado') {
      linea.weight += 2; linea.opacity = 1;
      halo.color = BASE.seleccionHalo[tema]; halo.weight = linea.weight + 5; halo.opacity = 0.95;
    }
    return { halo: halo, linea: linea };
  }

  // Objeto plano precalculado: ESTILOS.claro.viasPecuarias.hover.linea …
  var ESTILOS = {};
  ['claro', 'oscuro'].forEach(function (t) {
    ESTILOS[t] = {};
    Object.keys(BASE.claro).forEach(function (c) {
      ESTILOS[t][c] = { normal: estilo(c, 'normal', t), hover: estilo(c, 'hover', t), seleccionado: estilo(c, 'seleccionado', t) };
    });
  });

  function temaActual() {
    var forzado = document.documentElement.getAttribute('data-tema');
    if (forzado === 'claro' || forzado === 'oscuro') return forzado;
    return global.matchMedia && global.matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
  }

  /* Crea un L.LayerGroup con halo + línea e interacción hover/selección.
     capa puede ser una clave fija o una función(feature) -> clave (útil para los niveles de confianza). */
  var seleccionado = null;
  function capaConHalo(L, geojson, capa, opciones) {
    opciones = opciones || {};
    var claveDe = typeof capa === 'function' ? capa : function () { return capa; };
    var halos = [];
    var grupoHalo = L.geoJSON(geojson, {
      interactive: false,
      style: function (f) { return estilo(claveDe(f), 'normal').halo; },
      onEachFeature: function (f, l) { halos.push(l); }
    });
    var i = 0;
    var grupoLinea = L.geoJSON(geojson, {
      style: function (f) { return estilo(claveDe(f), 'normal').linea; },
      onEachFeature: function (f, l) {
        var halo = halos[i++], clave = claveDe(f);
        l._pc = { halo: halo, clave: clave };
        function pintar(estado) { var s = estilo(clave, estado); l.setStyle(s.linea); halo.setStyle(s.halo); }
        l.on('mouseover', function () { if (seleccionado !== l) pintar('hover'); });
        l.on('mouseout', function () { if (seleccionado !== l) pintar('normal'); });
        l.on('click', function (e) {
          if (seleccionado && seleccionado !== l) {
            var p = seleccionado._pc, s = estilo(p.clave, 'normal');
            seleccionado.setStyle(s.linea); p.halo.setStyle(s.halo);
          }
          seleccionado = l; pintar('seleccionado'); halo.bringToFront(); l.bringToFront();
          if (opciones.alSeleccionar) opciones.alSeleccionar(f, e);
        });
      }
    });
    return L.layerGroup([grupoHalo, grupoLinea]);
  }

  /* Ejemplo:
     var vias = PasoComunEstilos.capaConHalo(L, datosVias, 'viasPecuarias').addTo(mapa);
     var indicios = PasoComunEstilos.capaConHalo(L, datosIndicios, function (f) {
       return { baja: 'indicioBaja', media: 'indicioMedia', alta: 'indicioAlta' }[f.properties.confianza];
     }, { alSeleccionar: abrirFicha }).addTo(mapa);
     Orden recomendado (de abajo arriba): vías pecuarias, histórico, camino actual, indicios. */

  global.PasoComunEstilos = { BASE: BASE, ESTILOS: ESTILOS, estilo: estilo, temaActual: temaActual, capaConHalo: capaConHalo };
})(window);
