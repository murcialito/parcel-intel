// Estilos de capa del sistema de diseño Paso Común (historia #165, ADR 0046).
//
// Módulo puro: sin DOM, sin la librería de mapas y sin globales. Los valores y la aritmética son
// los de `docs/design-system/site/js/estilos-capas.js` (un test los compara con el original).
// Cada capa se dibuja dos veces: un halo oscuro debajo y la línea encima, para que se lea sobre
// la ortofoto. La diferencia entre capas nunca depende solo del color: también grosor y patrón.

export const CLAVES = Object.freeze([
  "viasPecuarias",
  "caminoActual",
  "trazadoHistorico",
  "indicioBaja",
  "indicioMedia",
  "indicioAlta",
  "candidato",
]);

const ESTADOS = Object.freeze(["normal", "hover", "seleccionado"]);
const TEMAS = Object.freeze(["claro", "oscuro"]);

function congelar(objeto) {
  for (const valor of Object.values(objeto)) {
    if (valor !== null && typeof valor === "object") congelar(valor);
  }
  return Object.freeze(objeto);
}

const claro = {
  // Vías pecuarias: banda ancha continua (cartografía informativa, no deslinde).
  viasPecuarias: { color: "#e69f00", weight: 6, opacity: 0.9, dashArray: null, lineCap: "butt", halo: { color: "#1b1408", extra: 3, opacity: 0.55 } },
  // Camino actual (IGN, sin asfaltar): línea fina continua, clara.
  caminoActual: { color: "#fdf3c4", weight: 2.5, opacity: 1, dashArray: null, lineCap: "round", halo: { color: "#1b1b17", extra: 3, opacity: 0.75 } },
  // Trazado histórico (planimetrías): discontinua.
  trazadoHistorico: { color: "#e3a6d0", weight: 3, opacity: 1, dashArray: "10 7", lineCap: "butt", halo: { color: "#2a1424", extra: 3, opacity: 0.6 } },
  // Indicios: punteado; la confianza sube con el tamaño y la densidad del punto.
  indicioBaja: { color: "#56b4e9", weight: 5, opacity: 0.85, dashArray: "1 12", lineCap: "round", halo: { color: "#0b2433", extra: 3, opacity: 0.55, dashArray: "1 12" } },
  indicioMedia: { color: "#56b4e9", weight: 7, opacity: 0.95, dashArray: "1 11", lineCap: "round", halo: { color: "#0b2433", extra: 3, opacity: 0.65, dashArray: "1 11" } },
  indicioAlta: { color: "#56b4e9", weight: 9, opacity: 1, dashArray: "1 10", lineCap: "round", halo: { color: "#0b2433", extra: 3, opacity: 0.75, dashArray: "1 10" } },
  // Tramos a verificar (historia #171): raya y punto en bermellón, distinta de las demás por
  // color y por patrón. No es parte del sistema de diseño original (docs/design-system).
  candidato: { color: "#d55e00", weight: 4, opacity: 1, dashArray: "14 6 2 6", lineCap: "butt", halo: { color: "#2b1100", extra: 3, opacity: 0.7, dashArray: "14 6 2 6" } },
};

// Modo oscuro: la ortofoto se atenúa por CSS; las líneas suben un punto de luminosidad.
const oscuro = JSON.parse(JSON.stringify(claro));
oscuro.viasPecuarias.color = "#f2b33d";
oscuro.caminoActual.color = "#fff6d6";
oscuro.trazadoHistorico.color = "#edb9dd";
for (const clave of ["indicioBaja", "indicioMedia", "indicioAlta"]) oscuro[clave].color = "#7cc8f0";
oscuro.candidato.color = "#f08a3a";

export const BASE = congelar({
  claro,
  oscuro,
  seleccionHalo: { claro: "#ffffff", oscuro: "#e8ebe8" },
});

