"""Point d'entrée CLI du pipeline Facebook Foncier Scraper.

Inspiré du modèle Actor (input clair → exécution → sortie structurée),
sans dépendance à la plateforme Apify.

Usage:
  python -m src --cookies-file cookies.json --group-limit 1
  python -m src --input input.json
  python -m src --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import config
from .scraper import (
    BlocageDetecteError,
    ProxyIncoherentError,
    SessionExpireeError,
    executer_scraping,
)

logger = logging.getLogger("facebook-foncier-scraper")


def _configurer_logging(verbose: bool = False) -> None:
    niveau = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _charger_input_json(chemin: Path) -> dict[str, Any]:
    with chemin.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{chemin} doit contenir un objet JSON.")
    return data


def _resoudre_cookies(args: argparse.Namespace, input_data: dict[str, Any]) -> str:
    """Priorité : --cookies-file > input.cookies > env."""
    if args.cookies_file:
        return Path(args.cookies_file).read_text(encoding="utf-8").strip()

    if input_data.get("cookies"):
        return str(input_data["cookies"]).strip()

    account = args.account or input_data.get("accountId")
    if account:
        val = os.environ.get(f"FB_COOKIES_JSON_{account}", "").strip()
        if val:
            return val
    return os.environ.get("FB_COOKIES_JSON", "").strip()


def _resoudre_proxy(args: argparse.Namespace, input_data: dict[str, Any]) -> dict[str, str] | None:
    if args.proxy:
        return config.parse_proxy_url(args.proxy)

    proxy_url = input_data.get("proxyUrl") or input_data.get("proxy")
    if proxy_url:
        return config.parse_proxy_url(str(proxy_url))

    account = args.account or input_data.get("accountId")
    if account:
        env_p = os.environ.get(f"PROXY_URL_{account}", "").strip()
        if env_p:
            return config.parse_proxy_url(env_p)
    return config.parse_proxy_url(os.environ.get("PROXY_URL", "").strip() or None)


def _sauvegarder_resultats(posts: list[dict[str, Any]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    chemin = out_dir / f"annonces_{ts}.json"
    with chemin.open("w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    return chemin


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="facebook-foncier-scraper",
        description="Pipeline de scraping des annonces foncières Facebook (Ouagadougou).",
    )
    p.add_argument(
        "--input",
        type=Path,
        help="Fichier JSON d'entrée (mode, daysBack, groupLimit, cookies, proxyUrl…)",
    )
    p.add_argument("--mode", choices=("daily", "backfill"), default=None)
    p.add_argument("--days-back", type=int, default=None)
    p.add_argument("--group-limit", type=int, default=None, help="0 = tous les groupes")
    p.add_argument("--account", type=str, default=None, help="Identifiant compte 1–5")
    p.add_argument("--cookies-file", type=Path, help="Fichier JSON des cookies Facebook")
    p.add_argument("--proxy", type=str, help="URL proxy http://user:pass@host:port")
    p.add_argument(
        "--no-proxy-check",
        action="store_true",
        help="Ne pas vérifier la géoloc du proxy avant de scraper",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Dossier de sortie des JSON (défaut: data/processed)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


async def run(args: argparse.Namespace) -> int:
    load_dotenv()
    _configurer_logging(args.verbose)

    input_data: dict[str, Any] = {}
    if args.input:
        input_data = _charger_input_json(args.input)
        logger.info("Input chargé depuis %s", args.input)

    mode = args.mode or input_data.get("mode") or "daily"
    days_back = args.days_back if args.days_back is not None else int(input_data.get("daysBack", 1))
    group_limit = (
        args.group_limit if args.group_limit is not None else int(input_data.get("groupLimit", 0))
    )
    account = args.account or input_data.get("accountId") or None

    cookies_json = _resoudre_cookies(args, input_data)
    if not cookies_json:
        logger.error(
            "Aucun cookie fourni. Utilisez --cookies-file, input.cookies, "
            "ou FB_COOKIES_JSON / FB_COOKIES_JSON_<n>."
        )
        return 1

    proxy = _resoudre_proxy(args, input_data)
    if proxy:
        logger.info("Proxy : %s", proxy.get("server"))
    else:
        logger.warning("Aucun proxy configuré – sortie via IP locale / runner.")

    logger.info(
        "Démarrage | mode=%s days_back=%s group_limit=%s account=%s",
        mode,
        days_back,
        group_limit or "tous",
        account or "default",
    )

    try:
        posts = await executer_scraping(
            cookies_json=cookies_json,
            mode=mode,
            days_back=days_back,
            group_limit=group_limit,
            compte=account,
            proxy=proxy,
            verifier_proxy=bool(proxy) and not args.no_proxy_check,
        )
    except SessionExpireeError as exc:
        logger.critical("Session Facebook expirée : %s", exc)
        return 2
    except BlocageDetecteError as exc:
        logger.critical("Blocage anti-bot : %s", exc)
        return 3
    except ProxyIncoherentError as exc:
        logger.critical("Proxy inutilisable : %s", exc)
        return 4
    except Exception:
        logger.exception("Erreur fatale")
        return 1

    if not posts:
        logger.warning("Aucun post candidat collecté.")
    else:
        chemin = _sauvegarder_resultats(posts, args.output_dir)
        logger.info("%d annonce(s) sauvegardée(s) → %s", len(posts), chemin)

    logger.info("Pipeline terminé.")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = asyncio.run(run(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
