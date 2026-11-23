"""
Contract the FieldTrack backend relies on for FOS synchronisation (release 3.2): in this client's Tally the FOS of a
customer is the PARENT GROUP of the customer's ledger, so every debtor ledger the agent exports must carry that group
exactly as Tally spells it (the backend normalises case / padding itself). Read-only: pure XML parsing, no Tally call.
"""
import xml.etree.ElementTree as ET

from tally_sync_agent.extractors import v2_extractors as v2


def _ledger(name: str, parent: str) -> ET.Element:
    return ET.fromstring(
        f'<LEDGER NAME="{name}"><GUID>g-{name}</GUID><PARENT>{parent}</PARENT>'
        "<OPENINGBALANCE>0</OPENINGBALANCE><CLOSINGBALANCE>0</CLOSINGBALANCE></LEDGER>"
    )


def test_debtor_payload_carries_the_ledger_group_exactly_as_tally_spells_it():
    item = v2.parse_debtor(_ledger("Katiyar Watch &amp; Radio (ZBR)", "Neeraj  (ZBR)"))
    assert item["parent"] == "Neeraj  (ZBR)"          # double space kept: the backend normalises it
    assert item["is_debtor"] is True and item["guid"] == "g-Katiyar Watch & Radio (ZBR)"


def test_moving_a_ledger_to_another_group_changes_the_exported_parent():
    before = v2.parse_debtor(_ledger("Sharma Mobiles", "Raunak Usha"))
    after = v2.parse_debtor(_ledger("Sharma Mobiles", "Sahil Gautam (Usha)"))
    assert (before["parent"], after["parent"]) == ("Raunak Usha", "Sahil Gautam (Usha)")
    assert before["guid"] == after["guid"]            # same ledger identity, new group


def test_non_debtor_snapshot_items_also_carry_their_group():
    masters = v2.Masters(ledger_parent={"Bank": "Bank Accounts"}, ledger_guid={"Bank": "gb"}, ledger_aliases={"Bank": []})
    items = {i["name"]: i for i in v2.ledger_snapshot_items(masters)}
    assert items["Bank"]["parent"] == "Bank Accounts" and items["Bank"]["is_debtor"] is False
