# Alert Manager pour Home Assistant

Alert Manager centralise les anomalies Home Assistant dans un moteur événementiel,
un panel **Alertes** et une seule entité : `sensor.alert_manager`.

Version minimale prise en charge : **Home Assistant 2026.8**.

## Fonctionnalités V1

- états internes `normal`, `pending` et `active` avec délais persistants ;
- détection automatique des indisponibilités, pertes de connectivité, équipements
  UniFi absents et batteries faibles ;
- règles personnalisées `equals`, `not_equals`, `above` et `below` sur l’état ou
  un attribut ;
- exclusions par label, entité ou appareil ;
- panel administrateur responsive, servi directement par l’intégration ;
- événements `alert_manager_alert_started` et
  `alert_manager_alert_resolved` ;
- aucune notification imposée et aucun polling global fréquent.

## Installation

### Installation manuelle

1. Copier `custom_components/alert_manager` dans le dossier
   `/config/custom_components/alert_manager` de Home Assistant.
2. Redémarrer Home Assistant.
3. Ouvrir **Paramètres → Appareils et services → Ajouter une intégration**.
4. Rechercher **Alert Manager** et confirmer l’ajout.
5. Ouvrir **Alertes** dans la barre latérale.

Aucune ressource Lovelace et aucune configuration YAML ne sont nécessaires.

### HACS

Le dépôt est compatible avec HACS comme **dépôt personnalisé** :

1. Dans HACS, ouvrir **Dépôts personnalisés**.
2. Ajouter `https://github.com/zoic21/ha_alert_manager` avec la catégorie
   **Integration**.
3. Installer Alert Manager, redémarrer Home Assistant et ajouter l’intégration.

Tant que le dépôt n’est pas publié dans le catalogue HACS par défaut, il doit être
ajouté manuellement comme dépôt personnalisé.

## Panel Alertes

Le panel est réservé aux administrateurs et contient quatre sections :

1. **Vue d’ensemble** : alertes actives et en attente, valeur, condition,
   équipement, pièce et dates. Le temps restant est calculé dans le
   navigateur depuis `due_at` ; il n’est jamais écrit chaque seconde dans Recorder.
2. **Surveillance automatique** : activation, délais, seuil de batterie et domaines
   surveillés.
3. **Règles personnalisées** : création, modification, activation et suppression.
4. **Exclusions et paramètres** : label, entités, appareils, délai global et délais
   particuliers.

Les identifiants d’appareil sont ceux du registre Home Assistant. Ils sont visibles
dans l’URL de la fiche d’un appareil ou via les outils de développement WebSocket.

## Détections automatiques

### Entités indisponibles

Une alerte est créée lorsqu’une entité d’un domaine surveillé passe à
`unavailable`. Les entrées désactivées dans le registre des entités, les appareils
désactivés et les exclusions sont ignorés. La seule présence de l’attribut
`restored: true` n’est **pas** un motif d’exclusion : une entité active peut être
restaurée légitimement après un redémarrage.

### Connectivité

Un `binary_sensor` ayant `device_class: connectivity` est en anomalie à `off`.
Un état `unavailable` est exclusivement traité par la détection des
indisponibilités, sans doublon.

### UniFi

Un `device_tracker` fourni par l’intégration `unifi`, ayant
`source_type: router`, est en anomalie lorsque son état n’est plus `home`.
`unavailable` reste traité par la catégorie des indisponibilités.

### Batteries

Un `sensor` ayant `device_class: battery` est en anomalie lorsque sa valeur
numérique est inférieure ou égale au seuil configuré (15 % par défaut). Un attribut
numérique `low_battery_level` remplace le seuil global pour cette entité. Les états
`unknown`, `unavailable`, non numériques, `NaN` et infinis sont ignorés par cette
catégorie.

## Règles personnalisées

Chaque règle possède un identifiant immuable généré par le backend. Elle compare
l’état principal ou un attribut d’une entité avec une valeur :

- `equals` : égalité textuelle exacte après suppression des espaces externes ;
- `not_equals` : différence textuelle ;
- `above` : valeur numérique strictement supérieure ;
- `below` : valeur numérique strictement inférieure.

