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


def test_guardar_token_en_env(tmp_path: object) -> None:
    from pathlib import Path

    from scripts.autorizar_google import ENV_VAR, guardar_en_env

    ruta = Path(str(tmp_path)) / ".env"
    ruta.write_text("A=1\n")
    guardar_en_env(ruta, '{"x":1}')
    guardar_en_env(ruta, '{"x":2}')
    assert ruta.read_text() == f'A=1\n{ENV_VAR}={{"x":2}}\n'
