import re

def normalize_indian_phone(value: object) -> str:
    if value is None:
        raise ValueError("Phone number is missing")
    raw = str(value).strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = re.sub(r"\\D", "", raw)
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError(f"Invalid Indian mobile number: {raw}")
    return f"+91{digits}"

def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}
