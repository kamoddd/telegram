from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

RASTER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True)
class ScheduleImage:
    url: str
    content: bytes
    sha256: str


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_raster_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(RASTER_EXTENSIONS)


def _normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace("_", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace(" ", "-")
    )


def _normalize_filename(path: str) -> str:
    filename = unquote(path).split("/")[-1]
    return _normalize_text(filename)


def _matches_filename_token(url: str, filename_token: str) -> bool:
    normalized_filename = _normalize_filename(urlparse(url).path)
    normalized_token = _normalize_text(filename_token)
    return normalized_token in normalized_filename


def _download_image(url: str, timeout_seconds: int = 30) -> bytes:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.content


def _extract_image_urls_by_token(html: str, base_url: str, filename_token: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc

    candidates: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue

        absolute = urljoin(base_url, src)
        parsed = urlparse(absolute)

        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != base_host:
            continue
        if not _is_raster_image_url(absolute):
            continue
        if not _matches_filename_token(absolute, filename_token):
            continue

        candidates.append(absolute)

    seen = set()
    unique_urls: List[str] = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)

    return unique_urls


def get_schedule_images(
    page_url: str,
    filename_token: str,
    timeout_seconds: int = 30,
    max_images: int = 2,
) -> List[ScheduleImage]:
    if max_images < 1:
        raise ValueError("max_images must be >= 1")

    response = requests.get(
        page_url,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    urls = _extract_image_urls_by_token(response.text, page_url, filename_token)

    if not urls:
        raise RuntimeError(f"Не удалось найти картинки по маске '{filename_token}'.")

    result: List[ScheduleImage] = []
    for url in urls:
        try:
            content = _download_image(url, timeout_seconds=timeout_seconds)
        except requests.RequestException:
            continue

        result.append(
            ScheduleImage(
                url=url,
                content=content,
                sha256=_hash_bytes(content),
            )
        )
        if len(result) >= max_images:
            break

    if not result:
        raise RuntimeError(f"Не удалось скачать картинки по маске '{filename_token}'.")

    return result
