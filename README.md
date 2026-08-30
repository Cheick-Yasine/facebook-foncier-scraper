# Facebook Foncier Scraper

**Apify Actor** pour scraper les groupes Facebook d’annonces foncières / immobilières à **Ouagadougou** (Burkina Faso).

Construit avec le **SDK Apify Python** + **Playwright** (mode mobile).

## Fonctionnalités

- Mode mobile (`m.facebook.com`) + fingerprint Android stable par compte
- Extraction JSON Comet (posts mis en avant + scroll GraphQL)
- Multi-comptes (`accountId` 1–5, isolation cookies / groupes)
- Proxy Apify ou custom (résidentiel recommandé)
- Filtrage regex niveau 1 (candidats fonciers)
- Output structuré dans le **Dataset** Apify
- Input schema prêt pour la Console Apify

## Structure

```text
facebook-foncier-scraper/
├── .actor/
│   ├── actor.json
│   ├── input_schema.json
│   └── dataset_schema.json
├── src/
│   ├── __main__.py
│   ├── main.py          # point d’entrée Actor
│   ├── config.py        # groupes, fingerprints, regex
│   └── scraper.py       # Playwright + extraction Comet
├── groups.csv           # liste des groupes cibles
├── Dockerfile
└── requirements.txt
```

## Démarrage rapide (local)

```bash
# CLI Apify (une fois)
npm install -g apify-cli

git clone https://github.com/Cheick-Yasine/facebook-foncier-scraper.git
cd facebook-foncier-scraper

pip install -r requirements.txt
playwright install chromium

# Créer un input local
mkdir -p storage/key_value_stores/default
cat > storage/key_value_stores/default/INPUT.json << 'EOF'
{
  "mode": "daily",
  "daysBack": 1,
  "groupLimit": 1,
  "accountId": "1",
  "cookies": "[...vos cookies Facebook en JSON...]"
}
EOF

apify run
```

## Input principal

| Champ | Description | Défaut |
|-------|-------------|--------|
| `mode` | `daily` ou `backfill` | `daily` |
| `daysBack` | Jours à remonter | `1` |
| `groupLimit` | Max groupes (0 = tous) | `0` |
| `accountId` | Compte "1"…"5" | vide |
| `cookies` | Cookies FB (JSON array) | **requis** |
| `proxyConfiguration` | Proxy Apify / custom | aucun |
| `skipLlm` | (réservé) | `false` |

Les cookies peuvent aussi être fournis via `FB_COOKIES_JSON` ou `FB_COOKIES_JSON_<n>` (env).

## Proxy

**Fortement recommandé** (les IP GitHub Actions / datacenter sont souvent bloquées).

- Via l’input `proxyConfiguration` (Apify Proxy)
- Ou variables d’env : `PROXY_URL` / `PROXY_URL_1` … `PROXY_URL_5`

Format : `http://user:pass@host:port`

Variables associées (optionnel) :
- `PROXY_COUNTRY_1=BF` (ou `FR`)
- `BROWSER_LOCALE_1=fr-FR`
- `BROWSER_TIMEZONE_1=Africa/Ouagadougou`

## Output

Chaque item du Dataset contient notamment :

- `id`, `groupe_id`, `groupe_nom`, `url`
- `texte`, `date_publication`, `scrape_le`
- (champs structurés LLM à venir : prix, surface, quartier…)

## Statut

| Composant | État |
|-----------|------|
| Structure Actor Apify | ✅ |
| Scraper Playwright mobile | ✅ migré |
| Extraction Comet + scroll | ✅ |
| Filtrage foncier regex | ✅ |
| Multi-comptes + groups.csv | ✅ |
| Proxy Apify / custom | ✅ |
| Enrichissement LLM (OpenAI) | ⏳ à brancher |
| Persistance seen_ids (KV store) | ⏳ à brancher |
| Écriture PostgreSQL | ⏳ optionnel |

## Repo précédent

[ouaga-foncier-etl](https://github.com/Cheick-Yasine/ouaga-foncier-etl) – pipeline GitHub Actions d’origine.

## Avertissement

L’automatisation de Facebook contrevient aux CGU de Meta. Utilisez un compte dédié, respectez les données personnelles, et assumez les risques de ban.
