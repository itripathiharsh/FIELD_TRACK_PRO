from scripts.compare_tally_guid_manifest import compare


def test_compare_finds_records_missing_from_tally_and_not_yet_synced():
    manifest = {"invoices": ["G1", "G2", "G3"], "payments": ["P1"], "customers": []}
    db = {
        "invoices": [("i1", "G1"), ("i2", "G2"), ("i9", "TEST-GUID"), ("i0", None)],
        "payments": [("p1", "P1")],
        "customers": [],
    }
    r = compare(manifest, db)
    assert r["invoices"]["database_not_in_tally"] == [("i9", "TEST-GUID")]
    assert r["invoices"]["database_without_reference"] == ["i0"]
    assert r["invoices"]["tally_not_in_database"] == 1
    assert r["payments"]["database_not_in_tally"] == [] and r["payments"]["tally_not_in_database"] == 0
