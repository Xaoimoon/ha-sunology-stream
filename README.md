# ha-sunology-stream

Intégration Home Assistant (non officielle) pour les panneaux solaires et le lecteur TIC Sunology Stream, via l'API cloud `backend-mobile.stream.sunology.eu`.

## Statut

🚧 En développement — fonctionnel en usage basique (config flow, capteurs de puissance/énergie/ERL), testé en conditions réelles via le devcontainer. Pas encore publié/packagé pour HACS.

## Contexte

L'application mobile Sunology Stream n'a pas d'API publique documentée. Les endpoints ci-dessous ont été identifiés par rétro-ingénierie du code JavaScript de l'application Android (Capacitor/Ionic), en septembre 2026.

### Authentification

Authentification par cookie de session (pas de token Bearer).

- `POST /api/login-post` — body `{"username": "<email>", "password": "<mot de passe>"}`
- `POST /api/logout`
- `GET /api/users/me` — profil de l'utilisateur connecté (sert aussi de vérification de session)

`/api/users/authenticated`, référencé dans le code JS de l'appli, n'existe pas côté serveur (404 confirmé).

Base URL : `https://backend-mobile.stream.sunology.eu`

### Endpoints de données

- `GET/PUT /api/client` — profil client (flags `hasGridStreamMeter`, `hasErl`, `hasStorageBattery`)
- `GET /api/devices/stations-and-storages`
- `GET /api/devices/accessories`
- `GET /api/stream-meter`
- `GET /api/storage-battery/all-paired`, `GET /api/storage-battery/{id}`
- `GET /api/solar-panels/{id}`
- `GET /api/erl`
- `GET /api/irradiance[-forecast]`, `POST /api/irradiance/history`
- `GET /api/history/{timeScale}/{date}?zone=` — `timeScale` confirmé : `DAILY`. `zone` doit être un `ZoneOffset` Java au format compact **sans deux-points** (`+0200`, pas `+02:00`, pas de nom IANA type `Europe/Paris` — tout ça est rejeté avec 400). Renvoie productions/consommations du jour en Wh (`wattValueSuffix.value`) + équivalent monétaire (`currency`, basé sur `kwhRate` du profil client) + taux d'autonomie (`selfReliance`).
- `POST /api/overview`

Les formes JSON réelles ont été capturées avec `scripts/probe.py` contre un vrai compte (voir section Développement) — les réponses ne sont pas commitées (données personnelles) mais servent à valider le parsing des entités.

## Installation

Pas encore prêt pour une installation via HACS ou manuelle. Copier `custom_components/sunology_stream` dans le dossier `custom_components` de votre installation Home Assistant une fois l'intégration fonctionnelle.

## Développement

Un devcontainer VS Code est fourni (inspiré de [ludeeus/integration_blueprint](https://github.com/ludeeus/integration_blueprint), le modèle de référence pour le développement d'intégrations HA custom) :

1. Ouvrir le repo dans VS Code avec l'extension **Dev Containers**, puis "Reopen in Container" (installe `homeassistant` + dépendances via `scripts/setup`).
2. Lancer `scripts/develop` — crée un dossier `config/` de dev (gitignored) et démarre Home Assistant avec l'intégration chargée, sur `http://localhost:8123`.
3. Compléter le config flow avec un vrai compte Sunology Stream depuis l'UI.

Pour capturer/rafraîchir les vraies formes de réponse API (hors HA, script autonome) :

```bash
cp .env.example .env   # renseigner SUNOLOGY_USERNAME / SUNOLOGY_PASSWORD
python scripts/probe.py
```

Les réponses sont sauvegardées dans `dev/fixtures/` (gitignored, contient des données personnelles).

## Avertissement

Projet non affilié à Sunology. Basé sur une API non documentée susceptible de changer sans préavis.

## Licence

MIT — voir [LICENSE](LICENSE).
