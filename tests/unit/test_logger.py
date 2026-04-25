"""Tests for src/utils/logger.py."""

import logging
from pathlib import Path

import pytest

from src.utils.logger import (
    _HealthCheckFilter,
    _ScrubSecretsFilter,
    get_logger,
    setup_logging,
)


class TestScrubSecretsFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        return record

    def test_scrubs_api_key_query_param(self):
        f = _ScrubSecretsFilter()
        record = self._make_record("GET /api?apikey=supersecret123")
        f.filter(record)
        assert "supersecret123" not in record.msg
        assert "***" in record.msg

    def test_scrubs_api_key_header_form(self):
        f = _ScrubSecretsFilter()
        record = self._make_record("api_key: abc123xyz")
        f.filter(record)
        assert "abc123xyz" not in record.msg

    def test_scrubs_authorization_header(self):
        f = _ScrubSecretsFilter()
        record = self._make_record("Authorization: mytoken999")
        f.filter(record)
        assert "mytoken999" not in record.msg
        assert "Authorization:" in record.msg

    def test_leaves_safe_messages_unchanged(self):
        f = _ScrubSecretsFilter()
        record = self._make_record("Starting scheduler job")
        result = f.filter(record)
        assert result is True
        assert record.msg == "Starting scheduler job"

    def test_always_returns_true(self):
        f = _ScrubSecretsFilter()
        record = self._make_record("anything")
        assert f.filter(record) is True


class TestHealthCheckFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="uvicorn.access", level=logging.INFO, pathname="",
            lineno=0, msg=msg, args=(), exc_info=None,
        )
        return record

    def test_drops_health_check_requests(self):
        f = _HealthCheckFilter()
        record = self._make_record('127.0.0.1 - "GET /api/health HTTP/1.1" 200')
        assert f.filter(record) is False

    def test_passes_other_requests(self):
        f = _HealthCheckFilter()
        record = self._make_record('127.0.0.1 - "GET /overview HTTP/1.1" 200')
        assert f.filter(record) is True


class TestSetupLogging:
    def test_creates_log_directory(self, tmp_path):
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        setup_logging(log_level="INFO", data_directory=tmp_path)
        assert log_dir.exists()

    def test_creates_log_files(self, tmp_path):
        setup_logging(log_level="DEBUG", data_directory=tmp_path)
        assert (tmp_path / "logs" / "boxarr.log").exists()
        assert (tmp_path / "logs" / "error.log").exists()

    def test_respects_log_level(self, tmp_path):
        setup_logging(log_level="WARNING", data_directory=tmp_path)
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_handles_permission_error_gracefully(self, tmp_path, monkeypatch):
        from logging.handlers import RotatingFileHandler

        original_init = RotatingFileHandler.__init__

        def raise_permission(*args, **kwargs):
            raise PermissionError("no write access")

        monkeypatch.setattr(RotatingFileHandler, "__init__", raise_permission)
        # Should not raise — falls back to stdout only
        setup_logging(log_level="INFO", data_directory=tmp_path)

    def test_suppresses_third_party_noise(self, tmp_path):
        setup_logging(log_level="DEBUG", data_directory=tmp_path)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_default_name(self):
        logger = get_logger()
        assert logger.name == "boxarr"

    def test_none_name(self):
        logger = get_logger(None)
        assert logger.name == "boxarr"
