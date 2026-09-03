"""
Optional insider-cluster / rug risk check via RiskDataApi (tnt-audit.com).

Not wired into the trading loop automatically — this repo's layering rules
(interfaces -> utils -> core -> platforms -> monitoring -> trading ->
bot_runner) mean the right call site inside trading/ depends on details of
each platform's buy flow that are outside this module's scope. See
learning-examples/risk_check_example.py for a standalone usage example, or
call check_token_risk() directly before a buy in your own bot_runner/trading
code.

Free to use: 5 calls/day with no API key/signup at all, or set
RISK_API_KEY in your environment for 15 free calls/day.
Get a key: https://tnt-audit.com/risk-api
"""

import os
from dataclasses import dataclass

import aiohttp

from utils.logger import get_logger

logger = get_logger(__name__)

RISK_API_URL = "https://tnt-audit.com/api/v1/token-risk"


@dataclass
class RiskCheckResult:
    """Result of a token risk check.

    ok is True when the check passed (or the API was unavailable, in which
    case this fails open rather than blocking a trade on a safety-net
    dependency). worst_cluster_percent is the largest share of supply held
    by wallets that trace back to a single first-funder.
    """

    ok: bool
    safety_score: int | None = None
    worst_cluster_percent: float = 0.0
    reason: str | None = None


async def check_token_risk(
    mint: str,
    max_cluster_percent: float = 50.0,
    api_key: str | None = None,
    timeout_seconds: float = 5.0,
) -> RiskCheckResult:
    """Check a Solana mint for insider wallet clusters before buying.

    Traces top holders back to their first funder — catches supply
    deliberately split across several wallets funded by the same source,
    which a simple top-holder-percentage check can miss entirely.

    Args:
        mint: Solana token mint address.
        max_cluster_percent: Fail the check if any funder-linked cluster
            holds more than this percent of supply.
        api_key: Optional RiskDataApi key (RISK_API_KEY env var by
            convention). Without one, calls use the free 5/day anonymous
            quota; 15/day free with a key from tnt-audit.com/risk-api.
        timeout_seconds: HTTP timeout — this is a safety-net check, not a
            hard dependency, so it should never stall a trade for long.

    Returns:
        RiskCheckResult. Fails open (ok=True) on any network/API error —
        callers should treat this as best-effort, not a hard gate.
    """
    key = api_key or os.environ.get("RISK_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(RISK_API_URL, params={"mint": mint}, headers=headers) as response:
                if response.status != 200:
                    logger.warning("Risk API returned %s for %s, skipping check", response.status, mint)
                    return RiskCheckResult(ok=True, reason="risk_api_unavailable")
                data = await response.json()

        clusters = data.get("insider_clusters", [])
        worst = max((c.get("percent_of_supply", 0) for c in clusters), default=0.0)

        ok = worst <= max_cluster_percent
        return RiskCheckResult(
            ok=ok,
            safety_score=data.get("safety_score"),
            worst_cluster_percent=worst,
            reason=None if ok else f"{worst:.1f}% of supply in a first-funder cluster (max {max_cluster_percent}%)",
        )
    except Exception as exc:  # noqa: BLE001 - safety-net check, never raises
        logger.warning("Risk check failed for %s: %s", mint, exc)
        return RiskCheckResult(ok=True, reason="risk_api_error")
