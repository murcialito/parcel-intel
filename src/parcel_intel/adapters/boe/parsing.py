from typing import NotRequired, TypedDict


class RawItem(TypedDict):
    identificador: str
    titulo: str
    url_pdf: dict[str, object]
    control: NotRequired[str]


def _as_list(value: object) -> list[dict[str, object]]:
    """El JSON de BOE colapsa cualquier elemento repetible a un `dict`
    suelto (no una lista de un elemento) cuando solo aparece una vez ese
    día — confirmado real en `REGISTRY.md` en tres niveles de anidamiento.
    `None`/ausente se normaliza a lista vacía."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    assert isinstance(value, dict)
    return [value]


def _items_from_container(container: dict[str, object]) -> list[RawItem]:
    """Un `departamento` (o `epigrafe`) puede traer sus disposiciones de dos
    formas confirmadas reales: directamente en `item`, o anidadas en
    `texto.item` (confirmado real en la sección "Anuncios particulares" del
    `20261015`, variante no detectada en la primera pasada de REGISTRY.md)."""
    items: list[RawItem] = []
    if "item" in container:
        items.extend(_as_list(container["item"]))  # type: ignore[arg-type]
    texto = container.get("texto")
    if isinstance(texto, dict) and "item" in texto:
        items.extend(_as_list(texto["item"]))  # type: ignore[arg-type]
    return items


class ParsedNotice(TypedDict):
    identifier: str
    title: str
    section_code: str
    section_name: str
    pdf_url: str


def parse_daily_summary(response: dict[str, object]) -> list[ParsedNotice]:
    """Recorre las variantes de anidamiento conocidas, sin asumir nunca que
    un campo repetible viene como lista: `departamento.item`,
    `departamento.texto.item` y `departamento.epigrafe[].item` están
    confirmadas con datos reales del `20261015` (ver REGISTRY.md).
    `departamento.epigrafe[].texto.item` se cubre por la misma reutilización
    simétrica de `_items_from_container`, pero no tiene evidencia real
    todavía en ninguna fixture — cobertura defensiva, no un caso confirmado."""
    data = response["data"]
    assert isinstance(data, dict)
    sumario = data["sumario"]
    assert isinstance(sumario, dict)
    diario_list = _as_list(sumario["diario"])

    notices: list[ParsedNotice] = []
    for diario in diario_list:
        for seccion in _as_list(diario["seccion"]):
            section_code = str(seccion["codigo"])
            section_name = str(seccion["nombre"])
            for departamento in _as_list(seccion.get("departamento")):
                raw_items = _items_from_container(departamento)
                for epigrafe in _as_list(departamento.get("epigrafe")):
                    raw_items.extend(_items_from_container(epigrafe))
                for raw_item in raw_items:
                    url_pdf = raw_item["url_pdf"]
                    assert isinstance(url_pdf, dict)
                    notices.append(
                        ParsedNotice(
                            identifier=str(raw_item["identificador"]),
                            title=str(raw_item["titulo"]),
                            section_code=section_code,
                            section_name=section_name,
                            pdf_url=str(url_pdf["texto"]),
                        )
                    )
    return notices
