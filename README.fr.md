<p align="center">
  <img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

🇬🇧 [English](README.md) · 🇫🇷 **Français**

# Alert Manager pour Home Assistant

**Repérez les problèmes de votre maison — et suivez-les jusqu’à leur résolution.**

Équipements indisponibles, batteries faibles, automatisations en erreur ou valeurs
anormales : Alert Manager rassemble les problèmes dans un seul panneau, avec des
notifications, une carte de dashboard et un historique.

[Documentation](docs/user-guide.md) ·
[Signaler un problème](https://github.com/zoic21/ha_alert_manager/issues)

<p align="center">
  <img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/dashboard.png" alt="Accueil Alert Manager avec les alertes en cours">
</p>

## Ce que vous pouvez faire

- **Surveiller les problèmes courants.** Détectez les entités indisponibles, pertes
  de connexion, batteries faibles, équipements UniFi absents, mises à jour disponibles,
  erreurs d’automatisation/script et instabilités répétées.
- **Créer vos propres règles.** Surveillez une température, une consommation anormale,
  un capteur qui ne change plus ou la fin d’un cycle d’appareil. Utilisez l’éditeur
  visuel ou le YAML.
- **Suivre chaque alerte.** Consultez les alertes actives, à venir et acquittées,
  leur chronologie et leurs occurrences passées. Acquitter une alerte indique que
  vous en avez connaissance, sans considérer le problème comme résolu.
- **Choisir vos notifications.** Sélectionnez les alertes par étiquette, avec des
  rappels, des messages groupés et des notifications informatives facultatives.
- **Afficher les alertes sur votre dashboard.** La carte intégrée les regroupe par
  équipement et accepte du CSS personnalisé.
- **Retrouver les références cassées.** Consultez les renommages d’entités et
  prévisualisez les remplacements avant de les appliquer.

L’interface est disponible en **français et en anglais**, sur ordinateur et mobile.

## Installation

Nécessite **Home Assistant 2026.8 ou ultérieur**.

1. Dans **HACS**, recherchez et installez **Alert Manager**.
2. Redémarrez Home Assistant.
3. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration**, puis
   recherchez **Alert Manager**.

Le panneau apparaît dans la barre latérale. Ouvrez **Configuration → Surveillance
automatique** pour vérifier les packs activés et leurs délais, puis ajoutez des
règles ou des profils de notification selon vos besoins.

**Mise à jour :** mettez à jour depuis HACS, redémarrez Home Assistant et actualisez
votre navigateur.

<details>
<summary>Installation manuelle</summary>

Copiez `custom_components/alert_manager` dans `/config/custom_components/alert_manager`,
redémarrez Home Assistant, puis ajoutez **Alert Manager** depuis
**Paramètres → Appareils et services**.

</details>

### Ajouter la carte de dashboard

Choisissez **Alert Manager** dans le sélecteur de cartes du dashboard. La carte est
incluse avec l’intégration ; actualisez votre navigateur après une installation ou
une mise à jour.

## Documentation

Les guides détaillés sont maintenus **en anglais** :

| Guide | Pour… |
| --- | --- |
| [Règles personnalisées](docs/custom-rules.md) | Créer des règles, séquences et conditions Jinja, avec des exemples. |
| [Configuration](docs/configuration.md) | Régler la surveillance, les notifications, les sauvegardes et les diagnostics. |
| [Cohérence de la configuration](docs/coherence.md) | Vérifier les références, consulter les renommages, appliquer des remplacements et exporter les entités. |
| [Dashboard et historique](docs/dashboard-and-history.md) | Configurer la carte, acquitter les alertes et explorer l’historique. |

L’[index de documentation](docs/user-guide.md) propose aussi les tâches courantes.
Pour une version installée, sélectionnez son tag de release sur GitHub.

<details>
<summary><strong>Voir plus de captures</strong></summary>

### Carte de dashboard

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/card.png" alt="Carte de dashboard compacte Alert Manager">

### Configuration de la carte

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/card%20configuration.png" alt="Éditeur visuel de la carte de dashboard">

### Alertes à venir

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/incomming.png" alt="Alertes en attente de leur délai de déclenchement">

### Détails et chronologie d’une alerte

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/alert.png" width="596" alt="Détails d’une alerte avec les étapes de séquence et les notifications">

### Règles personnalisées

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/regle%20personalis%C3%A9e.png" alt="Règles personnalisées Alert Manager">

### Séquences

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/sequence.png" width="574" alt="Éditeur de séquence avec étapes repliables">

### Profils de notification

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/notification.png" width="572" alt="Profil de notification avec exceptions standard et informative">

### Cohérence de la configuration

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/coherence.png" alt="Vérifications de cohérence de la configuration">

### Configuration

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/configuration.png" alt="Configuration Alert Manager">

</details>

Tous les utilisateurs connectés peuvent consulter la carte, l’Accueil et l’Historique.
La configuration et les actions, dont l’acquittement, nécessitent un administrateur.
Une seule instance d’Alert Manager est prise en charge par installation Home Assistant.

Une question ou une idée ? [Ouvrez une issue GitHub](https://github.com/zoic21/ha_alert_manager/issues).

Alert Manager est une intégration communautaire non officielle, sans affiliation
avec Home Assistant. Ce code a été écrit en partie avec l’aide de l’IA.
