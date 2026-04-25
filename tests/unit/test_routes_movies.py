"""Tests for /api/movies routes."""

import json

import pytest
from unittest.mock import MagicMock, patch

from src.utils.config import settings


class TestRootFoldersNoKey:
    def test_no_api_key_returns_empty(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.get("/api/movies/root-folders/available")
        assert resp.status_code == 200
        data = resp.json()
        assert data["folders"] == []
        assert data["mappings_enabled"] is False

    def test_suggest_no_api_key(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.post("/api/movies/root-folders/suggest", json=["Action"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggested"] is None

    def test_available_root_folders_exception(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            mock_cls.side_effect = RuntimeError("connection failed")
            resp = client.get("/api/movies/root-folders/available")
        assert resp.status_code == 200
        data = resp.json()
        assert data["folders"] == []
        assert "error" in data

    def test_suggest_root_folder_exception(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            mock_cls.side_effect = RuntimeError("connection failed")
            resp = client.post("/api/movies/root-folders/suggest", json=["Action"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggested"] is None
        assert data["reason"] == "error"


class TestIgnoreList:
    def test_get_ignore_list_empty(self, client):
        resp = client.get("/api/movies/ignore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ignored"] == []
        assert data["tmdb_ids"] == []

    def test_add_movie_to_ignore(self, client):
        resp = client.post(
            "/api/movies/ignore",
            json={"tmdb_id": 12345, "title": "Test Movie"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["added"] is True

    def test_add_duplicate_returns_already_ignored(self, client):
        client.post("/api/movies/ignore", json={"tmdb_id": 99999, "title": "Dupe"})
        resp = client.post(
            "/api/movies/ignore", json={"tmdb_id": 99999, "title": "Dupe"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] is False

    def test_unignore_movie(self, client):
        client.post("/api/movies/ignore", json={"tmdb_id": 55555, "title": "Remove Me"})
        resp = client.delete("/api/movies/ignore/55555")
        assert resp.status_code == 200
        data = resp.json()
        assert data["removed"] is True

    def test_unignore_non_existent(self, client):
        resp = client.delete("/api/movies/ignore/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["removed"] is False


class TestRefreshStoredStatus:
    def test_progress_endpoint_returns_state(self, client):
        resp = client.get("/api/movies/refresh-stored-status/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "complete" in data

    def test_refresh_without_api_key_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.post("/api/movies/refresh-stored-status")
        assert resp.status_code == 400

    def test_refresh_while_running_returns_409(self, client, monkeypatch):
        import src.api.routes.movies as movies_module

        monkeypatch.setattr(settings, "radarr_api_key", "somekey")
        original_state = dict(movies_module._refresh_state)
        movies_module._refresh_state["running"] = True
        try:
            resp = client.post("/api/movies/refresh-stored-status")
            assert resp.status_code == 409
        finally:
            movies_module._refresh_state.update(original_state)


class TestMovieWeeks:
    def test_invalid_tmdb_id_returns_400(self, client):
        resp = client.get("/api/movies/0/weeks")
        assert resp.status_code == 400

    def test_no_weekly_dir_returns_empty(self, client, isolated_data_dir):
        resp = client.get("/api/movies/27205/weeks")
        assert resp.status_code == 200
        assert resp.json()["weeks"] == []

    def test_found_in_weekly_json(self, client, weekly_json):
        resp = client.get("/api/movies/27205/weeks")
        assert resp.status_code == 200
        data = resp.json()
        assert "2025W01" in data["weeks"]

    def test_not_found_in_weekly_json(self, client, weekly_json):
        resp = client.get("/api/movies/9999999/weeks")
        assert resp.status_code == 200
        assert resp.json()["weeks"] == []


class TestMovieDetails:
    def test_no_api_key_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.get("/api/movies/123")
        assert resp.status_code == 400

    def test_movie_not_found_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_movie.return_value = None
            mock_cls.return_value = instance
            resp = client.get("/api/movies/9999")
        assert resp.status_code == 404


class TestMovieStatus:
    def test_no_api_key_returns_empty(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.post("/api/movies/status", json={"movie_ids": [1, 2]})
        assert resp.status_code == 200
        assert resp.json()["statuses"] == {}

    def test_with_radarr_returns_statuses(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", False)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "Ultra-HD")

        movie = MagicMock()
        movie.id = 1
        movie.hasFile = True
        movie.status = MagicMock()
        movie.qualityProfileId = 1
        movie.isAvailable = True

        profile = MagicMock()
        profile.id = 1
        profile.name = "HD-1080p"

        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_all_movies.return_value = [movie]
            instance.get_quality_profiles.return_value = [profile]
            mock_cls.return_value = instance
            resp = client.post("/api/movies/status", json={"movie_ids": [1]})

        assert resp.status_code == 200
        data = resp.json()
        assert "1" in data["statuses"]
        assert data["statuses"]["1"]["status"] == "Downloaded"

    def test_missing_status_correctly_detected(self, client, monkeypatch):
        from src.core.models import MovieStatus

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", False)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "")

        movie = MagicMock()
        movie.id = 2
        movie.hasFile = False
        movie.status = MovieStatus.RELEASED
        movie.isAvailable = True
        movie.qualityProfileId = 1

        profile = MagicMock()
        profile.id = 1
        profile.name = "HD-1080p"

        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_all_movies.return_value = [movie]
            instance.get_quality_profiles.return_value = [profile]
            mock_cls.return_value = instance
            resp = client.post("/api/movies/status", json={"movie_ids": [2]})

        assert resp.json()["statuses"]["2"]["status"] == "Missing"

    def test_in_cinemas_status(self, client, monkeypatch):
        from src.core.models import MovieStatus

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", False)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "")

        movie = MagicMock()
        movie.id = 3
        movie.hasFile = False
        movie.status = MovieStatus.IN_CINEMAS
        movie.isAvailable = False
        movie.qualityProfileId = 1

        profile = MagicMock()
        profile.id = 1
        profile.name = "HD-1080p"

        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_all_movies.return_value = [movie]
            instance.get_quality_profiles.return_value = [profile]
            mock_cls.return_value = instance
            resp = client.post("/api/movies/status", json={"movie_ids": [3]})

        assert resp.json()["statuses"]["3"]["status"] == "In Cinemas"


class TestRootFoldersWithKey:
    def test_with_radarr_returns_folders(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
        ):
            instance = MagicMock()
            mock_cls.return_value = instance
            rfm = MagicMock()
            rfm.get_available_root_folders.return_value = ["/movies", "/anime"]
            rfm.get_folder_stats.return_value = {}
            rfm_cls.return_value = rfm
            resp = client.get("/api/movies/root-folders/available")
        assert resp.status_code == 200
        data = resp.json()
        assert "/movies" in data["folders"]

    def test_suggest_with_radarr_returns_suggestion(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "radarr_root_folder", "/movies")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
        ):
            instance = MagicMock()
            mock_cls.return_value = instance
            rfm = MagicMock()
            rfm.suggest_folder_for_genres.return_value = "/anime"
            rfm_cls.return_value = rfm
            resp = client.post("/api/movies/root-folders/suggest", json=["Animation"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggested"] == "/anime"


class TestUpgradeMovieQuality:
    def test_no_api_key_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.post("/api/movies/123/upgrade")
        assert resp.status_code == 400

    def test_feature_disabled_returns_failure(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", False)
        resp = client.post("/api/movies/123/upgrade")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_movie_not_found_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", True)
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_movie.return_value = None
            mock_cls.return_value = instance
            resp = client.post("/api/movies/999/upgrade")
        assert resp.status_code == 404

    def test_upgrade_profile_not_found_returns_failure(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", True)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "Ultra-HD")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_movie.return_value = MagicMock()
            profile = MagicMock()
            profile.name = "HD-1080p"
            instance.get_quality_profiles.return_value = [profile]
            mock_cls.return_value = instance
            resp = client.post("/api/movies/123/upgrade")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not found" in data["message"]

    def test_upgrade_success(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", True)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "Ultra-HD")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_movie.return_value = MagicMock()
            upgrade_profile = MagicMock()
            upgrade_profile.id = 5
            upgrade_profile.name = "Ultra-HD"
            instance.get_quality_profiles.return_value = [upgrade_profile]
            instance.update_movie_quality_profile.return_value = MagicMock()
            mock_cls.return_value = instance
            resp = client.post("/api/movies/123/upgrade")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["new_profile"] == "Ultra-HD"


class TestAddMovie:
    def test_no_api_key_returns_config_error(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            mock_cls.side_effect = Exception("Radarr not configured")
            resp = client.post("/api/movies/add", json={"title": "Inception"})
        # Route catches HTTPException and returns success=False with 200
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            assert resp.json()["success"] is False

    def test_no_title_returns_failure(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService"):
            resp = client.post("/api/movies/add", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_not_found_on_tmdb_returns_failure(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = []
            mock_cls.return_value = instance
            resp = client.post("/api/movies/add", json={"title": "Nonexistent Film"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not found" in data["message"].lower()

    def test_successful_add(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "radarr_search_for_movie", True)
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
            patch("src.api.routes.movies.regenerate_weeks_with_movie"),
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 12345, "title": "Inception", "genres": ["Action"]}
            ]
            added = MagicMock()
            added.id = 42
            instance.add_movie.return_value = added
            mock_cls.return_value = instance
            rfm = MagicMock()
            rfm.determine_root_folder.return_value = "/movies"
            rfm_cls.return_value = rfm
            mock_gam.return_value = []  # no existing movies
            resp = client.post("/api/movies/add", json={"title": "Inception"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_movie_already_exists(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
            patch("src.api.routes.movies.regenerate_weeks_with_movie"),
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 27205, "title": "Inception", "genres": []}
            ]
            mock_cls.return_value = instance
            rfm = MagicMock()
            rfm.determine_root_folder.return_value = "/movies"
            rfm_cls.return_value = rfm
            existing = MagicMock()
            existing.tmdbId = 27205
            existing.id = 101
            mock_gam.return_value = [existing]
            resp = client.post("/api/movies/add", json={"title": "Inception"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "already exists" in data["message"]

    def test_add_error_already_exists_message(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 1, "title": "Film", "genres": []}
            ]
            instance.add_movie.side_effect = RuntimeError("already exists in library")
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"title": "Film"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "already exists" in data["message"].lower()

    def test_add_with_movie_title_field(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "radarr_search_for_movie", False)
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
            patch("src.api.routes.movies.regenerate_weeks_with_movie"),
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 555, "title": "The Matrix", "genres": []}
            ]
            added = MagicMock()
            added.id = 77
            instance.add_movie.return_value = added
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"movie_title": "The Matrix"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_add_with_tmdb_id_uses_matching_result(self, client, monkeypatch):
        """Test that when tmdb_id is provided it selects the right search result."""
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "radarr_search_for_movie", True)
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
            patch("src.api.routes.movies.regenerate_weeks_with_movie"),
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 100, "title": "Film A", "genres": []},
                {"tmdbId": 200, "title": "Film B", "genres": []},
            ]
            added = MagicMock()
            added.id = 99
            instance.add_movie.return_value = added
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post(
                "/api/movies/add", json={"title": "Film B", "tmdb_id": 200}
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_add_returns_failure_when_add_movie_returns_none(self, client, monkeypatch):
        """Test the branch where add_movie returns falsy (None)."""
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "radarr_search_for_movie", False)
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 777, "title": "Ghost Film", "genres": []}
            ]
            instance.add_movie.return_value = None  # Simulate failure
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"title": "Ghost Film"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Failed" in data["message"] or "failed" in data["message"].lower()

    def test_add_connection_error_message(self, client, monkeypatch):
        """Covers the connection error exception branch."""
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 1, "title": "X", "genres": []}
            ]
            instance.add_movie.side_effect = RuntimeError("connection refused to host")
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"title": "X"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "connection" in data["message"].lower()

    def test_add_unauthorized_error_message(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 1, "title": "X", "genres": []}
            ]
            instance.add_movie.side_effect = RuntimeError(
                "unauthorized 401 invalid key"
            )
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"title": "X"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Authentication failed"

    def test_add_not_found_error_message(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 1, "title": "X", "genres": []}
            ]
            instance.add_movie.side_effect = RuntimeError("not found 404")
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"title": "X"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Movie not found"

    def test_add_generic_error_message(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 1, "title": "X", "genres": []}
            ]
            instance.add_movie.side_effect = RuntimeError("something else entirely")
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.return_value = []
            resp = client.post("/api/movies/add", json={"title": "X"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Unexpected error"

    def test_add_existing_movies_cache_exception(self, client, monkeypatch):
        """Covers the except branch when get_all_movies_with_optional_cache_bypass raises."""
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "radarr_search_for_movie", False)
        with (
            patch("src.api.routes.movies.RadarrService") as mock_cls,
            patch("src.api.routes.movies.RootFolderManager") as rfm_cls,
            patch(
                "src.api.routes.movies.get_all_movies_with_optional_cache_bypass"
            ) as mock_gam,
            patch("src.api.routes.movies.regenerate_weeks_with_movie"),
        ):
            instance = MagicMock()
            instance.search_movie_tmdb.return_value = [
                {"tmdbId": 888, "title": "Cache Fail Film", "genres": []}
            ]
            added = MagicMock()
            added.id = 55
            instance.add_movie.return_value = added
            mock_cls.return_value = instance
            rfm_cls.return_value = MagicMock()
            rfm_cls.return_value.determine_root_folder.return_value = "/movies"
            mock_gam.side_effect = RuntimeError("cache error")
            resp = client.post("/api/movies/add", json={"title": "Cache Fail Film"})
        assert resp.status_code == 200
        # After cache exception, tmdb_id is None → already = None → proceeds to add
        data = resp.json()
        assert data["success"] is True


class TestMovieDetailsSuccess:
    def test_returns_movie_details(self, client, monkeypatch):
        from src.core.models import MovieStatus

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            movie = MagicMock()
            movie.id = 5
            movie.title = "The Matrix"
            movie.year = 1999
            movie.status = MovieStatus.RELEASED
            movie.hasFile = True
            movie.qualityProfileId = 1
            movie.monitored = True
            movie.overview = "A hacker discovers the world is a simulation."
            movie.runtime = 136
            movie.imdbId = "tt0133093"
            movie.tmdbId = 603
            instance.get_movie.return_value = movie
            mock_cls.return_value = instance
            resp = client.get("/api/movies/5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "The Matrix"
        assert data["has_file"] is True
        assert data["imdb_id"] == "tt0133093"

    def test_exception_returns_500(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            mock_cls.side_effect = RuntimeError("unexpected")
            resp = client.get("/api/movies/5")
        assert resp.status_code == 500


class TestMovieStatusPending:
    def test_pending_status(self, client, monkeypatch):
        from src.core.models import MovieStatus

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", False)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "")

        movie = MagicMock()
        movie.id = 4
        movie.hasFile = False
        movie.status = MovieStatus.ANNOUNCED
        movie.isAvailable = False
        movie.qualityProfileId = 1

        profile = MagicMock()
        profile.id = 1
        profile.name = "HD-1080p"

        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_all_movies.return_value = [movie]
            instance.get_quality_profiles.return_value = [profile]
            mock_cls.return_value = instance
            resp = client.post("/api/movies/status", json={"movie_ids": [4]})

        data = resp.json()
        assert data["statuses"]["4"]["status"] == "Pending"

    def test_status_exception_returns_empty(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            mock_cls.side_effect = RuntimeError("network error")
            resp = client.post("/api/movies/status", json={"movie_ids": [1]})
        assert resp.status_code == 200
        assert resp.json()["statuses"] == {}


class TestUpgradeFailure:
    def test_update_returns_none_gives_failure(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", True)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "Ultra-HD")
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.get_movie.return_value = MagicMock()
            upgrade_profile = MagicMock()
            upgrade_profile.id = 5
            upgrade_profile.name = "Ultra-HD"
            instance.get_quality_profiles.return_value = [upgrade_profile]
            instance.update_movie_quality_profile.return_value = None  # failure
            mock_cls.return_value = instance
            resp = client.post("/api/movies/999/upgrade")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Failed" in data["message"]

    def test_upgrade_exception_returns_500(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", True)
        with patch("src.api.routes.movies.RadarrService") as mock_cls:
            mock_cls.side_effect = RuntimeError("network failure")
            resp = client.post("/api/movies/999/upgrade")
        assert resp.status_code == 500


class TestIgnoreListErrors:
    def test_get_ignore_list_exception(self, client, monkeypatch):
        with patch("src.api.routes.movies.IgnoreList") as mock_cls:
            mock_cls.side_effect = RuntimeError("db error")
            resp = client.get("/api/movies/ignore")
        assert resp.status_code == 500

    def test_add_ignore_exception(self, client, monkeypatch):
        with patch("src.api.routes.movies.IgnoreList") as mock_cls:
            mock_cls.side_effect = RuntimeError("db error")
            resp = client.post(
                "/api/movies/ignore", json={"tmdb_id": 1, "title": "Film"}
            )
        assert resp.status_code == 500

    def test_remove_ignore_exception(self, client, monkeypatch):
        with patch("src.api.routes.movies.IgnoreList") as mock_cls:
            mock_cls.side_effect = RuntimeError("db error")
            resp = client.delete("/api/movies/ignore/1")
        assert resp.status_code == 500


class TestRefreshStoredStatusSuccess:
    def test_starts_refresh_with_valid_key(self, client, monkeypatch):
        import src.api.routes.movies as movies_module

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        original_state = dict(movies_module._refresh_state)
        movies_module._refresh_state["running"] = False
        try:
            resp = client.post("/api/movies/refresh-stored-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["started"] is True
        finally:
            movies_module._refresh_state.update(original_state)
            movies_module._refresh_state["running"] = False


class TestMovieWeeksEdgeCases:
    def test_weekly_dir_exists_but_movie_not_present(self, client, isolated_data_dir):
        """Covers the branch where weekly dir exists but tmdb_id not in any file."""
        weekly_dir = isolated_data_dir / "weekly_pages"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        data = {"year": 2025, "week": 1, "movies": [{"tmdb_id": 111, "title": "Other"}]}
        (weekly_dir / "202501.json").write_text(json.dumps(data))
        resp = client.get("/api/movies/99999/weeks")
        assert resp.status_code == 200
        assert resp.json()["weeks"] == []

    def test_skips_current_json_file(self, client, isolated_data_dir):
        """Verifies current.json is skipped during scan."""
        weekly_dir = isolated_data_dir / "weekly_pages"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        (weekly_dir / "current.json").write_text(
            json.dumps({"year": 2025, "week": 1, "movies": [{"tmdb_id": 42}]})
        )
        resp = client.get("/api/movies/42/weeks")
        assert resp.status_code == 200
        assert resp.json()["weeks"] == []
