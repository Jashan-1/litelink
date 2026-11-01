from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanResult:
    verdict: str  # allow | review | block
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)


async def scan(target_url: str) -> ScanResult:
    # shortcut: allows everything, replace with the real pipeline before opening sign-in beyond ALLOWED_EMAILS
    return ScanResult("allow", ["stub scanner: no checks ran"])
