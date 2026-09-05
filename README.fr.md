<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <a href="README.md">English</a> · 🇫🇷 <strong>Français</strong>
</p>

# Alert Manager pour Home Assistant

**Savoir quand quelque chose ne va pas dans Home Assistant — et garder le problème visible jusqu’à sa résolution.**

Alert Manager transforme les situations anormales de Home Assistant en problèmes que vous pouvez réellement suivre. Au lieu de répartir la logique entre templates, automatisations, notifications et cartes de dashboard, vous définissez ce qui n’est « pas normal » et Alert Manager le suit de sa détection jusqu’à sa résolution.

Il peut aussi rechercher les **références d’entités cassées dans votre configuration Home Assistant**, pratique pour retrouver les restes après le renommage ou la suppression d’une entité.

Quelques exemples :

- une entité est `unavailable` depuis plus de 15 minutes ;
- une batterie passe sous 15 % ;
- un capteur de connectivité reste à `off` ;
- un appareil UniFi reste `not_home` ;
- une automatisation ou un script se termine en erreur ;
- un réfrigérateur consomme plus de 200 W pendant 2 heures ;
- une température reste en dehors d’une plage attendue ;
- une valeur ou un attribut ne change plus depuis trop longtemps ;
- une automatisation ou un dashboard référence encore une entité qui n’existe plus ;
- n’importe quelle condition personnalisée basée sur un état, un attribut ou du Jinja.

La différence importante avec une simple notification : le problème **reste visible tant qu’il n’est pas résolu**.

## Ce qu’Alert Manager vous apporte

- **Un tableau de bord central** pour les alertes actives, à venir et acquittées.
- **Une surveillance automatique** des problèmes courants : entités indisponibles, connectivité, batteries faibles, appareils UniFi et automatisations ou scripts en erreur.
- **Des règles personnalisées puissantes** pour les états, attributs, plages de valeurs, absences de changement et conditions Jinja.
- **Une analyse de cohérence de la configuration** pour retrouver les références vers des entités disparues et revenir vers la configuration concernée lorsque c’est possible.
- **L’acquittement et l’historique** pour suivre un problème sans perdre de vue son état réel.
- **Recherche, filtres, tri, groupement et colonnes personnalisables**, avec une vue adaptée au mobile.
- **Des exclusions et temporisations** pour éviter que les situations normales ou les micro-coupures deviennent du bruit.
- **L’export YAML et des sauvegardes automatiques de la configuration**, avec une récupération guidée si la configuration enregistrée devient invalide.
- **Des entités et événements Home Assistant** pour alimenter vos propres dashboards et automatisations de notification.
- **Une interface en français et en anglais**.

Alert Manager ne vous impose **aucun système de notification**. Les notifications restent de simples automatisations Home Assistant : vous choisissez qui notifier, comment et quand.

## Captures d’écran

### Vue d’ensemble

<p align="center">
  <img src="docs/assets/screenshots/overview.webp" alt="Vue d’ensemble Alert Manager">
</p>

<details>
<summary><strong>Voir plus de captures</strong></summary>

### Historique

<p align="center">
  <img src="docs/assets/screenshots/history.webp" alt="Historique Alert Manager">
</p>

### Surveillance automatique

<p align="center">
  <img src="docs/assets/screenshots/automatic-monitoring.webp" alt="Surveillance automatique Alert Manager">
</p>

### Règles personnalisées

<p align="center">
  <img src="docs/assets/screenshots/custom-rules.webp" alt="Règles personnalisées Alert Manager">
</p>

### Analyse de cohérence

<p align="center">
  <img src="docs/assets/screenshots/coherence.png" alt="Analyse de cohérence Alert Manager">
</p>

### Éditeur de règle

<p align="center">
  <img src="docs/assets/screenshots/rule-editor.webp" width="520" alt="Éditeur de règle Alert Manager">
</p>

### Configuration

<p align="center">
  <img src="docs/assets/screenshots/configuration.webp" alt="Configuration Alert Manager">
