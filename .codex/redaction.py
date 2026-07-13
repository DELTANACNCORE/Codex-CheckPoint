"""Redact credentials before CxCP persists generated knowledge notes."""

from __future__ import annotations

import re


REDACTION_MARKER = "[REDACTED]"

_AUTHORIZATION_RE = re.compile(
    r"(?P<prefix>\bAuthorization\s*:\s*(?:Bearer|Basic)\s+)(?P<value>[A-Za-z0-9._~+/=-]+)",
    re.IGNORECASE,
)
_JSON_AUTHORIZATION_RE = re.compile(
    r"(?P<prefix>[\"']Authorization[\"']\s*:\s*[\"'](?:Bearer|Basic)\s+)(?P<value>[^\"'\s,;]+)(?P<suffix>[\"'])",
    re.IGNORECASE,
)
_NAMESPACE_RE = re.compile(
    r"(?P<prefix>\bX-Namespace\s*[:=]\s*)(?P<quote>[\"']?)(?P<value>[A-Za-z0-9._~+/=-]{8,})(?P=quote)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>(?<![A-Za-z0-9_])[\"']?(?:(?:[A-Za-z][A-Za-z0-9_.-]*[_-])?"
    r"(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|auth[_ -]?token|"
    r"client[_ -]?secret|(?:mysql|db|database)[_ -]?password|password|passwd|secret|token))"
    r"[\"']?\s*[:=]\s*)(?P<quote>[\"']?)(?P<value>[A-Za-z0-9_./+=:@~%\-]{8,})(?P=quote)",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_RE = re.compile(
    r"(?P<prefix>--?[A-Za-z0-9_.-]*(?:api[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"auth[-_]?token|client[-_]?secret|(?:mysql|db|database)[-_]?password|password|passwd|secret|token)\s+)"
    r"(?P<quote>[\"']?)(?P<value>[A-Za-z0-9_./+=:@~%\-]{8,})(?P=quote)",
    re.IGNORECASE,
)
_SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b", re.IGNORECASE)
_GOOGLE_API_KEY_RE = re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b")
_AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.IGNORECASE,
)
_COOKIE_RE = re.compile(r"(?P<prefix>\b(?:Set-)?Cookie\s*:\s*)(?P<value>[^\r\n]+)", re.IGNORECASE)


def _redact_with_optional_quote(match: re.Match[str]) -> str:
    quote = match.groupdict().get("quote") or ""
    return f"{match.group('prefix')}{quote}{REDACTION_MARKER}{quote}"


def redact_sensitive_text(text: str) -> str:
    """Return text with common credentials replaced by a stable marker.

    This helper intentionally operates on generated content only. Callers must
    not apply it to arbitrary user-authored vault documents as a side effect.
    """
    if not isinstance(text, str) or not text:
        return text

    text = _PRIVATE_KEY_RE.sub(REDACTION_MARKER, text)
    text = _AUTHORIZATION_RE.sub(lambda match: f"{match.group('prefix')}{REDACTION_MARKER}", text)
    text = _JSON_AUTHORIZATION_RE.sub(
        lambda match: f"{match.group('prefix')}{REDACTION_MARKER}{match.group('suffix')}",
        text,
    )
    text = _NAMESPACE_RE.sub(_redact_with_optional_quote, text)
    text = _SENSITIVE_ASSIGNMENT_RE.sub(_redact_with_optional_quote, text)
    text = _SENSITIVE_FLAG_RE.sub(_redact_with_optional_quote, text)
    text = _COOKIE_RE.sub(lambda match: f"{match.group('prefix')}{REDACTION_MARKER}", text)
    text = _SK_KEY_RE.sub(REDACTION_MARKER, text)
    text = _JWT_RE.sub(REDACTION_MARKER, text)
    text = _GITHUB_TOKEN_RE.sub(REDACTION_MARKER, text)
    text = _GOOGLE_API_KEY_RE.sub(REDACTION_MARKER, text)
    text = _AWS_ACCESS_KEY_RE.sub(REDACTION_MARKER, text)
    return text
