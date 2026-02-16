from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ScheduleImage:
    url: str
    content: bytes
    sha256: str


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download_image(url: str, timeout_seconds: int = 30) -> bytes:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.content


def _extract_schedule_image_urls(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[str] = []

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue

        alt = (img.get("alt") or "").lower()
        title = (img.get("title") or "").lower()
        merged = f"{src.lower()} {alt} {title}"
        absolute = urljoin(base_url, src)

        if "распис" in merged or "лед" in merged:
            candidates.append(absolute)

    if len(candidates) < 2:
        fallback: List[str] = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            absolute = urljoin(base_url, src)
            fallback.append(absolute)

        seen = set()
        unique_fallback: List[str] = []
        for url in fallback:
            if url in seen:
                continue
            seen.add(url)
            unique_fallback.append(url)
        candidates = unique_fallback

    seen = set()
    unique_urls: List[str] = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)

    return unique_urls[:2]


def get_schedule_images(page_url: str, timeout_seconds: int = 30) -> List[ScheduleImage]:
    response = requests.get(
        page_url,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    urls = _extract_schedule_image_urls(response.text, page_url)

    if len(urls) < 2:
        raise RuntimeError("Не удалось найти 2 картинки с расписанием на странице.")

    result: List[ScheduleImage] = []
    for url in urls:
        content = _download_image(url, timeout_seconds=timeout_seconds)
        result.append(
            ScheduleImage(
                url=url,
                content=content,
                sha256=_hash_bytes(content),
            )
        )
    return result

