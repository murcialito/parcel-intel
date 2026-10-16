import base64
from html import escape

from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.norm import effective_url
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.report import EnrichedParcelReport
from parcel_intel.domain.rule import Evidence, Finding
from parcel_intel.domain.watercourse import Watercourse

_VIEWBOX_SIZE = 560.0
_PADDING = 20.0


class EmptyGeometryError(Exception):
    """La parcela no tiene ningún anillo de geometría que dibujar.

    No debería ocurrir con datos reales de Catastro (una parcela siempre
    tiene al menos un anillo), pero `Geometry.rings` no lo garantiza a nivel
    de tipo, así que se señala explícitamente en vez de dejar que `min()`
    falle con un `ValueError` sin contexto.
    """

    def __init__(self, cadastral_reference: str) -> None:
        super().__init__(f"La parcela {cadastral_reference!r} no tiene geometría que renderizar")


def _all_points(geometries: list[Geometry]) -> list[tuple[float, float]]:
    return [point for geometry in geometries for ring in geometry.rings for point in ring]


def _ring_to_svg_path(ring: tuple[tuple[float, float], ...], transform: "_Transform") -> str:
    points = " ".join(f"{transform.x(x):.1f},{transform.y(y):.1f}" for x, y in ring)
    return f"M {points} Z"


class _Transform:
    """Escala coordenadas UTM (metros) a un viewBox SVG, invirtiendo el eje Y
    (en UTM crece hacia el norte; en SVG crece hacia abajo)."""

    def __init__(self, points: list[tuple[float, float]]) -> None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self._min_x, self._max_x = min(xs), max(xs)
        self._min_y, self._max_y = min(ys), max(ys)
        span = max(self._max_x - self._min_x, self._max_y - self._min_y, 1.0)
        self._scale = (_VIEWBOX_SIZE - 2 * _PADDING) / span

    def x(self, value: float) -> float:
        return _PADDING + (value - self._min_x) * self._scale

    def y(self, value: float) -> float:
        return _PADDING + (self._max_y - value) * self._scale


def _geometry_to_svg_paths(geometry: Geometry, transform: _Transform, css_class: str) -> str:
    return "\n".join(
        f'<path d="{_ring_to_svg_path(ring, transform)}" class="{css_class}" />'
        for ring in geometry.rings
    )


def _render_orthophoto_section(report: EnrichedParcelReport) -> str:
    orthophoto = report.orthophoto
    if orthophoto is None:
        return "<p><em>Ortofoto actual (PNOA) no disponible.</em></p>"
    encoded = base64.b64encode(orthophoto.image).decode("ascii")
    return (
        f'<img src="data:image/jpeg;base64,{encoded}" alt="Ortofoto actual" '
        f'style="max-width: 320px; border: 1px solid #ccc; border-radius: 4px;">'
    )


def _render_ndvi_section(report: EnrichedParcelReport) -> str:
    summary = report.ndvi_summary
    if summary is None:
        return "<p><em>Resumen NDVI (Sentinel-2) no disponible.</em></p>"
    return (
        f"<p>NDVI medio: <strong>{summary.mean:.2f}</strong> "
        f"(escena del {summary.scene_date.isoformat()}, "
        f"{summary.cloud_cover_percent:.0f}% nubes)</p>"
    )


def _render_bulletin_section(notices: tuple[BulletinNotice, ...] | None, label: str) -> str:
    if notices is None:
        return f"<p><em>{escape(label)} no disponible.</em></p>"
    if not notices:
        return (
            f"<p><em>Sin disposiciones de {escape(label)} que mencionen el municipio hoy.</em></p>"
        )
    items = "\n".join(
        f'<li><a href="{escape(notice.pdf_url)}">{escape(notice.title)}</a></li>'
        for notice in notices
    )
    return f"<ul>{items}</ul>"


def _render_land_classification_section(
    classifications: tuple[LandClassification, ...] | None,
) -> str:
    # El port nunca devuelve una tupla vacía como resultado válido (ADR
    # 0011): `None` es el único estado de "no disponible" para esta fuente.
    if classifications is None:
        return "<p><em>Clasificación de suelo (IDEM) no disponible.</em></p>"
    items = "\n".join(
        f"<li>{escape(c.general_category)} ({escape(c.detailed_category)}) "
        f"— {escape(c.municipality_name)}</li>"
        for c in classifications
    )
    return f"<ul>{items}</ul>"


def _render_watercourse_section(watercourses: tuple[Watercourse, ...] | None) -> str:
    if watercourses is None:
        return "<p><em>Cursos de agua (hidrografía) no disponible.</em></p>"
    if not watercourses:
        return "<p><em>Sin cursos de agua cercanos.</em></p>"
    items = "\n".join(
        f"<li>{escape(w.name) if w.name else 'sin nombre'} "
        f"— demarcación de {escape(w.hydrographic_demarcation_name)}</li>"
        for w in watercourses
    )
    return f"<ul>{items}</ul>"


