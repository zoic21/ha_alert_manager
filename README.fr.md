<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <a href="README.md">English</a> · 🇫🇷 <strong>Français</strong>
</p>

# Alert Manager pour Home Assistant

**Savoir quand quelque chose ne va pas — et garder le problème visible jusqu’à sa résolution.**

Alert Manager rassemble les problèmes de Home Assistant : équipements indisponibles, batteries faibles, automatisations en erreur, valeurs anormales ou références cassées dans la configuration. Chaque alerte est suivie de sa détection à sa résolution, plutôt que de se limiter à une notification facile à manquer.

[Installation](#installation) · [Guide utilisateur](docs/user-guide.fr.md) · [Signaler un problème](https://github.com/zoic21/ha_alert_manager/issues)

<p align="center">
  <img src="docs/assets/screenshots/dashboard.png" alt="Accueil Alert Manager avec les alertes en cours">
</p>

## Fonctionnalités

| Domaine | Possibilités |
| --- | --- |
| Surveillance automatique | Détecter les entités indisponibles, pertes de connectivité, batteries faibles, équipements UniFi absents, erreurs d’automatisation ou de script et instabilités répétées. Configurer les réglages et exceptions par équipement/entité dans chaque pack, avec des exclusions globales par étiquette. |
| Règles personnalisées | Surveiller états, attributs, seuils, plages, absence de changement, variations, transitions et conditions Jinja. Générer depuis des blueprints, éditer visuellement ou en YAML, dupliquer et tester sur les valeurs réelles, avec les profils de notification correspondants. |
| Gestion des alertes | Rechercher, filtrer et regrouper les alertes ; les acquitter sans limite ou temporairement ; consulter leurs détails, notifications et occurrences précédentes. Explorer l’historique et les statistiques de récurrence. |
| Carte de dashboard | Afficher une vue compacte adaptée au mobile, regroupée par équipement, avec filtre par étiquette, limite de tuiles, alignement et couleur des icônes. La carte se masque sans alerte correspondante et ouvre les détails au clic. |
| Notifications | Configurer des profils facultatifs avec plusieurs destinataires, nouvelles alertes, retours à la normale, rappels, regroupement et exceptions ordonnées par étiquette. Éditer en YAML, dupliquer ou envoyer un test. |
| Cohérence de la configuration | Retrouver les références statiques vers des entités absentes et les références d’appareils ZHA invalides, analyser à la demande ou selon un planning, et créer une alerte pour les problèmes non résolus. |
| Configuration et automatisations | Utiliser les étiquettes Home Assistant, l’import/export YAML, les sauvegardes automatiques de configuration, les entités de surveillance et les événements pour vos propres automatisations. |

L’interface est disponible en **français et en anglais**, sur ordinateur et mobile. Tous les utilisateurs connectés peuvent consulter la carte, l’Accueil et l’Historique ; la configuration et toutes les actions, dont l’acquittement, sont réservées aux administrateurs.

<details>
<summary><strong>Voir plus de captures</strong></summary>

### Carte de dashboard

<img src="docs/assets/screenshots/card.png" alt="Carte de dashboard compacte Alert Manager">

### Alertes à venir

<img src="docs/assets/screenshots/incomming.png" alt="Alertes en attente de leur délai de déclenchement">

### Historique

<img src="docs/assets/screenshots/history.png" alt="Historique des alertes et filtres">

### Règles personnalisées

<img src="docs/assets/screenshots/regle%20personalis%C3%A9e.png" alt="Règles personnalisées Alert Manager">

### Cohérence de la configuration

<img src="docs/assets/screenshots/coherence.png" alt="Résultats de l’analyse de cohérence">

### Configuration

<img src="docs/assets/screenshots/configuration.png" alt="Configuration Alert Manager">

</details>

## Installation

Nécessite **Home Assistant 2026.8 ou ultérieur**. Une seule instance d’Alert Manager est prise en charge par installation Home Assistant.

### HACS

1. Dans **HACS → Dépôts personnalisés**, ajoutez `https://github.com/zoic21/ha_alert_manager` avec la catégorie **Integration**.
2. Installez **Alert Manager**, puis redémarrez Home Assistant.
3. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration**, puis recherchez **Alert Manager**.

Le panneau apparaît dans la barre latérale de Home Assistant. Aucune configuration YAML n’est nécessaire.

<details>
<summary>Installation manuelle</summary>

Copiez `custom_components/alert_manager` dans `/config/custom_components/alert_manager`, redémarrez Home Assistant, puis ajoutez **Alert Manager** depuis **Paramètres → Appareils et services**.

</details>

### Ajouter la carte de dashboard

Choisissez **Alert Manager** dans le sélecteur de cartes du dashboard. Aucune installation frontend séparée ni ressource Lovelace manuelle n’est nécessaire ; actualisez le navigateur après une installation ou une mise à jour.

```yaml
type: custom:alert-manager-card
max_tiles: 5
alignment: left
```

## Utilisation

Commencez dans **Configuration → Surveillance automatique**, adaptez les packs activés et leurs délais, puis ajoutez des règles personnalisées pour les situations propres à votre installation. Les profils de notification sont facultatifs ; vos automatisations basées sur les événements restent utilisables.

Le **[guide utilisateur](docs/user-guide.fr.md)** détaille les exemples de règles, transitions, options de la carte et comportement au démarrage, notifications, acquittement temporaire, statistiques historiques, analyses de cohérence, YAML et récupération. Un **[guide en anglais](docs/user-guide.md)** est également disponible.

Pour les règles générées, consultez la **[documentation des blueprints](docs/blueprints/README.md)** et le **[guide de contribution](docs/rule-blueprints.md)**, en anglais.

Questions, bugs et idées de surveillance sont les bienvenus dans les **[issues GitHub](https://github.com/zoic21/ha_alert_manager/issues)**.

Alert Manager est une intégration communautaire non officielle, sans affiliation avec Home Assistant. Ce code a été écrit en partie avec l’aide de l’IA.