</p>

</details>

## Installation

### HACS

Tant qu’Alert Manager n’est pas disponible dans le catalogue HACS par défaut :

1. Ouvrez **HACS → Dépôts personnalisés**.
2. Ajoutez `https://github.com/zoic21/ha_alert_manager` comme **Integration**.
3. Installez **Alert Manager**.
4. Redémarrez Home Assistant.
5. Allez dans **Paramètres → Appareils et services → Ajouter une intégration** puis recherchez **Alert Manager**.

Le panneau **Alert Manager** apparaît ensuite dans la barre latérale de Home Assistant.

### Installation manuelle

1. Copiez `custom_components/alert_manager` dans `/config/custom_components/alert_manager`.
2. Redémarrez Home Assistant.
3. Ajoutez **Alert Manager** depuis **Paramètres → Appareils et services**.

Aucune ressource Lovelace et aucune configuration YAML ne sont nécessaires pour commencer.

## Surveillance automatique

Alert Manager peut surveiller automatiquement plusieurs problèmes courants :

| Surveillance | Condition d’alerte |
| --- | --- |
| Entités indisponibles | l’entité reste `unavailable` |
| Connectivité | un `binary_sensor` avec `device_class: connectivity` reste à `off` |
| Batterie faible | un capteur de batterie atteint le seuil configuré |
| UniFi | un `device_tracker` UniFi reste absent de `home` |
| Automatisations et scripts en erreur | une exécution d’`automation` ou de `script` se termine en erreur |

Chaque surveillance peut être activée indépendamment. Les délais et exclusions se règlent depuis l’interface, et les seuils de batterie peuvent être adaptés lorsque certains appareils ont besoin de limites différentes.

La surveillance des erreurs d’automatisation et de script n’a aucun délai par défaut. Une exécution suivante terminée avec succès résout l’alerte. Pour certaines automatisations ou certains scripts, il est possible d’exiger plusieurs cycles d’exécution consécutifs en erreur avant de la déclencher.

## Règles personnalisées

Pour tout le reste, vous pouvez créer vos propres règles directement depuis le panneau Alert Manager.

Une règle peut surveiller une ou plusieurs entités indépendamment et utiliser :

- l’état de l’entité ou un attribut imbriqué, y compris un tableau comme `data.*.key` ;
- des comparaisons d’égalité, de texte, de seuil numérique, **entre** deux valeurs ou **en dehors** de ces bornes ;
- la variation de l’état ou d’un attribut numérique depuis le moment où une condition Jinja devient vraie ;
- l’absence de tout changement, ou seulement un état ou un attribut précis qui ne change plus ;
- une condition Jinja en complément d’une comparaison, ou Jinja comme logique complète de la règle.

Les temporisations permettent d’exiger qu’une situation persiste avant de devenir une alerte, afin qu’une courte anomalie ne remplisse pas inutilement le dashboard. Les messages Jinja personnalisés sont figés par défaut au déclenchement, mais peuvent être maintenus à jour pendant toute la durée de l’alerte.

Une erreur de rendu Jinja est indéterminée : elle ne crée aucune nouvelle occurrence et conserve les alertes existantes, leurs échéances de passage en actif et le dernier message valide. Les dépendances restent suivies pour réévaluer la règle lors d’un changement pertinent. Pour les règles de variation, une erreur ne crée ni ne réinitialise la référence ; seule une condition Jinja explicitement fausse termine la fenêtre en cours. Les erreurs restent visibles dans les journaux et le testeur de règle.

Cela couvre par exemple les températures anormales, les consommations électriques inhabituelles, l’âge d’une sauvegarde, les codes d’erreur, les capteurs qui ne se mettent plus à jour ou presque n’importe quel état exposé par Home Assistant.

Les règles peuvent être éditées visuellement ou en YAML et dupliquées depuis le panneau. Une règle peut surveiller jusqu’à 50 entités et une configuration peut contenir jusqu’à 500 règles. En YAML, les règles entièrement basées sur Jinja utilisent `source: jinja` ; les anciennes règles en `source: none` sont migrées automatiquement.

