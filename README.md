# ha-sunology-stream

Intégration Home Assistant (non officielle) pour les panneaux solaires et le lecteur TIC Sunology Stream, via l'API cloud `backend-mobile.stream.sunology.eu`.

## Statut

🚧 En développement — fonctionnel en usage basique (config flow, capteurs de puissance/énergie/ERL, consommation du jour en heures creuses/pleines et son coût, diagnostics par panneau : WiFi, firmware, dernière synchro, seuil et mode de la batterie), testé en conditions réelles via le devcontainer. Pas encore publié/packagé pour HACS.

Les entités sont regroupées par appareil :
- **Installation Sunology** (un par compte) : puissance de production totale, énergie produite du jour, taux d'autonomie ;
- **Lecteur TIC Linky** (si le compte a un ERL) : puissances de consommation et d'achat au réseau, énergie consommée du jour, heures creuses/pleines, coûts, état et dernière synchro de l'ERL ;
- **un appareil par panneau** (modèle, n° de série, firmware) : production, batterie, diagnostics.

Le Lecteur TIC Linky et les panneaux sont reliés à l'Installation Sunology. Sans ERL, les capteurs de consommation restent sur l'appareil Installation Sunology.

Les capteurs heures creuses/pleines ne sont créés que si le compte a un lecteur TIC (ERL) et un contrat HP/HC renseigné dans l'appli. Ils sont calculés par heure terminée, donc avec jusqu'à une heure de retard. Entre minuit et la fin de la première heure, ils affichent encore le total complet de la veille, tranche 23h-minuit comprise, puis repartent de zéro : aucune heure n'est perdue. Les capteurs de coût sont en `state_class: total` avec un `last_reset` sur le jour affiché, donc utilisables comme « entité suivant les coûts totaux » dans le tableau de bord Énergie.

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
- `GET /api/solar-panels/{id}` — `id` = identifiant d'appareil (pas le numéro de série), obtenu via `/devices/stations-and-storages`. Renvoie `firmwareVersion`, `rssiWifi` (dBm), `lastSynchronizationDate`, `state`, `batteryThreshold` (seuil de déclenchement de la charge, 210-450 W) et `batteryPreserveEnergy` (option « nomade » : pas de décharge pendant 18 h).
- `GET /api/erl`
- `GET /api/irradiance[-forecast]`, `POST /api/irradiance/history`
- `GET /api/history/{timeScale}/{date}?zone=` — `timeScale` : `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`, `INFINITY`. Renvoie productions/consommations horaires du jour en Wh (`wattValueSuffix.value`) + équivalent monétaire (`currency`, basé sur `kwhRate` du profil client) + taux d'autonomie (`selfReliance`).
- `GET /api/client/energyAmountsAndCostsForDay?zone=&day=` — `day` = minuit local en ISO UTC (`2026-09-25T22:00:00.000Z`). Par heure terminée (clé = heure UTC) : `consumptionInKWh`/`consumptionInEuros`, `productionInKWh`, `energySoldInKWh`, `dischargeInKWh`, et `priceCentsPerKWh` (tarif HC/HP du contrat, au prorata pour les heures à cheval sur un changement de tarif). Renvoie une 500 tant qu'aucune heure du jour n'est terminée (juste après minuit), puis les 24 heures du jour, à 0 pour celles qui ne sont pas terminées.
- `GET /api/client/clientSignedContract` — contrat d'électricité (offre, option, puissance, `off_peak_hours` : plages d'heures creuses).
- `GET /api/client/electricityCosts?zone=` — cumuls achetés/produits/économisés en kWh et en euros.
- `POST /api/overview`

**Paramètre `zone`** : décalage UTC **en heures**, comme l'envoie l'appli (`-(new Date().getTimezoneOffset()) / 60`, soit `2` en heure d'été et `1` en hiver). `+02:00` est rejeté (400). `+0200` est accepté mais mal interprété : l'historique couvre alors plusieurs jours et la consommation est décalée d'environ 30 h, et `energyAmountsAndCostsForDay`/`electricityCosts` répondent 500.

Avec le bon `zone`, la consommation horaire issue de la TIC correspond à la courbe de charge Enedis à ~0,1 % près par jour (vérifié sur 7 jours via MyElectricalData).

Les formes JSON réelles ont été capturées avec `scripts/probe.py` contre un vrai compte (voir section Développement) — les réponses ne sont pas commitées (données personnelles) mais servent à valider le parsing des entités.

## Installation

Manuelle uniquement (pas de HACS — ce dépôt est hébergé sur Forgejo, or HACS ne supporte que les dépôts GitHub, même en "dépôt personnalisé") :

1. Repérer le dossier de configuration de votre installation Home Assistant (celui qui contient `configuration.yaml`).
2. Y créer un dossier `custom_components` s'il n'existe pas déjà.
3. Copier le dossier `custom_components/sunology_stream` de ce dépôt dedans, pour obtenir `<config>/custom_components/sunology_stream/`.
4. Redémarrer Home Assistant (obligatoire — les intégrations custom ne sont chargées qu'au démarrage).
5. **Paramètres > Appareils et services > Ajouter une intégration**, chercher "Sunology Stream", et se connecter avec son compte.

Si l'intégration n'apparaît pas dans la recherche après redémarrage, vérifier les logs (**Paramètres > Système > Journaux**) pour une erreur de chargement — le cas le plus probable est une version de Home Assistant trop ancienne (l'intégration utilise le pattern `entry.runtime_data`, disponible depuis HA 2024.6).

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

### Releases

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

## Avertissement

Projet non affilié à Sunology. Basé sur une API non documentée susceptible de changer sans préavis.

## Licence

MIT — voir [LICENSE](LICENSE).
