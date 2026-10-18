import re


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Return an Uzbek phone number as ``+998XXXXXXXXX``.

    Accepts the usual ways people type it ("90 123 45 67", "998901234567",
    "+998 (90) 123-45-67") and raises ``InvalidPhoneError`` for anything else,
    so the same number can never be stored twice in different shapes.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) != 12 or not digits.startswith("998"):
        raise InvalidPhoneError("Telefon raqamini +998 XX XXX XX XX ko'rinishida kiriting.")
    return "+" + digits
