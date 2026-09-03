"""
Standalone example: check a Solana token for insider wallet clusters before
buying, using the free RiskDataApi (tnt-audit.com).

Self-contained — does not import from src/, matches the convention of the
other scripts in this folder. Run directly:

    python learning-examples/risk_check_example.py <mint_address>

5 free calls/day, no signup. Set RISK_API_KEY in your environment for
15 free calls/day (email signup, no card) — get one at
https://tnt-audit.com/risk-api
"""

import asyncio
import os
import sys

import aiohttp

RISK_API_URL = "https://tnt-audit.com/api/v1/token-risk"


async def check_token_risk(mint: str, max_cluster_percent: float = 50.0) -> None:
    api_key = os.environ.get("RISK_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async with aiohttp.ClientSession() as session:
        async with session.get(RISK_API_URL, params={"mint": mint}, headers=headers) as response:
            if response.status != 200:
                print(f"Risk API unavailable (HTTP {response.status}) — check did not run, result unknown.")
                return
            data = await response.json()

    print(f"mint: {mint}")
    print(f"safety_score: {data.get('safety_score')}")

    clusters = data.get("insider_clusters", [])
    worst = max((c.get("percent_of_supply", 0) for c in clusters), default=0.0)
    print(f"insider clusters found: {len(clusters)}")
    print(f"worst cluster: {worst:.1f}% of supply shares one first-funder")

    if worst > max_cluster_percent:
        print(f"-> FAIL: exceeds {max_cluster_percent}% threshold, would skip this buy")
    else:
        print(f"-> PASS: under {max_cluster_percent}% threshold")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python risk_check_example.py <mint_address>")
        sys.exit(1)

    asyncio.run(check_token_risk(sys.argv[1]))
