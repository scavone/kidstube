"""Async HTTP client wrapping the Invidious REST API.

Replaces yt-dlp from the original BrainRotGuard — all video search, metadata,
and stream URL resolution goes through a local Invidious instance.
"""

import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)


class InvidiousClient:
    """Async client for the Invidious API."""

    def __init__(self, base_url: str = "http://invidious:3000", timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def search(
        self, query: str, max_results: int = 20, family_safe: bool = False
    ) -> list[dict]:
        """Search for videos and channels via Invidious.

        Returns a list of result dicts, each tagged with a "type" field:
        - "video": video_id, title, channel_name, channel_id, thumbnail_url, duration, published
        - "channel": channel_id, name, thumbnail_url, subscriber_count, video_count

        If family_safe is True, passes features=familySafe to Invidious
        for server-side filtering.
        """
        params = {"q": query, "sort_by": "relevance"}
        if family_safe:
            params["features"] = "familySafe"
        async with self._client() as client:
            resp = await client.get(
                "/api/v1/search",
                params=params,
            )
            resp.raise_for_status()
            raw_results = resp.json()

        results = []
        for item in raw_results:
            item_type = item.get("type")
            if item_type == "video":
                video = self._normalize_video(item)
                if video:
                    video["type"] = "video"
                    results.append(video)
            elif item_type == "channel":
                channel = self._normalize_channel(item)
                if channel:
                    results.append(channel)
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
            video["adaptive_formats"] = data.get("adaptiveFormats", [])
            video["hls_url"] = data.get("hlsUrl")
        return video

    async def get_stream_url(
        self, video_id: str, quality: str = "best"
    ) -> Optional[str]:
        """Extract the best playable stream URL for AVPlayer.

        Priority:
        1. hlsUrl from Invidious API — adaptive bitrate, up to 1080p+,
           natively supported by AVPlayer on tvOS.
        2. Best progressive MP4 from formatStreams (muxed, typically 360-720p).

        Stream URLs expire — always fetch fresh, never cache.
        """
        video = await self.get_video(video_id)
        if not video:
            return None

        # 1. Try HLS URL from video metadata (adaptive quality)
        hls_url = video.get("hls_url")
        if hls_url:
            logger.info("Using HLS stream for %s", video_id)
            return hls_url

        # 2. Fall back to progressive MP4
        streams = video.get("format_streams", [])
        selected = self._pick_best_stream(streams, quality)
        if selected:
            labels = [s.get("qualityLabel", "?") for s in streams if "video/mp4" in s.get("type", "")]
            logger.info("Using progressive stream for %s (available: %s)", video_id, ", ".join(labels))
        return selected

    def pick_best_adaptive_pair(
        self, adaptive_formats: list[dict], preferred_lang: str = ""
    ) -> Optional[tuple[str, str]]:
        """Pick the best H.264 video + AAC audio pair from adaptive formats.

        Returns (video_url, audio_url) or None if no suitable pair found.
        Intended for server-side remuxing via ffmpeg.
        If preferred_lang is set (e.g. "en"), audio tracks matching that
        language are preferred; falls back to all tracks if no match.
        """
        video_streams = []
        for fmt in adaptive_formats:
            mime = fmt.get("type", "")
            if "avc1" not in mime:
                continue
            url = fmt.get("url", "")
            if not url:
                continue
            res = fmt.get("resolution", "")
            height = 0
            if res:
                digits = res.replace("p", "").strip()
                if digits.isdigit():
                    height = int(digits)
            if height == 0:
                label = fmt.get("qualityLabel", "")
                for part in label.replace("p60", "p").replace("p50", "p").replace("p30", "p").split("p"):
                    if part.isdigit():
                        height = int(part)
                        break
            if 0 < height <= 1080:
                bitrate = int(fmt.get("bitrate", 0) or 0)
                video_streams.append({"url": url, "height": height, "bitrate": bitrate})

        if not video_streams:
            return None

        video_streams.sort(key=lambda s: (s["height"], s["bitrate"]), reverse=True)
        best_video = video_streams[0]

        audio_streams = []
        for fmt in adaptive_formats:
            mime = fmt.get("type", "")
            if "mp4a" not in mime:
                continue
            url = fmt.get("url", "")
            if not url:
                continue
            bitrate = int(fmt.get("bitrate", 0) or 0)
            lang = self._extract_audio_lang(fmt)
            audio_streams.append({"url": url, "bitrate": bitrate, "lang": lang})

        if not audio_streams:
            return None

        # Filter by preferred language if configured
        if preferred_lang:
            available_langs = {s["lang"] for s in audio_streams if s["lang"]}
            # Match base language code (e.g. "en" matches "en", "es" matches "es-419")
            lang_match = [
                s for s in audio_streams
                if s["lang"] == preferred_lang
                or s["lang"].startswith(preferred_lang + "-")
            ]
            if lang_match:
                audio_streams = lang_match
                logger.info("Audio language filter: selected %s (available: %s)",
                            preferred_lang, ", ".join(sorted(available_langs)) or "unknown")
            elif available_langs:
                logger.warning("Audio language filter: preferred %r not found (available: %s), using default",
                               preferred_lang, ", ".join(sorted(available_langs)))

        audio_streams.sort(key=lambda s: s["bitrate"], reverse=True)
        best_audio = audio_streams[0]

        logger.info(
            "Adaptive pair: %dp video (%dkbps) + %dkbps audio (lang=%s)",
            best_video["height"],
            best_video["bitrate"] // 1000,
            best_audio["bitrate"] // 1000,
            best_audio["lang"] or "unknown",
        )
        return (best_video["url"], best_audio["url"])

    @staticmethod
    def _extract_audio_lang(fmt: dict) -> str:
        """Extract language code from an adaptive audio format.

        Checks (in order):
        1. audioTrack.id field (e.g. {"id": "en.1"} -> "en")
        2. URL xtags parameter (e.g. xtags=acont=original:lang=en -> "en")
        """
        # 1. Try audioTrack metadata (some Invidious versions include this)
        track = fmt.get("audioTrack") or {}
        if track.get("id"):
            return track["id"].split(".")[0]

        # 2. Parse from URL xtags (Invidious encodes lang here for multi-audio videos)
        url = fmt.get("url", "")
        if url:
            qs = parse_qs(urlparse(url).query)
            for xtag in qs.get("xtags", []):
                for part in xtag.split(":"):
                    if part.startswith("lang="):
                        return part[5:]
        return ""

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

        # Extract channel avatar thumbnail
        thumbnails = data.get("authorThumbnails", [])
        thumbnail_url = None
        for thumb in thumbnails:
            width = thumb.get("width", 0)
            if 100 <= width <= 200:
                thumbnail_url = thumb.get("url", "")
                break
        if not thumbnail_url and thumbnails:
            thumbnail_url = thumbnails[-1].get("url", "")
        if thumbnail_url and thumbnail_url.startswith("//"):
            thumbnail_url = f"https:{thumbnail_url}"
        elif thumbnail_url and thumbnail_url.startswith("/"):
            thumbnail_url = f"{self.base_url}{thumbnail_url}"

        # Extract channel banner image
        banners = data.get("authorBanners", [])
        banner_url = None
        for banner in banners:
            width = banner.get("width", 0)
            if 1000 <= width <= 2000:
                banner_url = banner.get("url", "")
                break
        if not banner_url and banners:
            banner_url = banners[-1].get("url", "")
        if banner_url and banner_url.startswith("//"):
            banner_url = f"https:{banner_url}"
        elif banner_url and banner_url.startswith("/"):
            banner_url = f"{self.base_url}{banner_url}"

        return {
            "channel_id": data.get("authorId", channel_id),
            "name": data.get("author", ""),
            "handle": data.get("authorUrl", "").rstrip("/").split("/")[-1] or None,
            "subscriber_count": data.get("subCount", 0),
            "description": data.get("description", ""),
            "thumbnail_url": thumbnail_url,
            "banner_url": banner_url,
        }

    async def resolve_channel_by_handle(self, handle: str) -> Optional[dict]:
        """Resolve a @handle to channel info via search.

        Returns dict with: channel_id, name, handle, or None if not found.
        Invidious /channels/ endpoint only accepts UC... IDs, so we search instead.
        """
        query = handle if handle.startswith("@") else f"@{handle}"
        async with self._client() as client:
            try:
                resp = await client.get(
                    "/api/v1/search",
                    params={"q": query, "type": "channel", "sort_by": "relevance"},
                )
                resp.raise_for_status()
                results = resp.json()
            except Exception:
                return None

        # Match by authorUrl containing the handle
        handle_lower = handle.lstrip("@").lower()
        for item in results:
            author_url = item.get("authorUrl", "")
            # authorUrl is typically "/@handle" or "/channel/UCxxx"
            url_handle = author_url.rstrip("/").split("/")[-1].lstrip("@").lower()
            if url_handle == handle_lower:
                return {
                    "channel_id": item.get("authorId"),
                    "name": item.get("author", ""),
                    "handle": handle,
                }

        # Fallback: return the first channel result if any
        if results and results[0].get("type") == "channel":
            return {
                "channel_id": results[0].get("authorId"),
                "name": results[0].get("author", ""),
                "handle": handle,
            }

        return None

    def _normalize_channel(self, item: dict) -> Optional[dict]:
        """Convert an Invidious API channel search result to our simplified format."""
        channel_id = item.get("authorId")
        if not channel_id:
            return None

        thumbnails = item.get("authorThumbnails", [])
        thumbnail_url = None
        # Pick a medium-sized thumbnail (176px is typical for channel avatars)
        for thumb in thumbnails:
            width = thumb.get("width", 0)
            if 100 <= width <= 200:
                thumbnail_url = thumb.get("url", "")
                break
        if not thumbnail_url and thumbnails:
            thumbnail_url = thumbnails[-1].get("url", "")

        if thumbnail_url and thumbnail_url.startswith("//"):
            thumbnail_url = f"https:{thumbnail_url}"
        elif thumbnail_url and thumbnail_url.startswith("/"):
            thumbnail_url = f"{self.base_url}{thumbnail_url}"

        return {
            "type": "channel",
            "channel_id": channel_id,
            "name": item.get("author", ""),
            "thumbnail_url": thumbnail_url,
            "subscriber_count": item.get("subCount", 0),
            "video_count": item.get("videoCount", 0),
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
            "is_family_friendly": item.get("isFamilyFriendly", True),
            "description": item.get("description", ""),
        }

    def _pick_best_stream(
        self, streams: list[dict], quality: str = "best"
    ) -> Optional[str]:
        """Pick the best progressive MP4 stream for AVPlayer.

        Progressive formatStreams are muxed (video+audio) but typically max 720p.
        Used as fallback when no suitable adaptive format is found.
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
