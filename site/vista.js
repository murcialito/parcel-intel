// Vista del visor (historia #85): el único módulo, junto con app.js, que toca el DOM.
// Recibe el `document` por inyección (se prueba con un documento falso en Node).
// Todo texto que viene de datos se inserta con `textContent`, nunca como HTML (CA6).

export function crearVista(documento, textos) {
  const porId = (id) => {
    const elemento = documento.getElementById(id);
    if (!elemento) throw new Error(`falta el elemento #${id}`);
    return elemento;
  };
  const selector = porId("municipio");
  const mensaje = porId("mensaje");
  const avisoBase = porId("aviso-base");

  const TEXTO_ESTADO = {
    ok: "",
    cargando: textos.cargando,
    vacia: textos.sinTrazados,
    error: textos.errorCapa,
  };

  function ponerMunicipios(lista) {
    selector.replaceChildren();
    for (const { ine, nombre } of lista) {
      const opcion = documento.createElement("option");
      opcion.value = ine;
      opcion.textContent = nombre;
      selector.appendChild(opcion);
    }
  }

  function seleccionarMunicipio(ine) {
    selector.value = ine;
  }

  function ponerEstadoCapa(id, estado) {
    const elemento = porId(`estado-${id}`);
    elemento.textContent = TEXTO_ESTADO[estado] ?? "";
    elemento.dataset.estado = estado;
  }

  function mostrarMensaje(texto) {
    mensaje.textContent = texto;
  }

  function limpiarMensaje() {
    mensaje.textContent = "";
  }

  function mostrarAvisoBase(texto) {
    avisoBase.textContent = texto;
  }

  function nodoFicha({ titulo, fuente, nombre }) {
    const ficha = documento.createElement("div");
    ficha.className = "ficha";
    const cabecera = documento.createElement("strong");
    cabecera.textContent = titulo;
    ficha.appendChild(cabecera);
    if (nombre) {
      const p = documento.createElement("p");
      p.textContent = nombre;
      ficha.appendChild(p);
    }
    const pie = documento.createElement("p");
    pie.className = "ficha-fuente";
    pie.textContent = `Fuente: ${fuente}`;
    ficha.appendChild(pie);
    return ficha;
  }

  return {
    ponerMunicipios,
    seleccionarMunicipio,
    ponerEstadoCapa,
    mostrarMensaje,
    limpiarMensaje,
    mostrarAvisoBase,
    nodoFicha,
  };
}
