"""Tests for src/core/root_folder_manager.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.root_folder_manager import RootFolderManager
from src.utils.config import settings


class TestGetAvailableRootFolders:
    def test_no_radarr_service_returns_default(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_root_folder", "/movies")
        mgr = RootFolderManager(radarr_service=None)
        folders = mgr.get_available_root_folders()
        assert "/movies" in folders

    def test_radarr_service_returns_folders(self):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies", "/anime"]
        mgr = RootFolderManager(radarr_service=svc)
        folders = mgr.get_available_root_folders()
        assert "/movies" in folders
        assert "/anime" in folders

    def test_caches_result(self):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies"]
        mgr = RootFolderManager(radarr_service=svc)
        mgr.get_available_root_folders()
        mgr.get_available_root_folders()
        svc.get_root_folder_paths.assert_called_once()

    def test_radarr_error_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_root_folder", "/fallback")
        svc = MagicMock()
        svc.get_root_folder_paths.side_effect = RuntimeError("network error")
        mgr = RootFolderManager(radarr_service=svc)
        folders = mgr.get_available_root_folders()
        assert "/fallback" in folders

    def test_clear_cache(self):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies"]
        mgr = RootFolderManager(radarr_service=svc)
        mgr.get_available_root_folders()
        mgr.clear_cache()
        mgr.get_available_root_folders()
        assert svc.get_root_folder_paths.call_count == 2


class TestValidateRootFolder:
    def test_valid_folder_returns_true(self):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies", "/anime"]
        mgr = RootFolderManager(radarr_service=svc)
        assert mgr.validate_root_folder("/movies") is True

    def test_invalid_folder_returns_false(self):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies"]
        mgr = RootFolderManager(radarr_service=svc)
        assert mgr.validate_root_folder("/docs") is False


class TestDetermineRootFolder:
    def test_returns_default_when_mapping_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_root_folder", "/movies")
        with patch("src.core.root_folder_manager.settings") as mock_settings:
            mock_settings.radarr_root_folder = "/movies"
            mock_settings.radarr_root_folder_config.enabled = False
            mgr = RootFolderManager()
            result = mgr.determine_root_folder(genres=["Action"])
        assert result == "/movies"

    def test_uses_genre_mapping_when_available(self, monkeypatch):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies", "/anime"]
        with patch("src.core.root_folder_manager.settings") as mock_settings:
            mock_settings.radarr_root_folder = "/movies"
            mock_settings.radarr_root_folder_config.enabled = True
            mock_settings.get_root_folder_for_genres.return_value = "/anime"
            mgr = RootFolderManager(radarr_service=svc)
            result = mgr.determine_root_folder(
                genres=["Animation"], movie_title="Spirited Away"
            )
        assert result == "/anime"

    def test_falls_back_when_mapped_folder_unavailable(self):
        svc = MagicMock()
        svc.get_root_folder_paths.return_value = ["/movies"]
        with patch("src.core.root_folder_manager.settings") as mock_settings:
            mock_settings.radarr_root_folder = "/movies"
            mock_settings.radarr_root_folder_config.enabled = True
            mock_settings.get_root_folder_for_genres.return_value = "/unavailable"
            mgr = RootFolderManager(radarr_service=svc)
            result = mgr.determine_root_folder(genres=["Action"])
        assert result == "/movies"

    def test_no_genres_returns_default(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_root_folder", "/movies")
        mgr = RootFolderManager()
        result = mgr.determine_root_folder(genres=None)
        assert result == "/movies"


class TestGetFolderStats:
    def test_no_radarr_service_returns_empty(self):
        mgr = RootFolderManager()
        assert mgr.get_folder_stats() == {}

    def test_returns_stats_from_radarr(self):
        svc = MagicMock()
        svc.get_root_folders.return_value = [
            {"path": "/movies", "id": 1, "accessible": True, "freeSpace": 100}
        ]
        mgr = RootFolderManager(radarr_service=svc)
        stats = mgr.get_folder_stats()
        assert "/movies" in stats
        assert stats["/movies"]["accessible"] is True

    def test_radarr_error_returns_empty(self):
        svc = MagicMock()
        svc.get_root_folders.side_effect = RuntimeError("error")
        mgr = RootFolderManager(radarr_service=svc)
        assert mgr.get_folder_stats() == {}


class TestSuggestFolderForGenres:
    def test_returns_none_when_disabled(self):
        with patch("src.core.root_folder_manager.settings") as mock_settings:
            mock_settings.radarr_root_folder_config.enabled = False
            mgr = RootFolderManager()
            result = mgr.suggest_folder_for_genres(["Action"])
        assert result is None

    def test_returns_mapped_folder(self):
        with patch("src.core.root_folder_manager.settings") as mock_settings:
            mock_settings.radarr_root_folder = "/movies"
            mock_settings.radarr_root_folder_config.enabled = True
            mock_settings.get_root_folder_for_genres.return_value = "/anime"
            mgr = RootFolderManager()
            result = mgr.suggest_folder_for_genres(["Animation"])
        assert result == "/anime"

    def test_returns_none_when_same_as_default(self):
        with patch("src.core.root_folder_manager.settings") as mock_settings:
            mock_settings.radarr_root_folder = "/movies"
            mock_settings.radarr_root_folder_config.enabled = True
            mock_settings.get_root_folder_for_genres.return_value = "/movies"
            mgr = RootFolderManager()
            result = mgr.suggest_folder_for_genres(["Action"])
        assert result is None
