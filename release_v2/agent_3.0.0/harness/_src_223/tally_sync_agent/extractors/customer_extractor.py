import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.tally_client import TallyClient
from tally_sync_agent.extractors.brand_resolver import BrandResolver

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


class CustomerExtractor:
    """
    Extracts Customer / Outlet records from Tally Sundry Debtors collections.
    """

    def __init__(self, tally_client: TallyClient):
        self.client = tally_client

    def extract_customers(self, min_alter_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Extracts debtors from Tally.
        Uses AlterID filter if min_alter_id is provided to perform incremental extraction.
        """
        filter_clause = ""
        if min_alter_id and min_alter_id > 0:
            filter_clause = f"<FILTER>AlterIdFilter</FILTER>"

        query = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>DebtorsCol</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="DebtorsCol">
            <TYPE>Ledger</TYPE>
            <CHILDROF>$$GroupSundryDebtors</CHILDROF>
            <BELONGSTO>Yes</BELONGSTO>
            <FETCH>Name, Parent, Guid, AlterId, Address.List, PinCode, StateName, LedgerPhone, LedgerMobile, Mobile, Email, LedgerContact, PartyGstin, OpeningBalance, ClosingBalance, LedMailingDetails.List, LedGstRegDetails.List</FETCH>
            {filter_clause}
          </COLLECTION>
          {f'<SYSTEM TYPE="Formulae" NAME="AlterIdFilter">$$Number:$AlterId &gt; {min_alter_id}</SYSTEM>' if min_alter_id else ''}
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""

        logger.info(f"Extracting debtors from Tally (min_alter_id={min_alter_id})...")
        root = self.client.execute_tdl(query)
        ledgers = root.findall(".//LEDGER")
        logger.info(f"Retrieved {len(ledgers)} debtor ledgers from Tally.")

        extracted: List[Dict[str, Any]] = []
        for led in ledgers:
            name = (led.findtext("NAME") or led.attrib.get("NAME", "")).strip()
            if not name:
                continue

            parent = (led.findtext("PARENT") or "").strip()
            guid = (led.findtext("GUID") or "").strip()
            alter_id_str = (led.findtext("ALTERID") or "0").strip()
            try:
                alter_id = int(alter_id_str)
            except ValueError:
                alter_id = 0

            # Address lines
            address_lines = [
                node.text.strip()
                for node in led.findall(".//ADDRESS.LIST/ADDRESS")
                if node.text and node.text.strip()
            ]
            address = ", ".join(address_lines)
            # TallyPrime 3+ keeps pincode / state / GSTIN in nested detail lists;
            # older releases keep them on the ledger itself. Read whichever is filled.
            pincode = _first_text(led, "PINCODE", ".//LEDMAILINGDETAILS.LIST/PINCODE")
            state = _first_text(led, "STATENAME", ".//LEDMAILINGDETAILS.LIST/STATE")
            phone = _first_text(led, "LEDGERPHONE")
            mobile = _first_text(led, "LEDGERMOBILE", "MOBILE")
            email = _first_text(led, "EMAIL")
            contact_person = _first_text(led, "LEDGERCONTACT")
            gstin = _first_text(led, "PARTYGSTIN", ".//LEDGSTREGDETAILS.LIST/GSTIN")
            # Signed as Tally exports it (sign convention to be confirmed on the
            # client's data with `inspect-ledgers`); a reference figure only.
            closing_balance = _parse_amount(led.findtext("CLOSINGBALANCE"))
            # Balance at the start of the company's books (BooksFrom), signed as exported.
            opening_balance = _parse_amount(led.findtext("OPENINGBALANCE"))

            # Resolve brand
            brand = BrandResolver.resolve(parent_name=parent, ledger_name=name)

            # Detect DMS code in name or address
            outlet_code = None
            dms_match = DMS_REGEX.search(name)
            if dms_match:
                outlet_code = dms_match.group(1).upper()
            elif address:
                dms_match_addr = DMS_REGEX.search(address)
                if dms_match_addr:
                    outlet_code = dms_match_addr.group(1).upper()

            # Parse real Zone and Area from address lines & parent
            zone, area = parse_zone_and_area(name, parent, address_lines)

            extracted.append({
                "source_reference": guid or f"TALLY_LEDGER_{name}",
                "name": name,
                "parent_group": parent,
                "brand": brand,
                "outlet_code": outlet_code,
                "address": address,
                "state": state,
                "pincode": pincode,
                "contact_number": phone,
                "mobile": mobile,
                "email": email,
                "closing_balance": closing_balance,
                "opening_balance": opening_balance,
                "contact_person": contact_person,
                "gst_number": gstin,
                "zone": zone,
                "area": area,
                "alter_id": alter_id,
            })

        return extracted
