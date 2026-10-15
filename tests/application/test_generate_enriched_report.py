from datetime import date

import pytest

from parcel_intel.application.generate_enriched_report import (
    GenerateEnrichedParcelReportUseCase,
)
from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.ndvi import Grid, NdviGrid
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.report import ParcelReport
from parcel_intel.ports.errors import BulletinNotPublishedError, NoScenesAfterCloudFilterError
from tests.factories import make_parcel, make_provenance


class _FakeBaseRepository:
    """Repositorio ya poblado: `GenerateParcelReportUseCase` nunca llega a
    pedirle nada a Catastro, el foco de estos tests es el caso de uso
    enriquecido, no el ya cubierto en `test_generate_report.py`."""

    def __init__(self, cached_report: ParcelReport) -> None:
        self._cached_report = cached_report

    def get_report(self, cadastral_reference: str) -> ParcelReport:
        return self._cached_report

    def save_report(self, report: ParcelReport) -> None:
        raise AssertionError("no debería intentar guardar, el informe ya está cacheado")


class FakeOrthophotoPort:
    def __init__(
        self, orthophoto: Orthophoto | None = None, raises: Exception | None = None
    ) -> None:
        self._orthophoto = orthophoto
        self._raises = raises
        self.calls: list[tuple[Geometry, float]] = []

    def get_current_orthophoto(self, geometry: Geometry, margin_m: float) -> Orthophoto:
        self.calls.append((geometry, margin_m))
        if self._raises is not None:
            raise self._raises
        assert self._orthophoto is not None
        return self._orthophoto

    def get_historical_orthophoto(
        self, geometry: Geometry, margin_m: float, vintage: object
    ) -> Orthophoto:
        raise NotImplementedError


class FakeNdviSeriesPort:
    def __init__(
        self, grids: list[NdviGrid] | None = None, raises: Exception | None = None
    ) -> None:
        self._grids = grids if grids is not None else []
        self._raises = raises
        self.calls: list[tuple[Geometry, float, date, date, float]] = []

    def get_ndvi_series(
        self,
        geometry: Geometry,
        margin_m: float,
        start: date,
        end: date,
        max_cloud_cover_percent: float,
    ) -> list[NdviGrid]:
        self.calls.append((geometry, margin_m, start, end, max_cloud_cover_percent))
        if self._raises is not None:
            raise self._raises
        return self._grids


class FakeBulletinPort:
    def __init__(
        self, notices: list[BulletinNotice] | None = None, raises: Exception | None = None
    ) -> None:
        self._notices = notices if notices is not None else []
        self._raises = raises
        self.calls: list[str] = []

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        self.calls.append(day)
        if self._raises is not None:
            raise self._raises
        return self._notices


class _UnusedPort:
    """Ni `parcel_port` ni `building_port` deberían llamarse: el repositorio
    ya tiene un informe cacheado, así que `GenerateParcelReportUseCase`
    nunca toca Catastro."""

    def get_parcel(self, cadastral_reference: str) -> object:
        raise AssertionError("no debería llamar a Catastro con informe cacheado")

    def get_buildings(self, cadastral_reference: str) -> object:
        raise AssertionError("no debería llamar a Catastro con informe cacheado")


def _base_use_case() -> GenerateParcelReportUseCase:
    parcel = make_parcel(municipality="COLMENAR DE OREJA")
    unused_port = _UnusedPort()
    return GenerateParcelReportUseCase(
        parcel_port=unused_port,  # type: ignore[arg-type]
        building_port=unused_port,  # type: ignore[arg-type]
        repository=_FakeBaseRepository(cached_report=ParcelReport(parcel=parcel, buildings=())),
    )


def _fixed_today() -> date:
    return date(2026, 10, 15)


def _orthophoto() -> Orthophoto:
    return Orthophoto(image=b"fake-jpeg", vintage="actual", provenance=make_provenance("pnoa"))


def _ndvi_grid(scene_date: date = date(2026, 9, 1)) -> NdviGrid:
    values: Grid = ((0.2, 0.4), (0.6, float("nan")))
    return NdviGrid(
        values=values,
        bbox=(0.0, 0.0, 10.0, 10.0),
        srid=25830,
        scene_date=scene_date,
        cloud_cover_percent=10.0,
        provenance=make_provenance("sentinel2"),
    )


def _notice(title: str = "Convenio con el Ayuntamiento de Colmenar de Oreja") -> BulletinNotice:
    return BulletinNotice(
        identifier="BOCM-20261015-32",
        title=title,
        section_code="I",
        section_name="COMUNIDAD DE MADRID",
        pdf_url="https://example.org/x.pdf",
        provenance=make_provenance("bocm"),
    )


def test_todas_las_fuentes_disponibles_componen_el_informe_enriquecido() -> None:
    orthophoto_port = FakeOrthophotoPort(orthophoto=_orthophoto())
    ndvi_port = FakeNdviSeriesPort(grids=[_ndvi_grid()])
    boe_port = FakeBulletinPort(notices=[_notice("Disposición sin relación con el municipio")])
    bocm_port = FakeBulletinPort(notices=[_notice()])
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=orthophoto_port,
        ndvi_port=ndvi_port,
        boe_port=boe_port,
        bocm_port=bocm_port,
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is not None
    assert enriched.ndvi_summary.mean == pytest.approx((0.2 + 0.4 + 0.6) / 3)
    assert enriched.boe_notices == ()
    assert enriched.bocm_notices == (_notice(),)
    assert boe_port.calls == ["20261015"]
    assert bocm_port.calls == ["20261015"]


def test_fallo_de_pnoa_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(raises=RuntimeError("timeout")),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is None
    assert enriched.ndvi_summary is not None
    assert enriched.boe_notices == (_notice(),)
    assert enriched.bocm_notices == (_notice(),)
    assert enriched.report.parcel.municipality == "COLMENAR DE OREJA"


def test_fallo_de_sentinel2_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(
            raises=NoScenesAfterCloudFilterError(
                (0.0, 0.0, 1.0, 1.0), date(2026, 7, 1), date(2026, 10, 15), 40.0
            )
        ),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is None
    assert enriched.boe_notices == (_notice(),)
    assert enriched.bocm_notices == (_notice(),)


def test_fallo_de_boe_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(raises=BulletinNotPublishedError("20261015")),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is not None
    assert enriched.boe_notices is None
    assert enriched.bocm_notices == (_notice(),)


def test_fallo_de_bocm_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(raises=BulletinNotPublishedError("20261015")),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is not None
    assert enriched.boe_notices == (_notice(),)
    assert enriched.bocm_notices is None


def test_boletin_sin_coincidencias_devuelve_tupla_vacia_no_none() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice("Disposición sin relación con el municipio")]),
        bocm_port=FakeBulletinPort(notices=[]),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.boe_notices == ()
    assert enriched.bocm_notices == ()


def test_dia_consultado_es_el_today_inyectado_no_la_fecha_real() -> None:
    boe_port = FakeBulletinPort(notices=[])
    bocm_port = FakeBulletinPort(notices=[])
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=boe_port,
        bocm_port=bocm_port,
        today=lambda: date(2020, 1, 1),
    )

    use_case.execute("REFCAT-RETIRADA")

    assert boe_port.calls == ["20200101"]
    assert bocm_port.calls == ["20200101"]
