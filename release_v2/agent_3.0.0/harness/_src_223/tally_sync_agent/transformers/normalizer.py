from typing import Any, Dict, List, Optional


class Normalizer:
    """
    Transforms extracted Tally entities into clean, normalized FieldTrack schemas.
    """

    @staticmethod
    def normalize_customer(item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes customer dictionary for CustomerSyncItem."""
        return {
            "source_reference": str(item.get("source_reference", "")).strip(),
            "outlet_code": str(item.get("outlet_code", "")).strip() if item.get("outlet_code") else None,
            "name": str(item.get("name", "")).strip(),
            "parent_group": str(item.get("parent_group", "")).strip() if item.get("parent_group") else None,
            "brand": str(item.get("brand", "")).strip() if item.get("brand") else None,
            "address": str(item.get("address", "")).strip() if item.get("address") else None,
            "state": str(item.get("state", "")).strip() if item.get("state") else None,
            "pincode": str(item.get("pincode", "")).strip() if item.get("pincode") else None,
            "gst_number": str(item.get("gst_number", "")).strip() if item.get("gst_number") else None,
            "contact_number": str(item.get("contact_number", "")).strip() if item.get("contact_number") else None,
            "mobile": str(item.get("mobile", "")).strip() if item.get("mobile") else None,
            "email": str(item.get("email", "")).strip() if item.get("email") else None,
            "closing_balance": round(float(item["closing_balance"]), 2) if item.get("closing_balance") is not None else None,
            "opening_balance": round(float(item["opening_balance"]), 2) if item.get("opening_balance") is not None else None,
            "contact_person": str(item.get("contact_person", "")).strip() if item.get("contact_person") else None,
            "zone": str(item.get("zone", "")).strip() if item.get("zone") else None,
            "area": str(item.get("area", "")).strip() if item.get("area") else None,
            "alter_id": int(item.get("alter_id", 0)),
        }

    @staticmethod
    def normalize_invoice(item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes invoice dictionary for InvoiceSyncItem."""
        return {
            "source_reference": str(item.get("source_reference", "")).strip(),
            "invoice_number": str(item.get("invoice_number", "")).strip(),
            "outlet_code": str(item.get("outlet_code", "")).strip() if item.get("outlet_code") else None,
            "customer_name": str(item.get("customer_name", "")).strip(),
            "invoice_date": str(item.get("invoice_date", "")).strip(),
            "due_date": str(item.get("due_date", "")).strip() if item.get("due_date") else None,
            "amount": round(float(item.get("amount", 0.0)), 2),
            "brand": str(item.get("brand", "")).strip() if item.get("brand") else None,
            "voucher_type": str(item.get("voucher_type", "Sales")).strip(),
            "bill_name": str(item.get("bill_name", "")).strip() if item.get("bill_name") else None,
            "imported_outstanding_amount": round(float(item.get("imported_outstanding_amount", 0.0)), 2)
            if item.get("imported_outstanding_amount") is not None
            else None,
            "alter_id": int(item.get("alter_id", 0)),
        }

    @staticmethod
    def normalize_payment(item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes payment dictionary for PaymentSyncItem."""
        return {
            "source_reference": str(item.get("source_reference", "")).strip(),
            "receipt_number": str(item.get("receipt_number", "")).strip(),
            "outlet_code": str(item.get("outlet_code", "")).strip() if item.get("outlet_code") else None,
            "customer_name": str(item.get("customer_name", "")).strip(),
            "payment_date": str(item.get("payment_date", "")).strip(),
            "amount": round(float(item.get("amount", 0.0)), 2),
            "payment_method": str(item.get("payment_method", "CASH")).strip().upper(),
            "utr_reference": str(item.get("utr_reference", "")).strip() if item.get("utr_reference") else None,
            "cheque_number": str(item.get("cheque_number", "")).strip() if item.get("cheque_number") else None,
            "notes": str(item.get("notes", "")).strip() if item.get("notes") else None,
            "brand_allocations": item.get("brand_allocations") or [],
            # Tally's own bill-wise settlement ("Agst Ref" etc.): which invoice(s) this receipt pays.
            "bill_allocations": item.get("bill_allocations") or [],
            "alter_id": int(item.get("alter_id", 0)),
        }
