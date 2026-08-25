# Alert Manager pour Home Assistant

Alert Manager centralise les anomalies Home Assistant dans un moteur événementiel,
un panel **Alertes** et une seule entité : `sensor.alert_manager`.

Version minimale prise en charge : **Home Assistant 2026.8**.

## Fonctionnalités V1.2

- états internes `normal`, `pending` et `active` avec délais persistants ;
- détection automatique des indisponibilités, pertes de connectivité, équipements
  UniFi absents et batteries faibles ;
- packs automatiques décrits par le backend et activés uniquement lorsque leurs
  intégrations prérequises sont réellement disponibles ;
- règles personnalisées multi-entités `equals`, `not_equals`, `above` et `below`
  sur l’état ou un attribut, avec une alerte indépendante par source ;
- exclusions automatiques par plusieurs labels, entités ou appareils ;
- panel administrateur responsive, servi directement par l’intégration ;
- regroupement visuel, sans fusion des alertes, lorsque plusieurs anomalies
  appartiennent au même appareil ;
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
   équipement, pièce et dates. Le nom de la source ouvre le dialogue natif
   « Plus d’informations ». Le temps restant est calculé dans le
   navigateur depuis `due_at` ; il n’est jamais écrit chaque seconde dans Recorder.
   Plusieurs alertes rattachées au même identifiant d’appareil sont réunies dans
   une tuile avec une ligne par source. Une même tuile peut contenir des lignes
   actives et en attente. Une entité sans appareil, ou un appareil qui ne porte
   plus qu’une alerte, conserve une tuile individuelle compacte.
   Le total suivi additionne les couples règle personnalisée/entité actifs et les
   entités uniques couvertes par au moins une surveillance automatique.
2. **Surveillance automatique** : activation, délais et seuil de batterie. Les
   cartes sont produites depuis les métadonnées du backend et seuls les packs
   actuellement disponibles sont proposés.
3. **Règles personnalisées** : création et modification dans un volet latéral
   composé des éléments natifs Home Assistant. Un clic sur la ligne ouvre le
   volet, l’interrupteur natif en fin de ligne active la règle et la suppression
   se trouve uniquement dans le volet.
4. **Exclusions et paramètres** : labels, entités, appareils, délai global et délais
   particuliers. Les sélections utilisent les sélecteurs et la recherche natifs de
   Home Assistant.

## Détections automatiques

Les packs génériques **Entités indisponibles**, **Connectivité** et **Batteries
faibles** sont toujours disponibles. Le choix d’activation d’un pack est conservé
même si son prérequis devient temporairement indisponible. Dans ce cas, le pack ne
surveille aucune entité, ne conserve aucun timer et ne génère aucune alerte. Son
dernier réglage est repris automatiquement lorsque le prérequis redevient utilisable.

### Entités indisponibles

Une alerte est créée lorsqu’une entité de n’importe quel domaine passe exactement à
`unavailable` ; `unknown` n’est pas inclus. Les entités d’Alert Manager, les entrées
désactivées dans le registre, les appareils désactivés et les exclusions sont
ignorés. La seule présence de l’attribut
`restored: true` n’est **pas** un motif d’exclusion : une entité active peut être
restaurée légitimement après un redémarrage.

### Connectivité

Un `binary_sensor` ayant `device_class: connectivity` est en anomalie à `off`.
Un état `unavailable` est exclusivement traité par la détection des
indisponibilités, sans doublon.

### UniFi

Un `device_tracker` fourni par l’intégration `unifi`, ayant
`source_type: router`, est en anomalie lorsque son état n’est plus `home`.
`unavailable` reste traité par la catégorie des indisponibilités. Le pack UniFi
n’est proposé et exécuté que si Home Assistant possède au moins une entrée de
configuration UniFi chargée, non désactivée et utilisable.

### Batteries

Un `sensor` ayant `device_class: battery` est en anomalie lorsque sa valeur
numérique est inférieure ou égale au seuil configuré (15 % par défaut). Un attribut
numérique `low_battery_level` remplace le seuil global pour cette entité. Les états
`unknown`, `unavailable`, non numériques, `NaN` et infinis sont ignorés par cette
catégorie.

## Règles personnalisées

Chaque règle possède un identifiant immuable généré par le backend. Elle compare
l’état principal ou un attribut de plusieurs entités avec une valeur. Chaque
couple règle/entité a son propre cycle, son délai et son identifiant stable
`rule:<rule_uuid>:<entity_id>` :

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

Plusieurs labels d’exclusion peuvent être sélectionnés depuis le registre Home
Assistant. Lors de la migration, `pas_d_alerte` est présélectionné s’il existe, sans
être créé automatiquement. Une alerte automatique est exclue si au moins un label
sélectionné est posé sur l’entité ou son appareil. Les règles personnalisées
ignorent ces labels. Les listes explicites d’entités et d’appareils sont appliquées
en plus.

Ordre de priorité des délais :

1. durée de la règle personnalisée ;
2. délai particulier configuré pour l’entité ;
3. délai propre au pack automatique ;
4. délai global.

Tous les délais sont stockés en secondes. Un délai de pack laissé vide utilise le
délai global. Modifier un délai recalcule `due_at` depuis le `detected_at` original :
une alerte en attente devient immédiatement active si l’échéance est dépassée, et
une alerte active redevient en attente si sa nouvelle échéance est future. Son
identifiant et son cycle de vie sont conservés. Les délais particuliers V1.1 sont
réutilisés tels quels, sans migration destructive.

## Capteur unique

L’intégration crée exactement `sensor.alert_manager`. Son état est le nombre
d’alertes actives. Ses attributs ne contiennent que les alertes actives et en
attente :

```yaml
state: 2
attributes:
  active_count: 2
  pending_count: 1
  tracked_count: 47
  alerts:
    - id: unavailable:sensor.unas_cpu_usage
      type: unavailable
      entity_id: sensor.unas_cpu_usage
      device_id: 0123456789abcdef0123456789abcdef
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
dans les attributs. `device_id` est facultatif et n’est présent que pour une entité
rattachée à un appareil. Les listes `alerts` et `pending` restent toujours des
alertes individuelles : aucun groupe visuel n’est persisté ou exposé au capteur.

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
revérifiée avant de reprendre le délai ou l’état actif. Un état momentanément
absent ou `unknown` pendant le démarrage ne résout pas une alerte persistée ; une
valeur définitive ultérieure la confirme ou la résout. Une anomalie déjà présente
lors de la première installation commence avec son délai normal.

Le moteur écoute les changements d’état et les registres. Il ne réévalue que
l’entité concernée, sauf au démarrage, après une modification de configuration ou
un changement de registre ou de disponibilité d’un pack. Un seul timer est
planifié par alerte en attente. Le capteur n’est réécrit que si son contenu
structuré change réellement.

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

## Limites connues de la V1.2

- pas d’acquittement, snooze, répétition ou escalade ;
- pas d’historique des alertes résolues ;
- pas de template Jinja, condition combinée ou hystérésis ;
- pas d’import automatique des anciennes automatisations ;
- pas de notification directe, application mobile, add-on, MQTT ou entité par
  alerte ;
- le panel V1 est en français, tandis que le flux de configuration est traduit en
  français et en anglais.
