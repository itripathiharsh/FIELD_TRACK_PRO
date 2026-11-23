import time
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from tally_sync_agent.config.settings import settings, AGENT_VERSION
from tally_sync_agent.core.backend_client import BackendClient, BackendServerError, BackendAuthError
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError
from tally_sync_agent.extractors.customer_extractor import CustomerExtractor
from tally_sync_agent.extractors.invoice_extractor import InvoiceExtractor
from tally_sync_agent.extractors.payment_extractor import PaymentExtractor
from tally_sync_agent.transformers.normalizer import Normalizer
from tally_sync_agent.validators.data_validator import DataValidator


def _safe_checkpoint_alter_id(
    valid_items: List[Dict[str, Any]],
    rejected_items: List[Dict[str, Any]],
    current_alter_id: int,
) -> int:
    """
    Computes the next checkpoint AlterID such that it never advances past a validation-
    rejected record that is still unresolved in this batch.

    Without this, a later/higher-AlterID valid record being uploaded successfully would
    advance the checkpoint past an earlier/lower-AlterID rejected record, and Tally's
    incremental filter (AlterID > checkpoint) means that rejected record would then never
    be fetched again. This caps the advance at (lowest rejected AlterID - 1), so the
    rejected record stays inside the sync window on every future cycle until it is fixed
    (at which point it will be re-extracted and re-validated). It never regresses below
    the current checkpoint.
    """
    target = current_alter_id
    if valid_items:
        target = max(target, max(item["alter_id"] for item in valid_items))

    if rejected_items:
        rejected_alter_ids = [item["alter_id"] for item in rejected_items if item.get("alter_id") is not None]
        if rejected_alter_ids:
            target = min(target, min(rejected_alter_ids) - 1)

    return max(target, current_alter_id)


