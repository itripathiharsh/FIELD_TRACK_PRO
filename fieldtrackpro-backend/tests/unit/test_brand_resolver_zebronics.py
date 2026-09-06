import sys
import os
from pathlib import Path
import pytest

# Ensure tally_sync_agent can be imported
workspace_root = Path(__file__).resolve().parents[4]
if (workspace_root / "tally_sync_agent").exists() and str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from tally_sync_agent.extractors.brand_resolver import BrandResolver
from app.services.brand_service import (
    resolve_canonical_brand_name,
    resolve_from_outlet_code,
    normalize_brand_name,
)


def test_brand_resolver_zebronics_parent_group():
    """Test resolution of Zebronics and variants from Tally parent group."""
    assert BrandResolver.resolve_from_parent("Sundry Debtors - Zebronics") == "Zebronics"
    assert BrandResolver.resolve_from_parent("Sundry Debtors - ZBR") == "Zebronics"
    assert BrandResolver.resolve_from_parent("Sundry Debtors (ZBR)") == "Zebronics"
    assert BrandResolver.resolve_from_parent("Sundry Debtors- PH.") == "Philips"
    assert BrandResolver.resolve_from_parent("Sundry Debtors- Oppo") == "Oppo"
    assert BrandResolver.resolve_from_parent("Sundry Debtors - USHA") == "USHA"
    assert BrandResolver.resolve_from_parent("Sundry Debtors - VU") == "VU"
    assert BrandResolver.resolve_from_parent("Sundry Debtors") is None


def test_brand_resolver_outlet_code():
    """Test resolution of Zebronics and other brands from DMS outlet code prefix."""
    assert BrandResolver.resolve_from_code("SGRGZBR3201") == "Zebronics"
    assert BrandResolver.resolve_from_code("sgrgzbr9999") == "Zebronics"
    assert BrandResolver.resolve_from_code("SGRGUS1455") == "USHA"
    assert BrandResolver.resolve_from_code("SGRGVU3241") == "VU"
    assert BrandResolver.resolve_from_code("UPDD00678399") == "Philips"
    assert BrandResolver.resolve_from_code("RANDOM1234") is None
    assert BrandResolver.resolve_from_code(None) is None


def test_brand_resolver_ledger_name():
    """Test resolution of Zebronics suffix in ledger name."""
    assert BrandResolver.resolve_from_name("R.K. Telecom (Zebronics)") == "Zebronics"
    assert BrandResolver.resolve_from_name("Shree Ram Info (ZBR)") == "Zebronics"
    assert BrandResolver.resolve_from_name("Aashi Mobile World (Philips)") == "Philips"
    assert BrandResolver.resolve_from_name("Sai Communications (Oppo)") == "Oppo"
    assert BrandResolver.resolve_from_name("Generic Store") is None


def test_brand_service_backend_canonicalization():
    """Test backend brand service canonical resolution and aliases."""
    assert resolve_canonical_brand_name("zbr") == "Zebronics"
    assert resolve_canonical_brand_name("ZEBRONICS") == "Zebronics"
    assert resolve_canonical_brand_name("Zebronics") == "Zebronics"
    assert resolve_canonical_brand_name("usha") == "USHA"
    assert resolve_canonical_brand_name("vu") == "VU"
    assert resolve_canonical_brand_name("oppo") == "Oppo"
    assert resolve_canonical_brand_name("philips") == "Philips"
    assert resolve_canonical_brand_name("ph") == "Philips"

    assert resolve_from_outlet_code("SGRGZBR1234") == "Zebronics"
    assert resolve_from_outlet_code("SGRGUS5678") == "USHA"
    assert resolve_from_outlet_code("SGRGVU9012") == "VU"
    assert resolve_from_outlet_code("UPDD3456") == "Philips"
    assert resolve_from_outlet_code(None) is None
