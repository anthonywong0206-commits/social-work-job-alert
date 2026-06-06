import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup


TELEGRAM_LIMIT = 3900

QUERIES = [
    '"\u793e\u6703\u5de5\u4f5c\u52a9\u7406" "\u9577\u8005" "\u622a\u6b62\u65e5\u671f" "\u9999\u6e2f"',
    '"SWA" "\u9577\u8005\u670d\u52d9" "\u9999\u6e2f"',
    '"Social Work Assistant" "elderly" "Hong Kong"',
    '"InterRAI 9.3" "\u793e\u6703\u5de5\u4f5c\u52a9\u7406" "\u9999\u6e2f"',
    '"\u5b89\u8001\u670d\u52d9\u7d71\u4e00\u8a55\u4f30\u6a5f\u5236" "\u793e\u5de5" "\u9999\u6e2f"',
    'site:ctgoodjobs.hk \u793e\u6703\u5de5\u4f5c\u52a9\u7406 \u9577\u8005 \u526f\u5b78\u58eb',
    'site:hk.jobsdb.com swa \u9577\u8005 \u793e\u5de5',
]

JOB_KEYWORDS = [
    "\u793e\u6703\u5de5\u4f5c\u52a9\u7406",
    "\u793e\u5de5",
    "social work assistant",
    "social worker",
    "swa",
]

SERVICE_KEYWORDS = [
    "\u9577\u8005",
    "\u5b89\u8001",
    "\u8b77\u8001",
    "elderly",
    "older",
    "carer",
    "day care",
    "community support",
]

QUALIFICATION_KEYWORDS = [
    "\u526f\u5b78\u58eb",
    "\u9ad8\u7d1a\u6587\u6191",
    "\u6587\u6191",
    "associate degree",
    "higher diploma",
    "diploma",
]

ASSESSOR_KEYWORDS = [
    "interrai",
    "interrai 9.3",
    "\u5b89\u8001\u670d\u52d9\u7d71\u4e00\u8a55\u4f30\u6a5f\u5236",
    "\u8a55\u4f30\u54e1",
]

EXPIRED_KEYWORDS = [
    "\u5df2\u622a\u6b62",
    "\u7533\u8acb\u671f\u5df2\u904e",
    "expired",
    "closed",
    "no longer accepting",
]

NOT_SPECIFIED = "\u672a\u5217\u660e"
NOT_MENTIONED = "\u672a\u898b\u63d0\u53ca"
MENTIONED = "\u6709\u63d0\u53ca"


@dataclass
class Candidate:
    title: str
    url: str
    source: str
    snippet: str
    deadline: str = NOT_SPECIFIED
    assessor: str = NOT_MENTIONED
    score: int = 0


