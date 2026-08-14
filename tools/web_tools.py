import re
import urllib.parse
from html import unescape
from typing import Dict, Any, List, Optional, Tuple
import httpx
from tools.base import BaseTool
from theme import console


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Searches the web using DuckDuckGo (no API keys required) and returns clean titles, snippets, and external URLs."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The web search query string."
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of search results to return (1 to 5, default: 4)."
            }
        },
        "required": ["query"]
    }

    def __init__(self, config_mgr: Optional[Any] = None):
        self._config_mgr = config_mgr

    async def execute(self, query: str, max_results: int = 4) -> Dict[str, Any]:
        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        data = {"q": query}

        try:
            max_results = int(max_results)
        except (ValueError, TypeError):
            max_results = 4

        # Limit result count strictly between 1 and 5
        limit = min(max(1, max_results), 5)
        req_timeout = self._config_mgr.config.timeouts.web if self._config_mgr else 15.0

        try:
            async with httpx.AsyncClient(timeout=req_timeout, follow_redirects=True) as client:
                resp = await client.post(url, data=data, headers=headers)
                html_text = resp.text

            link_matches: List[Tuple[str, str]] = []
            for attrs, inner_html in re.findall(r'<a\s+([^>]*)>(.*?)</a>', html_text, re.DOTALL):
                if "result-link" not in attrs:
                    continue
                href_match = re.search(r'href=["\']([^"\']+)["\']', attrs)
                if href_match:
                    link_matches.append((href_match.group(1), inner_html))

            snippet_matches = re.findall(r'<td[^>]*class=["\']result-snippet["\'][^>]*>(.*?)</td>', html_text, re.DOTALL)

            valid_results: List[Dict[str, str]] = []
            seen_urls = set()

            for orig_idx, (url_str, raw_title) in enumerate(link_matches):
                if "uddg=" in url_str:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url_str).query)
                    clean_url = parsed.get("uddg", [url_str])[0]
                else:
                    clean_url = url_str

                if (
                    "duckduckgo.com" in clean_url 
                    or not clean_url.startswith("http") 
                    or clean_url in seen_urls
                ):
                    continue

                seen_urls.add(clean_url)
                clean_title = unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()

                if clean_url and clean_title:
                    snippet_text = ""
                    if orig_idx < len(snippet_matches):
                        snippet_text = unescape(re.sub(r'<[^>]+>', '', snippet_matches[orig_idx])).strip()
                    valid_results.append({
                        "title": clean_title,
                        "url": clean_url,
                        "snippet": snippet_text
                    })

            final_results: List[Dict[str, str]] = [
                {
                    "title": item["title"],
                    "snippet": item["snippet"] or "No snippet available.",
                    "url": item["url"]
                }
                for item in valid_results[:limit]
            ]

            if not final_results:
                return {
                    "query": query, 
                    "results": [], 
                    "message": f"No external web results found for '{query}'. (HTTP Status: {resp.status_code})"
                }

            return {
                "query": query, 
                "count": len(final_results), 
                "results": final_results
            }

        except Exception as e:
            return {"error": f"Web search failed: {str(e)}"}


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetches the HTML content of a URL and converts it into clean, readable text."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The web page URL to fetch."
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters of page text to return."
            }
        },
        "required": ["url"]
    }

    def __init__(self, config_mgr: Optional[Any] = None):
        self._config_mgr = config_mgr

    async def execute(self, url: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
        headers = {"User-Agent": USER_AGENT}
        req_timeout = self._config_mgr.config.timeouts.web if self._config_mgr else 15.0

        try:
            max_chars = int(max_chars) if max_chars is not None else None
        except (ValueError, TypeError):
            max_chars = None

        char_limit = max_chars if max_chars is not None else (self._config_mgr.config.budgets.web if self._config_mgr else 8000)

        try:
            async with httpx.AsyncClient(timeout=req_timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                html_text = resp.text

            cleaned_html = re.sub(
                r'<(script|style|nav|footer|header)[^>]*>.*?</\1>', 
                '', 
                html_text, 
                flags=re.DOTALL | re.IGNORECASE
            )

            text_content = re.sub(r'<[^>]+>', ' ', cleaned_html)
            text_content = unescape(text_content)

            lines = [line.strip() for line in text_content.splitlines() if line.strip()]
            clean_text = "\n".join(lines)

            if len(clean_text) > char_limit:
                clean_text = clean_text[:char_limit] + f"\n\n[... Truncated at {char_limit} characters ...]"

            return {
                "url": url,
                "length": len(clean_text),
                "content": clean_text
            }

        except Exception as e:
            return {"error": f"Failed to fetch URL '{url}': {str(e)}"}
