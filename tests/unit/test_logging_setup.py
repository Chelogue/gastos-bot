import io
import json

import structlog

from gastos_bot.logging_setup import bind_context, configure_logging, get_logger


def _lines(buf: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_json_con_severity_y_timestamp() -> None:
    buf = io.StringIO()
    configure_logging("INFO", "json", stream=buf)
    get_logger("test").info("hola", cosa=1)
    (line,) = _lines(buf)
    assert line["event"] == "hola"
    assert line["cosa"] == 1
    assert line["severity"] == "INFO"
    assert line["level"] == "info"
    assert "timestamp" in line


def test_bind_context_agrega_y_limpia_update_id() -> None:
    buf = io.StringIO()
    configure_logging("INFO", "json", stream=buf)
    log = get_logger()
    with bind_context(update_id=42, telegram_id=None):
        log.info("dentro")
    log.info("fuera")
    dentro, fuera = _lines(buf)
    assert dentro["update_id"] == 42
    assert "telegram_id" not in dentro
    assert "update_id" not in fuera


def test_nivel_filtra() -> None:
    buf = io.StringIO()
    configure_logging("WARNING", "json", stream=buf)
    log = get_logger()
    log.info("no sale")
    log.warning("sale")
    (line,) = _lines(buf)
    assert line["event"] == "sale"


def test_console_no_rompe() -> None:
    buf = io.StringIO()
    configure_logging("INFO", "console", stream=buf)
    get_logger().info("visible")
    assert "visible" in buf.getvalue()
    structlog.reset_defaults()
