import logging

import taf.log as taf_log
import taf.settings as settings


def test_initialize_logger_handlers_silences_tuf_logger_by_default(monkeypatch):
    monkeypatch.setattr(settings, "VERBOSITY", 0)
    taf_log.initialize_logger_handlers()
    assert logging.getLogger("tuf").getEffectiveLevel() == logging.WARNING


def test_initialize_logger_handlers_enables_tuf_logger_at_debug_verbosity(monkeypatch):
    monkeypatch.setattr(settings, "VERBOSITY", 2)
    taf_log.initialize_logger_handlers()
    assert logging.getLogger("tuf").getEffectiveLevel() == logging.DEBUG

    monkeypatch.setattr(settings, "VERBOSITY", 0)
    taf_log.initialize_logger_handlers()
    assert logging.getLogger("tuf").getEffectiveLevel() == logging.WARNING


def test_initialize_logger_handlers_ignores_a_permissive_root_config(monkeypatch):
    monkeypatch.setattr(settings, "VERBOSITY", 0)
    original_root_handlers = logging.root.handlers[:]
    original_root_level = logging.root.level
    try:
        # simulate an app embedding taf that configures logging permissively
        logging.basicConfig(level=logging.INFO, force=True)
        taf_log.initialize_logger_handlers()
        assert logging.getLogger("tuf.api._payload").getEffectiveLevel() == (
            logging.WARNING
        )
    finally:
        logging.root.handlers = original_root_handlers
        logging.root.level = original_root_level
