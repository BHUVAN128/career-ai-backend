"""
YouTube video recommendation service.
Primary lookup: youtubesearchpython (if available).
Fallback lookup: lightweight YouTube HTML parsing (no API key).
Results are cached in-process with a 1-hour TTL.
"""
import asyncio
import json
import re
import time
import urllib.parse
import urllib.request
from typing import TypedDict


class VideoResult(TypedDict):
    video_id: str
    title: str
    thumbnail_url: str
    channel_name: str
    duration: str
    view_count: str


# Simple in-process cache: key -> (result, expires_at)
_cache: dict[str, tuple[VideoResult | None, float]] = {}
_CACHE_TTL = 3600  # 1 hour


def _parse_view_count(view_str: str | None) -> int:
    """Convert '1.2M views' -> 1_200_000 for ranking."""
    if not view_str:
        return 0
    s = view_str.replace(",", "").lower()
    try:
        if "b" in s:
            return int(float(s.replace("b", "").strip()) * 1_000_000_000)
        if "m" in s:
            return int(float(s.replace("m", "").strip()) * 1_000_000)
        if "k" in s:
            return int(float(s.replace("k", "").strip()) * 1_000)
        digits = "".join(c for c in s if c.isdigit())
        return int(digits) if digits else 0
    except Exception:
        return 0


def _search_via_library(query: str, limit: int = 8) -> VideoResult | None:
    """Try youtubesearchpython if installed and functional."""
    try:
        from youtubesearchpython import VideosSearch  # type: ignore

        vs = VideosSearch(query, limit=limit)
        r = vs.result()
        items = r.get("result", [])
        if not items:
            return None

        # Pick the video with the highest view count among the top results.
        best = None
        best_views = -1
        for item in items:
            if item.get("type") != "video":
                continue
            vc = item.get("viewCount", {})
            views_text = vc.get("text", "") if isinstance(vc, dict) else str(vc or "")
            views = _parse_view_count(views_text)
            if views > best_views:
                best_views = views
                best = item

        if not best:
            best = items[0]

        vid_id = best.get("id", "")
        if not vid_id:
            return None

        thumbnails = best.get("thumbnails", [])
        thumb = (
            thumbnails[-1]["url"]
            if thumbnails and isinstance(thumbnails[-1], dict) and thumbnails[-1].get("url")
            else f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
        )

        channel = best.get("channel", {})
        channel_name = channel.get("name", "") if isinstance(channel, dict) else str(channel or "")

        duration_obj = best.get("duration")
        duration = duration_obj if isinstance(duration_obj, str) else "-"

        view_text = ""
        vc = best.get("viewCount", {})
        if isinstance(vc, dict):
            view_text = vc.get("text", "")
        elif isinstance(vc, str):
            view_text = vc

        return VideoResult(
            video_id=vid_id,
            title=best.get("title", query),
            thumbnail_url=thumb,
            channel_name=channel_name,
            duration=duration,
            view_count=view_text,
        )
    except Exception:
        return None


def _search_via_html(query: str) -> VideoResult | None:
    """Fallback: parse YouTube search HTML to extract first video id/title."""
    try:
        q = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={q}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # video ids are stable 11-char tokens in JSON payload.
        ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        if not ids:
            return None
        vid_id = ids[0]

        title = query
        # Try extracting title from ytInitialData JSON.
        marker = "var ytInitialData = "
        i = html.find(marker)
        if i != -1:
            j = html.find(";</script>", i)
            if j != -1:
                raw = html[i + len(marker) : j]
                try:
                    data = json.loads(raw)
                    blobs = json.dumps(data)
                    m = re.search(r'"videoId":"%s".{0,250}?"title":\{"runs":\[\{"text":"([^"]+)"' % re.escape(vid_id), blobs)
                    if m:
                        title = m.group(1)
                except Exception:
                    pass

        return VideoResult(
            video_id=vid_id,
            title=title,
            thumbnail_url=f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
            channel_name="YouTube",
            duration="-",
            view_count="",
        )
    except Exception:
        return None


def _search_sync(query: str, limit: int = 8) -> VideoResult | None:
    """Synchronous search — run inside asyncio.to_thread."""
    result = _search_via_library(query, limit=limit)
    if result:
        return result
    return _search_via_html(query)


async def get_best_video(step_id: str, query: str, lang_code: str = "en") -> VideoResult | None:
    """
    Return the best YouTube video for the given query.
    Language variants append a language suffix to the query.
    Results cached per (step_id, lang_code) for 1 hour.
    """
    cache_key = f"{step_id}:{lang_code}"
    now = time.time()
    if cache_key in _cache:
        result, expires_at = _cache[cache_key]
        if now < expires_at:
            return result

    lang_labels = {
        "hi": "Hindi",
        "ta": "Tamil",
        "te": "Telugu",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "pt": "Portuguese",
        "ja": "Japanese",
        "ko": "Korean",
        "zh-CN": "Chinese",
    }
    lang_name = lang_labels.get(lang_code)
    search_query = f"{query} tutorial {lang_name}" if lang_name else f"{query} tutorial"

    result = await asyncio.to_thread(_search_sync, search_query)
    _cache[cache_key] = (result, now + _CACHE_TTL)
    return result
