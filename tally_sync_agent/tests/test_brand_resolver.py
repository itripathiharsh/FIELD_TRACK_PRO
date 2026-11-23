from tally_sync_agent.extractors.brand_resolver import BrandResolver


def test_brand_resolver_from_parent():
    assert BrandResolver.resolve_from_parent("Sundry Debtors- PH.") == "Philips"
    assert BrandResolver.resolve_from_parent("Sundry Debtors - PHILIPS") == "Philips"
    assert BrandResolver.resolve_from_parent("Sundry Debtors- Oppo") == "Oppo"
    assert BrandResolver.resolve_from_parent("Sundry Debtors- USHA") == "USHA"
    assert BrandResolver.resolve_from_parent("Sundry Debtors- VU") == "VU"
    assert BrandResolver.resolve_from_parent("General Debtors") is None


def test_brand_resolver_from_name():
    assert BrandResolver.resolve_from_name("Aashi Mobile World (Philips)") == "Philips"
    assert BrandResolver.resolve_from_name("Aashi Mobile World (Oppo)") == "Oppo"
    assert BrandResolver.resolve_from_name("Kanpur Electronics - USHA") == "USHA"
    assert BrandResolver.resolve_from_name("Lucky Store") is None


def test_brand_resolver_precedence():
    # Item brand takes highest priority
    assert BrandResolver.resolve(
        parent_name="Sundry Debtors- PH.",
        ledger_name="Aashi Mobile World (Oppo)",
        item_brand="USHA",
    ) == "USHA"

    # Parent group takes next priority
    assert BrandResolver.resolve(
        parent_name="Sundry Debtors- PH.",
        ledger_name="Aashi Mobile World (Oppo)",
    ) == "Philips"

    # Name suffix takes priority when parent is generic
    assert BrandResolver.resolve(
        parent_name="Sundry Debtors",
        ledger_name="Aashi Mobile World (Oppo)",
    ) == "Oppo"
