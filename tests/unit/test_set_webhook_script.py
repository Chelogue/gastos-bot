import pytest

from scripts.set_webhook import validar_url


def test_url_valida() -> None:
    assert validar_url("https://x.a.run.app/webhook") == "https://x.a.run.app/webhook"


@pytest.mark.parametrize(
    "url", ["http://x.a.run.app/webhook", "https://x.a.run.app/", "https:///webhook", "x"]
)
def test_url_invalida(url: str) -> None:
    with pytest.raises(SystemExit):
        validar_url(url)
