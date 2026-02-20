"""Bright Data tool wrappers — search, scrape, download."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from markdownify import markdownify as md

from src.config.settings import get_config, get_settings

logger = logging.getLogger(__name__)

# PDF/Excel content inspection
try:
    import fitz  # pymupdf

    def _inspect_pdf(filepath: Path) -> dict:
        """Read first 2 pages of a PDF, return text snippet and metadata."""
        try:
            doc = fitz.open(str(filepath))
            info = {"pages": len(doc), "valid": True}
            text_parts = []
            for i in range(min(2, len(doc))):
                page_text = doc[i].get_text().strip()
                if page_text:
                    text_parts.append(page_text[:600])
            doc.close()
            info["first_pages_text"] = "\n---\n".join(text_parts) if text_parts else "(no extractable text)"
            return info
        except Exception as exc:
            return {"valid": False, "error": str(exc)}

except ImportError:
    def _inspect_pdf(filepath: Path) -> dict:
        """Fallback: check magic bytes only."""
        try:
            with open(filepath, "rb") as f:
                header = f.read(5)
            return {"valid": header == b"%PDF-", "pages": None, "first_pages_text": "(pymupdf not installed)"}
        except Exception as exc:
            return {"valid": False, "error": str(exc)}


def _inspect_xlsx(filepath: Path) -> dict:
    """Check if an XLSX/XLS file is a valid archive."""
    try:
        if filepath.suffix.lower() == ".xlsx":
            with zipfile.ZipFile(filepath) as z:
                names = z.namelist()
            return {"valid": True, "entries": len(names), "is_zip": True}
        else:
            # .xls — check OLE2 magic bytes
            with open(filepath, "rb") as f:
                header = f.read(8)
            is_ole = header[:4] == b"\xd0\xcf\x11\xe0"
            return {"valid": is_ole, "is_ole": is_ole}
    except (zipfile.BadZipFile, Exception) as exc:
        return {"valid": False, "error": str(exc)}

_API_BASE = "https://api.brightdata.com/request"
_CONTENT_LIMIT = 12000  # chars of converted markdown to keep


def _api_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().BRIGHT_DATA_API_TOKEN}",
        "Content-Type": "application/json",
    }


# ── search ──────────────────────────────────────────────────────────────────

def search(query: str) -> dict:
    """Run a SERP search via Bright Data and return organic results."""
    cfg = get_config().bright_data
    payload = {
        "zone": cfg.serp_zone,
        "url": f"https://www.google.com/search?q={requests.utils.quote(query)}&num=10",
        "format": "raw",
    }
    try:
        resp = requests.post(_API_BASE, json=payload, headers=_api_headers(), timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("SERP search failed: %s", exc)
        return {"error": str(exc), "results": []}

    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    organic = data.get("organic", [])

    results = []
    for item in organic[:10]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", item.get("url", "")),
            "snippet": item.get("description", item.get("snippet", "")),
        })

    if not results and resp.text:
        return {"results": [], "note": "SERP returned HTML instead of structured data. Try a different query."}

    return {"results": results}


# ── scrape_page ─────────────────────────────────────────────────────────────

def scrape_page(url: str) -> dict:
    """Scrape a page via Bright Data Web Unlocker, convert HTML to markdown."""
    cfg = get_config().bright_data
    payload = {
        "zone": cfg.web_unlocker_zone,
        "url": url,
        "format": "raw",
    }
    try:
        resp = requests.post(_API_BASE, json=payload, headers=_api_headers(), timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Scrape failed for %s: %s", url, exc)
        return {"error": str(exc), "url": url, "content": ""}

    raw_html = resp.text
    content_type = resp.headers.get("content-type", "")

    # Convert HTML to clean markdown
    if "html" in content_type or raw_html.strip().startswith("<"):
        content = md(raw_html, strip=["script", "style", "nav", "footer", "header"])
        # Clean up excessive whitespace from conversion
        lines = [line.strip() for line in content.splitlines()]
        content = "\n".join(line for line in lines if line)
    else:
        content = raw_html

    content = content[:_CONTENT_LIMIT]
    return {"url": url, "content": content, "content_type": content_type}


# ── download_file ───────────────────────────────────────────────────────────

def download_file(url: str, filename: str) -> dict:
    """Download a file through Bright Data Web Unlocker API and save to disk."""
    cfg = get_config().bright_data

    # Only allow bare filenames, never paths.
    requested_name = (filename or "").strip()
    if not requested_name:
        return {
            "url": url,
            "filename": filename,
            "error": "Filename is required.",
            "success": False,
        }

    if Path(requested_name).name != requested_name:
        return {
            "url": url,
            "filename": filename,
            "error": "Invalid filename. Provide a basename only, without directories.",
            "success": False,
        }

    dl_dir = Path(get_config().download.base_dir)
    dl_dir.mkdir(parents=True, exist_ok=True)
    filepath = dl_dir / requested_name

    # Extract the filename from the URL for verification
    parsed = urlparse(url)
    url_filename = Path(parsed.path).name if parsed.path else ""

    try:
        payload = {
            "zone": cfg.web_unlocker_zone,
            "url": url,
            "format": "raw",
        }
        resp = requests.post(_API_BASE, json=payload, headers=_api_headers(), timeout=90)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        # Auto-reject: HTML response when expecting a binary file
        is_binary_ext = any(requested_name.lower().endswith(e) for e in (".pdf", ".xlsx", ".xls"))
        if is_binary_ext and "html" in content_type.lower():
            return {
                "url": url,
                "filename": requested_name,
                "error": f"URL returned HTML (content-type: {content_type}) instead of the expected file. This URL likely points to a web page, not a downloadable file. Try finding the direct download link.",
                "success": False,
            }

        with open(filepath, "wb") as f:
            f.write(resp.content)

        size = filepath.stat().st_size

        result = {
            "url": url,
            "filename": requested_name,
            "path": str(filepath),
            "size_bytes": size,
            "content_type": content_type,
            "url_filename": url_filename,
            "success": True,
        }

        # Content inspection — verify the file is what it claims to be
        if requested_name.lower().endswith(".pdf"):
            inspection = _inspect_pdf(filepath)
            result["file_inspection"] = inspection
            if not inspection.get("valid"):
                result["warning"] = f"File does not appear to be a valid PDF: {inspection.get('error', 'invalid header')}"
            elif inspection.get("first_pages_text"):
                # Include snippet so the LLM can verify document identity
                result["first_pages_preview"] = inspection["first_pages_text"][:800]
                result["page_count"] = inspection.get("pages")
        elif requested_name.lower().endswith((".xlsx", ".xls")):
            inspection = _inspect_xlsx(filepath)
            result["file_inspection"] = inspection
            if not inspection.get("valid"):
                result["warning"] = f"File does not appear to be a valid Excel file: {inspection.get('error', 'invalid format')}"

        return result
    except requests.RequestException as exc:
        logger.error("Download failed for %s: %s", url, exc)
        return {
            "url": url,
            "filename": requested_name,
            "error": str(exc),
            "success": False,
        }
