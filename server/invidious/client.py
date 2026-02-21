"""Async HTTP client wrapping the Invidious REST API.

Replaces yt-dlp from the original BrainRotGuard — all video search, metadata,
and stream URL resolution goes through a local Invidious instance.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class InvidiousClient:
    """Async client for the Invidious API."""

    def __init__(self, base_url: str = "http://invidious:3000", timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Search for videos via Invidious.

        Returns a list of simplified video dicts with keys:
        video_id, title, channel_name, channel_id, thumbnail_url, duration, published
        """
        async with self._client() as client:
            resp = await client.get(
                "/api/v1/search",
                params={"q": query, "type": "video", "sort_by": "relevance"},
            )
            resp.raise_for_status()
            raw_results = resp.json()

        results = []
        for item in raw_results:
            if item.get("type") != "video":
                continue
            video = self._normalize_video(item)
            if video:
                results.append(video)
            if len(results) >= max_results:
                break

        return results

    async def get_video(self, video_id: str) -> Optional[dict]:
        """Fetch full metadata for a single video.

        Returns normalized video dict or None if not found.
        """
        async with self._client() as client:
            try:
                resp = await client.get(f"/api/v1/videos/{video_id}")
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise
            data = resp.json()

        video = self._normalize_video(data)
        if video:
            video["format_streams"] = data.get("formatStreams", [])
        return video

    async def get_stream_url(
        self, video_id: str, quality: str = "best"
    ) -> Optional[str]:
        """Extract the best playable stream URL for AVPlayer.

        Prefers: progressive MP4, highest quality <= 1080p.
        Returns the proxied Invidious URL (streams through local Invidious).
        Stream URLs expire — always fetch fresh, never cache.
        """
        video = await self.get_video(video_id)
        if not video:
            return None

        streams = video.get("format_streams", [])
        return self._pick_best_stream(streams, quality)

    async def get_channel_videos(
        self, channel_id: str, continuation: str = ""
    ) -> list[dict]:
        """Fetch videos for a channel.

        Returns a list of normalized video dicts.
        """
        params: dict = {}
        if continuation:
            params["continuation"] = continuation

        async with self._client() as client:
            try:
                resp = await client.get(
                    f"/api/v1/channels/{channel_id}/videos",
                    params=params,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return []
                raise
            data = resp.json()

        videos_raw = data if isinstance(data, list) else data.get("videos", [])
        results = []
        for item in videos_raw:
            video = self._normalize_video(item)
            if video:
                results.append(video)
        return results

    async def get_channel_info(self, channel_id: str) -> Optional[dict]:
        """Fetch channel metadata.

        Returns dict with: channel_id, name, handle, subscriber_count, description
        """
        async with self._client() as client:
            try:
                resp = await client.get(f"/api/v1/channels/{channel_id}")
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise
            data = resp.json()

        return {
            "channel_id": data.get("authorId", channel_id),
            "name": data.get("author", ""),
            "handle": data.get("authorUrl", "").rstrip("/").split("/")[-1] or None,
            "subscriber_count": data.get("subCount", 0),
            "description": data.get("description", ""),
        }

    def _normalize_video(self, item: dict) -> Optional[dict]:
        """Convert an Invidious API video object to our simplified format."""
        video_id = item.get("videoId")
        if not video_id:
            return None

        thumbnails = item.get("videoThumbnails", [])
        thumbnail_url = None
        for thumb in thumbnails:
            if thumb.get("quality") in ("medium", "default", "sddefault"):
                thumbnail_url = thumb.get("url", "")
                break
        if not thumbnail_url and thumbnails:
            thumbnail_url = thumbnails[0].get("url", "")

        # Ensure thumbnail URL is absolute
        if thumbnail_url and thumbnail_url.startswith("/"):
            thumbnail_url = f"{self.base_url}{thumbnail_url}"

        return {
            "video_id": video_id,
            "title": item.get("title", ""),
            "channel_name": item.get("author", ""),
            "channel_id": item.get("authorId", ""),
            "thumbnail_url": thumbnail_url,
            "duration": item.get("lengthSeconds", 0),
            "published": item.get("published", 0),
            "view_count": item.get("viewCount", 0),
        }

    def _pick_best_stream(
        self, streams: list[dict], quality: str = "best"
    ) -> Optional[str]:
        """Pick the best progressive MP4 stream for AVPlayer.

        AVPlayer on tvOS supports progressive MP4 and HLS natively.
        Invidious formatStreams are progressive; adaptiveFormats are DASH (not supported).
        We filter for video/mp4 and pick the highest quality <= 1080p.
        """
        mp4_streams = []
        for s in streams:
            mime = s.get("type", "")
            if "video/mp4" not in mime:
                continue
            url = s.get("url", "")
            if not url:
                continue
            # Parse resolution from qualityLabel (e.g. "720p", "1080p60")
            label = s.get("qualityLabel", "")
            height = 0
            for part in label.replace("p60", "p").replace("p50", "p").split("p"):
                if part.isdigit():
                    height = int(part)
                    break
            mp4_streams.append({"url": url, "height": height, "label": label})

        if not mp4_streams:
            return None

        # Filter to max 1080p, then pick highest
        eligible = [s for s in mp4_streams if s["height"] <= 1080]
        if not eligible:
            eligible = mp4_streams

        eligible.sort(key=lambda s: s["height"], reverse=True)
        return eligible[0]["url"]
