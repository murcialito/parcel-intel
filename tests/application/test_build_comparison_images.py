from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from tests.acceptance.test_historia_121 import FakePort, _line, _request


def test_los_bytes_no_se_guardan_en_el_resultado() -> None:
    result = BuildComparisonImagesUseCase(FakePort()).execute(_request(_line(80)))
    assert all(not hasattr(i, "image") for i in result.windows[0].images)


def test_fallo_no_expone_el_mensaje() -> None:
    port = FakePort(fail={"AMS_1956-1957": ConnectionError("http://secreto")})
    omitted = BuildComparisonImagesUseCase(port).execute(_request(_line(80))).windows[0].omitted
    assert "secreto" not in repr(omitted)