def get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def fetch(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def unwrap_duckduckgo_url(href: str) -> str:
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc:
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
    return href


def search_duckduckgo(query: str) -> list[Candidate]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    results: list[Candidate] = []
    for result in soup.select(".result")[:8]:
        link = result.select_one(".result__a")
        if not link:
            continue
        title = clean_text(link.get_text(" "))
        href = unwrap_duckduckgo_url(link.get("href", ""))
        snippet_el = result.select_one(".result__snippet")
        snippet = clean_text(snippet_el.get_text(" ")) if snippet_el else ""
        if href.startswith("http"):
            results.append(Candidate(title=title, url=href, source=source_name(href), snippet=snippet))
    return results


def source_name(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or "web"


def clean_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def parse_deadline(text: str) -> str:
    patterns = [
        r"(?:\u622a\u6b62\u65e5\u671f|\u622a\u6b62\u7533\u8acb\u65e5\u671f|\u7533\u8acb\u622a\u6b62\u65e5\u671f|\u622a\u6b62)[:\uff1a\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"(?:\u622a\u6b62\u65e5\u671f|\u622a\u6b62\u7533\u8acb\u65e5\u671f|\u7533\u8acb\u622a\u6b62\u65e5\u671f|\u622a\u6b62)[:\uff1a\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        r"(?:closing date|deadline)[:\uff1a\s]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"(\d{4}\u5e74\d{1,2}\u6708\d{1,2}\u65e5)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return NOT_SPECIFIED


def deadline_is_past(deadline: str, today: date) -> bool:
    if deadline == NOT_SPECIFIED:
        return False
    normalized = deadline.replace("\u5e74", "-").replace("\u6708", "-").replace("\u65e5", "")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(normalized, fmt).date() < today
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(deadline).date() < today
    except (TypeError, ValueError):
        return False


def enrich(candidate: Candidate, today: date) -> Candidate | None:
    seed_text = f"{candidate.title} {candidate.snippet}"
    page_text = ""
    try:
        html = fetch(candidate.url)
        soup = BeautifulSoup(html, "html.parser")
        page_text = clean_text(soup.get_text(" "))
    except requests.RequestException:
        page_text = ""

    combined = clean_text(f"{seed_text} {page_text[:6000]}")
    if contains_any(combined, EXPIRED_KEYWORDS):
        return None
    if not contains_any(combined, JOB_KEYWORDS):
        return None
    if not contains_any(combined, SERVICE_KEYWORDS):
        return None

    candidate.deadline = parse_deadline(combined)
    if deadline_is_past(candidate.deadline, today):
        return None

    candidate.assessor = MENTIONED if contains_any(combined, ASSESSOR_KEYWORDS) else NOT_MENTIONED
    candidate.score = 0
    candidate.score += 5 if candidate.assessor == MENTIONED else 0
    candidate.score += 3 if contains_any(combined, SERVICE_KEYWORDS) else 0
    candidate.score += 2 if contains_any(combined, QUALIFICATION_KEYWORDS) else 0
    candidate.snippet = clean_text(candidate.snippet or page_text[:260])
    return candidate


def dedupe(candidates: Iterable[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        key = candidate.url.split("?")[0].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def build_message(candidates: list[Candidate], today: date) -> str:
    if not candidates:
        return (
            "\u3010\u9999\u6e2f\u793e\u5de5 / SWA \u8077\u4f4d\u641c\u5c0b\u3011\n"
            f"\u641c\u5c0b\u65e5\u671f\uff1a{today.isoformat()}\n\n"
            "\u4eca\u65e5\u672a\u627e\u5230\u4ecd\u53ef\u7533\u8acb\u4e26\u7b26\u5408\u689d\u4ef6\u7684\u65b0\u7a7a\u7f3a\u3002"
        )

    lines = [
        "\u3010\u9999\u6e2f\u793e\u5de5 / SWA \u8077\u4f4d\u641c\u5c0b\u3011",
        f"\u641c\u5c0b\u65e5\u671f\uff1a{today.isoformat()}",
        "\u898f\u5247\uff1a\u5df2\u622a\u6b62\u8077\u4f4d\u5df2\u5254\u9664\uff1b\u6c92\u6709\u622a\u6b62\u65e5\u671f\u4f46\u770b\u4f3c\u4ecd\u62db\u8058\u8005\u4fdd\u7559\u3002",
        "",
    ]
    for index, job in enumerate(candidates[:6], start=1):
        lines.extend(
            [
                f"{index}. {job.title}",
                f"\u62db\u52df\u6a5f\u69cb/\u4f86\u6e90\uff1a{job.source}",
                f"\u5de5\u4f5c\u5167\u5bb9\u6458\u8981\uff1a{job.snippet[:220] or '\u672a\u80fd\u64f7\u53d6\u6458\u8981\uff0c\u8acb\u6253\u958b\u9023\u7d50\u67e5\u770b\u3002'}",
                "\u5b78\u6b77\u53ca\u5176\u4ed6\u8981\u6c42\uff1a\u8acb\u4ee5\u8077\u4f4d\u9801\u70ba\u6e96\uff1b\u5df2\u6309\u793e\u5de5/SWA\u53ca\u9577\u8005\u670d\u52d9\u95dc\u9375\u5b57\u7be9\u9078\u3002",
                f"InterRAI 9.3 / \u8a55\u4f30\u54e1\u8cc7\u6b77\uff1a{job.assessor}",
                f"\u622a\u6b62\u65e5\u671f\uff1a{job.deadline}",
                "\u7279\u5225\u7559\u610f\uff1a\u8acb\u6253\u958b\u9023\u7d50\u78ba\u8a8d\u7533\u8acb\u65b9\u6cd5\u53ca\u5b8c\u6574\u8981\u6c42\u3002",
                f"\u9023\u7d50\uff1a{job.url}",
                "",
            ]
        )
    return "\n".join(lines)[:TELEGRAM_LIMIT]


def send_telegram(text: str) -> None:
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()


def main() -> None:
    today = date.today()
    raw: list[Candidate] = []
    for query in QUERIES:
        try:
            raw.extend(search_duckduckgo(query))
        except requests.RequestException:
            continue

    enriched = [job for job in (enrich(candidate, today) for candidate in dedupe(raw)) if job]
    enriched.sort(key=lambda item: item.score, reverse=True)
    message = build_message(enriched, today)
    print(message)
    if os.getenv("DRY_RUN") != "1":
        send_telegram(message)


if __name__ == "__main__":
    main()
