import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger


class BackendAuthError(Exception):
    """Raised when authentication with FieldTrack Pro backend fails (401/403)."""
    pass


class BackendServerError(Exception):
    """Raised when the backend returns an error status or is unreachable.

    `status` is the HTTP status (None = connection failure / no response). 4xx other than 401/403
    means the backend rejected the request itself (permanent until fixed); None or 5xx is transient."""

    def __init__(self, message: str = "", status: Optional[int] = None):
        super().__init__(message)
        self.status = status

    @property
    def is_rejection(self) -> bool:
        return self.status is not None and 400 <= self.status < 500


class BackendClient:
    """
    Client for communicating with the FieldTrack Pro cloud backend API.
    All communication is OUTBOUND over HTTPS/HTTP.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.backend_url).rstrip("/")
        self.agent_id = agent_id or settings.agent_id
        self.agent_key = agent_key or settings.agent_key
        self.timeout = timeout or settings.backend_timeout_seconds

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.agent_id and self.agent_key:
            headers["X-Agent-Id"] = self.agent_id
            headers["X-Agent-Key"] = self.agent_key
        return headers

    def _request(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, method: str = "POST"
    ) -> Any:
        """
        Executes an HTTP request to the backend with standard validation and error handling.
        """
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url,
            data=body,
            headers=self._headers(),
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_text = resp.read().decode("utf-8")
                return json.loads(resp_text)
        except urllib.error.HTTPError as he:
            status = he.code
            err_body = ""
            try:
                err_body = he.read().decode("utf-8")
            except Exception:
                pass

            if status in (401, 403):
                logger.error(f"Backend authentication failed (status={status}): {err_body}")
                raise BackendAuthError(f"Agent authentication rejected: {err_body}")
            else:
                logger.warning(f"Backend API error (status={status}): {err_body}")
                raise BackendServerError(f"Backend error {status}: {err_body}", status=status)
        except urllib.error.URLError as ue:
            logger.warning(f"Backend unreachable at {url}: {ue}")
            raise BackendServerError(f"Could not connect to FieldTrack Backend: {ue}") from ue
        except Exception as ex:
            logger.error(f"Unexpected backend client error: {ex}")
            raise BackendServerError(f"Backend request failed: {ex}") from ex

    def heartbeat(
        self,
        agent_version: str,
        tally_status: str,
        company_name: Optional[str] = None,
        company_guid: Optional[str] = None,
        checkpoints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends a liveness heartbeat to the backend."""
        payload = {
            "agent_version": agent_version,
            "tally_status": tally_status,
            "company_name": company_name,
            "company_guid": company_guid,
            "checkpoints": checkpoints or {},
        }
        return self._request("/api/v1/integrations/tally/heartbeat", payload)

    def sync_customers(
        self, batch_id: str, company_guid: Optional[str], customers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Uploads a batch of customer/outlet records."""
        payload = {
            "batch_id": batch_id,
            "company_guid": company_guid,
            "customers": customers,
        }
        return self._request("/api/v1/integrations/tally/sync/customers", payload)

    def sync_invoices(
        self, batch_id: str, company_guid: Optional[str], invoices: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Uploads a batch of sales invoice records."""
        payload = {
            "batch_id": batch_id,
            "company_guid": company_guid,
            "invoices": invoices,
        }
        return self._request("/api/v1/integrations/tally/sync/invoices", payload)

    def sync_payments(
        self, batch_id: str, company_guid: Optional[str], payments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Uploads a batch of receipt/payment records."""
        payload = {
            "batch_id": batch_id,
            "company_guid": company_guid,
            "payments": payments,
        }
        return self._request("/api/v1/integrations/tally/sync/payments", payload)

    # ---------------------------------------------------------------- agent 2.0

    def sync_ledgers(self, batch_id: str, company_guid: Optional[str], ledgers: List[Dict[str, Any]],
                     snapshot_id: Optional[str] = None, is_final_chunk: bool = False,
                     as_of: Optional[str] = None, period_start: Optional[str] = None) -> Dict[str, Any]:
        return self._request("/api/v1/integrations/tally/sync/ledgers", {
            "batch_id": batch_id, "company_guid": company_guid, "snapshot_id": snapshot_id,
            "is_final_chunk": is_final_chunk, "as_of": as_of, "period_start": period_start, "ledgers": ledgers,
        })

    def sync_vouchers(self, batch_id: str, company_guid: Optional[str], vouchers: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._request("/api/v1/integrations/tally/sync/vouchers",
                             {"batch_id": batch_id, "company_guid": company_guid, "vouchers": vouchers})

    def sync_bills(self, batch_id: str, company_guid: Optional[str], bills: List[Dict[str, Any]],
                   snapshot_id: str, as_of_date: str, is_final_chunk: bool) -> Dict[str, Any]:
        return self._request("/api/v1/integrations/tally/sync/bills", {
            "batch_id": batch_id, "company_guid": company_guid, "snapshot_id": snapshot_id,
            "as_of_date": as_of_date, "is_final_chunk": is_final_chunk, "bills": bills,
        })

    def get_capabilities(self) -> Dict[str, Any]:
        """2.2.0: what the backend guarantees. `history_safe` = historical FY rows cannot create pending-close
        periods, move live openings or distort dashboards (B1/B4). An older backend answers 404."""
        return self._request("/api/v1/integrations/tally/capabilities", data=None, method="GET")

    def sync_manifest(self, batch_id: str, company_guid: Optional[str], guids: List[str], snapshot_id: str,
                      window_from: str, window_to: str, is_final_chunk: bool) -> Dict[str, Any]:
        return self._request("/api/v1/integrations/tally/sync/manifest", {
            "batch_id": batch_id, "company_guid": company_guid, "snapshot_id": snapshot_id,
            "window_from": window_from, "window_to": window_to, "is_final_chunk": is_final_chunk, "guids": guids,
        })


    def get_pending_writeback_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Claims pending writeback jobs from FieldTrack backend."""
        return self._request(
            f"/api/v1/integrations/tally/outbox/pending?limit={limit}",
            data=None,
            method="GET",
        )

    def ack_writeback_job(
        self,
        job_id: str,
        tally_guid: Optional[str] = None,
        tally_master_id: Optional[str] = None,
        tally_voucher_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Acknowledges successful creation of receipt voucher in Tally."""
        payload = {
            "tally_guid": tally_guid,
            "tally_master_id": tally_master_id,
            "tally_voucher_number": tally_voucher_number,
        }
        return self._request(f"/api/v1/integrations/tally/outbox/{job_id}/ack", payload)

    def fail_writeback_job(
        self, job_id: str, error_message: str, is_retryable: bool = True
    ) -> Dict[str, Any]:
        """Reports failure for writeback job."""
        payload = {
            "error_message": error_message,
            "is_retryable": is_retryable,
        }
        return self._request(f"/api/v1/integrations/tally/outbox/{job_id}/fail", payload)


class DryRunBackend(BackendClient):
    """Records every payload to JSON files instead of uploading (client-side dry run).
    Answers like a backend that accepted everything, so the engine runs end to end."""

    def __init__(self, out_dir):
        super().__init__(base_url="http://dry-run.invalid", agent_id="dry-run", agent_key="dry-run")
        from pathlib import Path
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.counter = 0

    def _request(self, endpoint: str, data: Optional[Dict[str, Any]] = None, method: str = "POST") -> Any:
        if method == "GET":
            return {} if endpoint.endswith("/capabilities") else []
        self.counter += 1
        name = endpoint.rstrip("/").split("/")[-1]
        (self.out / f"{self.counter:06d}_{name}.json").write_text(json.dumps(data, default=str), encoding="utf-8")
        n = 0
        for key in ("vouchers", "ledgers", "bills", "guids", "customers", "invoices", "payments"):
            if isinstance((data or {}).get(key), list):
                n = len(data[key])
        return {"status": "DRY_RUN", "batch_id": (data or {}).get("batch_id", ""), "total_received": n,
                "created_count": 0, "updated_count": 0, "retired_count": 0, "failed_count": 0,
                "errors": [], "details": {}}

    def get_pending_writeback_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        return []
