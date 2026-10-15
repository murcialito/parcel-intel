from html import escape

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.report import ParcelReport

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
        super().__init__(
            f"La parcela {cadastral_reference!r} no tiene geometría que renderizar"
        )


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


def render_parcel_report_html(report: ParcelReport) -> str:
    """Renderiza el informe de una parcela como una página HTML autocontenida.

    Es deliberadamente simple (sin plantillas de terceros, solo f-strings):
    esta historia busca tener algo visible cuanto antes, no el render final
    del informe de `docs/vision.md` (que todavía no tiene hallazgos ni
    reglas que mostrar).
    """
    geometries = [report.parcel.geometry] + [b.geometry for b in report.buildings]
    points = _all_points(geometries)
    if not points:
        raise EmptyGeometryError(report.parcel.cadastral_reference)
    transform = _Transform(points)

    parcel_svg = _geometry_to_svg_paths(report.parcel.geometry, transform, "parcel")
    buildings_svg = "\n".join(
        _geometry_to_svg_paths(b.geometry, transform, "building") for b in report.buildings
    )

    buildings_rows = (
        "\n".join(
            f"<tr><td>{escape(b.cadastral_reference)}</td>"
            f"<td>{b.area_m2:.0f} m²</td>"
            f"<td>{b.construction_year if b.construction_year is not None else '—'}</td></tr>"
            for b in report.buildings
        )
        or "<tr><td colspan=\"3\"><em>Sin edificios registrados en Catastro.</em></td></tr>"
    )

    parcel = report.parcel
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Parcel Intel — {escape(parcel.cadastral_reference)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.4rem; }}
  .meta {{ color: #555; margin-bottom: 1.5rem; }}
  .layout {{ display: flex; gap: 2rem; flex-wrap: wrap; align-items: flex-start; }}
  svg {{ background: #eef3ee; border: 1px solid #ccc; border-radius: 4px; }}
  path.parcel {{ fill: #cfe8cf; stroke: #2f7d32; stroke-width: 1.5; }}
  path.building {{ fill: #c99; stroke: #8a2e2e; stroke-width: 1; }}
  table {{ border-collapse: collapse; min-width: 320px; }}
  td, th {{ padding: 0.4rem 0.8rem; border-bottom: 1px solid #ddd; text-align: left; }}
  .badge {{ display: inline-block; padding: 0.1rem 0.5rem; border-radius: 3px;
            background: #fff3cd; color: #7a5b00; font-size: 0.8rem; }}
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
      <h2>Edificios ({len(report.buildings)})</h2>
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
</body>
</html>
"""
