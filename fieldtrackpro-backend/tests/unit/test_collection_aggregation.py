import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import uuid

from app.models.user import Role, User
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import get_dashboard_summary


@pytest.mark.asyncio
async def test_dashboard_collection_aggregation_prevents_double_count():
    """
    Regression test for PART 1:
    Verifies that get_dashboard_summary never double-counts verified collections
    by adding bi_data.total_collection to live_verified_col.
    """
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        role=Role.ADMIN,
        is_active=True,
    )
    
    # Mock session
    mock_session = AsyncMock()
    
    # Mock ReportService get_business_bi_dashboard
    from app.schemas.financial_snapshot import BusinessBIDashboard
    mock_bi = BusinessBIDashboard(
        snapshot_date="2026-09-05",
        month_period="2026-09",
        is_finalized=False,
        total_outlets=1691,
        total_sales=Decimal("364782522.02"),
        total_collection=Decimal("432072762.88"),
        total_market_outstanding=Decimal("64765228.00"),
        total_overdue_gt_90=Decimal("8628728.00"),
        brand_summaries=[],
        zone_summaries=[],
        area_summaries=[],
        fos_summaries=[],
        raw_outlet_rows=[],
    )
    
    # Mock session executes
    # 1. emp_stmt count -> 30
    # 2. visit_q row -> (6, 1, 0, 2, 0, 3)
    # 3. exc_q row -> (1, 0)
    # 4. col_q row -> total_count=4762, verified_sum=Decimal("432072762.88")
    # 5. cust_q count -> 1691
    # 6. order_q count -> 0
    # 7. field_exceptions -> ([], 0)
    
    class MockResult:
        def __init__(self, value):
            self._value = value
        def scalar(self):
            return self._value
        def scalar_one(self):
            return self._value
        def scalar_one_or_none(self):
            return self._value
        def one(self):
            return self._value
        def all(self):
            return self._value
            
    v_mock = MagicMock()
    v_mock.total = 6
    v_mock.completed = 1
    v_mock.pending = 0
    v_mock.in_progress = 2
    v_mock.flagged = 0
    v_mock.gps_verified = 3
    
    e_mock = MagicMock()
    e_mock.total = 1
    e_mock.pending = 0
    
    c_mock = MagicMock()
    c_mock.total_count = 4762
    c_mock.verified_sum = Decimal("432072762.88")
    
    mock_session.execute.side_effect = [
        MockResult(30),       # emp_stmt
        MockResult(v_mock),   # visit_q
        MockResult(e_mock),   # exc_q
        MockResult(c_mock),   # col_q
        MockResult(1691),     # cust_q
        MockResult(0),        # order_q
    ]
    
    from unittest.mock import patch
    with patch("app.services.report_service.ReportService.get_business_bi_dashboard", return_value=mock_bi), \
         patch("app.services.field_exception_service.list_field_exceptions", return_value=([], 0)):
        
        res: DashboardSummaryResponse = await get_dashboard_summary(
            current_user=admin_user,
            session=mock_session,
        )
        
        # Authoritative assertions:
        # 1. Total collection must equal verified sum, NOT doubled (₹43.20 Cr, NOT ₹86.41 Cr)
        assert res.kpis.total_collection == Decimal("432072762.88")
        assert res.kpis.total_collection != Decimal("864145525.76")
        
        # 2. Outlets and employees
        assert res.kpis.total_outlets == 1691
        assert res.kpis.total_employees == 30
        assert res.kpis.total_sales == Decimal("364782522.02")
        assert res.kpis.total_market_outstanding == Decimal("64765228.00")
