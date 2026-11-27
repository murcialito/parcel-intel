from collections.abc import Sequence
from datetime import date

from parcel_intel.application.kit_campo import PublishFieldKitUseCase
from parcel_intel.domain.kit_campo import (
    KitGeometry,
    KitLayerId,
    MunicipalKit,
    PublishedFeature,
    PublishedKitFile,
    PublishedLayerFile,
)
from parcel_intel.ports.kit_campo import PublishedLayerFileError

LINE = KitGeometry(lines=(((-3.5, 40.0), (-3.4, 40.1)),))


class FakeSource:
    def __init__(self, files: dict[tuple[str, str], PublishedLayerFile | Exception]) -> None:
        self._files = files

    def read(self, layer: KitLayerId, municipality_code: str) -> PublishedLayerFile | None:
        item = self._files.get((layer, municipality_code))
        if isinstance(item, Exception):
            raise item
        return item


class FakeSink:
    def __init__(self) -> None:
        self.calls: list[Sequence[MunicipalKit]] = []

    def write(self, kits: Sequence[MunicipalKit]) -> tuple[PublishedKitFile, ...]:
        self.calls.append(kits)
        return tuple(PublishedKitFile(k.municipality_code, "x", 1) for k in kits)


def trail_file(layer: KitLayerId, code: str) -> PublishedLayerFile:
    return PublishedLayerFile(
        layer, code, (PublishedFeature("t", LINE, {"nombre": "n"}),), "f", "l", ("a",), "aviso"
    )


DAY = date(2026, 11, 27)


def test_incluye_las_capas_publicadas_y_anota_las_que_faltan() -> None:
    sink = FakeSink()
    source = FakeSource({("camino_actual", "28043"): trail_file("camino_actual", "28043")})
    result = PublishFieldKitUseCase(source, sink).execute(["28043"], DAY)
    assert result.failures == ()
    assert result.included == (
        ("28043", ("camino_actual",), ("vias_pecuarias", "discrepancias", "candidatos")),
    )
    assert sink.calls[0][0].generated_on == DAY


def test_un_municipio_sin_capas_falla_y_no_escribe_ninguno() -> None:
    sink = FakeSink()
    source = FakeSource({("camino_actual", "28043"): trail_file("camino_actual", "28043")})
    result = PublishFieldKitUseCase(source, sink).execute(["28043", "28013"], DAY)
    assert [f.municipality_code for f in result.failures] == ["28013"]
    assert sink.calls == []
    assert result.published == ()


def test_un_fichero_corrupto_es_un_fallo_del_municipio() -> None:
    sink = FakeSink()
    source = FakeSource({("camino_actual", "28043"): PublishedLayerFileError("roto")})
    result = PublishFieldKitUseCase(source, sink).execute(["28043"], DAY)
    assert result.failures[0].reason == "roto"
    assert sink.calls == []


def test_un_fichero_de_otro_municipio_falla() -> None:
    sink = FakeSink()
    source = FakeSource({("camino_actual", "28043"): trail_file("camino_actual", "28013")})
    result = PublishFieldKitUseCase(source, sink).execute(["28043"], DAY)
    assert result.failures and sink.calls == []
