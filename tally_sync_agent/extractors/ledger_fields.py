"""Ledger-field helpers used by the v2/3.0 extractors (moved from the removed v1 customer_extractor in 3.0)."""
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


# Regex to detect standard DMS codes (e.g. UPDD00678399, DMS12345, etc.)
DMS_REGEX = re.compile(r"\b([A-Z]{2,4}\d{6,10})\b", re.IGNORECASE)

KNOWN_STATES = {"uttar pradesh", "up", "delhi", "haryana", "bihar", "madhya pradesh", "mp", "uttarakhand", "rajasthan", "maharashtra"}

PHONE_OR_GARBAGE = re.compile(
    r"^(mob|ph|phone|contact|tel|c/o|m-|\+?91|\d{6}$|\d{10}$)", re.IGNORECASE
)

DISTRICT_MAP = {
    "kanpur nagar": "Kanpur",
    "kanpur dehat": "Kanpur Dehat",
    "kanpur": "Kanpur",
    "knp": "Kanpur",
    "unnao": "Unnao",
    "lucknow": "Lucknow",
    "lko": "Lucknow",
    "varanasi": "Varanasi",
    "banaras": "Varanasi",
    "prayagraj": "Prayagraj",
    "allahabad": "Prayagraj",
    "gorakhpur": "Gorakhpur",
    "gkp": "Gorakhpur",
    "ballia": "Ballia",
    "kannauj": "Kannauj",
    "fatehpur": "Fatehpur",
    "azamgarh": "Azamgarh",
    "jaunpur": "Jaunpur",
    "mau": "Mau",
    "noida": "Noida",
    "greater noida": "Noida",
    "gautam buddha nagar": "Noida",
    "gautambuddha nagar": "Noida",
    "haridwar": "Haridwar",
    "dehradun": "Dehradun",
    "gurugram": "Gurugram",
    "gurgaon": "Gurugram",
    "ghaziabad": "Ghaziabad",
    "ayodhya": "Ayodhya",
    "faizabad": "Ayodhya",
    "bareilly": "Bareilly",
    "aligarh": "Aligarh",
    "agra": "Agra",
    "jhansi": "Jhansi",
    "etawah": "Etawah",
    "auraiya": "Auraiya",
    "farrukhabad": "Farrukhabad",
    "hardoi": "Hardoi",
    "sitapur": "Sitapur",
    "raebareli": "Raebareli",
    "barabanki": "Barabanki",
    "mirzapur": "Mirzapur",
    "ghazipur": "Ghazipur",
    "chandauli": "Chandauli",
    "basti": "Basti",
    "sant kabir nagar": "Sant Kabir Nagar",
    "siddharthnagar": "Siddharthnagar",
    "maharajganj": "Maharajganj",
    "kushinagar": "Kushinagar",
    "deoria": "Deoria",
    "bhadohi": "Bhadohi",
    "sonbhadra": "Sonbhadra",
    "amethi": "Amethi",
    "sultanpur": "Sultanpur",
    "pauri garhwal": "Pauri Garhwal",
    "meerut": "Meerut",
    "sonipat": "Sonipat",
    "mumbai": "Mumbai",
    "mumbai suburban": "Mumbai",
    "new delhi": "Delhi",
}

LOCALITY_TO_ZONE = {
    # Kanpur Nagar localities
    "kalyanpur": ("Kanpur", "Kalyanpur"),
    "kidwai nagar": ("Kanpur", "Kidwai Nagar"),
    "govind nagar": ("Kanpur", "Govind Nagar"),
    "yashoda nagar": ("Kanpur", "Yashoda Nagar"),
    "panki": ("Kanpur", "Panki"),
    "rawatpur": ("Kanpur", "Rawatpur"),
    "lal bangla": ("Kanpur", "Lal Bangla"),
    "barra": ("Kanpur", "Barra"),
    "jajmau": ("Kanpur", "Jajmau"),
    "chakeri": ("Kanpur", "Chakeri"),
    "kakadeo": ("Kanpur", "Kakadeo"),
    "ghatampur": ("Kanpur", "Ghatampur"),
    "bilhaur": ("Kanpur", "Bilhaur"),
    "bithoor": ("Kanpur", "Bithoor"),
    "naubasta": ("Kanpur", "Naubasta"),
    "gujaini": ("Kanpur", "Gujaini"),
    "patara": ("Kanpur", "Patara"),
    "shyam nagar": ("Kanpur", "Shyam Nagar"),
    "harjinder nagar": ("Kanpur", "Harjinder Nagar"),
    "shastri nagar": ("Kanpur", "Shastri Nagar"),
    "sanigawan": ("Kanpur", "Sanigawan Road"),
    "fazalganj": ("Kanpur", "Fazalganj"),
    "armapur": ("Kanpur", "Armapur"),
    "gwaltoli": ("Kanpur", "Gwaltoli"),
    "gaultoli": ("Kanpur", "Gwaltoli"),
    "swaroop nagar": ("Kanpur", "Swaroop Nagar"),
    "arya nagar": ("Kanpur", "Arya Nagar"),
    "gumti": ("Kanpur", "Gumti"),
    "nayaganj": ("Kanpur", "Nayaganj"),
    "birhana road": ("Kanpur", "Birhana Road"),
    "vijay nagar": ("Kanpur", "Vijay Nagar"),
    "geeta ngr": ("Kanpur", "Geeta Nagar"),
    "kaushalpuri": ("Kanpur", "Kaushalpuri"),
    "dindyalpuram": ("Kanpur", "Naubasta"),

    # Unnao localities
    "shuklaganj": ("Unnao", "Shuklaganj"),
    "safipur": ("Unnao", "Safipur"),
    "bangarmau": ("Unnao", "Bangarmau"),
    "nawabganj": ("Unnao", "Nawabganj"),
    "maurawan": ("Unnao", "Maurawan"),
    "hasanganj": ("Unnao", "Hasanganj"),
    "purwa": ("Unnao", "Purwa"),
    "gangaghat": ("Unnao", "Shuklaganj"),
    "achhalganj": ("Unnao", "Achhalganj"),
    "bighapur": ("Unnao", "Bighapur"),
    "miyanganj": ("Unnao", "Miyanganj"),
    "fatehpur chaurasi": ("Unnao", "Fatehpur Chaurasi"),
    "adarsh nagar": ("Unnao", "Adarsh Nagar"),

    # Kanpur Dehat localities
    "raniya": ("Kanpur Dehat", "Raniyan"),
    "raniyan": ("Kanpur Dehat", "Raniyan"),
    "akbarpur": ("Kanpur Dehat", "Akbarpur"),
    "jhinjhak": ("Kanpur Dehat", "Jhinjhak"),
    "rasulabad": ("Kanpur Dehat", "Rasulabad"),
    "bhognipur": ("Kanpur Dehat", "Bhognipur"),
    "sikandra": ("Kanpur Dehat", "Sikandra"),
    "rura": ("Kanpur Dehat", "Rura"),
    "pukhrayan": ("Kanpur Dehat", "Pukhrayan"),
    "derapur": ("Kanpur Dehat", "Derapur"),
    "shivli": ("Kanpur Dehat", "Shivli"),
}


