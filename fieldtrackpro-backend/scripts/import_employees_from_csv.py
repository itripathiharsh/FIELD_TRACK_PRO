"""
Import employees strictly from the provided CSV export.
Ensures ONLY the employees in the CSV exist in the database (preserving superadmin).
"""
import csv
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, delete, func
from app.database import AsyncSessionLocal
from app.models.user import User, Role
from app.models.employee import Employee
from app.models.fos_mapping import FOSEmployeeMapping
from app.core.security import hash_password

FOS_ALIASES = {
    "11001": ["sahil", "Sahil"],
    "11002": ["raunak", "Raunak", "RAUNAK"],
    "11003": ["yogesh", "Yogesh", "YOGESH"],
    "11004": ["amit", "Amit", "AMIT", "amit jaiswal", "Amit Jaiswal"],
    "11005": ["sandeep", "Sandeep"],
    "11006": ["jagat", "Jagat"],
    "11007": ["jitendra", "Jitendra"],
    "11008": ["parvej", "Parvej"],
    "11021": ["manish", "Manish"],
    "11023": ["dharmendra", "Dharmendra"],
    "11025": ["mohit", "Mohit"],
}

async def import_employees(csv_path: str):
    print(f"Reading employee data from: {csv_path}")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Found {len(rows)} employee records in CSV.")

    valid_emp_ids = set()
    valid_emp_codes = set()
    valid_user_ids = set()

    for r in rows:
        valid_emp_ids.add(uuid.UUID(r["id"].strip()))
        valid_emp_codes.add(r["employee_code"].strip())
        valid_user_ids.add(uuid.UUID(r["user_id"].strip()))

    admin_hash = hash_password("AdminPass123!")
    emp_hash = hash_password("Password@123!")

    async with AsyncSessionLocal() as session:
        # Step 1: Remove any employees NOT in the CSV (to satisfy "only these should be the employees")
        existing_employees = (await session.execute(select(Employee))).scalars().all()
        removed_emp_count = 0
        for emp in existing_employees:
            if emp.id not in valid_emp_ids and emp.employee_code not in valid_emp_codes:
                print(f"Removing extraneous employee: {emp.employee_code} - {emp.full_name} ({emp.id})")
                await session.delete(emp)
                removed_emp_count += 1
        if removed_emp_count > 0:
            await session.flush()
            print(f"Removed {removed_emp_count} non-conforming employees.")

        # Step 2: Remove any non-admin users that are not in the valid CSV user_ids
        existing_users = (await session.execute(select(User))).scalars().all()
        removed_user_count = 0
        for usr in existing_users:
            if usr.email == "admin@fieldtrack.test":
                continue # Always keep superadmin
            if usr.id not in valid_user_ids and usr.role == Role.EMPLOYEE:
                print(f"Removing extraneous user: {usr.email} ({usr.id})")
                await session.delete(usr)
                removed_user_count += 1
        if removed_user_count > 0:
            await session.flush()
            print(f"Removed {removed_user_count} non-conforming users.")

        # Step 3: Insert / Upsert Users & Employees from CSV
        imported_count = 0
        for r in rows:
            emp_id = uuid.UUID(r["id"].strip())
            user_id = uuid.UUID(r["user_id"].strip())
            full_name = r["full_name"].strip()
            employee_code = r["employee_code"].strip()
            working_profile = r["working_profile"].strip() if r.get("working_profile") else None
            cug = r["cug"].strip() if r.get("cug") else None
            address = r["address"].strip() if r.get("address") else "Kanpur, Uttar Pradesh"
            must_change_pwd = r.get("must_change_password", "").strip().upper() == "TRUE"
            
            user_email = r["user_email"].strip() if r.get("user_email") else None
            user_mobile = r["user_mobile"].strip() if r.get("user_mobile") else None
            user_role_str = r.get("user_role", "EMPLOYEE").strip().upper()
            role = Role.ADMIN if user_role_str == "ADMIN" else Role.EMPLOYEE
            pwd_hash = admin_hash if role == Role.ADMIN else emp_hash

            # A. Upsert User
            # Search by ID, email, or mobile
            usr_stmt = select(User).where(
                (User.id == user_id) | 
                (User.email == user_email) | 
                (User.mobile_number == user_mobile)
            )
            user = (await session.execute(usr_stmt)).scalar_one_or_none()
            if not user:
                user = User(
                    id=user_id,
                    email=user_email,
                    mobile_number=user_mobile,
                    role=role,
                    is_active=True,
                    password_hash=pwd_hash,
                )
                session.add(user)
                await session.flush()
            else:
                user.id = user_id
                user.email = user_email
                user.mobile_number = user_mobile
                user.role = role
                user.is_active = True
                user.password_hash = pwd_hash
                await session.flush()

            # B. Upsert Employee
            emp_stmt = select(Employee).where(
                (Employee.id == emp_id) | 
                (Employee.employee_code == employee_code) | 
                (Employee.user_id == user_id)
            )
            emp = (await session.execute(emp_stmt)).scalar_one_or_none()
            if not emp:
                emp = Employee(
                    id=emp_id,
                    user_id=user_id,
                    full_name=full_name,
                    employee_code=employee_code,
                    working_profile=working_profile,
                    cug=cug,
                    address=address,
                    must_change_password=must_change_pwd,
                )
                session.add(emp)
                await session.flush()
            else:
                emp.id = emp_id
                emp.user_id = user_id
                emp.full_name = full_name
                emp.employee_code = employee_code
                emp.working_profile = working_profile
                emp.cug = cug
                emp.address = address
                emp.must_change_password = must_change_pwd
                await session.flush()

            # C. FOS Aliases if applicable
            if employee_code in FOS_ALIASES:
                for alias in FOS_ALIASES[employee_code]:
                    fos_stmt = select(FOSEmployeeMapping).where(
                        func.lower(FOSEmployeeMapping.raw_fos_name) == alias.lower()
                    )
                    mapping = (await session.execute(fos_stmt)).scalar_one_or_none()
                    if not mapping:
                        session.add(FOSEmployeeMapping(raw_fos_name=alias, employee_id=emp_id))
                    else:
                        mapping.employee_id = emp_id

            imported_count += 1
            print(f"[{imported_count}/{len(rows)}] Imported: {employee_code} - {full_name} ({working_profile}, {role.value})")

        await session.commit()
        print("\nAll records successfully committed to database!")

        # Final Verification
        final_emp_count = (await session.execute(select(func.count(Employee.id)))).scalar_one()
        final_usr_count = (await session.execute(select(func.count(User.id)))).scalar_one()
        print("--------------------------------------------------")
        print(f"Verification Summary:")
        print(f"Total Employees in DB: {final_emp_count} (Expected: {len(rows)})")
        print(f"Total Users in DB:     {final_usr_count} (Expected: {len(rows) + 1} including superadmin)")
        print("--------------------------------------------------")

if __name__ == "__main__":
    import asyncio

    # Try original download path, otherwise fall back to workspace scratch copy
    target_csv = r"C:\Users\Admin\Downloads\employees_export - employees_export.csv.csv"
    if not os.path.exists(target_csv):
        target_csv = r"f:\Field track pro v2 for test\scratch\employees_export.csv"

    asyncio.run(import_employees(target_csv))