// Opacidad del relleno de los polígonos (decisión de producto de #165, ADR 0046).
export const RELLENO = congelar({
  viasPecuarias: 0.15,
  indicioBaja: 0.1,
  indicioMedia: 0.1,
  indicioAlta: 0.1,
});

// Devuelve { halo, linea } nuevos en cada llamada. Error si clave, estado o tema no existen.
export function estilo(clave, estado = "normal", tema = "claro") {
  if (!TEMAS.includes(tema)) throw new Error(`Tema desconocido: ${tema}`);
  if (!ESTADOS.includes(estado)) throw new Error(`Estado desconocido: ${estado}`);
  if (!CLAVES.includes(clave)) throw new Error(`Capa desconocida: ${clave}`);
  const b = BASE[tema][clave];
  const linea = { color: b.color, weight: b.weight, opacity: b.opacity, dashArray: b.dashArray, lineCap: b.lineCap, lineJoin: "round" };
  const halo = { color: b.halo.color, weight: b.weight + b.halo.extra, opacity: b.halo.opacity, dashArray: b.halo.dashArray || null, lineCap: b.lineCap, lineJoin: "round", interactive: false };
  if (estado === "hover") {
    linea.weight += 2;
    linea.opacity = 1;
    halo.weight += 2;
    halo.opacity = Math.min(1, halo.opacity + 0.15);
  } else if (estado === "seleccionado") {
    linea.weight += 2;
    linea.opacity = 1;
    halo.color = BASE.seleccionHalo[tema];
    halo.weight = linea.weight + 5;
    halo.opacity = 0.95;
  }
  return { halo, linea };
}

// ESTILOS[tema][clave][estado] -> { halo, linea }, precalculado.
export const ESTILOS = congelar(
  Object.fromEntries(
    TEMAS.map((t) => [
      t,
      Object.fromEntries(
        CLAVES.map((c) => [c, Object.fromEntries(ESTADOS.map((e) => [e, estilo(c, e, t)]))]),
      ),
    ]),
  ),
);

// Estilo de un trazado concreto. El halo es solo contorno; la línea de un polígono lleva además
// un relleno tenue del color de la línea si la capa tiene `RELLENO` (CA7).
export function estiloTrazado(clave, estado, tema, poligono) {
  const { halo, linea } = estilo(clave, estado, tema);
  halo.fill = false;
  const relleno = Object.hasOwn(RELLENO, clave) ? RELLENO[clave] : null;
  if (poligono && relleno !== null) {
    linea.fill = true;
    linea.fillColor = linea.color;
    linea.fillOpacity = estado === "normal" ? relleno : relleno + 0.1;
  } else {
    linea.fill = false;
  }
  return { halo, linea };
}

// El tema forzado por la persona gana; si no, manda la preferencia del sistema.
export function temaDe(forzado, prefiereOscuro) {
  if (forzado === "claro" || forzado === "oscuro") return forzado;
  return prefiereOscuro ? "oscuro" : "claro";
}

// Cobertura (historia #185): velo gris sobre lo que aún no tiene datos y contorno de cada
// municipio cubierto, con un halo claro para que se lea sobre el mapa y la ortofoto. No es
// una capa de trazados: no entra en CLAVES ni en el sistema de diseño original de #165.
export const COBERTURA = congelar({
  claro: {
    velo: { color: "#2e3430", opacity: 0.22 },
    borde: { color: "#2f6b3f", weight: 2.5, opacity: 1 },
    halo: { color: "#ffffff", weight: 6, opacity: 0.9 },
    activo: { color: "#2f6b3f", weight: 3.5, opacity: 1 },
  },
  oscuro: {
    velo: { color: "#000000", opacity: 0.28 },
    borde: { color: "#7cc290", weight: 2.5, opacity: 1 },
    halo: { color: "#151816", weight: 6, opacity: 0.9 },
    activo: { color: "#95d0a6", weight: 3.5, opacity: 1 },
  },
});
