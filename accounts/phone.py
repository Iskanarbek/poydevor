import re


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Return a phone number in international form ``+<country code><number>``.

    Any country is accepted. Numbers typed with a leading "+" (or "00") keep
    their country code; a bare 9-digit number is treated as Uzbek, and a bare
    number starting with 998 stays Uzbek. Formatting characters are removed so
    the same number is never stored twice in different shapes.
    """
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        digits = digits[2:]
    elif not text.startswith("+") and len(digits) == 9:
        digits = "998" + digits
    if not 7 <= len(digits) <= 15 or digits.startswith("0"):
        raise InvalidPhoneError("Telefon raqamini davlat kodi bilan kiriting, masalan +998 90 123 45 67.")
    return "+" + digits
