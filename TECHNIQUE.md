# Documentation technique

Détails d'implémentation, API Sunology Stream, développement et releases de l'intégration. Pour l'installation et l'utilisation, voir le [README](README.md).

## Fonctionnement de l'intégration

- **Données** : l'intégration interroge l'API cloud `backend-mobile.stream.sunology.eu` (`iot_class: cloud_polling`). La vue d'ensemble (`/api/overview`) est relue toutes les 30 s.
- **Nouveaux panneaux** : les entités d'un panneau sont créées dès qu'il figure dans l'overview, ses diagnostics dès que ses détails (`/api/solar-panels/{id}`) sont récupérés. Un rafraîchissement immédiat est déclenché quand un nouveau panneau apparaît.
- **Heures creuses/pleines** : calculées à partir de `energyAmountsAndCostsForDay`, qui ne renvoie que les heures terminées. Juste après minuit, l'endpoint répond 500 tant qu'aucune heure n'est terminée : les capteurs gardent alors le total complet de la veille, tranche 23h-minuit comprise.
- **Coûts** : kWh de chaque tarif × prix unitaire Selectra (`/selectra/planning/details`). À défaut, l'intégration utilise les coûts horaires de l'API, dont les prix sont arrondis au centime.
- **Rafraîchissement des prix Selectra** : à leur date `next_update`, quand le contrat change dans l'appli, et au moins une fois par jour.
- **Tableau de bord Énergie** : les capteurs de coût sont en `state_class: total` avec un `last_reset` sur le jour affiché. Le « prix actuel » suit le calendrier `/selectra/planning/prices`.
- **Version minimale de Home Assistant** : 2024.6, pour le pattern `entry.runtime_data` (déclarée dans `hacs.json`). Testé sur 2026.6.

## API Sunology Stream

L'application mobile Sunology Stream n'a pas d'API publique documentée. Les endpoints ci-dessous ont été identifiés par rétro-ingénierie du code JavaScript de l'application Android (Capacitor/Ionic), en septembre 2026.

Base URL : `https://backend-mobile.stream.sunology.eu`

### Authentification

Authentification par cookie de session (pas de token Bearer).

- `POST /api/login-post` — body `{"username": "<email>", "password": "<mot de passe>"}`
- `POST /api/logout`
- `GET /api/users/me` — profil de l'utilisateur connecté (sert aussi de vérification de session)

`/api/users/authenticated`, référencé dans le code JS de l'appli, n'existe pas côté serveur (404 confirmé).

### Endpoints de données

