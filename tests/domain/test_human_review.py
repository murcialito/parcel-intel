import pytest

from parcel_intel.domain.human_review import GITHUB_USER_RE, is_github_user


@pytest.mark.parametrize("value", ["a", "murcialito", "revisora-sintetica", "A1-b2", "a" * 39])
def test_usuarios_validos(value: str) -> None:
    assert is_github_user(value)
    assert GITHUB_USER_RE.fullmatch(value)


@pytest.mark.parametrize(
    "value", ["", "-empieza", "a" * 40, "con espacio", "tilde-á", "a_b", None, 3, b"bytes"]
)
def test_usuarios_no_validos(value: object) -> None:
    assert not is_github_user(value)
