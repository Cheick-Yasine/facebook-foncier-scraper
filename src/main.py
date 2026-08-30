"""Apify Actor entrypoint for Facebook Foncier Scraper.

This is the main entry point of the Actor. It follows the standard Apify
Python Actor pattern:

1. Enter the Actor context
2. Read and validate input
3. Run the scraping pipeline
4. Push results to the default dataset
"""

from __future__ import annotations

import asyncio
from typing import Any

from apify import Actor


async def main() -> None:
    async with Actor:
        # 1. Read input
        actor_input: dict[str, Any] = await Actor.get_input() or {}

        mode = actor_input.get("mode", "daily")
        days_back = int(actor_input.get("daysBack", 1))
        group_limit = int(actor_input.get("groupLimit", 0))
        batch_size = int(actor_input.get("batchSize", 5))
        account_id = actor_input.get("accountId") or None
        skip_llm = bool(actor_input.get("skipLlm", False))
        cookies_json = actor_input.get("cookies")

        Actor.log.info(
            "Starting Facebook Foncier Scraper | mode=%s days_back=%s "
            "group_limit=%s account=%s",
            mode,
            days_back,
            group_limit or "all",
            account_id or "default",
        )

        # 2. Proxy configuration (Apify Proxy or custom)
        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get("proxyConfiguration")
        )

        # 3. Placeholder for the real pipeline
        # -----------------------------------------------------------------
        # TODO: migrate the Playwright scraper from ouaga-foncier-etl here.
        # For now we push a sample item so the Actor is runnable end-to-end.
        # -----------------------------------------------------------------

        sample_item = {
            "id": "sample-post-001",
            "groupe_id": "sample-group",
            "groupe_nom": "LOCATION DE MAISON & VENTE DE PARCELLE A Ouagadougou",
            "url": "https://www.facebook.com/groups/sample/posts/001",
            "texte": "Terrain 300m² à vendre à Ouaga 2000 - 15 millions FCFA",
            "date_publication": "2026-08-29T10:00:00+00:00",
            "date_incertaine": False,
            "scrape_le": "2026-08-30T12:00:00+00:00",
            "type_annonce": "vente",
            "prix": 15_000_000,
            "devise": "XOF",
            "surface": 300,
            "quartier": "Ouaga 2000",
            "telephone": None,
            "_meta": {
                "mode": mode,
                "days_back": days_back,
                "account_id": account_id,
                "note": "Sample item – real scraper not yet migrated",
            },
        }

        await Actor.push_data(sample_item)

        Actor.log.info("Actor finished successfully (sample data only).")


if __name__ == "__main__":
    asyncio.run(main())