Les règles peuvent porter des étiquettes Home Assistant (`label_ids` en YAML), affichées dans le tableau. Pour les notifications, elles complètent les étiquettes de l’entité et de l’appareil : elles servent au filtre du profil et aux exceptions par étiquette. Les exceptions ciblent uniquement un pack ou une étiquette.

### Exemples

#### Un thermostat qui chauffe sans réchauffer la pièce

Lorsque le thermostat commence à chauffer, la condition Jinja devient vraie et Alert Manager mémorise la température initiale. Après deux heures, la règle déclenche une alerte si la pièce a gagné moins de 0,2 °C. Dans le message, value correspond à la variation de température mesurée.

```yaml
name: "Thermostat : surveillance"
enabled: true
entity_ids:
  - "climate.tado_smart_thermostat_su0582429440"
source: "attribute_variation"
attribute: "current_temperature"
operator: "below"
value: "0.2"
duration: 7200
message: "Le chauffage {{ state_attr(entity_id, 'friendly_name') }} est en marche depuis 2 h, mais la température n'a augmenté que de {{ value | float(0) | round(1) }} °C."
update_message_when_active: false
condition_template: "{{ state.state == 'heating' }}"
```

#### Messages Bayrol en ignorant les états attendus

Cette règle évalue chaque clé de message du tableau data de Bayrol. Elle ne peut devenir active que lorsqu’aucun des états attendus de débit, de démarrage ou de mode enjoy n’est présent ; sa condition Jinja impose aussi que le débit soit présent.

```yaml
name: "Alerte Bayrol"
enabled: true
entity_ids:
  - "sensor.bayrol_messages"
source: "attribute"
attribute: "data.*.key"
operator: "not_contains"
value:
  - "al_no_flow_bnc"
  - "al_start_delay"
  - "enjoy"
duration: 5400
message: "{% if state_attr('sensor.bayrol_messages','data') %}\n{% for item in state_attr('sensor.bayrol_messages','data') %}     \n    {% if item.key not in ['al_no_flow_bnc','enjoy','al_start_delay'] %}       \n      {{ item.message | replace(\"\\n\",\" \") }}  \n    {% endif %}      \n{% endfor %}     \n{% endif %}"
update_message_when_active: false
condition_template: "{% set flow = states('binary_sensor.bayrol_flow_contact') %}\n{{ (flow == 'on') }}"
```

## Analyse de cohérence

La page **Cohérence** compare les références statiques d’entités trouvées dans votre configuration Home Assistant avec les entités réellement présentes.

Lorsqu’un problème est trouvé, Alert Manager indique d’où il vient et permet, lorsque c’est possible, d’ouvrir directement l’automatisation, le script, le dashboard, le template ou l’autre objet Home Assistant concerné. Les résultats sont conservés entre les redémarrages et sont également exposés via `sensor.alert_manager_coherence_issue`, ce qui permet de surveiller l’échec d’un contrôle de cohérence comme n’importe quel autre problème.

Les analyses peuvent être lancées à la demande ou automatiquement chaque jour, chaque semaine ou chaque mois. L’analyse du dossier ESPHome peut être désactivée et certaines références connues peuvent être ignorées depuis la configuration.

Cette page donne également accès aux 50 dernières entités supprimées encore conservées par Home Assistant, avec leur date de suppression et leur intégration. La liste est lue directement dans le registre d’entités de Home Assistant : Alert Manager ne maintient pas son propre historique des suppressions.

## Export et récupération de la configuration

La configuration complète peut être exportée et importée en YAML. Alert Manager conserve également les trois derniers exports quotidiens valides de la configuration. Ils peuvent être téléchargés ou restaurés depuis la page Configuration.

