import re


def normalize_phone(raw):
    """Samakan format nomor: '+62 812-3456', '62812...' dan '0812...' jadi '0812...'."""
    cleaned = re.sub(r"[\s().-]", "", raw or "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned.isdigit():
        raise ValueError("Nomor telepon hanya boleh berisi angka.")
    if cleaned.startswith("62"):
        cleaned = "0" + cleaned[2:]
    elif cleaned.startswith("8"):
        cleaned = "0" + cleaned
    if not cleaned.startswith("0") or not 9 <= len(cleaned) <= 14:
        raise ValueError("Format nomor telepon tidak valid.")
    return cleaned
