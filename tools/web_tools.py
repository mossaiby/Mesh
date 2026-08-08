import re
import urllib.parse
from html import unescape
from typing import Dict, Any, List, Optional
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

    async def execute(self, query: str, max_results: int = 4) -> Dict[str, Any]:
        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        data = {"q": query}

        # Limit result count strictly between 1 and 5
        limit = min(max(1, max_results), 5)

        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.post(url, data=data, headers=headers)
                html_text = resp.text

            # Parse DuckDuckGo Lite HTML. Scope the link regex to result-link
            # anchors specifically (rather than every <a> tag on the page) so
            # link_matches stays aligned, position-for-position, with
            # snippet_matches -- otherwise unrelated anchors (nav, pagination,
            # header) could shift the two lists out of sync and pair a title
            # with the wrong snippet.
            link_matches = re.findall(
                r'<a[^>]*class=["\']result-link["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                html_text, re.DOTALL
            )
            snippet_matches = re.findall(r'<td[^>]*class=["\']result-snippet["\'][^>]*>(.*?)</td>', html_text, re.DOTALL)

            valid_results: List[Dict[str, str]] = []
            seen_urls = set()

            # Walk link_matches and snippet_matches together (they come from
            # the same ordered sequence of result rows) so a title is always
            # paired with the snippet from its own row, even if earlier rows
            # get skipped as internal/duplicate links.
            for orig_idx, (url_str, raw_title) in enumerate(link_matches):
                # Extract clean target URL if wrapped in DuckDuckGo redirect
                if "uddg=" in url_str:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url_str).query)
                    clean_url = parsed.get("uddg", [url_str])[0]
                else:
                    clean_url = url_str

                # Filter out internal DuckDuckGo links, relative links, or duplicates
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
                "description": "Maximum characters of page text to return (default: 8000)."
            }
        },
        "required": ["url"]
    }

    async def execute(self, url: str, max_chars: int = 8000) -> Dict[str, Any]:
        headers = {"User-Agent": USER_AGENT}

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                html_text = resp.text

            # Strip scripts, styles, navigation, headers, and footers
            cleaned_html = re.sub(
                r'<(script|style|nav|footer|header)[^>]*>.*?</\1>', 
                '', 
                html_text, 
                flags=re.DOTALL | re.IGNORECASE
            )

            # Remove remaining HTML tags
            text_content = re.sub(r'<[^>]+>', ' ', cleaned_html)
            text_content = unescape(text_content)

            # Normalize lines and whitespace
            lines = [line.strip() for line in text_content.splitlines() if line.strip()]
            clean_text = "\n".join(lines)

            if len(clean_text) > max_chars:
                clean_text = clean_text[:max_chars] + f"\n\n[... Truncated at {max_chars} characters ...]"

            return {
                "url": url,
                "length": len(clean_text),
                "content": clean_text
            }

        except Exception as e:
            return {"error": f"Failed to fetch URL '{url}': {str(e)}"}