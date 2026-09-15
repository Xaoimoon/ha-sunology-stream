# ha-sunology-stream

Intégration Home Assistant (non officielle) pour les panneaux solaires et le lecteur TIC Sunology Stream, via l'API cloud `backend-mobile.stream.sunology.eu`.

## Statut

🚧 En développement — pas encore fonctionnel.

## Contexte

L'application mobile Sunology Stream n'a pas d'API publique documentée. Les endpoints ci-dessous ont été identifiés par rétro-ingénierie du code JavaScript de l'application Android (Capacitor/Ionic), en septembre 2026.

### Authentification

Authentification par cookie de session (pas de token Bearer).

- `POST /api/login-post` — body `{"username": "<email>", "password": "<mot de passe>"}`
- `POST /api/logout`
- `GET /api/users/me` — profil de l'utilisateur connecté
- `GET /api/users/authenticated` — vérifie si la session est active

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
- `GET /api/history/{timeScale}/{date}?zone=`
- `POST /api/overview`

Le format exact des réponses JSON n'a pas encore été observé en clair — à documenter au fur et à mesure de l'implémentation.

## Installation

Pas encore prêt pour une installation via HACS ou manuelle. Copier `custom_components/sunology_stream` dans le dossier `custom_components` de votre installation Home Assistant une fois l'intégration fonctionnelle.

## Avertissement

Projet non affilié à Sunology. Basé sur une API non documentée susceptible de changer sans préavis.

## Licence

MIT — voir [LICENSE](LICENSE).
