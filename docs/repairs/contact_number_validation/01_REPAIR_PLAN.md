# Contact Number Validation Repair — Plan

**Date:** 2026-08-19
**Defect:** Contact number field accepts arbitrary values (ABCDEREZ@, hello, etc.)

---

## 1. Root Cause

**Backend:** `app/schemas/customer.py` only enforced `min_length=1, max_length=20` on `contact_number`. No pattern/format validation.

**Frontend:** `CustomersPage.tsx` used `type="tel"` with `maxLength={20}` — no real validation.

**Result:** Any string 1-20 characters was accepted and persisted.

---

## 2. Validation Rule Chosen

**Pattern:** `^[\d+\-\s\(\)]{1,20}$`

**Why:**
- Accepts digits, `+`, `-`, spaces, parentheses — covers all legitimate international phone formats
- Rejects letters, symbols (`@`, `#`, `$`, etc.), and arbitrary text
- Does NOT enforce country-specific formats (intentionally per requirements)
- 1-20 character limit preserved (matches database `varchar(20)`)

**Accepted examples:**
- `+919876543210` (international)
- `+1 555-123-4567` (formatted)
- `1234567890` (plain digits)
- `(555) 123-4567` (parentheses)

**Rejected examples:**
- `ABCDEREZ@` (letters + symbols)
- `hello` (text)
- `123abc` (mixed)
- `!@#$%^&*` (symbols only)
- `abcdefghijklmnopqrst` (letters)

---

## 3. Files Changed

| File | Change |
|------|--------|
| `app/validation/__init__.py` | New — shared phone validation constants |
| `app/schemas/customer.py` | Added pattern validation to `contact_number` |
| `app/schemas/user.py` | Added pattern validation to `mobile_number` |
| `src/utils/phoneValidation.ts` | New — frontend phone validation utility |
| `src/pages/CustomersPage.tsx` | Added frontend validation + import |
| `src/pages/EmployeesPage.tsx` | Added frontend validation + import |
| `tests/test_validation.py` | Added 17 regression tests |

---

## 4. Scope

- **Fixed:** `customer.contact_number`, `user.mobile_number`
- **Not changed:** Any other fields, UI design, colors, unrelated validation
