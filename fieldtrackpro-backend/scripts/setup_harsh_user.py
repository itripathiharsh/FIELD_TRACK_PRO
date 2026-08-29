import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User, Role
from app.models.employee import Employee
from app.core.security import hash_password

async def setup_user():
    email = "imharshofficial322@gmail.com"
    password = "Imharsh@1"
    password_hash = hash_password(password)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if user:
            print(f"Existing user found: {user.email} (id: {user.id}, role: {user.role})")
            user.password_hash = password_hash
            user.is_active = True
            await session.commit()
            print(f"Password updated successfully for {email}")
        else:
            print(f"Creating new ADMIN user for {email}...")
            new_user = User(
                email=email,
                mobile_number="9999999999",
                password_hash=password_hash,
                role=Role.ADMIN,
                is_active=True
            )
            session.add(new_user)
            await session.flush()
            
            new_employee = Employee(
                user_id=new_user.id,
                full_name="Harsh Tripathi",
                employee_code="ADM001",
                working_profile="Admin / Lead",
                cug="9999999999"
            )
            session.add(new_employee)
            await session.commit()
            print(f"User {email} created successfully as ADMIN with full Employee profile!")

if __name__ == "__main__":
    asyncio.run(setup_user())
