"""Apify Actor entrypoint – Facebook Foncier Scraper (Ouagadougou).

1. Lit l'input Actor
2. Configure le proxy (Apify Proxy ou custom)
3. Lance le scraper Playwright (mode mobile)
4. Pousse les résultats dans le Dataset par défaut
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from apify import Actor

from . import config
from .scraper import (
    BlocageDetecteError,
    ProxyIncoherentError,
    SessionExpireeError,
    executer_scraping,
)


async def main() -> None:
    async with Actor:
        actor_input: dict[str, Any] = await Actor.get_input() or {}

        mode = actor_input.get("mode", "daily")
        days_back = int(actor_input.get("daysBack", 1))
        group_limit = int(actor_input.get("groupLimit", 0))
        account_id = actor_input.get("accountId") or None
        cookies_json = actor_input.get("cookies") or ""

        # Fallback : secrets d'environnement (CI / local)
        if not cookies_json:
            if account_id:
                cookies_json = os.environ.get(f"FB_COOKIES_JSON_{account_id}", "")
            if not cookies_json:
                cookies_json = os.environ.get("FB_COOKIES_JSON", "")

        if not cookies_json:
            await Actor.fail(
                "Aucun cookie Facebook fourni. "
                "Passez-les via l'input `cookies` ou la variable d'environnement "
                "FB_COOKIES_JSON / FB_COOKIES_JSON_<n>."
            )
            return

        Actor.log.info(
            "Démarrage | mode=%s days_back=%s group_limit=%s account=%s",
            mode,
            days_back,
            group_limit or "tous",
            account_id or "default",
        )

        # --- Proxy -------------------------------------------------------
        proxy_dict: dict[str, str] | None = None
        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get("proxyConfiguration")
        )
        if proxy_configuration:
            proxy_url = await proxy_configuration.new_url()
            if proxy_url:
                proxy_dict = config.parse_proxy_url(proxy_url)
                Actor.log.info("Proxy Apify configuré : %s", proxy_dict.get("server") if proxy_dict else proxy_url)

        # Fallback proxy custom (env)
        if proxy_dict is None:
            env_proxy = None
            if account_id:
                env_proxy = os.environ.get(f"PROXY_URL_{account_id}")
            if not env_proxy:
                env_proxy = os.environ.get("PROXY_URL")
            proxy_dict = config.parse_proxy_url(env_proxy)
            if proxy_dict:
                Actor.log.info("Proxy custom : %s", proxy_dict.get("server"))

        # --- Scraping ----------------------------------------------------
        try:
            posts = await executer_scraping(
                cookies_json=cookies_json,
                mode=mode,
                days_back=days_back,
                group_limit=group_limit,
                compte=account_id,
                proxy=proxy_dict,
                verifier_proxy=bool(proxy_dict),
            )
        except SessionExpireeError as exc:
            await Actor.fail(f"Session Facebook expirée : {exc}")
            return
        except BlocageDetecteError as exc:
            await Actor.fail(f"Blocage anti-bot détecté : {exc}")
            return
        except ProxyIncoherentError as exc:
            await Actor.fail(f"Problème de proxy : {exc}")
            return
        except Exception as exc:
            Actor.log.exception("Erreur fatale pendant le scraping")
            await Actor.fail(str(exc))
            return

        # --- Output ------------------------------------------------------
        if not posts:
            Actor.log.warning("Aucun post candidat collecté.")
        else:
            await Actor.push_data(posts)
            Actor.log.info("%d annonce(s) poussée(s) dans le Dataset.", len(posts))

        Actor.log.info("Actor terminé avec succès.")


if __name__ == "__main__":
    asyncio.run(main())