def _first_text(elem: ET.Element, *paths: str) -> str:
    """First non-empty text among the given child tags / XPath-lite paths."""
    for path in paths:
        for node in elem.findall(path):
            if node.text and node.text.strip():
                return node.text.strip()
    return ""


def _parse_amount(raw: Optional[str]) -> Optional[float]:
    if not raw or not raw.strip():
        return None
    try:
        return float(raw.strip().replace(",", ""))
    except ValueError:
        return None


def parse_zone_and_area(name: str, parent: str, address_lines: list[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Extracts real Zone and Area from Tally address lines and parent groups.
    Does NOT guess fake data.
    """
    clean_lines = []
    for l in address_lines:
        s = l.strip()
        if not s or s in ["00", "0", "-", ".", ","]:
            continue
        if PHONE_OR_GARBAGE.match(s):
            continue
        s = re.sub(r"[\s,;]+(mob|ph|phone)[\.:\s\-#]*\d.*$", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"[\s,-]+\d{6}$", "", s).strip()
        if s and s.lower() not in KNOWN_STATES:
            clean_lines.append(s)

    zone = None
    area = None

    # 1. Search for known District in clean_lines (from bottom up)
    for line in reversed(clean_lines):
        l_low = line.lower()
        for k, target_zone in DISTRICT_MAP.items():
            if re.search(r"\b" + re.escape(k) + r"\b", l_low):
                zone = target_zone
                break
        if zone:
            break

    # 2. Check for known Localities in clean_lines
    matched_locality = None
    for line in reversed(clean_lines):
        l_low = line.lower()
        for loc_key, (loc_zone, loc_area) in LOCALITY_TO_ZONE.items():
            if re.search(r"\b" + re.escape(loc_key) + r"\b", l_low):
                matched_locality = (loc_zone, loc_area)
                if not zone:
                    zone = loc_zone
                area = loc_area
                break
        if matched_locality:
            break

    # 3. Fallback for Zone from Parent Group or Name
    if not zone:
        for source_str in [parent, name]:
            s_low = source_str.lower()
            for k, target_zone in DISTRICT_MAP.items():
                if re.search(r"\b" + re.escape(k) + r"\b", s_low):
                    zone = target_zone
                    break
            if zone:
                break

    # Also check locality in name if still no area
    if not area:
        n_low = name.lower()
        for loc_key, (loc_zone, loc_area) in LOCALITY_TO_ZONE.items():
            if re.search(r"\b" + re.escape(loc_key) + r"\b", n_low):
                if not zone:
                    zone = loc_zone
                area = loc_area
                break

    # 4. Resolve Area if zone exists but area wasn't from LOCALITY_TO_ZONE
    if zone and not area and clean_lines:
        candidate_areas = []
        for line in clean_lines:
            if line.lower() in [zone.lower(), f"{zone.lower()} nagar", f"{zone.lower()} dehat"]:
                continue
            if re.match(r"^(\d+[\w\s\-\/\.\,]*)?$", line) and len(line) < 6:
                continue
            candidate_areas.append(line)

        if candidate_areas:
            area = candidate_areas[-1]
            if re.search(r"\b" + re.escape(zone) + r"\b", area, re.IGNORECASE):
                cleaned_a = re.sub(r"\b" + re.escape(zone) + r"\b", "", area, flags=re.IGNORECASE).strip(" ,-")
                if cleaned_a:
                    area = cleaned_a
        else:
            area = f"{zone} Central"
    elif zone and not area:
        area = f"{zone} Central"

    if zone and area:
        zone = zone.strip().title()
        area = area.strip().title()
        if area.lower() == zone.lower():
            area = f"{zone} City"
        return zone, area
    return None, None