Les conversions numériques refusent les booléens, valeurs invalides, `NaN` et
infinis. Une règle portant sur un attribut absent n’est pas déclenchée. Les états
principaux `unknown` et `unavailable` sont laissés aux détections automatiques.

Exemples :

- `binary_sensor.chrony_en_cours_d_execution equals off` ;
- `sensor.solarflow_2400_pro_is_error equals 1` ;
- `sensor.ups_code_d_etat not_equals OL CHRG` ;
- `sensor.frigo_temperature above 9` pendant 1 800 secondes ;
- `sensor.eas_bai_waterpressure_press below 1`.

## Exclusions et priorité des délais

Le label d’exclusion vaut `pas_d_alerte` par défaut. Une entité est exclue si le
label est posé sur elle ou sur son appareil associé. Les listes explicites d’entités
et d’appareils sont appliquées en plus.

Ordre de priorité des délais :

1. durée de la règle personnalisée ;
2. délai particulier configuré pour l’entité ;
3. attribut `alert_delay` de l’entité, entier ou chaîne numérique entière valide ;
4. délai de la catégorie automatique ;
5. délai global.

Tous les délais sont stockés en secondes. L’interface affiche aussi leur forme
lisible.

## Capteur unique

L’intégration crée exactement `sensor.alert_manager`. Son état est le nombre
d’alertes actives. Ses attributs ne contiennent que les alertes actives et en
attente :

```yaml
state: 2
attributes:
  active_count: 2
  pending_count: 1
  alerts:
    - id: unavailable:sensor.unas_cpu_usage
      type: unavailable
      entity_id: sensor.unas_cpu_usage
      name: UNAS
      value: unavailable
      condition: État indisponible
      detected_at: "2026-08-24T14:10:00+02:00"
      due_at: "2026-08-24T14:25:00+02:00"
      active_since: "2026-08-24T14:25:00+02:00"
      delay: 900
  pending:
    - id: battery:sensor.detecteur_entree_battery
      type: battery
      entity_id: sensor.detecteur_entree_battery
      value: 12
      unit: "%"
      condition: Batterie inférieure ou égale à 15 %
      detected_at: "2026-08-24T14:20:00+02:00"
      due_at: "2026-08-24T14:35:00+02:00"
      delay: 900
```

Aucun historique résolu et aucun compte à rebours périodique ne sont enregistrés
dans les attributs.

## Événements et notifications

À l’activation d’une alerte, Alert Manager émet
`alert_manager_alert_started`. À sa résolution, il émet
`alert_manager_alert_resolved` avec `resolved_at`. Une alerte déjà active avant un
redémarrage n’émet pas un second événement de démarrage.

Exemple d’automatisation mobile :

```yaml
alias: Notification Alert Manager
triggers:
  - trigger: event
    event_type: alert_manager_alert_started
actions:
  - action: notify.mobile_app_mon_telephone
    data:
      title: "{{ trigger.event.data.name }}"
      message: >-
        {{ trigger.event.data.condition }}
        ({{ trigger.event.data.entity_id }})
      data:
        tag: "{{ trigger.event.data.id }}"
mode: queued
```

L’intégration n’envoie elle-même aucune notification.

## Persistance et performances

La configuration et les états `pending`/`active` sont enregistrés dans un `Store`
Home Assistant versionné avec écritures atomiques. Au démarrage, la condition est
revérifiée avant de reprendre le délai ou l’état actif. Une anomalie déjà présente
lors de la première installation commence avec son délai normal.

Le moteur écoute les changements d’état et les registres. Il ne réévalue que
l’entité concernée, sauf au démarrage, après une modification de configuration ou
un changement de registre. Un seul timer est planifié par alerte en attente. Le
capteur n’est réécrit que si son contenu structuré change réellement.

## Développement et tests

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q

npm run build
npm run lint:frontend
npm run test:frontend
```

Les workflows exécutent également Hassfest et la validation HACS.

## Limites connues de la V1

- pas d’acquittement, snooze, répétition ou escalade ;
- pas d’historique des alertes résolues ;
- pas de template Jinja, condition combinée ou hystérésis ;
- pas d’import automatique des anciennes automatisations ;
- pas de notification directe, application mobile, add-on, MQTT ou entité par
  alerte ;
- le panel V1 est en français, tandis que le flux de configuration est traduit en
  français et en anglais.
