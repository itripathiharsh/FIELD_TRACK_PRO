import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger

# Regex to strip invalid XML control characters that Tally sometimes emits
ILLEGAL_XML_CHARS = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]|&#(?:[0-8]|1[124-9]|2[0-9]|3[01]);"
)


class TallyConnectionError(Exception):
    """Raised when communication with TallyPrime fails."""
    pass


class TallyClient:
    """
    Communicates with the local TallyPrime instance via XML over HTTP (port 9000).
    Read-only: export (TDL) requests only. 3.0 removed the v1 voucher write-back code.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.base_url = base_url or settings.tally_url
        self.timeout = timeout or settings.tally_timeout_seconds

    def is_reachable(self) -> bool:
        """Fast non-blocking socket probe to verify if TallyPrime is listening on port 9000."""
        import socket
        from urllib.parse import urlparse
        try:
            parsed = urlparse(self.base_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 9000
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    def _clean_xml(self, raw: str) -> str:
        """Strip control characters and fix unbound namespace prefixes (e.g. UDF:xxx)."""
        cleaned = ILLEGAL_XML_CHARS.sub("", raw)
        return re.sub(r'<(/?)(\w+):', r'<\1\2_', cleaned)

    def send_xml(self, xml_payload: str) -> str:
        """
        Sends raw XML to TallyPrime and returns the response string.
        """
        cleaned_payload = xml_payload.strip()
        data = cleaned_payload.encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Content-Type": "text/xml;charset=utf-8",
                "Connection": "close",
                "Content-Length": str(len(data)),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                raw_text = resp_bytes.decode("utf-8", errors="replace")
                return self._clean_xml(raw_text)
        except urllib.error.URLError as ex:
            logger.warning(f"Tally connection failed: {ex}")
            raise TallyConnectionError(f"Could not connect to Tally at {self.base_url}: {ex}") from ex
        except Exception as ex:
            logger.warning(f"Unexpected error communicating with Tally: {ex}")
            raise TallyConnectionError(f"Tally query failed: {ex}") from ex

    def execute_tdl(self, xml_payload: str) -> ET.Element:
        """
        Sends XML request and parses response into an XML ElementTree root.
        """
        response_text = self.send_xml(xml_payload)
        try:
            return ET.fromstring(response_text)
        except ET.ParseError as pe:
            logger.error(f"Failed to parse XML response from Tally: {pe}")
            # Try once more with aggressive character stripping
            safe_text = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", response_text)
            return ET.fromstring(safe_text)

    def list_companies(self) -> List[Dict[str, str]]:
        """Every company OBJECT loaded in Tally. Scalar <COMPANY>8</COMPANY> count fields (inside
        <CMPINFO>) are not companies and are skipped (the 2.1.0 'blank company', R9)."""
        from tally_sync_agent.extractors import tally_xml as tx
        root = self.execute_tdl(tx.company_request())
        out = []
        for cmp in root.iter("COMPANY"):
            if not len(cmp):
                continue
            name = (cmp.findtext("NAME") or cmp.attrib.get("NAME", "")).strip()
            if not name:
                continue
            out.append({
                "name": name,
                "guid": (cmp.findtext("GUID") or "").strip(),
                "starting_date": (cmp.findtext("STARTINGDATE") or "").strip(),
                "ending_date": (cmp.findtext("ENDINGDATE") or "").strip(),
                "books_from": (cmp.findtext("BOOKSFROM") or "").strip(),
            })
        return out

    def get_company_info(self) -> Optional[Dict[str, Any]]:
        """The company to sync, selected BY GUID (2.2.0, R9). Never guesses:

          * EXPECTED_COMPANY_GUID set   -> that company, or {"error": "WRONG_COMPANY", ...} if not loaded
          * not set, exactly one loaded -> that company
          * more than one loaded        -> {"error": "MULTIPLE_COMPANIES", ...} (unscoped master lists
                                           could otherwise come from another company)
          * none loaded                 -> None
        No GUID is ever made up (2.1.0 fell back to a hard-coded GUID)."""
        try:
            companies = self.list_companies()
        except TallyConnectionError:
            raise
        except Exception as ex:
            logger.warning(f"Failed to query the loaded companies: {ex}")
            return None
        if not companies:
            return None
        names = [c["name"] for c in companies]
        if len(companies) > 1:
            return {"error": "MULTIPLE_COMPANIES", "name": None, "guid": None, "companies": names}
        expected = (settings.expected_company_guid or "").strip()
        c = companies[0]
        if expected and c["guid"] != expected:
            return {"error": "WRONG_COMPANY", "name": c["name"], "guid": c["guid"] or None, "companies": names}
        if not c["guid"]:
            return {"error": "NO_COMPANY_GUID", "name": c["name"], "guid": None, "companies": names}
        return {**c, "companies": names}