def _render_flood_hazard_section(samples: tuple[FloodHazardSample, ...] | None) -> str:
    # El fallo es atómico (las 5 peticiones a la vez, ADR 0012/0013): no
    # existe un estado parcial, así que `None` es una única frase, nunca
    # una fila por combinación.
    if samples is None:
        return "<p><em>Peligrosidad por inundación no disponible.</em></p>"
    items = "\n".join(
        f"<li>{escape(s.kind)} T{s.return_period_years}: "
        f"{f'{s.water_depth_m:.2f} m' if s.water_depth_m is not None else 'NO DATA'}</li>"
        for s in samples
    )
    return f"<ul>{items}</ul>"


def _render_livestock_trail_section(trails: tuple[LivestockTrail, ...] | None) -> str:
    if trails is None:
        return "<p><em>Vías pecuarias (IDEM) no disponible.</em></p>"
    if not trails:
        return "<p><em>Sin vías pecuarias cercanas.</em></p>"
    items = "\n".join(
        f"<li>{escape(t.name)} ({escape(t.trail_type)}) — {escape(t.municipality_name)} "
        f"— {t.area_m2:.0f} m² / {t.length_m:.0f} m</li>"
        for t in trails
    )
    # `area_m2`/`length_m` no son la anchura legal (ADR 0014) -- nota
    # explícita para que el fundador no la confunda al verificar a ojo.
    return (
        f"<ul>{items}</ul>"
        '<p class="meta">area_m2/length_m son la franja real cartografiada, '
        "no la anchura legal de la Ley de Vías Pecuarias.</p>"
    )


def _render_protected_area_section(areas: tuple[ProtectedArea, ...] | None) -> str:
    if areas is None:
        return "<p><em>Espacios protegidos Red Natura 2000 (IDEM) no disponible.</em></p>"
    if not areas:
        return "<p><em>Sin espacios protegidos Red Natura 2000 cercanos.</em></p>"
    items = "\n".join(
        f"<li>Plan {escape(a.plan_code)}: {escape(a.plan_name)} "
        f"— Zona {escape(a.zone_code)}: {escape(a.zone_name)}</li>"
        for a in areas
    )
    return f"<ul>{items}</ul>"


def _render_findings_section(findings: tuple[Finding, ...]) -> str:
    # Sin hallazgo posible por fallo de red aquí (es cómputo puro sobre
    # datos ya obtenidos) -- la lista vacía es un resultado válido en sí
    # mismo, no un "no disponible": frase distinta a propósito (historia
    # 0017).
    if not findings:
        return "<p><em>Sin hallazgos de las reglas evaluadas.</em></p>"
    items = "\n".join(
        f"<li><strong>{escape(f.rule.outcome)}</strong> "
        f"(severidad: {escape(f.severity)}, confianza: {f.confidence:.2f})<br>"
        f"Autoridad: {escape(f.rule.authority)}<br>"
        f'Normativa: <a href="{escape(effective_url(f.rule.citation))}">'
        f"{escape(f.rule.citation.norm.title)} — {escape(f.rule.citation.article)}</a>"
        f"<ul>{''.join(_render_evidence_item(e) for e in f.evidence)}</ul></li>"
        for f in findings
    )
    return f"<ul>{items}</ul>"


def _render_evidence_item(evidence: Evidence) -> str:
    # measured_value/unit son opcionales desde la historia 0018: un
    # solape contra una entidad sin ningún campo numérico reutilizable
    # (p. ej. ProtectedArea) no tiene magnitud real que citar.
    if evidence.measured_value is None:
        return f"<li>{escape(evidence.description)}: {escape(evidence.source_name)}</li>"
    return (
        f"<li>{escape(evidence.description)}: "
        f"{escape(evidence.source_name)} — "
        f"{evidence.measured_value:.2f} {escape(evidence.unit or '')}</li>"
    )


