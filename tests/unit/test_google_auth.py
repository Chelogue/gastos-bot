import json

from gastos_bot.storage.google_auth import SCOPE_DRIVE, SCOPE_SHEETS, get_credentials


def test_token_oauth_de_usuario_sin_red() -> None:
    token = json.dumps(
        {
            "client_id": "id",
            "client_secret": "secret",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "type": "authorized_user",
        }
    )
    creds = get_credentials((SCOPE_SHEETS, SCOPE_DRIVE), None, token)
    assert creds.refresh_token == "refresh" and set(creds.scopes) == {SCOPE_SHEETS, SCOPE_DRIVE}
