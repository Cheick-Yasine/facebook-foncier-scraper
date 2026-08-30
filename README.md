# Facebook Foncier Scraper

Pipeline autonome pour scraper les groupes Facebook d’annonces foncières / immobilières à **Ouagadougou** (Burkina Faso).

Inspiré du modèle Actor (input clair → exécution → sortie structurée), **sans** dépendance à Apify.

## Fonctionnalités

- Mode mobile (`m.facebook.com`) + fingerprint Android stable par compte
- Extraction JSON Comet (posts mis en avant + scroll GraphQL)
- Multi-comptes (`accountId` 1–5)
- Proxy custom (résidentiel recommandé)
- Filtrage regex niveau 1 (candidats fonciers)
- Sortie JSON dans `data/processed/`
- CLI simple + fichier d’input JSON optionnel

## Structure

```text
facebook-foncier-scraper/
├── src/
│   ├── __main__.py      # python -m src
│   ├── main.py          # CLI / orchestration
│   ├── config.py        # groupes, fingerprints, regex
│   └── scraper.py       # Playwright + extraction Comet
├── groups.csv
├── input.example.json
├── pyproject.toml       # deps gérées avec uv
└── requirements.txt     # miroir optionnel
```

## Installation (uv)

Prérequis : [uv](https://docs.astral.sh/uv/) installé.

```bash
git clone https://github.com/Cheick-Yasine/facebook-foncier-scraper.git
cd facebook-foncier-scraper

# Python 3.12 (évite 3.14 : pas encore de wheels Playwright/greenlet)
uv python install 3.12
uv sync --python 3.12

# Navigateur Playwright
uv run playwright install chromium
```

> **Important :** le projet impose `requires-python = ">=3.11,<3.14"`.  
> Ne pas utiliser Python 3.14 pour l’instant.

## Utilisation

### Option A – arguments CLI

```bash
uv run python -m src \
  --cookies-file cookies.json \
  --group-limit 1 \
  --days-back 1 \
  --account 1 \
  --proxy "http://user:pass@host:port"
```

### Option B – fichier d’input (style Actor)

```bash
cp input.example.json input.json
# Éditer input.json (cookies, proxyUrl, groupLimit…)

uv run python -m src --input input.json
```

### Variables d’environnement (alternative)

```bash
export FB_COOKIES_JSON='[...]'          # ou FB_COOKIES_JSON_1
export PROXY_URL='http://user:pass@host:port'
uv run python -m src --group-limit 1 --account 1
```

## Paramètres principaux

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| `--mode` | `daily` ou `backfill` | `daily` |
| `--days-back` | Jours à remonter | `1` |
| `--group-limit` | Max groupes (`0` = tous) | `0` |
| `--account` | Compte `1`…`5` | vide |
| `--cookies-file` | Fichier JSON cookies FB | — |
| `--proxy` | URL proxy | — |
| `--output-dir` | Dossier de sortie | `data/processed` |

## Sortie

Fichier JSON horodaté dans `data/processed/annonces_YYYYMMDDTHHMMSSZ.json`.

Chaque objet contient notamment : `id`, `groupe_id`, `groupe_nom`, `url`, `texte`, `date_publication`, `scrape_le`.

## Statut

| Composant | État |
|-----------|------|
| CLI autonome (sans Apify) | ✅ |
| Gestion deps avec uv | ✅ |
| Scraper Playwright mobile | ✅ |
| Extraction Comet + scroll | ✅ |
| Filtrage foncier regex | ✅ |
| Multi-comptes + groups.csv | ✅ |
| Proxy custom | ✅ |
| Enrichissement LLM | ⏳ |
| Persistance seen_ids | ⏳ |
| GitHub Actions / cron | ⏳ |

## Repo précédent

[ouaga-foncier-etl](https://github.com/Cheick-Yasine/ouaga-foncier-etl)

## Avertissement

L’automatisation de Facebook contrevient aux CGU de Meta. Compte dédié recommandé.
