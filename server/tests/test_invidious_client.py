"""Tests for invidious/client.py — Invidious API client."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from invidious.client import InvidiousClient


@pytest.fixture
def client():
    return InvidiousClient(base_url="http://test-invidious:3000")


class TestNormalizeVideo:
    def test_normalizes_basic_video(self, client):
        raw = {
            "videoId": "abc123_def",
            "title": "Test Video",
            "author": "Test Channel",
            "authorId": "UC1234",
            "lengthSeconds": 300,
            "published": 1700000000,
            "viewCount": 50000,
            "videoThumbnails": [
                {"quality": "medium", "url": "https://i.ytimg.com/vi/abc/mqdefault.jpg"}
            ],
        }
        result = client._normalize_video(raw)
        assert result["video_id"] == "abc123_def"
        assert result["title"] == "Test Video"
        assert result["channel_name"] == "Test Channel"
        assert result["channel_id"] == "UC1234"
        assert result["duration"] == 300
        assert result["thumbnail_url"] == "https://i.ytimg.com/vi/abc/mqdefault.jpg"

    def test_returns_none_without_video_id(self, client):
        assert client._normalize_video({}) is None
        assert client._normalize_video({"title": "no id"}) is None

    def test_relative_thumbnail_gets_absolute(self, client):
        raw = {
            "videoId": "test123",
            "videoThumbnails": [
                {"quality": "default", "url": "/vi/test123/default.jpg"}
            ],
        }
        result = client._normalize_video(raw)
        assert result["thumbnail_url"] == "http://test-invidious:3000/vi/test123/default.jpg"


class TestPickBestStream:
    def test_picks_highest_mp4_under_1080p(self, client):
        streams = [
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://360.mp4", "qualityLabel": "360p"},
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://720.mp4", "qualityLabel": "720p"},
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://1080.mp4", "qualityLabel": "1080p"},
        ]
        assert client._pick_best_stream(streams) == "http://1080.mp4"

    def test_skips_non_mp4(self, client):
        streams = [
            {"type": "video/webm; codecs=\"vp9\"", "url": "http://webm.url", "qualityLabel": "1080p"},
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://mp4.url", "qualityLabel": "720p"},
        ]
        assert client._pick_best_stream(streams) == "http://mp4.url"

    def test_returns_none_for_empty(self, client):
        assert client._pick_best_stream([]) is None

    def test_falls_back_if_all_above_1080p(self, client):
        streams = [
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://4k.mp4", "qualityLabel": "2160p"},
        ]
        # Should still return something rather than None
        assert client._pick_best_stream(streams) == "http://4k.mp4"

    def test_handles_60fps_label(self, client):
        streams = [
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://1080p60.mp4", "qualityLabel": "1080p60"},
            {"type": "video/mp4; codecs=\"avc1\"", "url": "http://720p.mp4", "qualityLabel": "720p"},
        ]
        assert client._pick_best_stream(streams) == "http://1080p60.mp4"


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_normalized_results(self, client):
        mock_response = [
            {
                "type": "video",
                "videoId": "vid1",
                "title": "Result 1",
                "author": "Channel A",
                "authorId": "UCA",
                "lengthSeconds": 120,
                "videoThumbnails": [],
            },
            {
                "type": "video",
                "videoId": "vid2",
                "title": "Result 2",
                "author": "Channel B",
                "authorId": "UCB",
                "lengthSeconds": 300,
                "videoThumbnails": [],
            },
            {
                "type": "channel",  # Should be filtered out
                "authorId": "UCC",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch.object(client, "_client", return_value=mock_client_instance):
            results = await client.search("test query")

        assert len(results) == 2
        assert results[0]["video_id"] == "vid1"
        assert results[1]["video_id"] == "vid2"

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client):
        mock_response = [
            {"type": "video", "videoId": f"vid{i}", "title": f"Video {i}", "author": "Ch", "authorId": "UC", "lengthSeconds": 60, "videoThumbnails": []}
            for i in range(10)
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch.object(client, "_client", return_value=mock_client_instance):
            results = await client.search("test", max_results=3)

        assert len(results) == 3


class TestGetVideo:
    @pytest.mark.asyncio
    async def test_returns_video_with_format_streams(self, client):
        mock_data = {
            "videoId": "testid12345",
            "title": "Test Video",
            "author": "Author",
            "authorId": "UCID",
            "lengthSeconds": 600,
            "videoThumbnails": [],
            "formatStreams": [
                {"type": "video/mp4", "url": "http://stream.mp4", "qualityLabel": "720p"}
            ],
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch.object(client, "_client", return_value=mock_client_instance):
            result = await client.get_video("testid12345")

        assert result["video_id"] == "testid12345"
        assert "format_streams" in result
        assert len(result["format_streams"]) == 1

    @pytest.mark.asyncio
    async def test_returns_none_for_404(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_resp)

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=error)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch.object(client, "_client", return_value=mock_client_instance):
            result = await client.get_video("nonexistent1")

        assert result is None
