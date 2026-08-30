"""Scraping Facebook (Playwright async) – version Actor.

Logique adaptée depuis ouaga-foncier-etl/scraper.py :
- mode mobile (m.facebook.com)
- extraction JSON Comet
- fingerprint mobile stable par compte
- support proxy
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from . import config

logger = logging.getLogger("facebook-foncier-scraper.scraper")


class SessionExpireeError(Exception):
    """Cookies Facebook invalides."""


class BlocageDetecteError(Exception):
    """Mur anti-bot / checkpoint détecté."""


class ProxyIncoherentError(Exception):
    """Proxy inutilisable ou pays incohérent."""


# --------------------------------------------------------------------------- #
# Cookies
# --------------------------------------------------------------------------- #

_SAMESITE_MAP = {
    "strict": "Strict",
    "lax": "Lax",
    "none": "None",
    "no_restriction": "None",
    "unspecified": "Lax",
}


def _normaliser_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    converti: dict[str, Any] = {
        "name": cookie["name"],
        "value": cookie["value"],
        "domain": cookie["domain"],
        "path": cookie.get("path") or "/",
    }
    if cookie.get("httpOnly") is not None:
        converti["httpOnly"] = bool(cookie["httpOnly"])
    if cookie.get("secure") is not None:
        converti["secure"] = bool(cookie["secure"])

    expiration = cookie.get("expires", cookie.get("expirationDate"))
    if expiration is not None and not cookie.get("session"):
        converti["expires"] = float(expiration)

    same_site = cookie.get("sameSite")
    if same_site:
        mapped = _SAMESITE_MAP.get(str(same_site).lower())
        if mapped:
            converti["sameSite"] = mapped
    return converti


def charger_cookies(cookies_json: str) -> list[dict[str, Any]]:
    try:
        bruts = json.loads(cookies_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cookies JSON invalide : {exc}") from exc

    if not isinstance(bruts, list) or not bruts:
        raise ValueError("Les cookies doivent être une liste non vide.")

    requis = {"name", "value", "domain"}
    for i, c in enumerate(bruts):
        if not isinstance(c, dict) or not requis.issubset(c):
            raise ValueError(f"Cookie #{i} invalide (champs manquants).")

    cookies = [_normaliser_cookie(c) for c in bruts]
    noms = {c["name"] for c in cookies}
    if "c_user" not in noms or "xs" not in noms:
        logger.warning("Cookies c_user/xs absents – session probablement non authentifiée.")
    return cookies


# --------------------------------------------------------------------------- #
# Navigateur
# --------------------------------------------------------------------------- #


async def creer_navigateur(
    playwright,
    cookies: list[dict[str, Any]],
    compte: str | None = None,
    proxy: dict[str, str] | None = None,
) -> tuple[Browser, BrowserContext]:
    user_agent, viewport = config.choisir_fingerprint_mobile(compte)
    region = config.parametres_regionaux(compte)
    logger.info(
        "Fingerprint mobile : %sx%s | UA=%s...",
        viewport["width"],
        viewport["height"],
        user_agent[:50],
    )

    navigateur = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
        proxy=proxy,
    )
    contexte = await navigateur.new_context(
        viewport=viewport,
        user_agent=user_agent,
        is_mobile=True,
        has_touch=True,
        locale=region.locale,
        timezone_id=region.fuseau_horaire,
    )
    await contexte.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    await contexte.add_cookies(cookies)
    contexte.set_default_navigation_timeout(config.NAVIGATION_TIMEOUT_MS)
    return navigateur, contexte


async def verifier_proxy_et_region(
    contexte: BrowserContext,
    compte: str | None,
) -> None:
    region = config.parametres_regionaux(compte)
    page = await contexte.new_page()
    try:
        reponse = await page.goto(
            config.PROXY_GEO_CHECK_URL,
            wait_until="domcontentloaded",
            timeout=config.PROXY_GEO_CHECK_TIMEOUT_MS,
        )
        if reponse is None or not reponse.ok:
            statut = reponse.status if reponse is not None else "aucune réponse"
            raise ProxyIncoherentError(f"Vérification proxy impossible ({statut}).")

        try:
            donnees = json.loads(await page.locator("body").inner_text())
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProxyIncoherentError("Réponse géoloc illisible.") from exc

        pays = str(donnees.get("country_code") or donnees.get("country") or "").upper()
        if pays and pays != region.pays:
            raise ProxyIncoherentError(
                f"Pays proxy incohérent : attendu={region.pays}, observé={pays}."
            )
        logger.info("Proxy OK – pays=%s locale=%s", pays or "?", region.locale)
    except ProxyIncoherentError:
        raise
    except Exception as exc:
        raise ProxyIncoherentError(f"Proxy inutilisable : {exc}") from exc
    finally:
        await page.close()


async def detecter_blocage_ou_session_expiree(page: Page) -> None:
    url = page.url.lower()
    if any(f in url for f in ("checkpoint", "login.php", "recover")):
        raise BlocageDetecteError(f"URL checkpoint/login : {page.url}")

    try:
        contenu = (await page.content()).lower()
    except Exception:
        return

    if any(
        m in contenu
        for m in (
            "nous voulons juste vérifier",
            "confirmez votre identité",
            "we just want to make sure",
        )
    ):
        raise BlocageDetecteError("Texte anti-bot détecté.")

    if '"user_id":"0"' in contenu or '"actorid":"0"' in contenu:
        raise SessionExpireeError("Session Comet déconnectée (USER_ID=0).")


# --------------------------------------------------------------------------- #
# Extraction JSON Comet
# --------------------------------------------------------------------------- #

_CLES_STORY = ("id", "comet_sections")


def _est_noeud_story(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("id"), str)
        and all(c in obj for c in _CLES_STORY)
    )


def _chercher(obj: Any, pred: Callable[[Any], bool], max_depth: int = 12) -> Any | None:
    file: deque[tuple[Any, int]] = deque([(obj, 0)])
    while file:
        courant, profondeur = file.popleft()
        if profondeur > max_depth:
            continue
        if pred(courant):
            return courant
        if isinstance(courant, dict):
            for v in courant.values():
                file.append((v, profondeur + 1))
        elif isinstance(courant, list):
            for v in courant:
                file.append((v, profondeur + 1))
    return None


def _extraire_texte(story: dict) -> str | None:
    def _ok(v: Any) -> bool:
        return (
            isinstance(v, dict)
            and isinstance(v.get("message"), dict)
            and isinstance(v["message"].get("text"), str)
            and bool(v["message"]["text"].strip())
        )

    t = _chercher(story, _ok)
    return t["message"]["text"] if t else None


def _extraire_url(story: dict) -> str | None:
    def _ok(v: Any) -> bool:
        return (
            isinstance(v, dict)
            and isinstance(v.get("url"), str)
            and ("/posts/" in v["url"] or "/permalink/" in v["url"])
        )

    t = _chercher(story, _ok)
    return t["url"] if t else None


def _extraire_date(story: dict) -> datetime | None:
    def _ok(v: Any) -> bool:
        return (
            isinstance(v, dict)
            and isinstance(v.get("creation_time"), (int, float))
            and not isinstance(v.get("creation_time"), bool)
            and v["creation_time"] > 1_000_000_000
        )

    t = _chercher(story, _ok)
    if not t:
        return None
    try:
        return datetime.fromtimestamp(t["creation_time"], tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def extraire_stories(payload: Any, groupe_id: str, groupe_nom: str) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    vus: set[str] = set()
    maintenant = datetime.now(timezone.utc)

    def _parcourir(obj: Any) -> None:
        if isinstance(obj, dict):
            if _est_noeud_story(obj) and obj["id"] not in vus:
                texte = _extraire_texte(obj)
                if texte:
                    vus.add(obj["id"])
                    date = _extraire_date(obj)
                    posts.append(
                        {
                            "id": obj["id"],
                            "groupe_id": groupe_id,
                            "groupe_nom": groupe_nom,
                            "url": _extraire_url(obj),
                            "texte": texte,
                            "date_publication": date.isoformat() if date else None,
                            "date_incertaine": date is None,
                            "scrape_le": maintenant.isoformat(),
                        }
                    )
                    return
            for v in obj.values():
                _parcourir(v)
        elif isinstance(obj, list):
            for v in obj:
                _parcourir(v)

    try:
        _parcourir(payload)
    except RecursionError:
        logger.warning("Profondeur JSON excessive – extraction partielle.")
    return posts


def _extraire_depuis_html(html: str, groupe_id: str, groupe_nom: str) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    vus: set[str] = set()
    for blob in re.findall(
        r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for p in extraire_stories(payload, groupe_id, groupe_nom):
            if p["id"] not in vus:
                vus.add(p["id"])
                posts.append(p)
    return posts


# --------------------------------------------------------------------------- #
# Scraping d'un groupe
# --------------------------------------------------------------------------- #


async def _scroll_humain(page: Page) -> None:
    hauteur = await page.evaluate("window.innerHeight")
    for _ in range(random.randint(2, 4)):
        distance = random.uniform(0.4, 1.1) * hauteur
        await page.evaluate(f"window.scrollBy(0, {distance})")
        await asyncio.sleep(
            random.uniform(config.SCROLL_MICRO_PAUSE_MIN_S, config.SCROLL_MICRO_PAUSE_MAX_S)
        )


async def scraper_groupe(
    contexte: BrowserContext,
    groupe: config.Groupe,
    max_days_back: int,
    seen_ids: set[str],
) -> list[dict[str, Any]]:
    date_limite = datetime.now(timezone.utc) - timedelta(days=max_days_back)
    page = await contexte.new_page()
    nouveaux: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    taches: set[asyncio.Task] = set()

    async def _traiter_reponse(reponse: Any) -> None:
        try:
            corps = await reponse.text()
        except Exception:
            return
        corps = corps.removeprefix("for (;;);")
        for candidat in (corps, *corps.splitlines()):
            candidat = candidat.strip()
            if not candidat:
                continue
            try:
                payload = json.loads(candidat)
            except json.JSONDecodeError:
                continue
            captures.extend(extraire_stories(payload, groupe.id, groupe.nom))

    def _sur_reponse(reponse: Any) -> None:
        if any(f in reponse.url for f in config.GRAPHQL_URL_FRAGMENTS):
            tache = asyncio.ensure_future(_traiter_reponse(reponse))
            taches.add(tache)
            tache.add_done_callback(taches.discard)

    page.on("response", _sur_reponse)

    try:
        logger.info("Ouverture : %s (%s)", groupe.nom, groupe.url)
        await page.goto(groupe.url, wait_until="domcontentloaded")
        await detecter_blocage_ou_session_expiree(page)
        await asyncio.sleep(
            random.uniform(config.TEMPS_LECTURE_MIN_S, config.TEMPS_LECTURE_MAX_S)
        )

        # Posts mis en avant (HTML initial)
        html = await page.content()
        for p in _extraire_depuis_html(html, groupe.id, groupe.nom):
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                nouveaux.append(p)

        etapes_sans = 0
        for etape in range(config.MAX_PAGES_ABSOLU):
            debut = len(captures)
            await _scroll_humain(page)
            await asyncio.sleep(
                random.uniform(config.PAGE_DELAY_MIN_S, config.PAGE_DELAY_MAX_S)
            )
            if taches:
                await asyncio.gather(*list(taches), return_exceptions=True)

            bruts = captures[debut:]
            inedits = [p for p in bruts if p["id"] not in seen_ids]
            # dédup locale
            vus_etape: set[str] = set()
            uniques = []
            for p in inedits:
                if p["id"] not in vus_etape:
                    vus_etape.add(p["id"])
                    uniques.append(p)

            if uniques:
                etapes_sans = 0
                for p in uniques:
                    seen_ids.add(p["id"])
                nouveaux.extend(uniques)
            else:
                etapes_sans += 1

            # Arrêt temporel
            dates = [
                datetime.fromisoformat(p["date_publication"])
                for p in uniques
                if p.get("date_publication")
            ]
            if dates and min(dates) < date_limite:
                logger.info("Fenêtre temporelle atteinte pour %s", groupe.nom)
                break

            if etapes_sans >= config.MAX_PAGES_SANS_NOUVEAU_POST:
                logger.info("Plus de nouveaux posts sur %s", groupe.nom)
                break

            logger.info(
                "%s | scroll %d | +%d posts (total %d)",
                groupe.nom,
                etape + 1,
                len(uniques),
                len(nouveaux),
            )

    except PlaywrightTimeoutError as exc:
        logger.error("Timeout sur %s : %s", groupe.nom, exc)
    finally:
        page.remove_listener("response", _sur_reponse)
        if taches:
            await asyncio.gather(*list(taches), return_exceptions=True)
        await page.close()

    return nouveaux


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


async def executer_scraping(
    *,
    cookies_json: str,
    mode: str = "daily",
    days_back: int = 1,
    group_limit: int = 0,
    compte: str | None = None,
    proxy: dict[str, str] | None = None,
    verifier_proxy: bool = True,
) -> list[dict[str, Any]]:
    """Point d'entrée scraping. Retourne la liste des posts collectés."""
    cookies = charger_cookies(cookies_json)
    groupes = config.charger_groupes(
        limite=group_limit if group_limit > 0 else None,
        compte=compte,
    )
    logger.info(
        "Compte=%s | mode=%s | %d groupe(s) | days_back=%d",
        compte or "default",
        mode,
        len(groupes),
        days_back,
    )

    if proxy:
        logger.info("Proxy : %s", proxy.get("server"))

    seen_ids: set[str] = set()
    tous_posts: list[dict[str, Any]] = []

    async with async_playwright() as pw:
        for i, groupe in enumerate(groupes):
            navigateur = None
            contexte = None
            try:
                navigateur, contexte = await creer_navigateur(
                    pw, cookies, compte, proxy
                )
                if proxy and verifier_proxy:
                    await verifier_proxy_et_region(contexte, compte)

                posts = await scraper_groupe(
                    contexte, groupe, days_back, seen_ids
                )
                # Filtre foncier niveau 1
                candidats = [p for p in posts if config.est_candidat_foncier(p.get("texte", ""))]
                logger.info(
                    "%s : %d posts bruts → %d candidats fonciers",
                    groupe.nom,
                    len(posts),
                    len(candidats),
                )
                tous_posts.extend(candidats)

            except (SessionExpireeError, BlocageDetecteError, ProxyIncoherentError):
                logger.critical("Erreur fatale sur %s – arrêt.", groupe.nom, exc_info=True)
                raise
            except Exception:
                logger.exception("Erreur sur %s – groupe ignoré.", groupe.nom)
            finally:
                if contexte:
                    await contexte.close()
                if navigateur:
                    await navigateur.close()

            if i < len(groupes) - 1:
                pause = random.uniform(
                    config.PAUSE_ENTRE_GROUPES_MIN_S,
                    config.PAUSE_ENTRE_GROUPES_MAX_S,
                )
                logger.info("Pause inter-groupe %.0fs", pause)
                await asyncio.sleep(pause)

    return tous_posts
