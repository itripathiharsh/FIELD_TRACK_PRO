import re
from typing import Optional

# Known brand map: (pattern -> Canonical Brand Name)
BRAND_PATTERNS = [
    (re.compile(r"\b(philips|ph\b|ph\.)", re.IGNORECASE), "Philips"),
    (re.compile(r"\b(oppo)\b", re.IGNORECASE), "Oppo"),
    (re.compile(r"\b(usha)\b", re.IGNORECASE), "USHA"),
    (re.compile(r"\b(vu)\b", re.IGNORECASE), "VU"),
    (re.compile(r"\b(zebronics|zbr)\b", re.IGNORECASE), "Zebronics"),
    (re.compile(r"\b(vivo)\b", re.IGNORECASE), "Vivo"),
    (re.compile(r"\b(samsung)\b", re.IGNORECASE), "Samsung"),
    (re.compile(r"\b(realme)\b", re.IGNORECASE), "Realme"),
    (re.compile(r"\b(oneplus)\b", re.IGNORECASE), "OnePlus"),
    (re.compile(r"\b(xiaomi|mi)\b", re.IGNORECASE), "Xiaomi"),
]


class BrandResolver:
    """
    Resolves client brands according to actual Tally structure and naming conventions.
    """

    @staticmethod
    def resolve_from_parent(parent_name: Optional[str]) -> Optional[str]:
        """
        Extracts brand from parent group name.
        e.g., 'Sundry Debtors- PH.' -> 'Philips'
              'Sundry Debtors- Oppo' -> 'Oppo'
              'Sundry Debtors - Zebronics' -> 'Zebronics'
        """
        if not parent_name:
            return None
            
        clean = parent_name.strip()
        for pattern, canonical in BRAND_PATTERNS:
            if pattern.search(clean):
                return canonical
                
        return None

    @staticmethod
    def resolve_from_code(outlet_code: Optional[str]) -> Optional[str]:
        """
        Resolves brand from structured DMS / outlet code prefix.
        e.g., 'SGRGZBR3201' -> 'Zebronics'
              'SGRGUS1455'  -> 'USHA'
              'SGRGVU3241'  -> 'VU'
              'UPDD00678399' -> 'Philips'
        """
        if not outlet_code:
            return None
        code = outlet_code.strip().upper()
        if code.startswith("SGRGZBR"):
            return "Zebronics"
        if code.startswith("SGRGUS"):
            return "USHA"
        if code.startswith("SGRGVU"):
            return "VU"
        if code.startswith("UPDD"):
            return "Philips"
        return None

    @staticmethod
    def resolve_from_name(ledger_name: Optional[str]) -> Optional[str]:
        """
        Extracts brand suffix from ledger name if present.
        e.g., 'Aashi Mobile World (Philips)' -> 'Philips'
              'Z1 Eletronics (zbr)' -> 'Zebronics'
        """
        if not ledger_name:
            return None

        # Check inside parentheses, brackets or after dash
        match = re.search(r"[\(\[\-]\s*([a-zA-Z0-9\.\s]+)\s*[\)\]]?$", ledger_name)
        if match:
            suffix = match.group(1).strip()
            for pattern, canonical in BRAND_PATTERNS:
                if pattern.search(suffix):
                    return canonical

        # Check anywhere in the name
        for pattern, canonical in BRAND_PATTERNS:
            if pattern.search(ledger_name):
                return canonical

        # Check for embedded UPDD code in name, e.g. 'Warsi Telecom (UPDD640001)'
        if "updd" in ledger_name.lower():
            return "Philips"

        return None

    @classmethod
    def resolve(
        cls,
        parent_name: Optional[str] = None,
        ledger_name: Optional[str] = None,
        item_brand: Optional[str] = None,
        outlet_code: Optional[str] = None,
    ) -> Optional[str]:
        """
        Comprehensive resolution:
        1. Item brand if explicitly provided
        2. Structured outlet/DMS code prefix (SGRGZBR, SGRGUS, SGRGVU, UPDD)
        3. Parent group (highest authority in Tally structure)
        4. Ledger name suffix/mention
        """
        if item_brand:
            for pattern, canonical in BRAND_PATTERNS:
                if pattern.search(item_brand):
                    return canonical
            return item_brand.strip()

        from_code = cls.resolve_from_code(outlet_code)
        if from_code:
            return from_code

        from_parent = cls.resolve_from_parent(parent_name)
        if from_parent:
            return from_parent

        from_name = cls.resolve_from_name(ledger_name)
        if from_name:
            return from_name

        return None
