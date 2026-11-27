// Capturas del visor estático para que el agente diseñador vea su trabajo (rol:disenador).
//
// Uso: node scripts/capturar_visor.mjs [--sitio site] [--salida capturas] [--escena nombre=/ruta ...]
// Por defecto, la escena «inicio=/». Cada escena se captura en escritorio (1440×900) y en móvil
// (390×844), en tema claro y oscuro: <salida>/<escena>-<pantalla>-<tema>.png. Los errores de consola
// y las peticiones fallidas o con 4xx/5xx van a <salida>/errores.txt. Sale con 0 aunque haya errores:
// los lista el resumen, y el agente decide.
// Necesita Playwright con Chromium. La ruta de su instalación va en PW_DIR (el workflow la instala
// en $RUNNER_TEMP/pw). No es dependencia del proyecto.

import { createServer } from "node:http";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";

const args = process.argv.slice(2);
const opcion = (nombre, porDefecto) => {
  const i = args.indexOf(nombre);
  return i >= 0 ? args[i + 1] : porDefecto;
};
const sitio = resolve(opcion("--sitio", "site"));
const salida = resolve(opcion("--salida", "capturas"));
const escenas = [];
args.forEach((a, i) => {
  if (a === "--escena") {
    const [nombre, ...ruta] = args[i + 1].split("=");
    escenas.push({ nombre, ruta: ruta.join("=") || "/" });
  }
});
if (!escenas.length) escenas.push({ nombre: "inicio", ruta: "/" });

const pwDir = process.env.PW_DIR;
if (!pwDir) {
  console.error("Falta PW_DIR: la ruta donde está instalado Playwright (npm install --prefix <dir> playwright).");
  process.exit(2);
}
const { chromium } = createRequire(join(pwDir, "/"))("playwright");

const TIPOS = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json", ".geojson": "application/geo+json",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
  ".woff2": "font/woff2", ".woff": "font/woff", ".webmanifest": "application/manifest+json", ".ico": "image/x-icon",
};
const servidor = createServer((req, res) => {
  const ruta = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let fichero = normalize(join(sitio, ruta));
  if (!fichero.startsWith(sitio)) { res.writeHead(403).end(); return; }
  try {
    if (statSync(fichero).isDirectory()) fichero = join(fichero, "index.html");
    res.writeHead(200, { "content-type": TIPOS[extname(fichero)] || "application/octet-stream" });
    res.end(readFileSync(fichero));
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((ok) => servidor.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${servidor.address().port}`;

mkdirSync(salida, { recursive: true });
const PANTALLAS = { escritorio: { width: 1440, height: 900 }, movil: { width: 390, height: 844 } };
const errores = [];
const navegador = await chromium.launch();
try {
  for (const { nombre, ruta } of escenas) {
    for (const [pantalla, viewport] of Object.entries(PANTALLAS)) {
      for (const tema of ["light", "dark"]) {
        const contexto = await navegador.newContext({
          viewport, colorScheme: tema, isMobile: pantalla === "movil", hasTouch: pantalla === "movil",
          deviceScaleFactor: 1, locale: "es-ES",
        });
        const pagina = await contexto.newPage();
        const etiqueta = `${nombre}-${pantalla}-${tema === "light" ? "claro" : "oscuro"}`;
        pagina.on("console", (m) => { if (m.type() === "error") errores.push(`${etiqueta}: consola: ${m.text()}`); });
        pagina.on("pageerror", (e) => errores.push(`${etiqueta}: excepción: ${e.message}`));
        pagina.on("requestfailed", (r) => errores.push(`${etiqueta}: petición fallida: ${r.url()}`));
        pagina.on("response", (r) => { if (r.status() >= 400) errores.push(`${etiqueta}: HTTP ${r.status()}: ${r.url()}`); });
        await pagina.goto(base + ruta, { waitUntil: "networkidle", timeout: 60000 }).catch((e) => errores.push(`${etiqueta}: carga: ${e.message}`));
        await pagina.waitForTimeout(800);
        await pagina.screenshot({ path: join(salida, `${etiqueta}.png`) });
        await contexto.close();
      }
    }
  }
} finally {
  await navegador.close();
  servidor.close();
}
writeFileSync(join(salida, "errores.txt"), errores.join("\n") + (errores.length ? "\n" : ""));
console.log(`${escenas.length * 4} capturas en ${salida}; ${errores.length} errores (errores.txt).`);
