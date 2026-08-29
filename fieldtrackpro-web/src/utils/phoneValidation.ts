/**
 * Phone number validation utilities.
 *
 * Mirrors the backend validation rules defined in app/validation/__init__.py.
 * Keep these in sync with the backend PHONE_PATTERN and PHONE_MAX_LENGTH.
 */

export const PHONE_MAX_LENGTH = 20;

// Regex: only digits, +, -, spaces, parentheses. 1 to PHONE_MAX_LENGTH chars.
export const PHONE_PATTERN = /^[\d+\s()-]{1,20}$/;

export interface PhoneValidationOptions {
  required?: boolean;
}

/**
 * Validate a phone number string.
 * Returns an error message string if invalid, or null if valid.
 */
export function validatePhoneNumber(
  value: string | null | undefined,
  options: PhoneValidationOptions = { required: true }
): string | null {
  const isRequired = options.required !== false;
  if (!value || value.trim() === "") {
    if (isRequired) {
      return "Phone number is required";
    }
    return null;
  }

  const trimmed = value.trim();

  if (trimmed.length > PHONE_MAX_LENGTH) {
    return `Phone number must be at most ${PHONE_MAX_LENGTH} characters`;
  }

  if (!PHONE_PATTERN.test(trimmed)) {
    return "Phone number can only contain digits, +, -, spaces, and parentheses";
  }

  return null;
}

/**
 * Check if a phone number is valid (boolean).
 */
export function isValidPhoneNumber(
  value: string | null | undefined,
  options: PhoneValidationOptions = { required: true }
): boolean {
  return validatePhoneNumber(value, options) === null;
}
