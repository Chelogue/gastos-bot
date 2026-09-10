from pydantic import SecretStr

from gastos_bot.auth import telegram_secret_is_valid

EXPECTED = SecretStr("un-secreto-bien-largo-123")


def test_valido() -> None:
    assert telegram_secret_is_valid("un-secreto-bien-largo-123", EXPECTED)


def test_invalido_o_ausente() -> None:
    assert not telegram_secret_is_valid("otro", EXPECTED)
    assert not telegram_secret_is_valid("", EXPECTED)
    assert not telegram_secret_is_valid(None, EXPECTED)
