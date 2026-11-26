"""Caso de uso `PublishLayersUseCase` con dobles en memoria. Datos SINTÉTICOS."""

from collections.abc import Sequence
from datetime import date

import pytest

from parcel_intel.application.publish_layers import PublishLayersUseCase
from parcel_intel.domain.discrepancy_report import TrailLayer
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.published_layers import PublishedFile, TrailLayerPublication
from parcel_intel.domain.trail import SourceKind, Trail
from parcel_intel.ports.errors import TrailLayerUnavailableError

VP: SourceKind = "via_pecuaria_oficial"
RT: SourceKind = "ign_red_transporte"
PUBLIC = Provenance(
    "sintética", "https://example.invalid", date(2026, 11, 26), "CC BY 4.0", Redistribution.PUBLIC
)


def _trail(source: SourceKind, code: str) -> Trail:
    return Trail(
        identifier="T1",
        source=source,
        role="via",
        name=None,
        trail_type=None,
        municipality_code=code,
        geometry=MultiLineGeometry(lines=(((0.0, 0.0), (1.0, 1.0)),), srid=25830),
        provenance=PUBLIC,
        data_date=None,
        character="sintética",
    )


class _Layers:
    def __init__(self, layers: dict[tuple[SourceKind, str], TrailLayer | Exception]) -> None:
        self._layers = layers
        self.calls: list[tuple[SourceKind, str]] = []

    def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
        self.calls.append((source, municipality_code))
        value = self._layers.get((source, municipality_code))
        if value is None:
            raise TrailLayerUnavailableError(source, municipality_code, "sin fichero")
        if isinstance(value, Exception):
            raise value
        return value


class _Sink:
    def __init__(self) -> None:
        self.calls: list[tuple[TrailLayerPublication, ...]] = []

    def publish(self, publications: Sequence[TrailLayerPublication]) -> tuple[PublishedFile, ...]:
        self.calls.append(tuple(publications))
        return tuple(
            PublishedFile(p.spec.layer_id, p.municipality_code, "x", 1, None, False)
            for p in publications
        )


def _layer(
    source: SourceKind, code: str, *, empty: bool = False, name: str | None = "M"
) -> TrailLayer:
    trails = () if empty else (_trail(source, code),)
    return TrailLayer(source, code, PUBLIC, trails, name, None)


def test_publica_en_orden_municipio_y_capa_con_una_sola_llamada_al_sink() -> None:
    layers = _Layers(
        {
            (VP, "28001"): _layer(VP, "28001"),
            (RT, "28001"): _layer(RT, "28001"),
            (VP, "28002"): _layer(VP, "28002"),
            (RT, "28002"): _layer(RT, "28002"),
        }
    )
    sink = _Sink()

    result = PublishLayersUseCase(layers, sink).execute(["28002", "28001"])

    assert layers.calls == [(VP, "28002"), (RT, "28002"), (VP, "28001"), (RT, "28001")]
    assert len(sink.calls) == 1
    assert [(p.spec.layer_id, p.municipality_code) for p in sink.calls[0]] == [
        ("vias_pecuarias", "28002"),
        ("camino_actual", "28002"),
        ("vias_pecuarias", "28001"),
        ("camino_actual", "28001"),
    ]
    assert len(result.published) == 4
    assert result.failures == ()


def test_solo_las_capas_pedidas() -> None:
    layers = _Layers({(RT, "28001"): _layer(RT, "28001")})
    sink = _Sink()

    result = PublishLayersUseCase(layers, sink).execute(["28001"], ["camino_actual"])

    assert layers.calls == [(RT, "28001")]
    assert [f.layer_id for f in result.published] == ["camino_actual"]


def test_sin_capa_es_fallo_y_no_se_llama_al_sink() -> None:
    sink = _Sink()

    result = PublishLayersUseCase(_Layers({(VP, "28001"): _layer(VP, "28001")}), sink).execute(
        ["28001"]
    )

    assert sink.calls == []
    assert result.published == ()
    assert [(f.layer_id, f.municipality_code) for f in result.failures] == [
        ("camino_actual", "28001")
    ]
    assert result.failures[0].reason.startswith("sin capa: ")


def test_un_fichero_corrupto_se_propaga_sin_llamar_al_sink() -> None:
    sink = _Sink()
    layers = _Layers({(VP, "28001"): ValueError("corrupto")})

    with pytest.raises(ValueError, match="corrupto"):
        PublishLayersUseCase(layers, sink).execute(["28001"])
    assert sink.calls == []


def test_capa_vacia_publicable_no_se_publica() -> None:
    sink = _Sink()
    layers = _Layers(
        {(VP, "28001"): _layer(VP, "28001", empty=True), (RT, "28001"): _layer(RT, "28001")}
    )

    result = PublishLayersUseCase(layers, sink).execute(["28001"])

    assert result.empty == (("vias_pecuarias", "28001"),)
    assert [p.spec.layer_id for p in sink.calls[0]] == ["camino_actual"]


def test_todo_vacio_no_llama_al_sink() -> None:
    sink = _Sink()
    layers = _Layers(
        {
            (VP, "28001"): _layer(VP, "28001", empty=True),
            (RT, "28001"): _layer(RT, "28001", empty=True),
        }
    )

    result = PublishLayersUseCase(layers, sink).execute(["28001"])

    assert sink.calls == []
    assert len(result.empty) == 2
    assert result.failures == ()


def test_capa_sin_nombre_de_municipio_es_fallo() -> None:
    sink = _Sink()
    layers = _Layers(
        {(VP, "28001"): _layer(VP, "28001", name=None), (RT, "28001"): _layer(RT, "28001")}
    )

    result = PublishLayersUseCase(layers, sink).execute(["28001"])

    assert sink.calls == []
    assert "sin nombre de municipio" in result.failures[0].reason


def test_capa_de_otra_fuente_es_fallo() -> None:
    sink = _Sink()
    layers = _Layers({(VP, "28001"): _layer(RT, "28001"), (RT, "28001"): _layer(RT, "28001")})

    result = PublishLayersUseCase(layers, sink).execute(["28001"])

    assert sink.calls == []
    assert "ign_red_transporte" in result.failures[0].reason


def test_no_redistribuible_nombra_la_procedencia() -> None:
    internal = Provenance("idem", "https://example.invalid/interna", date(2026, 11, 26), "x")
    sink = _Sink()
    layers = _Layers(
        {
            (VP, "28001"): TrailLayer(VP, "28001", internal, (), "M"),
            (RT, "28001"): _layer(RT, "28001"),
        }
    )

    result = PublishLayersUseCase(layers, sink).execute(["28001"])

    assert sink.calls == []
    reason = result.failures[0].reason
    assert reason.startswith("no redistribuible")
    assert "https://example.invalid/interna" in reason
    assert "solo_uso_interno" in reason