class SyncEngine:
    """
    Coordinates the entire read-only synchronization pipeline between TallyPrime and FieldTrack Cloud.
    Guarantees:
    - No full table scans
    - Strict tenant isolation
    - Checkpoints advance only on backend confirmation
    - Durable local retry queue on network failure
    - Idempotent payload delivery
    """

    def __init__(
        self,
        tally_client: Optional[TallyClient] = None,
        backend_client: Optional[BackendClient] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        retry_queue: Optional[RetryQueue] = None,
        quarantine_store: Optional[QuarantineStore] = None,
    ):
        self.tally = tally_client or TallyClient()
        self.backend = backend_client or BackendClient()
        self.checkpoints = checkpoint_manager or CheckpointManager()
        self.retry_queue = retry_queue or RetryQueue()
        self.quarantine = quarantine_store or QuarantineStore()

        self.cust_extractor = CustomerExtractor(self.tally)
        self.inv_extractor = InvoiceExtractor(self.tally)
        self.pmt_extractor = PaymentExtractor(self.tally)

    def process_retry_queue(self) -> None:
        """Attempts to flush any pending batches from previous network drops."""
        ready_items = self.retry_queue.get_pending_ready()
        if not ready_items:
            return

        logger.info(f"Processing {len(ready_items)} pending batches from local retry queue...")
        for item in ready_items:
            q_id = item["id"]
            b_type = item["batch_type"]
            b_id = item["batch_id"]
            guid = item["company_guid"]
            records = item["records"]

            try:
                if b_type == "customers":
                    self.backend.sync_customers(b_id, guid, records)
                elif b_type == "invoices":
                    self.backend.sync_invoices(b_id, guid, records)
                elif b_type == "payments":
                    self.backend.sync_payments(b_id, guid, records)

                self.retry_queue.mark_success(q_id)
            except (BackendServerError, Exception) as ex:
                self.retry_queue.mark_failure(q_id, str(ex))
                # Stop processing further retries if backend is currently down
                break

    def _chunk_list(self, items: List[Any], chunk_size: int) -> List[List[Any]]:
        return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    def process_writeback_jobs(self, company_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Polls pending writeback jobs from FieldTrack backend (BE -> Tally),
        generates and submits Receipt vouchers to TallyPrime, and acknowledges
        success back to the backend.
        """
        stats = {"polled": 0, "succeeded": 0, "failed": 0}
        try:
            jobs = self.backend.get_pending_writeback_jobs(limit=10)
        except Exception as ex:
            logger.warning(f"Could not poll pending writeback jobs from backend: {ex}")
            return stats

        if not jobs:
            return stats

        stats["polled"] = len(jobs)
        logger.info(f"Processing {len(jobs)} pending Tally writeback jobs...")

        for job in jobs:
            job_id = str(job["id"])
            payload = job.get("payload", {})
            entity_type = (job.get("entity_type") or "PAYMENT").upper()

            try:
                # 1. Post Voucher XML to Tally based on entity type
                if entity_type == "SALES_ORDER":
                    res = self.tally.import_sales_order(payload, company_name=company_name)
                    item_desc = f"Sales Order {payload.get('order_number') or payload.get('order_id')}"
                else:
                    res = self.tally.import_receipt(payload, company_name=company_name)
                    payment_id = payload.get("payment_id")
                    item_desc = f"Payment {payment_id}"

                if res.success:
                    # 2. Acknowledge backend with Tally identifiers.
                    # The voucher is already in Tally at this point - if the ACK call itself
                    # fails (cold start, timeout, network blip), that must NOT fall through to
                    # the generic except below and get reported as a Tally failure (which would
                    # mark the job retryable and risk a duplicate post next cycle). Instead, leave
                    # it PROCESSING: once its lease expires it will be reclaimed, and the pre-post
                    # dedupe check in import_receipt/import_sales_order will find this voucher and
                    # self-heal by acking it rather than posting again.
                    try:
                        self.backend.ack_writeback_job(
                            job_id=job_id,
                            tally_guid=res.guid,
                            tally_master_id=res.master_id,
                            tally_voucher_number=res.voucher_number,
                        )
                        stats["succeeded"] += 1
                        logger.info(
                            f"Writeback job {job_id} for {item_desc} CONFIRMED in Tally (GUID={res.guid}, VchNum={res.voucher_number})."
                        )
                    except Exception as ack_ex:
                        logger.error(
                            f"Writeback job {job_id} for {item_desc} was posted to Tally (GUID={res.guid}) "
                            f"but the backend ACK failed: {ack_ex}. Leaving job PROCESSING - it will self-heal "
                            f"via the pre-post dedupe check once reclaimed, not get reported as a Tally failure."
                        )
                        stats["failed"] += 1
                else:
                    # 3. Report failure back to backend
                    self.backend.fail_writeback_job(
                        job_id=job_id,
                        error_message=res.error_message or "Tally rejected voucher",
                        is_retryable=res.is_retryable,
                    )
                    stats["failed"] += 1
                    logger.warning(
                        f"Writeback job {job_id} ({item_desc}) failed: {res.error_message} (retryable={res.is_retryable})"
                    )

            except TallyConnectionError as tce:
                logger.error(f"Tally connection error processing writeback job {job_id}: {tce}")
                try:
                    self.backend.fail_writeback_job(
                        job_id=job_id,
                        error_message=f"Tally connection failed: {tce}",
                        is_retryable=True,
                    )
                except Exception:
                    pass
                stats["failed"] += 1
                break
            except Exception as ex:
                logger.error(f"Unexpected error processing writeback job {job_id}: {ex}")
                try:
                    self.backend.fail_writeback_job(
                        job_id=job_id,
                        error_message=f"Processing error: {ex}",
                        is_retryable=True,
                    )
                except Exception:
                    pass
                stats["failed"] += 1

        return stats

    def run_sync(self, is_initial: bool = False) -> Dict[str, Any]:
        """
        Executes a single end-to-end sync cycle.
        """
        start_time = time.time()
        results = {
            "writeback": {"polled": 0, "succeeded": 0, "failed": 0},
            "customers": {"extracted": 0, "uploaded": 0, "failed": 0},
            "invoices": {"extracted": 0, "uploaded": 0, "failed": 0},
            "payments": {"extracted": 0, "uploaded": 0, "failed": 0},
            "duration_seconds": 0.0,
            "status": "COMPLETED",
        }

        # 1. Process local durable retry queue first
        try:
            self.process_retry_queue()
        except Exception as ex:
            logger.warning(f"Error processing retry queue: {ex}")

        # 2. Verify Tally Connection & get active company
        try:
            company_info = self.tally.get_company_info()
            if not company_info or not company_info.get("name"):
                logger.warning("No active company found loaded in TallyPrime. Skipping sync cycle.")
                results["status"] = "NO_COMPANY_LOADED"
                return results

            company_name = company_info["name"]
            company_guid = company_info.get("guid")
            logger.info(f"Connected to Tally: Company='{company_name}' GUID='{company_guid}'")
        except TallyConnectionError as tce:
            logger.warning(f"TallyPrime is not reachable: {tce}")
            results["status"] = "TALLY_UNAVAILABLE"
            return results

        # Send heartbeat to backend
        try:
            self.backend.heartbeat(
                agent_version=AGENT_VERSION,
                tally_status="ONLINE",
                company_name=company_name,
                company_guid=company_guid,
                checkpoints=self.checkpoints.get_all_checkpoints(),
            )
        except Exception as ex:
            logger.warning(f"Heartbeat to backend failed: {ex}")

        # 3. Process BE -> Tally Write-Back Outbox (only when explicitly enabled: this WRITES into the client's Tally)
        if not settings.writeback_enabled:
            logger.info("Write-back to Tally is DISABLED (TALLY_WRITEBACK_ENABLED not set): read-only mode, nothing is posted into Tally.")
            results["writeback"] = {"polled": 0, "succeeded": 0, "failed": 0, "disabled": True}
        else:
            try:
                wb_stats = self.process_writeback_jobs(company_name=company_name)
                results["writeback"] = wb_stats
            except Exception as ex:
                logger.error(f"Error processing writeback jobs: {ex}")
                results["writeback"] = {"polled": 0, "succeeded": 0, "failed": 0, "error": str(ex)}

        # 4. Synchronize Customers / Outlets

        try:
            cust_cp = self.checkpoints.get_checkpoint("customers")
            min_alter_id = 0 if is_initial else (cust_cp.get("last_alter_id") or 0)
            raw_customers = self.cust_extractor.extract_customers(min_alter_id=min_alter_id)
            results["customers"]["extracted"] = len(raw_customers)

            normalized_custs = [Normalizer.normalize_customer(c) for c in raw_customers]
            valid_custs, rejected_custs = DataValidator.filter_valid("customers", normalized_custs)
            results["customers"]["failed"] += len(rejected_custs)
            for item in rejected_custs:
                self.quarantine.add(
                    "customers",
                    item.get("source_reference") or f"UNKNOWN_customers_{item.get('alter_id')}",
                    item.get("alter_id"),
                    item.get("validation_error") or "unknown",
                    item,
                )

            # Consider ALL still-unresolved quarantine entries for this entity, not just
            # this cycle's rejections - a record quarantined in a PREVIOUS cycle that
            # simply isn't returned by Tally this cycle (for any reason) must still block
            # the checkpoint until it's actually resolved, otherwise it would be silently
            # skipped across cycles rather than within one.
            # Exclude entries this very cycle is about to resolve (same source_reference
            # now valid) - otherwise a record fixed and re-synced in the SAME cycle it's
            # quarantined-from would stay blocked for one extra cycle (safe, but needless
            # lag). Anything not in valid_custs this cycle still fully blocks the advance.
            resolving_refs = {c["source_reference"] for c in valid_custs}
            all_unresolved_custs = [
                u for u in self.quarantine.list_unresolved("customers")
                if u["source_reference"] not in resolving_refs
            ]
            max_alter = _safe_checkpoint_alter_id(valid_custs, all_unresolved_custs, min_alter_id)
            if valid_custs:
                batches = self._chunk_list(valid_custs, settings.batch_size)

                for batch in batches:
                    b_id = str(uuid.uuid4())
                    try:
                        res = self.backend.sync_customers(b_id, company_guid, batch)
                        results["customers"]["uploaded"] += res.get("created_count", 0) + res.get("updated_count", 0)
                        # Checkpoint advances ONLY after successful upload
                        self.checkpoints.update_checkpoint("customers", alter_id=max_alter, records_count=len(batch))
                        for item in batch:
                            self.quarantine.mark_resolved("customers", item["source_reference"])
                    except (BackendServerError, Exception) as ex:
                        logger.error(f"Customer batch upload failed, saving to durable retry queue: {ex}")
                        self.retry_queue.enqueue("customers", b_id, company_guid, batch)
                        results["customers"]["failed"] += len(batch)
        except Exception as ex:
            logger.error(f"Error during customer synchronization: {ex}")

        # 4. Synchronize Invoices
        try:
            inv_cp = self.checkpoints.get_checkpoint("invoices")
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Always from the sync start date: a voucher keyed in today but dated
            # earlier (a backdated receipt / invoice) must still be found. AlterID
            # (filtered inside Tally) is what keeps each cycle incremental.
            from_date = settings.sync_from_date
            to_date = today_str
            min_alter_id = 0 if is_initial else (inv_cp.get("last_alter_id") or 0)

            raw_invoices = self.inv_extractor.extract_invoices(
                from_date=from_date, to_date=to_date, min_alter_id=min_alter_id
            )
            results["invoices"]["extracted"] = len(raw_invoices)

            normalized_invs = [Normalizer.normalize_invoice(inv) for inv in raw_invoices]
            valid_invs, rejected_invs = DataValidator.filter_valid("invoices", normalized_invs)
            results["invoices"]["failed"] += len(rejected_invs)
            for item in rejected_invs:
                self.quarantine.add(
                    "invoices",
                    item.get("source_reference") or f"UNKNOWN_invoices_{item.get('alter_id')}",
                    item.get("alter_id"),
                    item.get("validation_error") or "unknown",
                    item,
                )

            # See the customers block above for why this uses ALL unresolved quarantine
            # entries, not just this cycle's rejections.
            resolving_refs = {i["source_reference"] for i in valid_invs}
            all_unresolved_invs = [
                u for u in self.quarantine.list_unresolved("invoices")
                if u["source_reference"] not in resolving_refs
            ]
            max_alter = _safe_checkpoint_alter_id(valid_invs, all_unresolved_invs, min_alter_id)
            if valid_invs:
                batches = self._chunk_list(valid_invs, settings.batch_size)

                for batch in batches:
                    b_id = str(uuid.uuid4())
                    try:
                        res = self.backend.sync_invoices(b_id, company_guid, batch)
                        results["invoices"]["uploaded"] += res.get("created_count", 0) + res.get("updated_count", 0)
                        self.checkpoints.update_checkpoint(
                            "invoices", last_sync_date=to_date, alter_id=max_alter, records_count=len(batch)
                        )
                        for item in batch:
                            self.quarantine.mark_resolved("invoices", item["source_reference"])
                    except (BackendServerError, Exception) as ex:
                        logger.error(f"Invoice batch upload failed, saving to durable retry queue: {ex}")
                        self.retry_queue.enqueue("invoices", b_id, company_guid, batch)
                        results["invoices"]["failed"] += len(batch)
        except Exception as ex:
            logger.error(f"Error during invoice synchronization: {ex}")

        # 5. Synchronize Payments
        try:
            pmt_cp = self.checkpoints.get_checkpoint("payments")
            today_str = datetime.now().strftime("%Y-%m-%d")

            # See invoices: always from the sync start date, AlterID keeps it incremental.
            from_date = settings.sync_from_date
            to_date = today_str
            min_alter_id = 0 if is_initial else (pmt_cp.get("last_alter_id") or 0)

            raw_payments = self.pmt_extractor.extract_payments(
                from_date=from_date, to_date=to_date, min_alter_id=min_alter_id
            )
            results["payments"]["extracted"] = len(raw_payments)

            normalized_pmts = [Normalizer.normalize_payment(p) for p in raw_payments]
            valid_pmts, rejected_pmts = DataValidator.filter_valid("payments", normalized_pmts)
            results["payments"]["failed"] += len(rejected_pmts)
            for item in rejected_pmts:
                self.quarantine.add(
                    "payments",
                    item.get("source_reference") or f"UNKNOWN_payments_{item.get('alter_id')}",
                    item.get("alter_id"),
                    item.get("validation_error") or "unknown",
                    item,
                )

            # See the customers block above for why this uses ALL unresolved quarantine
            # entries, not just this cycle's rejections.
            resolving_refs = {p["source_reference"] for p in valid_pmts}
            all_unresolved_pmts = [
                u for u in self.quarantine.list_unresolved("payments")
                if u["source_reference"] not in resolving_refs
            ]
            max_alter = _safe_checkpoint_alter_id(valid_pmts, all_unresolved_pmts, min_alter_id)
            if valid_pmts:
                batches = self._chunk_list(valid_pmts, settings.batch_size)

                for batch in batches:
                    b_id = str(uuid.uuid4())
                    try:
                        res = self.backend.sync_payments(b_id, company_guid, batch)
                        results["payments"]["uploaded"] += res.get("created_count", 0) + res.get("updated_count", 0)
                        self.checkpoints.update_checkpoint(
                            "payments", last_sync_date=to_date, alter_id=max_alter, records_count=len(batch)
                        )
                        for item in batch:
                            self.quarantine.mark_resolved("payments", item["source_reference"])
                    except (BackendServerError, Exception) as ex:
                        logger.error(f"Payment batch upload failed, saving to durable retry queue: {ex}")
                        self.retry_queue.enqueue("payments", b_id, company_guid, batch)
                        results["payments"]["failed"] += len(batch)
        except Exception as ex:
            logger.error(f"Error during payment synchronization: {ex}")

        results["duration_seconds"] = round(time.time() - start_time, 2)
        logger.info(
            f"SYNC_CYCLE_FINISHED status={results['status']} "
            f"customers=(ext={results['customers']['extracted']}, up={results['customers']['uploaded']}) "
            f"invoices=(ext={results['invoices']['extracted']}, up={results['invoices']['uploaded']}) "
            f"payments=(ext={results['payments']['extracted']}, up={results['payments']['uploaded']}) "
            f"duration={results['duration_seconds']}s"
        )
        return results