def render_parcel_report_html(
    report: EnrichedParcelReport, findings: tuple[Finding, ...] = ()
) -> str:
    """Renderiza el informe de una parcela como una página HTML autocontenida.

    Es deliberadamente simple (sin plantillas de terceros, solo f-strings):
    esta historia busca tener algo visible cuanto antes, no el render final
    del informe de `docs/vision.md` (que todavía no tiene hallazgos ni
    reglas que mostrar). Desde la historia 0010 recibe un
    `EnrichedParcelReport` (parcela/edificios de Catastro más evidencia de
    PNOA/Sentinel-2/BOE/BOCM, cada una opcional si la fuente falló — ver
    ADR 0010), extendido en la historia 0013 con IDEM/cauces/peligrosidad
    por inundación (ADR 0013) y en la historia 0016 con vías pecuarias y
    Red Natura 2000 (ADR 0016).
    """
    parcel_report = report.report
    geometries = [parcel_report.parcel.geometry] + [b.geometry for b in parcel_report.buildings]
    points = _all_points(geometries)
    if not points:
        raise EmptyGeometryError(parcel_report.parcel.cadastral_reference)
    transform = _Transform(points)

    parcel_svg = _geometry_to_svg_paths(parcel_report.parcel.geometry, transform, "parcel")
    buildings_svg = "\n".join(
        _geometry_to_svg_paths(b.geometry, transform, "building") for b in parcel_report.buildings
    )

    buildings_rows = (
        "\n".join(
            f"<tr><td>{escape(b.cadastral_reference)}</td>"
            f"<td>{b.area_m2:.0f} m²</td>"
            f"<td>{b.construction_year if b.construction_year is not None else '—'}</td></tr>"
            for b in parcel_report.buildings
        )
        or '<tr><td colspan="3"><em>Sin edificios registrados en Catastro.</em></td></tr>'
    )

    parcel = parcel_report.parcel
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Parcel Intel — {escape(parcel.cadastral_reference)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  .meta {{ color: #555; margin-bottom: 1.5rem; }}
  .layout {{ display: flex; gap: 2rem; flex-wrap: wrap; align-items: flex-start; }}
  svg {{ background: #eef3ee; border: 1px solid #ccc; border-radius: 4px; }}
  path.parcel {{ fill: #cfe8cf; stroke: #2f7d32; stroke-width: 1.5; }}
  path.building {{ fill: #c99; stroke: #8a2e2e; stroke-width: 1; }}
  table {{ border-collapse: collapse; min-width: 320px; }}
  td, th {{ padding: 0.4rem 0.8rem; border-bottom: 1px solid #ddd; text-align: left; }}
  .badge {{ display: inline-block; padding: 0.1rem 0.5rem; border-radius: 3px;
            background: #fff3cd; color: #7a5b00; font-size: 0.8rem; }}
  .sources {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
  .sources > div {{ min-width: 260px; }}
  ul {{ padding-left: 1.2rem; }}
</style>
</head>
<body>
  <h1>Parcela {escape(parcel.cadastral_reference)}</h1>
  <p class="meta">
    {escape(parcel.municipality)} · {parcel.area_m2:.0f} m² · EPSG:{parcel.geometry.srid}
    <br><span class="badge">indicio a verificar — no es un dictamen jurídico</span>
  </p>
  <div class="layout">
    <svg viewBox="0 0 {_VIEWBOX_SIZE:.0f} {_VIEWBOX_SIZE:.0f}" width="420" height="420">
      {parcel_svg}
      {buildings_svg}
    </svg>
    <div>
      <h2>Edificios ({len(parcel_report.buildings)})</h2>
      <table>
        <thead><tr><th>Referencia</th><th>Superficie</th><th>Año construcción</th></tr></thead>
        <tbody>
          {buildings_rows}
        </tbody>
      </table>
      <p class="meta">
        Procedencia: {escape(parcel.provenance.source)}<br>
        Consultado: {parcel.provenance.retrieved_at.isoformat()}
      </p>
    </div>
  </div>

  <div class="sources">
    <div>
      <h2>Hallazgos</h2>
      {_render_findings_section(findings)}
    </div>
    <div>
      <h2>Ortofoto actual (PNOA)</h2>
      {_render_orthophoto_section(report)}
    </div>
    <div>
      <h2>NDVI (Sentinel-2)</h2>
      {_render_ndvi_section(report)}
    </div>
    <div>
      <h2>BOE — hoy</h2>
      {_render_bulletin_section(report.boe_notices, "BOE")}
    </div>
    <div>
      <h2>BOCM — hoy</h2>
      {_render_bulletin_section(report.bocm_notices, "BOCM")}
    </div>
    <div>
      <h2>Clasificación de suelo (IDEM)</h2>
      {_render_land_classification_section(report.land_classifications)}
    </div>
    <div>
      <h2>Cursos de agua cercanos</h2>
      {_render_watercourse_section(report.watercourses)}
    </div>
    <div>
      <h2>Peligrosidad por inundación</h2>
      {_render_flood_hazard_section(report.flood_hazard)}
    </div>
    <div>
      <h2>Vías pecuarias cercanas</h2>
      {_render_livestock_trail_section(report.livestock_trails)}
    </div>
    <div>
      <h2>Red Natura 2000</h2>
      {_render_protected_area_section(report.protected_areas)}
    </div>
  </div>
</body>
</html>
"""