- `GET/PUT /api/client` — profil client (flags `hasGridStreamMeter`, `hasErl`, `hasStorageBattery`)
- `GET /api/devices/stations-and-storages`
- `GET /api/devices/accessories`
- `GET /api/stream-meter`
- `GET /api/storage-battery/all-paired`, `GET /api/storage-battery/{id}`
- `GET /api/solar-panels/{id}` — `id` = identifiant d'appareil (pas le numéro de série), obtenu via `/devices/stations-and-storages`. Renvoie `firmwareVersion`, `rssiWifi` (dBm), `lastSynchronizationDate`, `state`, `batteryThreshold` (seuil de déclenchement de la charge, 210-450 W) et `batteryPreserveEnergy` (option « nomade » : pas de décharge pendant 18 h).
- `GET /api/erl`
- `GET /api/irradiance[-forecast]`, `POST /api/irradiance/history`
- `GET /api/history/{timeScale}/{date}?zone=` — `timeScale` : `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`, `INFINITY`. Renvoie productions/consommations horaires du jour en Wh (`wattValueSuffix.value`) + équivalent monétaire (`currency`, basé sur `kwhRate` du profil client) + taux d'autonomie (`selfReliance`).
- `GET /api/client/energyAmountsAndCostsForDay?zone=&day=` — `day` = minuit local en ISO UTC (`2026-09-25T22:00:00.000Z`). Par heure terminée (clé = heure UTC) : `consumptionInKWh`/`consumptionInEuros`, `productionInKWh`, `energySoldInKWh`, `dischargeInKWh`, et `priceCentsPerKWh` (tarif HC/HP du contrat, au prorata pour les heures à cheval sur un changement de tarif). Renvoie une 500 tant qu'aucune heure du jour n'est terminée (juste après minuit), puis les 24 heures du jour, à 0 pour celles qui ne sont pas terminées.
- `GET /api/client/clientSignedContract` — contrat d'électricité saisi dans l'appli (Paramètres > Tarifs énergie). `config` : `pdl`, `offer_name`, `option_name`, `off_peak_hours` (plages d'heures creuses, coupées à minuit), `distributor_name`, et des identifiants (`power_id`, `provider_id`…) dont les libellés (« 9 kVA », « EDF »…) sont dans `questionsForSelectra.<champ>.options`.
- `POST /api/selectra/planning/details` — corps : `config` du contrat. Fiche tarifaire Selectra : offre, option, `features` (prix au kWh par période, `key` « price kwh hc » / « price kwh hp », abonnement), heures creuses Enedis actuelles et à venir (`distributor_off_peak_hours`). Une lecture, que l'appli appelle à l'affichage des tarifs.
- `POST /api/selectra/planning/prices` — corps : `config` du contrat. Calendrier des prix à venir (`prices` : `start`, `end`, `name`, `price`), `currency`, `next_update`.
- `GET /api/client/electricityCosts?zone=` — cumuls achetés/produits/économisés en kWh et en euros.
- `POST /api/overview`

### Paramètre `zone`

Décalage UTC **en heures**, comme l'envoie l'appli (`-(new Date().getTimezoneOffset()) / 60`, soit `2` en heure d'été et `1` en hiver). `+02:00` est rejeté (400). `+0200` est accepté mais mal interprété : l'historique couvre alors plusieurs jours et la consommation est décalée d'environ 30 h, et `energyAmountsAndCostsForDay`/`electricityCosts` répondent 500.

Avec le bon `zone`, la consommation horaire issue de la TIC correspond à la courbe de charge Enedis à ~0,1 % près par jour (vérifié sur 7 jours via MyElectricalData).

Les formes JSON réelles ont été capturées avec `scripts/probe.py` contre un vrai compte (voir [Développement](#développement)). Les réponses ne sont pas commitées (données personnelles) mais servent à valider le parsing des entités.

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

### Tests

```bash
scripts/test
```

Suite pytest ciblée (pas de couverture exhaustive façon HA core) : `api.py` (logique HTTP/retry/erreurs, mockée avec `aioresponses`, aucun appel réseau réel) et l'extraction de données du coordinator/sensor, testée contre des fixtures réelles anonymisées (`tests/fixtures/`, dérivées de captures `scripts/probe.py` avec les données personnelles retirées). Pas de tests sur `config_flow.py` — nécessiterait `pytest-homeassistant-custom-component`, jugé disproportionné pour ce projet (la version actuelle de ludeeus/integration_blueprint a d'ailleurs abandonné cette approche).

## Releases

Le versioning (`manifest.json`) suit [SemVer](https://semver.org/) et est bumpé automatiquement par `.forgejo/workflows/release.yml` à chaque push sur `main`, à partir des messages de commit [Conventional Commits](https://www.conventionalcommits.org/) :

- `feat: ...` → minor
- `fix: ...` / `perf: ...` → patch
- `BREAKING CHANGE:` en pied de message, ou `!` avant le `:` (ex. `feat!: ...`) → major
- tout le reste (`docs:`, `chore:`, `refactor:`, `test:`, ...) ne déclenche pas de release

Le workflow calcule la version suivante (`scripts/bump_version.py`), met à jour `manifest.json`, commit (`chore(release): vX.Y.Z`, avec un garde-fou pour ne pas se re-déclencher lui-même), tag, et crée une release Forgejo via l'API (`scripts/create_release.py`). Prérequis côté instance : un runner Forgejo Actions enregistré, avec le token par défaut autorisé en écriture sur le dépôt (`permissions: contents: write`).

Prévisualiser la prochaine version sans rien modifier :

```bash
python scripts/bump_version.py --dry-run
```

### Miroir GitHub et HACS

Le dépôt principal est sur Forgejo (`brokk.xaoimoon.fr`) ; [github.com/Xaoimoon/ha-sunology-stream](https://github.com/Xaoimoon/ha-sunology-stream) en est un miroir (push mirror Forgejo), nécessaire parce que HACS ne supporte que GitHub.

- Le miroir reçoit les commits et les tags, puis `.github/workflows/release.yml` crée une GitHub Release pour chaque tag `vX.Y.Z` : HACS s'appuie sur les releases et ignore les tags seuls.
- Forgejo ignore `.github/workflows` tant que `.forgejo/workflows` existe.
- GitHub ne déclenche aucun workflow quand plus de trois tags sont poussés d'un coup (cas de la première synchro du miroir) : créer alors les releases manquantes à la main, via **Actions > GitHub Release > Run workflow** avec le tag.
- `hacs.json` déclare le nom affiché dans HACS et la version minimale de Home Assistant.
