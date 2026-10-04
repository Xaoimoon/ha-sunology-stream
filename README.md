# Sunology Stream pour Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)
[![Installations actives](https://img.shields.io/badge/dynamic/json?style=for-the-badge&color=41BDF5&label=Active%20installations&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.sunology_stream.total)](https://analytics.home-assistant.io/)
[![Release](https://img.shields.io/github/v/release/Xaoimoon/ha-sunology-stream?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/releases)
[![Licence](https://img.shields.io/github/license/Xaoimoon/ha-sunology-stream?style=for-the-badge)](LICENSE)

[![Maintenu](https://img.shields.io/badge/maintained-yes-green.svg?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/commits/main)
[![Activité](https://img.shields.io/github/commit-activity/y/Xaoimoon/ha-sunology-stream?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/commits/main)

Intégration Home Assistant (non officielle) pour les panneaux solaires Sunology Stream et le lecteur TIC Linky. Elle affiche dans Home Assistant les mêmes informations que l'application Sunology Stream : production solaire, consommation du foyer, heures creuses et pleines, coûts et état des panneaux.

## Fonctionnalités

- Production solaire en temps réel et énergie produite du jour, au total et par panneau.
- Consommation du foyer et achat au réseau, si vous avez un lecteur TIC Linky.
- Consommation du jour en heures creuses et heures pleines, et son coût.
- Prix de l'électricité de votre contrat : heures creuses, heures pleines et prix actuel.
- Batterie et état de chaque panneau : WiFi, firmware, dernière synchronisation, seuil de charge, mode nomade.
- Compatible avec le tableau de bord Énergie de Home Assistant.

## Installation

### Via HACS (recommandé)

1. Dans HACS, menu **⋮ > Dépôts personnalisés**, ajouter `https://github.com/Xaoimoon/ha-sunology-stream` avec le type **Intégration**.
2. Rechercher "Sunology Stream" dans HACS, puis **Télécharger**.
3. Redémarrer Home Assistant.

HACS vous proposera ensuite automatiquement les nouvelles versions.

### Manuelle

1. Repérer le dossier de configuration de Home Assistant (celui qui contient `configuration.yaml`).
2. Y créer un dossier `custom_components` s'il n'existe pas déjà.
3. Copier le dossier `custom_components/sunology_stream` de ce dépôt dedans, pour obtenir `<config>/custom_components/sunology_stream/`.
4. Redémarrer Home Assistant.

## Configuration

1. **Paramètres > Appareils et services > Ajouter une intégration**.
2. Chercher "Sunology Stream".
3. Se connecter avec l'e-mail et le mot de passe du compte de l'application Sunology Stream.

Home Assistant Core 2024.6 ou plus récent est requis. Si l'intégration n'apparaît pas dans la recherche, consulter **Paramètres > Système > Journaux** : la cause la plus probable est une version de Home Assistant trop ancienne.

## Appareils et entités

L'intégration crée trois types d'appareils :

- **Installation Sunology** (un par compte) : puissance de production totale, énergie produite du jour, taux d'autonomie.
- **Lecteur TIC Linky** (si vous en avez un) :
  - puissance consommée et puissance achetée au réseau ;
  - énergie consommée du jour, dont heures creuses et heures pleines, et leur coût ;
  - prix heures creuses, heures pleines et prix actuel, en €/kWh ;
  - état et dernière synchronisation du lecteur ;
  - en diagnostic, le contrat renseigné dans l'application : PDL, offre, option tarifaire, puissance souscrite, plages d'heures creuses, fournisseur, gestionnaire de réseau.
- **Un appareil par panneau** (modèle, n° de série, firmware) : production, batterie et diagnostics.

Le lecteur TIC Linky et les panneaux sont rattachés à l'appareil Installation Sunology. Sans lecteur TIC Linky, les capteurs de consommation sont placés sur l'appareil Installation Sunology.

## Bon à savoir

### Heures creuses et heures pleines

- Ces capteurs n'apparaissent que si vous avez un lecteur TIC Linky **et** un contrat heures creuses / heures pleines renseigné dans l'application Sunology (**Paramètres > Tarifs énergie**).
- Ils sont mis à jour à la fin de chaque heure, donc avec jusqu'à une heure de retard.
- Entre minuit et 1 h, ils affichent encore le total de la veille, puis repartent de zéro. Aucune heure n'est perdue.
- Les coûts utilisent les prix de votre contrat, comme dans l'application, et suivent leurs changements.

### Tableau de bord Énergie

- Les capteurs de coût peuvent servir d'**entité suivant les coûts totaux**.
- Le capteur **Prix actuel** peut servir d'**entité avec le prix actuel**.

### Ajout et retrait de panneaux

- Un panneau ajouté dans l'application Sunology apparaît tout seul dans Home Assistant, en moins d'une minute, sans redémarrage.
- Un panneau retiré de l'application passe en « indisponible ». Vous pouvez alors supprimer son appareil depuis sa fiche dans Home Assistant. Les panneaux encore présents sur le compte ne peuvent pas être supprimés.
- Si un panneau supprimé de Home Assistant revient ensuite sur le compte, recharger l'intégration pour le faire réapparaître.

### Connexion internet

Les données passent par le cloud Sunology : l'intégration a besoin d'internet, et les valeurs sont celles que l'application affiche.

## Avertissement

Projet non affilié à Sunology. L'intégration repose sur une API non documentée qui peut changer sans préavis.

## Pour les développeurs

Le fonctionnement de l'API, l'environnement de développement, les tests et le processus de release sont décrits dans [TECHNIQUE.md](https://github.com/Xaoimoon/ha-sunology-stream/blob/main/TECHNIQUE.md).

## Licence

MIT — voir [LICENSE](LICENSE).
