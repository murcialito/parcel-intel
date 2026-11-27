// Estado del visor en el enlace (historia #185): `?municipio=<ine>&tramo=<id>`. Puro: sin DOM ni
// `location`; app.js le pasa la cadena de búsqueda y escribe el resultado en el historial.
// Lo que no tiene la forma esperada se ignora, nunca llega al controlador.

const INE = /^\d{5}$/;
const TRAMO = /^[0-9a-f]{16}$/;

export function leerEnlace(busqueda) {
  const parametros = new URLSearchParams(typeof busqueda === "string" ? busqueda : "");
  const municipio = parametros.get("municipio");
  const tramo = parametros.get("tramo");
  const municipioValido = municipio !== null && INE.test(municipio) ? municipio : null;
  return {
    municipio: municipioValido,
    tramo: municipioValido !== null && tramo !== null && TRAMO.test(tramo) ? tramo : null,
  };
}

// Cadena de búsqueda («?…» o «» para la vista de España).
export function escribirEnlace({ municipio = null, tramo = null } = {}) {
  if (municipio === null || !INE.test(municipio)) return "";
  const parametros = new URLSearchParams({ municipio });
  if (tramo !== null && TRAMO.test(tramo)) parametros.set("tramo", tramo);
  return `?${parametros.toString()}`;
}
