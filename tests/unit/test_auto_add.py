"""Tests for src/core/auto_add.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.auto_add import auto_add_missing_movies
from src.core.boxoffice import BoxOfficeMovie
from src.core.matcher import MatchResult
from src.utils.config import settings


def _make_result(title="Test Movie", rank=1, matched=False, radarr_movie=None):
    bo_movie = BoxOfficeMovie(rank=rank, title=title, weekend_gross=1_000_000)
    return MatchResult(
        box_office_movie=bo_movie,
        radarr_movie=radarr_movie,
        confidence=1.0 if matched else 0.0,
    )


def _make_radarr_svc(profiles=None, search_results=None, add_result=None):
    svc = MagicMock()
    profile = MagicMock()
    profile.id = 1
    profile.name = "HD-1080p"
    svc.get_quality_profiles.return_value = [profile] if profiles is None else profiles
    search_result = {
        "tmdbId": 12345,
        "title": "Test Movie",
        "year": 2024,
        "genres": ["Action"],
        "certification": "PG-13",
        "originalLanguage": {"name": "English"},
        "remotePoster": None,
    }
    svc.search_movie.return_value = (
        search_results if search_results is not None else [search_result]
    )
    added = MagicMock()
    added.title = "Test Movie"
    svc.add_movie.return_value = add_result or added
    return svc


class TestAutoAddMissingMovies:
    def test_all_matched_returns_empty(self):
        matched = _make_result(matched=True, radarr_movie=MagicMock())
        results = auto_add_missing_movies([matched], MagicMock(), 2024)
        assert results == []

    def test_empty_list_returns_empty(self):
        results = auto_add_missing_movies([], MagicMock(), 2024)
        assert results == []

    def test_adds_unmatched_movie(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert "Test Movie" in results

    def test_no_quality_profiles_returns_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        svc = _make_radarr_svc(profiles=[])
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_not_found_in_tmdb_skips(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc(search_results=[])
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_ignored_movie_skipped(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = {12345}
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_rerelease_skipped(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", True
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        search_result = {
            "tmdbId": 99,
            "title": "Old Movie",
            "year": 2000,
            "genres": [],
            "originalLanguage": {},
        }
        svc = _make_radarr_svc(search_results=[search_result])
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_genre_whitelist_skips_non_matching(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", True
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_mode", "whitelist"
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_whitelist", ["Animation"]
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()  # search returns genres=["Action"]
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_genre_blacklist_skips_blacklisted(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", True
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_mode", "blacklist"
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_blacklist", ["Action"]
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()  # search returns genres=["Action"]
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_rating_filter_skips_wrong_rating(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", True
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_whitelist", ["G", "PG"]
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()  # certification="PG-13"
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_language_whitelist_skips_wrong_language(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", True
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_mode", "whitelist"
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_whitelist", ["Japanese"]
        )
        svc = _make_radarr_svc()  # language=English
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_language_blacklist_skips_blacklisted(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", True
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_mode", "blacklist"
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_blacklist", ["English"]
        )
        svc = _make_radarr_svc()  # language=English
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []

    def test_limit_applied(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 1)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()
        movies = [_make_result(title=f"Movie {i}", rank=i) for i in range(1, 5)]
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            results = auto_add_missing_movies(movies, svc, 2024)
        # Only 1 call to add_movie due to limit
        assert svc.add_movie.call_count <= 1

    def test_exception_during_add_continues(self, monkeypatch):
        monkeypatch.setattr(settings, "radarr_quality_profile_default", "HD-1080p")
        monkeypatch.setattr(settings, "boxarr_features_auto_add_limit", 100)
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_ignore_rereleases", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_genre_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_rating_filter_enabled", False
        )
        monkeypatch.setattr(
            settings, "boxarr_features_auto_add_language_filter_enabled", False
        )
        svc = _make_radarr_svc()
        svc.add_movie.side_effect = RuntimeError("add failed")
        with patch("src.core.auto_add.IgnoreList") as mock_il:
            mock_il.return_value.get_ignored_tmdb_ids.return_value = set()
            # Should not raise
            results = auto_add_missing_movies([_make_result()], svc, 2024)
        assert results == []
