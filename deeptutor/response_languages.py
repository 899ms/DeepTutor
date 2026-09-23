"""Supported model output languages shared by prompts and Settings."""

SUPPORTED_RESPONSE_LANGUAGES: tuple[str, ...] = (
    "en",
    "zh",
    "zh-tw",
    "ja",
    "ko",
    "es",
    "fr",
    "de",
    "ru",
    "pt",
    "it",
    "ar",
    "pl",
    "uk",
)


def validate_reply_language_override(value: str | None) -> str | None:
    """Validate a conversation override without changing its meaning.

    ``None`` means follow the account default. A typo must fail visibly rather
    than silently turning a fixed-language conversation back into default.
    """
    if value is None:
        return None
    if value not in SUPPORTED_RESPONSE_LANGUAGES:
        raise ValueError("Unsupported reply language")
    return value
