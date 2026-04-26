"""Tests for /api/config routes."""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.config import settings


class TestGetConfiguration:
    def test_returns_config_response(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "radarr_url" in data
        assert "radarr_configured" in data
        assert "scheduler_enabled" in data
        assert "auto_add" in data

    def test_masks_api_key(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "secretkey123")
        resp = client.get("/api/config")
        data = resp.json()
        assert data["radarr_api_key"] == "***"
        assert "secretkey123" not in resp.text

    def test_empty_api_key_not_masked(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.get("/api/config")
        data = resp.json()
        assert data["radarr_api_key"] == ""
        assert data["radarr_configured"] is False


class TestGetRootFolderConfiguration:
    def test_returns_root_folder_config(self, client):
        resp = client.get("/api/config/root-folders")
        assert resp.status_code == 200
        data = resp.json()
        assert "default_root_folder" in data
        assert "config" in data
        assert "enabled" in data["config"]
        assert "mappings" in data["config"]


class TestTestConfiguration:
    def test_connection_failure_returns_failure(self, client):
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = False
            mock_cls.return_value = instance

            resp = client.post(
                "/api/config/test",
                json={"url": "http://localhost:7878", "api_key": "badkey"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_connection_success_returns_profiles(self, client):
        profile = MagicMock()
        profile.id = 1
        profile.name = "HD-1080p"
        folder = {"path": "/movies", "freeSpace": 100000}
        status_resp = {"version": "4.0.0"}

        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = True
            instance.get_quality_profiles.return_value = [profile]
            instance.get_root_folders.return_value = [folder]
            instance.get_system_status.return_value = status_resp
            mock_cls.return_value = instance

            resp = client.post(
                "/api/config/test",
                json={"url": "http://localhost:7878", "api_key": "goodkey"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["profiles"]) == 1
        assert data["profiles"][0]["name"] == "HD-1080p"

    def test_exception_returns_failure(self, client):
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            mock_cls.side_effect = Exception("connection refused")
            resp = client.post(
                "/api/config/test",
                json={"url": "http://bad-host", "api_key": "x"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestSaveConfiguration:
    def test_invalid_cron_returns_failure(self, client):
        resp = client.post(
            "/api/config/save",
            json={
                "radarr_url": "http://localhost:7878",
                "radarr_api_key": "key",
                "boxarr_scheduler_enabled": True,
                "boxarr_scheduler_cron": "NOT A VALID CRON",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "cron" in data["message"].lower() or "Invalid" in data["message"]

    def test_radarr_connection_failure_returns_failure(self, client):
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = False
            mock_cls.return_value = instance

            resp = client.post(
                "/api/config/save",
                json={
                    "radarr_url": "http://localhost:7878",
                    "radarr_api_key": "key",
                    "boxarr_scheduler_enabled": False,
                    "boxarr_scheduler_cron": "0 23 * * 2",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "connection" in data["message"].lower() or "Cannot" in data["message"]

    def test_successful_save_writes_yaml(self, client, isolated_data_dir):
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = True
            mock_cls.return_value = instance

            resp = client.post(
                "/api/config/save",
                json={
                    "radarr_url": "http://localhost:7878",
                    "radarr_api_key": "validkey",
                    "radarr_root_folder": "/movies",
                    "boxarr_scheduler_enabled": True,
                    "boxarr_scheduler_cron": "0 23 * * 2",
                    "boxarr_features_auto_add": True,
                    "boxarr_features_quality_upgrade": False,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert (isolated_data_dir / "local.yaml").exists()


class TestCheckForUpdate:
    def _mock_async_client(
        self, mock_cls, *, status_code=200, data=None, raise_exc=None
    ):
        """Helper to set up an async httpx client mock."""
        instance = MagicMock()

        async def _aenter(*a, **kw):
            return instance

        async def _aexit(*a, **kw):
            return False

        if raise_exc is not None:

            async def _get(*a, **kw):
                raise raise_exc

        else:

            async def _get(*a, **kw):
                resp = MagicMock()
                resp.status_code = status_code
                resp.json.return_value = data or {}
                return resp

        instance.__aenter__ = _aenter
        instance.__aexit__ = _aexit
        instance.get = _get
        mock_cls.return_value = instance

    def test_returns_no_update_on_exception(self, client):
        with patch("src.api.routes.config.httpx") as mock_httpx:
            import httpx

            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.AsyncClient.side_effect = RuntimeError("network down")
            resp = client.get("/api/config/check-update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["update_available"] is False

    def test_returns_no_update_on_timeout(self, client):
        import httpx

        with patch("src.api.routes.config.httpx.AsyncClient") as mock_cls:
            self._mock_async_client(
                mock_cls, raise_exc=httpx.TimeoutException("timeout")
            )
            resp = client.get("/api/config/check-update")
        assert resp.status_code == 200
        assert resp.json()["update_available"] is False

    def test_update_available_when_newer_version(self, client):
        with (
            patch("src.api.routes.config.httpx.AsyncClient") as mock_cls,
            patch("src.api.routes.config.__version__", "0.1.0"),
        ):
            self._mock_async_client(
                mock_cls,
                status_code=200,
                data={
                    "tag_name": "v9.9.9",
                    "html_url": "https://github.com/example/release",
                    "name": "v9.9.9",
                    "published_at": "2025-01-01T00:00:00Z",
                },
            )
            resp = client.get("/api/config/check-update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["update_available"] is True
        assert data["latest_version"] == "9.9.9"
        assert data["changelog_url"] is not None

    def test_no_update_when_on_latest(self, client):
        with (
            patch("src.api.routes.config.httpx.AsyncClient") as mock_cls,
            patch("src.api.routes.config.__version__", "99.0.0"),
        ):
            self._mock_async_client(
                mock_cls,
                status_code=200,
                data={
                    "tag_name": "v1.0.0",
                    "html_url": None,
                    "name": None,
                    "published_at": None,
                },
            )
            resp = client.get("/api/config/check-update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["update_available"] is False
        assert data["changelog_url"] is None

    def test_non_200_response_returns_no_update(self, client):
        with patch("src.api.routes.config.httpx.AsyncClient") as mock_cls:
            self._mock_async_client(mock_cls, status_code=503, data={})
            resp = client.get("/api/config/check-update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["update_available"] is False


class TestSaveConfigurationExtended:
    def test_save_with_upgrade_profile(self, client, isolated_data_dir, monkeypatch):
        """Covers the radarr_quality_profile_upgrade non-empty branch."""
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = True
            mock_cls.return_value = instance
            resp = client.post(
                "/api/config/save",
                json={
                    "radarr_url": "http://localhost:7878",
                    "radarr_api_key": "testkey",
                    "boxarr_scheduler_enabled": False,
                    "boxarr_scheduler_cron": "0 23 * * 2",
                    "radarr_quality_profile_upgrade": "Ultra-HD",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_save_with_root_folder_config(self, client, isolated_data_dir, monkeypatch):
        """Covers root_folder_config post branch with mappings."""
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = True
            mock_cls.return_value = instance
            resp = client.post(
                "/api/config/save",
                json={
                    "radarr_url": "http://localhost:7878",
                    "radarr_api_key": "testkey",
                    "boxarr_scheduler_enabled": False,
                    "boxarr_scheduler_cron": "0 23 * * 2",
                    "radarr_root_folder_config": {
                        "enabled": True,
                        "mappings": [
                            {
                                "genres": ["Animation"],
                                "root_folder": "/anime",
                                "priority": 0,
                            }
                        ],
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_save_exception_returns_failure(
        self, client, isolated_data_dir, monkeypatch
    ):
        """Covers the outer except block in save_configuration."""
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = True
            mock_cls.return_value = instance
            # Force an exception by making settings write fail
            with patch("src.api.routes.config.Settings") as mock_settings_cls:
                mock_settings_cls.side_effect = RuntimeError("unexpected config error")
                resp = client.post(
                    "/api/config/save",
                    json={
                        "radarr_url": "http://localhost:7878",
                        "radarr_api_key": "testkey",
                        "boxarr_scheduler_enabled": False,
                        "boxarr_scheduler_cron": "0 23 * * 2",
                    },
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_test_connection_version_exception(self, client):
        """Covers the try/except around get_system_status."""
        with patch("src.api.routes.config.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.test_connection.return_value = True
            instance.get_quality_profiles.return_value = []
            instance.get_root_folders.return_value = []
            instance.get_system_status.side_effect = RuntimeError("version unavailable")
            mock_cls.return_value = instance
            resp = client.post(
                "/api/config/test",
                json={"url": "http://localhost:7878", "api_key": "key"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["version"] == "Unknown"  # fallback
