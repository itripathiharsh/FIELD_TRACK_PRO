import asyncio
import asyncpg
from decimal import Decimal

async def populate_settlements():
    conn = await asyncpg.connect("postgresql://fieldtrack_app:XcWG3aLw7s8mL75vrvl97aDZTSXbr4y6@127.0.0.1:5432/fieldtrackpro_dev")
    
    # Fetch all customers who have both invoices and verified payments
    cust_rows = await conn.fetch("""
        SELECT DISTINCT customer_id FROM invoices 
        INTERSECT 
        SELECT DISTINCT customer_id FROM payments WHERE status = 'VERIFIED'
    """)
    print(f"Found {len(cust_rows)} customers with both invoices and verified payments.")
    
    total_allocated = Decimal("0.00")
    total_allocations_created = 0
    total_payments_linked = 0
    
    async with conn.transaction():
        # Clear existing allocations if any
        await conn.execute("DELETE FROM payment_invoice_allocations")
        
        for crow in cust_rows:
            cid = crow["customer_id"]
            
            invoices = await conn.fetch("""
                SELECT id, invoice_number, invoice_date, amount 
                FROM invoices 
                WHERE customer_id = $1 
                ORDER BY invoice_date ASC, created_at ASC
            """, cid)
            
            payments = await conn.fetch("""
                SELECT id, amount, payment_date, source_reference 
                FROM payments 
                WHERE customer_id = $1 AND status = 'VERIFIED' 
                ORDER BY payment_date ASC, created_at ASC
            """, cid)
            
            inv_balances = {inv["id"]: inv["amount"] for inv in invoices}
            inv_nums = {inv["id"]: inv["invoice_number"] for inv in invoices}
            
            for p in payments:
                p_id = p["id"]
                p_amt = p["amount"]
                p_rem = p_amt
                p_alloc_invoices = []
                
                for inv in invoices:
                    inv_id = inv["id"]
                    curr_bal = inv_balances[inv_id]
                    if curr_bal <= Decimal("0.00"):
                        continue
                    if p_rem <= Decimal("0.00"):
                        break
                        
                    settle_amt = min(p_rem, curr_bal)
                    inv_balances[inv_id] -= settle_amt
                    p_rem -= settle_amt
                    total_allocated += settle_amt
                    p_alloc_invoices.append(inv_id)
                    
                    await conn.execute("""
                        INSERT INTO payment_invoice_allocations 
                            (id, payment_id, invoice_id, bill_name, bill_type, allocated_amount, created_at, updated_at)
                        VALUES 
                            (gen_random_uuid(), $1, $2, $3, 'FIFO_ON_ACCOUNT', $4, now(), now())
                        ON CONFLICT (payment_id, invoice_id) 
                        DO UPDATE SET allocated_amount = EXCLUDED.allocated_amount
                    """, p_id, inv_id, inv_nums[inv_id], settle_amt)
                    total_allocations_created += 1
                
                # If payment allocated to exactly 1 invoice, set payment.invoice_id
                if len(p_alloc_invoices) == 1:
                    await conn.execute("""
                        UPDATE payments SET invoice_id = $1 WHERE id = $2
                    """, p_alloc_invoices[0], p_id)
                    total_payments_linked += 1
                    
        # Update imported_outstanding_amount on all invoices to reflect true remaining balance
        await conn.execute("""
            UPDATE invoices i
            SET imported_outstanding_amount = GREATEST(
                i.amount - COALESCE((
                    SELECT SUM(allocated_amount) 
                    FROM payment_invoice_allocations 
                    WHERE invoice_id = i.id
                ), 0),
                0
            )
        """)
        
    print(f"Settlement complete:")
    print(f"  Allocations created: {total_allocations_created}")
    print(f"  Total settled amount: {total_allocated:,.2f}")
    print(f"  Payments linked 1-to-1: {total_payments_linked}")
    
    # Verification
    inv_os_sum = await conn.fetchval("SELECT coalesce(sum(imported_outstanding_amount), 0) FROM invoices")
    print(f"  Total Remaining Invoice Outstanding: {inv_os_sum:,.2f}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(populate_settlements())
