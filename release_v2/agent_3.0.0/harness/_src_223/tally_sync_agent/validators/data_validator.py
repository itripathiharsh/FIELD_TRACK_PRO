import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from tally_sync_agent.core.logger import logger

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DataValidator:
    """
    Performs pre-flight data validation on extracted records before sending to backend.
    Rejects/quarantines malformed items to guarantee data integrity.
    """

    @classmethod
    def validate_customer(cls, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates customer record."""
        name = item.get("name")
        if not name or not str(name).strip():
            return False, "Missing customer name"

        if not item.get("source_reference"):
            return False, "Missing source_reference"

        return True, None

    @classmethod
    def validate_invoice(cls, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates invoice record."""
        inv_num = item.get("invoice_number")
        if not inv_num or not str(inv_num).strip():
            return False, "Missing invoice_number"

        cust_name = item.get("customer_name")
        if not cust_name or not str(cust_name).strip():
            return False, "Missing customer_name"

        inv_date = item.get("invoice_date")
        if not inv_date or not DATE_PATTERN.match(str(inv_date)):
            return False, f"Invalid invoice_date format: {inv_date}"

        amount = item.get("amount")
        if amount is None or float(amount) < 0:
            return False, f"Invalid invoice amount: {amount}"

        return True, None

    @classmethod
    def validate_payment(cls, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates payment/receipt record."""
        receipt_num = item.get("receipt_number")
        if not receipt_num or not str(receipt_num).strip():
            return False, "Missing receipt_number"

        cust_name = item.get("customer_name")
        if not cust_name or not str(cust_name).strip():
            return False, "Missing customer_name"

        pmt_date = item.get("payment_date")
        if not pmt_date or not DATE_PATTERN.match(str(pmt_date)):
            return False, f"Invalid payment_date format: {pmt_date}"

        amount = item.get("amount")
        if amount is None or float(amount) <= 0:
            return False, f"Invalid payment amount: {amount}"

        return True, None

    @classmethod
    def filter_valid(
        cls, entity_type: str, records: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Partitions records into (valid_records, rejected_records).
        """
        valid = []
        rejected = []

        for item in records:
            if entity_type == "customers":
                is_valid, err = cls.validate_customer(item)
            elif entity_type == "invoices":
                is_valid, err = cls.validate_invoice(item)
            elif entity_type == "payments":
                is_valid, err = cls.validate_payment(item)
            else:
                is_valid, err = True, None

            if is_valid:
                valid.append(item)
            else:
                item_copy = dict(item)
                item_copy["validation_error"] = err
                rejected.append(item_copy)
                logger.warning(f"VALIDATION_FAILED entity={entity_type} error={err} record={item.get('source_reference')}")

        return valid, rejected
