import pytest

from scripts.create_sheet import parse_ids


def test_parse_ids() -> None:
    assert parse_ids(None) == {}
    assert parse_ids("Marcelo=111, Nikole=222") == {"Marcelo": 111, "Nikole": 222}


@pytest.mark.parametrize("raw", ["Marcelo", "=111", "Marcelo=abc"])
def test_parse_ids_invalido(raw: str) -> None:
    with pytest.raises(SystemExit):
        parse_ids(raw)
