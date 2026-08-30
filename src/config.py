"""Configuration centrale de l'Actor Facebook Foncier Scraper.

Adapté depuis ouaga-foncier-etl pour le pattern Apify Actor.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("facebook-foncier-scraper.config")

# --------------------------------------------------------------------------- #
# Chemins
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent.parent
GROUPS_CSV_PATH = BASE_DIR / "groups.csv"

COMPTES_VALIDES = {"1", "2", "3", "4", "5"}

# --------------------------------------------------------------------------- #
# Groupes Facebook
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Groupe:
    id: str
    nom: str
    url: str
    actif: bool = True
    compte: str = "1"


def charger_groupes(
    chemin: Path = GROUPS_CSV_PATH,
    limite: int | None = None,
    compte: str | None = None,
) -> list[Groupe]:
    """Charge les groupes actifs depuis groups.csv."""
    if compte is not None and compte not in COMPTES_VALIDES:
        raise ValueError(
            f"Compte '{compte}' inconnu (valeurs valides : {sorted(COMPTES_VALIDES)})."
        )

    if not chemin.exists():
        raise FileNotFoundError(f"Fichier de groupes introuvable : {chemin}")

    groupes: list[Groupe] = []
    with chemin.open(encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        colonnes = {"id", "nom", "url", "actif"}
        if lecteur.fieldnames is None or not colonnes.issubset(set(lecteur.fieldnames)):
            raise ValueError(f"En-têtes CSV invalides dans {chemin}")

        colonne_compte = "compte" in (lecteur.fieldnames or [])
        for ligne in lecteur:
            if ligne["id"].strip().upper().startswith("TODO"):
                continue
            valeur_compte = (ligne.get("compte") or "").strip() if colonne_compte else ""
            valeur_compte = valeur_compte or "1"
            if valeur_compte not in COMPTES_VALIDES:
                raise ValueError(
                    f"Compte '{valeur_compte}' invalide pour le groupe '{ligne['id']}'"
                )

            url_brute = ligne["url"].strip()
            url_mobile = re.sub(
                r"https?://(www\.|web\.)?facebook\.com",
                "https://m.facebook.com",
                url_brute,
            )
            groupes.append(
                Groupe(
                    id=ligne["id"].strip(),
                    nom=ligne["nom"].strip(),
                    url=url_mobile,
                    actif=ligne["actif"].strip().lower() in ("1", "true", "vrai", "oui"),
                    compte=valeur_compte,
                )
            )

    actifs = [g for g in groupes if g.actif]
    if compte is not None:
        actifs = [g for g in actifs if g.compte == compte]
    if not actifs:
        raise ValueError(
            f"Aucun groupe actif"
            + (f" pour le compte '{compte}'" if compte else "")
        )

    if limite is not None and limite > 0:
        actifs = actifs[:limite]
    return actifs


# --------------------------------------------------------------------------- #
# Proxies & région
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ParametresRegionaux:
    pays: str
    locale: str
    fuseau_horaire: str


def parametres_regionaux(compte: str | None = None) -> ParametresRegionaux:
    def _var(nom: str, defaut: str) -> str:
        if compte:
            v = os.environ.get(f"{nom}_{compte}", "").strip()
            if v:
                return v
        return os.environ.get(nom, "").strip() or defaut

    pays = _var("PROXY_COUNTRY", "BF").upper()
    if not re.fullmatch(r"[A-Z]{2}", pays):
        raise ValueError("PROXY_COUNTRY doit être un code ISO à 2 lettres")
    return ParametresRegionaux(
        pays=pays,
        locale=_var("BROWSER_LOCALE", "fr-FR"),
        fuseau_horaire=_var("BROWSER_TIMEZONE", "Africa/Ouagadougou"),
    )


def parse_proxy_url(url: str | None) -> dict[str, str] | None:
    """Parse une URL proxy au format Playwright."""
    if not url or not url.strip():
        return None
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https", "socks5"} or not parts.hostname:
        return None
    server = f"{parts.scheme.lower()}://{parts.hostname}"
    if parts.port:
        server += f":{parts.port}"
    proxy: dict[str, str] = {"server": server}
    if parts.username:
        proxy["username"] = urllib.parse.unquote(parts.username)
    if parts.password:
        proxy["password"] = urllib.parse.unquote(parts.password)
    return proxy


# --------------------------------------------------------------------------- #
# Fingerprints mobile
# --------------------------------------------------------------------------- #

MOBILE_PROFILES = [
    {
        "nom": "Galaxy S23",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
        ),
        "viewport": {"width": 360, "height": 780},
    },
    {
        "nom": "Pixel 8",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
        ),
        "viewport": {"width": 412, "height": 915},
    },
    {
        "nom": "Galaxy A53",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 13; SM-A536B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
        ),
        "viewport": {"width": 360, "height": 800},
    },
    {
        "nom": "Redmi Note 11",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 12; Redmi Note 11) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
        ),
        "viewport": {"width": 393, "height": 873},
    },
    {
        "nom": "Galaxy S21",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
        ),
        "viewport": {"width": 384, "height": 854},
    },
]


def choisir_fingerprint_mobile(compte: str | None = None) -> tuple[str, dict[str, int]]:
    if compte is None:
        index = 0
    else:
        if compte not in COMPTES_VALIDES:
            raise ValueError(f"Compte '{compte}' inconnu.")
        index = int(compte) - 1
    profil = MOBILE_PROFILES[index]
    return str(profil["user_agent"]), dict(profil["viewport"])


# --------------------------------------------------------------------------- #
# Constantes scraping
# --------------------------------------------------------------------------- #

MOBILE_FACEBOOK_BASE_URL = "https://m.facebook.com"
PROXY_GEO_CHECK_URL = "https://ip.decodo.com/json"
PROXY_GEO_CHECK_TIMEOUT_MS = 20_000
NAVIGATION_TIMEOUT_MS = 30_000

PAGE_DELAY_MIN_S = 4.0
PAGE_DELAY_MAX_S = 12.0
SCROLL_MICRO_PAUSE_MIN_S = 0.3
SCROLL_MICRO_PAUSE_MAX_S = 1.5
TEMPS_LECTURE_MIN_S = 5.0
TEMPS_LECTURE_MAX_S = 15.0
PAUSE_ENTRE_GROUPES_MIN_S = 30.0
PAUSE_ENTRE_GROUPES_MAX_S = 90.0

MAX_PAGES_SANS_NOUVEAU_POST = 4
MAX_PAGES_ABSOLU = 40
GRAPHQL_URL_FRAGMENTS = ["/api/graphql/"]
JSON_PROFONDEUR_MAX = 12

# Filtrage regex foncier (niveau 1)
_MOTS_FONCIER = [
    r"parcelle", r"terrain", r"lotissement", r"non\s+loti", r"zone\s+lotie",
    r"cession", r"hectares?", r"superficie",
]
_MOTS_DOCUMENT = [
    r"attestation", r"titre\s+foncier", r"\btf\b", r"puh", r"permis\s+d[' ]habiter",
    r"apfr", r"acte\s+de\s+cession",
]
_MOTS_TRANSACTION = [
    r"\b[àa]\s+vendre\b", r"\bvente\b", r"\bvendre\b", r"\bc[ée]der\b", r"\bprix\b",
]

MOTIF_FONCIER = re.compile(
    r"\b(" + "|".join(_MOTS_FONCIER + _MOTS_DOCUMENT + _MOTS_TRANSACTION) + r")\b",
    re.IGNORECASE,
)
MOTIF_SUPERFICIE_NUMERIQUE = re.compile(r"\d\s*(m2|m²|ha)(?=\D|$)", re.IGNORECASE)
MOTIF_RECHERCHE_ACHAT = re.compile(
    r"\b(je\s+recherche|recherche\s+un[e]?|cherche\s+un[e]?|besoin\s+d[' ]un[e]?)\b",
    re.IGNORECASE,
)
MOTIF_SIGNAL_VENTE = re.compile(
    r"\b([àa]\s+vendre|vends|disponible\s+[àa]\s+la\s+vente)\b|prix\s*:?\s*\d+",
    re.IGNORECASE,
)
MOTIF_SPAM = re.compile(
    r"(cliquez\s+ici|gagnez\s+\d|forex\s+trading|crypto\s*(monnaie)?\s+gratuit)",
    re.IGNORECASE,
)


def est_candidat_foncier(texte: str) -> bool:
    if not texte or not texte.strip():
        return False
    if MOTIF_SPAM.search(texte):
        return False
    if not (MOTIF_FONCIER.search(texte) or MOTIF_SUPERFICIE_NUMERIQUE.search(texte)):
        return False
    if MOTIF_RECHERCHE_ACHAT.search(texte) and not MOTIF_SIGNAL_VENTE.search(texte):
        return False
    return True
