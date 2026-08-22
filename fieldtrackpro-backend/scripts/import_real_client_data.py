"""
Real Client Data Importer & Seeder for FieldTrack Pro.
Imports Employee Master, Outlets, FOS Mappings, Zones, Areas, and Financial Snapshots
from real client Excel files in `F:\\sentio wala\\sheet`.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal
from collections import defaultdict

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.models.user import User, Role
from app.models.employee import Employee
from app.models.territory import Territory
from app.models.area import Area
from app.models.customer import Customer
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.fos_mapping import FOSEmployeeMapping
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.services.import_service import generate_onboarding_excel

DEFAULT_TEMP_PASSWORD = "Password@123!"

# Client Real Employee Roster (Telecom: 11001-11020, CE: 11021-11030)
REAL_EMPLOYEES = [
    {"code": "11001", "name": "Sahil Verma", "profile": "FOS", "email": "sahil.verma@sgrgservices.com", "cug": "9839011001", "aliases": ["sahil", "Sahil"]},
    {"code": "11002", "name": "Raunak Sharma", "profile": "FOS", "email": "raunak.sharma@sgrgservices.com", "cug": "9839011002", "aliases": ["raunak", "Raunak", "RAUNAK"]},
    {"code": "11003", "name": "Yogesh Kumar", "profile": "FOS", "email": "yogesh.kumar@sgrgservices.com", "cug": "9839011003", "aliases": ["yogesh", "Yogesh", "YOGESH"]},
    {"code": "11004", "name": "Amit Jaiswal", "profile": "FOS", "email": "amit.jaiswal@sgrgservices.com", "cug": "9839011004", "aliases": ["amit", "Amit", "AMIT", "amit jaiswal", "Amit Jaiswal"]},
    {"code": "11005", "name": "Sandeep Mishra", "profile": "FOS", "email": "sandeep.mishra@sgrgservices.com", "cug": "9839011005", "aliases": ["sandeep", "Sandeep"]},
    {"code": "11006", "name": "Jagat Singh", "profile": "FOS", "email": "jagat.singh@sgrgservices.com", "cug": "9839011006", "aliases": ["jagat", "Jagat"]},
    {"code": "11007", "name": "Jitendra Yadav", "profile": "FOS", "email": "jitendra.yadav@sgrgservices.com", "cug": "9839011007", "aliases": ["jitendra", "Jitendra"]},
    {"code": "11008", "name": "Parvej Alam", "profile": "FOS", "email": "parvej.alam@sgrgservices.com", "cug": "9839011008", "aliases": ["parvej", "Parvej"]},
    {"code": "11009", "name": "Anurag Shukla", "profile": "TSE", "email": "anurag.shukla@sgrgservices.com", "cug": "9839011009", "aliases": []},
    {"code": "11010", "name": "Vikas Gupta", "profile": "Team Leader", "email": "vikas.gupta@sgrgservices.com", "cug": "9839011010", "aliases": []},
    {"code": "11011", "name": "Ramesh Chand", "profile": "Billing", "email": "ramesh.chand@sgrgservices.com", "cug": "9839011011", "aliases": []},
    {"code": "11012", "name": "Pankaj Dixit", "profile": "Accountant CE/Telecom", "email": "pankaj.dixit@sgrgservices.com", "cug": "9839011012", "aliases": []},
    {"code": "11013", "name": "Suresh Tiwari", "profile": "Sn. Accountant", "email": "suresh.tiwari@sgrgservices.com", "cug": "9839011013", "aliases": []},
    {"code": "11014", "name": "Deepak Soni", "profile": "ASM", "email": "deepak.soni@sgrgservices.com", "cug": "9839011014", "aliases": []},
    {"code": "11015", "name": "Neeraj Rajput", "profile": "Sales Manager", "email": "neeraj.rajput@sgrgservices.com", "cug": "9839011015", "aliases": []},
    {"code": "11016", "name": "Pradeep Kumar", "profile": "Manager", "email": "pradeep.kumar@sgrgservices.com", "cug": "9839011016", "aliases": []},
    {"code": "11017", "name": "Santosh Pal", "profile": "Delivery Boy", "email": "santosh.pal@sgrgservices.com", "cug": "9839011017", "aliases": []},
    {"code": "11018", "name": "Mukesh Singh", "profile": "Driver", "email": "mukesh.singh@sgrgservices.com", "cug": "9839011018", "aliases": []},
    {"code": "11019", "name": "Arun Pandey", "profile": "TSE", "email": "arun.pandey@sgrgservices.com", "cug": "9839011019", "aliases": []},
    {"code": "11020", "name": "Sunil Trivedi", "profile": "Director", "email": "sunil.trivedi@sgrgservices.com", "cug": "9839011020", "aliases": []},
    {"code": "11021", "name": "Manish Awasthi", "profile": "FOS", "email": "manish.awasthi@sgrgservices.com", "cug": "9839011021", "aliases": []},
    {"code": "11022", "name": "Alok Srivastava", "profile": "TSE", "email": "alok.srivastava@sgrgservices.com", "cug": "9839011022", "aliases": []},
    {"code": "11023", "name": "Dharmendra Rathore", "profile": "FOS", "email": "dharmendra.rathore@sgrgservices.com", "cug": "9839011023", "aliases": []},
    {"code": "11024", "name": "Kavita Bajpai", "profile": "Accountant", "email": "kavita.bajpai@sgrgservices.com", "cug": "9839011024", "aliases": []},
    {"code": "11025", "name": "Mohit Tandon", "profile": "FOS", "email": "mohit.tandon@sgrgservices.com", "cug": "9839011025", "aliases": []},
    {"code": "11026", "name": "Rajesh Gaur", "profile": "ASM", "email": "rajesh.gaur@sgrgservices.com", "cug": "9839011026", "aliases": []},
    {"code": "11027", "name": "Vinay Chaturvedi", "profile": "Sales Manager", "email": "vinay.chaturvedi@sgrgservices.com", "cug": "9839011027", "aliases": []},
    {"code": "11028", "name": "Gaurav Sahu", "profile": "Delivery Boy", "email": "gaurav.sahu@sgrgservices.com", "cug": "9839011028", "aliases": []},
    {"code": "11029", "name": "Harish Rawat", "profile": "Billing", "email": "harish.rawat@sgrgservices.com", "cug": "9839011029", "aliases": []},
    {"code": "11030", "name": "Rohit Pathak", "profile": "Director", "email": "rohit.pathak@sgrgservices.com", "cug": "9839011030", "aliases": []},
]


def run_import() -> None:
    sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url)

    candidate_paths = [
        Path(__file__).resolve().parent.parent / "data" / "sheet" / "Combined_BI_Excle_By_TGIshan.xlsx",
        Path(__file__).resolve().parent.parent.parent / "sheet" / "Combined_BI_Excle_By_TGIshan.xlsx",
        Path(r"F:\sentio wala\sheet\Combined_BI_Excle_By_TGIshan.xlsx"),
    ]
    excel_path = None
    for p in candidate_paths:
        if p.exists():
            excel_path = str(p)
            break

    if not excel_path:
        print("Error: Real BI Excel file not found in any candidate path")
        return

    print(f"Loading real client workbook: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheet = wb["Raw Data"]
    rows = list(sheet.iter_rows(values_only=True))
    header = rows[0]
    data_rows = rows[1:]
    print(f"Found {len(data_rows)} data rows in 'Raw Data' sheet.")

    with Session(engine) as session:
        # 1. Ensure Admin User
        admin_email = "admin@fieldtrack.test"
        admin_user = session.execute(select(User).where(User.email == admin_email)).scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                email=admin_email,
                password_hash=hash_password("AdminPass123!"),
                role=Role.ADMIN,
                is_active=True,
            )
            session.add(admin_user)
            session.flush()

        # 2. Provision Real Employees & FOS Mappings
        print("Provisioning real client employees (Telecom: 11001-11020, CE: 11021-11030)...")
        emp_map = {} # fos alias -> employee_id
        credentials_list = []

        for emp_info in REAL_EMPLOYEES:
            code = emp_info["code"]
            email = emp_info["email"]
            name = emp_info["name"]
            profile = emp_info["profile"]
            cug = emp_info["cug"]

            # User account
            user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if not user:
                user = User(
                    email=email,
                    mobile_number=cug,
                    password_hash=hash_password(DEFAULT_TEMP_PASSWORD),
                    role=Role.ADMIN if profile in ["Director", "Sales Manager"] else Role.EMPLOYEE,
                    is_active=True,
                )
                session.add(user)
                session.flush()

            # Employee profile
            emp = session.execute(select(Employee).where(Employee.employee_code == code)).scalar_one_or_none()
            if not emp:
                emp = Employee(
                    user_id=user.id,
                    employee_code=code,
                    full_name=name,
                    working_profile=profile,
                    cug=cug,
                    address="Kanpur, Uttar Pradesh",
                    must_change_password=True,
                )
                session.add(emp)
                session.flush()
            else:
                emp.full_name = name
                emp.working_profile = profile
                emp.cug = cug

            # FOS name aliases
            for alias in emp_info.get("aliases", []):
                emp_map[alias.lower()] = emp.id
                fos_map_obj = session.execute(
                    select(FOSEmployeeMapping).where(func.lower(FOSEmployeeMapping.raw_fos_name) == alias.lower())
                ).scalar_one_or_none()
                if not fos_map_obj:
                    session.add(FOSEmployeeMapping(raw_fos_name=alias, employee_id=emp.id))

            credentials_list.append({
                "employee_name": name,
                "employee_id": code,
                "email": email,
                "temporary_password": DEFAULT_TEMP_PASSWORD,
                "application_role": user.role.value if hasattr(user.role, "value") else str(user.role),
                "working_profile": profile,
                "cug": cug,
            })

        session.flush()

        # 3. Cache Territories (Zones) and Areas
        terr_cache = {t.name.lower(): t for t in session.execute(select(Territory)).scalars().all()}
        area_cache = {(a.name.lower(), a.territory_id): a for a in session.execute(select(Area)).scalars().all()}
        cust_cache = {c.outlet_code.lower(): c for c in session.execute(select(Customer)).scalars().all() if c.outlet_code}

        today_date = date.today()

        def _to_dec(v):
            if v is None:
                return Decimal("0.00")
            try:
                return Decimal(str(v).replace(",", ""))
            except Exception:
                return Decimal("0.00")

        # 4. In-Memory Aggregation of Excel Rows per (dms_code, brand)
        # Some physical outlets have multiple rows in the client sheet representing sub-accounts/transactions.
        # Aggregating within the file ensures exact totals before upserting into the database.
        file_agg = {}
        for row in data_rows:
            brand = str(row[0] or "General").strip()
            dms_code = str(row[1] or "").strip()
            outlet_name = str(row[2] or "").strip()
            zone_name = str(row[3] or "General Zone").strip()
            area_name = str(row[4] or "General Area").strip()
            if not area_name or area_name == "-":
                area_name = "General Area"
            fos_name = str(row[5] or "").strip()

            if not dms_code:
                continue

            key = (dms_code.lower(), brand)
            if key not in file_agg:
                file_agg[key] = {
                    "brand": brand,
                    "dms_code": dms_code,
                    "outlet_name": outlet_name,
                    "zone_name": zone_name,
                    "area_name": area_name,
                    "fos_names": set([fos_name]) if fos_name else set(),
                    "sales": Decimal("0.00"),
                    "collection": Decimal("0.00"),
                    "market_outstanding": Decimal("0.00"),
                    "bucket_lt_15": Decimal("0.00"),
                    "bucket_15_30": Decimal("0.00"),
                    "bucket_30_45": Decimal("0.00"),
                    "bucket_45_60": Decimal("0.00"),
                    "bucket_60_75": Decimal("0.00"),
                    "bucket_75_90": Decimal("0.00"),
                    "bucket_gt_90": Decimal("0.00"),
                }
            else:
                if outlet_name and not file_agg[key]["outlet_name"]:
                    file_agg[key]["outlet_name"] = outlet_name
                if fos_name:
                    file_agg[key]["fos_names"].add(fos_name)

            file_agg[key]["sales"] += _to_dec(row[6])
            file_agg[key]["collection"] += _to_dec(row[7])
            file_agg[key]["market_outstanding"] += _to_dec(row[8])
            file_agg[key]["bucket_lt_15"] += _to_dec(row[9])
            file_agg[key]["bucket_15_30"] += _to_dec(row[10])
            file_agg[key]["bucket_30_45"] += _to_dec(row[11])
            file_agg[key]["bucket_45_60"] += _to_dec(row[12])
            file_agg[key]["bucket_60_75"] += _to_dec(row[13])
            file_agg[key]["bucket_75_90"] += _to_dec(row[14])
            file_agg[key]["bucket_gt_90"] += _to_dec(row[15])

        outlets_created = 0
        outlets_updated = 0
        financial_snapshots_count = 0
        assignments_count = 0
        unmatched_fos = set()

        print(f"Upserting {len(file_agg)} aggregated outlet & financial records idempotently...")

        for (dms_key, brand), agg_data in file_agg.items():
            dms_code = agg_data["dms_code"]
            outlet_name = agg_data["outlet_name"]
            zone_name = agg_data["zone_name"]
            area_name = agg_data["area_name"]

            # Territory (Zone)
            z_key = zone_name.lower()
            terr_obj = terr_cache.get(z_key)
            if not terr_obj:
                terr_obj = Territory(name=zone_name, status="ACTIVE")
                session.add(terr_obj)
                session.flush()
                terr_cache[z_key] = terr_obj

            # Area
            a_key = (area_name.lower(), terr_obj.id)
            area_obj = area_cache.get(a_key)
            if not area_obj:
                area_obj = Area(name=area_name, territory_id=terr_obj.id)
                session.add(area_obj)
                session.flush()
                area_cache[a_key] = area_obj

            # Customer (Outlet)
            cust_obj = cust_cache.get(dms_key)
            if not cust_obj:
                cust_obj = Customer(
                    name=outlet_name or dms_code,
                    outlet_code=dms_code,
                    territory_id=terr_obj.id,
                    area_id=area_obj.id,
                    location_status="MISSING",
                    contact_number="",
                    address=f"{area_name}, {zone_name}",
                    created_by=admin_user.id,
                )
                session.add(cust_obj)
                session.flush()
                cust_cache[dms_key] = cust_obj
                outlets_created += 1
            else:
                cust_obj.name = outlet_name or cust_obj.name
                cust_obj.territory_id = terr_obj.id
                cust_obj.area_id = area_obj.id
                outlets_updated += 1

            # FOS Assignments
            for fos_name in agg_data["fos_names"]:
                if fos_name and fos_name not in ["-", "Office", "None"]:
                    emp_id = emp_map.get(fos_name.lower())
                    if emp_id:
                        existing_assign = session.execute(
                            select(EmployeeCustomerAssignment).where(
                                EmployeeCustomerAssignment.employee_id == emp_id,
                                EmployeeCustomerAssignment.customer_id == cust_obj.id,
                            )
                        ).scalar_one_or_none()
                        if not existing_assign:
                            session.add(EmployeeCustomerAssignment(
                                employee_id=emp_id,
                                customer_id=cust_obj.id,
                                created_by=admin_user.id,
                            ))
                            assignments_count += 1
                    else:
                        unmatched_fos.add(fos_name)

            # Idempotent Financial Snapshot Upsert (REPLACE values rather than accumulate)
            snap = session.execute(
                select(OutletFinancialSnapshot).where(
                    OutletFinancialSnapshot.customer_id == cust_obj.id,
                    OutletFinancialSnapshot.brand == brand,
                    OutletFinancialSnapshot.snapshot_date == today_date,
                )
            ).scalar_one_or_none()

            if not snap:
                snap = OutletFinancialSnapshot(
                    customer_id=cust_obj.id,
                    brand=brand,
                    snapshot_date=today_date,
                    sales=agg_data["sales"],
                    collection=agg_data["collection"],
                    market_outstanding=agg_data["market_outstanding"],
                    bucket_lt_15=agg_data["bucket_lt_15"],
                    bucket_15_30=agg_data["bucket_15_30"],
                    bucket_30_45=agg_data["bucket_30_45"],
                    bucket_45_60=agg_data["bucket_45_60"],
                    bucket_60_75=agg_data["bucket_60_75"],
                    bucket_75_90=agg_data["bucket_75_90"],
                    bucket_gt_90=agg_data["bucket_gt_90"],
                )
                session.add(snap)
            else:
                snap.sales = agg_data["sales"]
                snap.collection = agg_data["collection"]
                snap.market_outstanding = agg_data["market_outstanding"]
                snap.bucket_lt_15 = agg_data["bucket_lt_15"]
                snap.bucket_15_30 = agg_data["bucket_15_30"]
                snap.bucket_30_45 = agg_data["bucket_30_45"]
                snap.bucket_45_60 = agg_data["bucket_45_60"]
                snap.bucket_60_75 = agg_data["bucket_60_75"]
                snap.bucket_75_90 = agg_data["bucket_75_90"]
                snap.bucket_gt_90 = agg_data["bucket_gt_90"]

            financial_snapshots_count += 1

        session.commit()

        # Generate Onboarding Credentials Excel
        cred_excel_path = r"F:\sentio wala\sheet\Employee_Onboarding_Credentials.xlsx"
        cred_bytes = generate_onboarding_excel(credentials_list)
        with open(cred_excel_path, "wb") as f:
            f.write(cred_bytes)

        print("\n=======================================================")
        print("REAL DATA IMPORT COMPLETED SUCCESSFULLY!")
        print("=======================================================")
        print(f"Employees Provisioned: {len(REAL_EMPLOYEES)}")
        print(f"Total Outlets In DB: {len(cust_cache)} (Created: {outlets_created}, Updated: {outlets_updated})")
        print(f"Zones Created/Loaded: {len(terr_cache)}")
        print(f"Areas Created/Loaded: {len(area_cache)}")
        print(f"FOS Assignments Established: {assignments_count}")
        print(f"Financial Snapshots Stored: {financial_snapshots_count}")
        print(f"Unmatched FOS (reported for admin): {sorted(list(unmatched_fos))}")
        print(f"Credentials Excel Saved: {cred_excel_path}")
        print("=======================================================\n")


if __name__ == "__main__":
    run_import()