Si la configuration enregistrée ne peut pas être chargée au démarrage, Alert Manager démarre de façon sûre avec les valeurs par défaut, affiche un avertissement persistant et laisse un administrateur choisir une sauvegarde. Aucune restauration n’est effectuée silencieusement. La restauration d’une sauvegarde complète remplace la configuration actuelle, les alertes en cours et l’historique.

## Cycle de vie d’une alerte

Une alerte peut être :

- **À venir** tant que sa temporisation est encore en cours ;
- **Active** lorsque la condition est présente depuis suffisamment longtemps ;
- **Acquittée** lorsque vous avez pris connaissance du problème mais qu’il n’est pas encore résolu ;
- **Résolue** lorsque la condition anormale disparaît.

Les alertes résolues peuvent être conservées dans l’historique, ce qui permet de repérer les problèmes récurrents au lieu de seulement voir ce qui ne va pas à l’instant présent.

Un clic sur une alerte ouvre son détail, notamment la valeur qui l’a déclenchée et sa valeur actuelle, avec un accès contextuel à l’entité Home Assistant concernée lorsqu’il est disponible.

## Être notifié sans être spammé

Alert Manager émet l’événement `alert_manager_device_alert_started` lorsqu’un appareil passe en alerte. Les alertes qui arrivent à peu d’intervalle pour le même appareil sont regroupées avant l’émission de l’événement, ce qui permet d’envoyer **une notification utile pour l’appareil au lieu d’une notification par règle**.

Exemple :

```yaml
alias: Notification Alert Manager
triggers:
  - trigger: event
    event_type: alert_manager_device_alert_started
actions:
  - action: script.notification
    metadata: {}
    data:
      title: '{{ trigger.event.data.device_name }} en alerte'
      message: |-
        {% for message in trigger.event.data.messages | default([], true) %}
        - {{ message }}
        {% endfor %}
      recipients:
        - loic
mode: queued
```

`script.notification` n’est qu’un exemple : remplacez-le par votre propre script de notification ou n’importe quelle action de notification Home Assistant.

### Suivi des notifications par alerte

Les détails d’une alerte affichent les notifications de ses profils intégrés : nombre d’envois (rappels compris), profils correspondants même sans rappel et date du dernier envoi. Un lot compte une fois par profil et par alerte, dès qu’au moins une cible a été notifiée ; les tests et les échecs complets sont exclus. L’historique conserve séparément les envois de retour à la normale, leurs profils et leur dernière date. Ces informations survivent aux redémarrages ; elles sont masquées pour les alertes à venir et les anciens envois ne sont pas reconstitués. Les notifications envoyées par des automatisations externes ne sont pas comptabilisées.

## Entités et événements Home Assistant

Alert Manager expose plusieurs entités afin que son état puisse aussi être utilisé en dehors du panneau intégré :

- `switch.alert_manager_main_monitoring`
- `sensor.alert_manager_main_active`
- `sensor.alert_manager_main_pending`
- `sensor.alert_manager_main_acknowledge`
- `sensor.alert_manager_device_main_active`
- `sensor.alert_manager_coherence_issue`

Événements utiles :

- `alert_manager_alert_started`
- `alert_manager_alert_resolved`
- `alert_manager_device_alert_started`
- `alert_manager_alert_acknowledged`
- `alert_manager_alert_unacknowledged`

L’acquittement est également disponible via `alert_manager.acknowledge` et `alert_manager.unacknowledge`.

## Prérequis

- Home Assistant **2026.8 ou plus récent**.
- Une seule instance d’Alert Manager par installation Home Assistant.
- Un compte administrateur est nécessaire pour accéder au panneau Alert Manager.

Alert Manager est une intégration communautaire non officielle et n’est pas affiliée au projet Home Assistant.

## Note

Ce code a été ecrit en partie avec l'aide d'une IA

## Retours

Alert Manager évolue activement et les installations réelles sont le meilleur moyen de trouver les cas limites.

Les rapports de bug, idées et cas de surveillance inhabituels sont les bienvenus dans les **[GitHub Issues](https://github.com/zoic21/ha_alert_manager/issues)**.
