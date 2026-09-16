<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <a href="README.md">English</a> · 🇫🇷 <strong>Français</strong>
</p>

# Alert Manager pour Home Assistant

**Savoir quand quelque chose ne va pas — et garder le problème visible jusqu’à sa résolution.**

Alert Manager rassemble les problèmes de Home Assistant : équipements indisponibles, batteries faibles, automatisations en erreur, valeurs anormales ou références cassées dans la configuration. Chaque alerte est suivie de sa détection à sa résolution, plutôt que de se limiter à une notification facile à manquer.

Utilisez la surveillance automatique pour les problèmes courants et les règles personnalisées pour vos équipements. Un problème reste visible tant qu’il nécessite votre attention ; l’acquitter indique que vous en avez connaissance, pas qu’il est corrigé. Les occurrences résolues peuvent être conservées dans l’historique pour repérer les problèmes récurrents.

[Installation](#installation) · [Documentation](docs/user-guide.md) · [Signaler un problème](https://github.com/zoic21/ha_alert_manager/issues)

<p align="center">
  <img src="docs/assets/screenshots/dashboard.png" alt="Accueil Alert Manager avec les alertes en cours">
</p>

## Possibilités

### Surveiller automatiquement les problèmes courants

Activez les packs d’entités indisponibles, pertes de connectivité, batteries faibles, équipements UniFi absents, erreurs d’exécution d’automatisation/script et instabilités répétées. Adaptez les délais, seuils et exclusions pour qu’une situation attendue ou une micro-coupure ne produise pas d’alertes inutiles.

Tout se configure depuis le panneau. Les étiquettes servent à organiser les alertes et sélectionner les notifications ; les entités de surveillance et événements restent disponibles pour vos propres automatisations.

### Définir des règles propres à votre installation

Surveillez un réfrigérateur consommant plus de 200 W pendant deux heures, une température hors plage, un chauffage sans hausse de température suffisante, un capteur qui ne change plus ou la fin d’un cycle d’appareil.

Les règles prennent en charge états, attributs imbriqués, comparaisons numériques et textuelles, absence de changement, variations, transitions, séquences ordonnées et conditions Jinja. Une règle peut surveiller plusieurs entités indépendamment. Le mode Séquence propose de 2 à 20 étapes réordonnables sur la même valeur : maintien continu « Au moins », validation à la sortie « Moins de » ou « Entre deux durées », et délai total facultatif. Dès le maintien de la première étape, la séquence apparaît dans les alertes à venir avec sa progression et les valeurs horodatées. L’étape en cours affiche le maintien restant ou la limite de sortie, avec un compteur local et une indication de dépassement. Une expiration ou remise à zéro la retire sans historique ni notification de résolution. Les étapes terminées restent acquises ; une interruption de surveillance remet la progression à zéro. Après le démarrage, la valeur courante peut amorcer la première étape ; les durées repartent de cette observation, sans compter le temps d’arrêt. Les étapes sont repliables en résumé, désactivables individuellement et réordonnables par glisser-déposer depuis leur poignée (également au clavier : flèches, Début et Fin). Les étapes désactivées sont ignorées ; si toutes le sont, la séquence ne déclenche rien. La résolution suit la dernière étape activée. Le détail de l’alerte inclut une chronologie compacte toujours visible indiquant la valeur et l’horodatage de début de chaque étape, conservés dans l’historique. Transitions et séquences se résolvent après une durée, quand l’état d’arrivée ou la dernière étape n’est plus vrai, ou selon une comparaison de valeur distincte. Le testeur affiche le suivi observé sans le modifier. Éditez visuellement ou en YAML, dupliquez une règle et testez un brouillon sur les valeurs réelles, avec les profils de notification correspondants. Les messages Jinja expliquent le problème et peuvent rester actualisés tant que l’alerte est active.

Toutes les alertes proposent une chronologie commune toujours visible, sans limite d’événements affichés (la fenêtre défile si nécessaire) : détection, activation, acquittement, résolution, étapes de séquence et occurrences d’instabilité. Les notifications de début et de résolution affichent leur horaire et le profil au moment de l’envoi ; les rappels sont regroupés par nombre total avec les profils, sans horaire. Les envois enregistrés sont conservés après résolution et redémarrage (100 derniers par catégorie hors rappels). Les anciennes alertes affichent les informations déjà disponibles.


### Suivre les alertes du dashboard à l’historique

L’Accueil distingue les alertes actives, à venir et acquittées, avec recherche, filtres, tri, groupement par équipement, colonnes personnalisables et sélection multiple. Ouvrez une alerte pour consulter ses valeurs au déclenchement et actuelles, ses notifications et ses occurrences précédentes. L’acquittement peut être illimité ou temporaire. Les 10 derniers acquittements et désacquittements (y compris les expirations automatiques) sont horodatés dans la chronologie et conservés après résolution et redémarrage ; le plus ancien est supprimé au-delà de cette limite.

La carte de dashboard intégrée propose une vue compacte regroupée par équipement. Choisissez les limites desktop/mobile, le tri, les labels à afficher ou masquer, l’ancienneté et le regroupement facultatifs, l’alignement et la couleur des icônes ; elle se masque sans alerte correspondante et ouvre les détails au clic. L’Historique permet de consulter les occurrences résolues et leurs statistiques de récurrence : alertes fréquentes, équipements touchés et durées actives cumulées.

### Choisir les notifications et vérifier la configuration

Les profils de notification facultatifs gèrent plusieurs destinataires, nouvelles alertes, retours à la normale, rappels, regroupement et exceptions ordonnées par étiquette. Ils peuvent être testés, dupliqués et édités en YAML. Vos automatisations basées sur les événements restent utilisables à la place.

L’analyse de cohérence retrouve les références statiques vers des entités et appareils ZHA absents dans les sources de configuration prises en charge. Lancez-la à la demande ou selon un planning, ouvrez la configuration concernée lorsque c’est possible et conservez éventuellement une alerte tant que des problèmes subsistent. L’import/export YAML et les sauvegardes automatiques permettent aussi de récupérer la configuration.

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

## Documentation

Commencez dans **Configuration → Surveillance automatique**, vérifiez les packs activés et leurs délais, puis ajoutez des règles propres à votre installation. Les profils de notification sont facultatifs.

La documentation détaillée est maintenue **uniquement en anglais** :

| Guide | Contenu |
| --- | --- |
| [Règles personnalisées](docs/custom-rules.md) | Opérations, attributs, Jinja, variations, transitions, testeur et exemples YAML. |
| [Configuration](docs/configuration.md) | Packs, délais, exclusions, profils de notification, YAML, sauvegardes et diagnostics. |
| [Cohérence de la configuration](docs/coherence.md) | Références, vérifications ZHA, exclusions, planification et alertes de cohérence. |
| [Dashboard et historique](docs/dashboard-and-history.md) | Accueil, carte, acquittement, démarrage, historique et statistiques de récurrence. |

L’[index de documentation](docs/user-guide.md) donne accès aux quatre guides. La documentation suit la branche consultée ; utilisez la branche de release ou le tag correspondant à votre version installée.

Questions, bugs et idées de surveillance sont les bienvenus dans les **[issues GitHub](https://github.com/zoic21/ha_alert_manager/issues)**.

Alert Manager est une intégration communautaire non officielle, sans affiliation avec Home Assistant. Ce code a été écrit en partie avec l’aide de l’IA.
