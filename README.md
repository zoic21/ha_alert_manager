<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇫🇷 <strong>Français</strong> | 🇬🇧 <a href="README.en.md">English</a>
</p>

# Alert Manager pour Home Assistant

Alert Manager centralise les anomalies Home Assistant dans un moteur événementiel,
un panel **Alertes** et une seule entité : `sensor.alert_manager`.

Version minimale prise en charge : **Home Assistant 2026.8**. Alert Manager est
une intégration communautaire non officielle, sans lien avec le projet Home
Assistant.

## Fonctionnalités V1.4

- états internes `normal`, `pending` et `active` avec délais persistants ;
- détection automatique des indisponibilités, pertes de connectivité, équipements
  UniFi absents et batteries faibles ;
- packs automatiques décrits par le backend et activés uniquement lorsque leurs
  intégrations prérequises sont réellement disponibles ;
- règles personnalisées multi-entités `equals`, `not_equals`, `contains`,
  `not_contains`, `above` et `below` sur l’état ou un attribut, avec plusieurs
  valeurs possibles pour les comparaisons textuelles et une alerte indépendante
  par source ;
- exclusions automatiques par plusieurs labels, entités ou appareils ;
- panel administrateur responsive, servi directement par l’intégration ;
- interface, flux de configuration, packs et conditions disponibles en français
  et en anglais selon la langue de chaque utilisateur Home Assistant ;
- regroupement visuel, sans fusion des alertes, lorsque plusieurs anomalies
  appartiennent au même appareil ;
- acquittement persistant de chaque alerte active depuis le panneau ou les
  automatisations Home Assistant ;
- événements `alert_manager_alert_started` et
  `alert_manager_alert_resolved`, complétés par
  `alert_manager_alert_acknowledged` et
  `alert_manager_alert_unacknowledged` ;
- aucune notification imposée et aucun polling global fréquent.

Alert Manager centralise des anomalies simples et indépendantes. Il ne remplace
ni un système de supervision externe, ni l’historique de Home Assistant, ni une
solution de notification : les automatisations restent sous le contrôle de
l’utilisateur.

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

Chaque version publiée possède un tag `vX.Y.Z` et une release GitHub avec son
changelog. HACS affiche ainsi la version fonctionnelle publiée et ses notes, et
non l’identifiant du dernier commit de la branche principale.

Tant que le dépôt n’est pas publié dans le catalogue HACS par défaut, il doit être
ajouté manuellement comme dépôt personnalisé.

## Ajout de l’intégration et accès au panneau

Après installation et redémarrage, ouvrir **Paramètres → Appareils et services →
Ajouter une intégration**, rechercher **Alert Manager**, puis confirmer. Une seule
instance est autorisée. Le panneau **Alert Manager** apparaît ensuite dans la barre
latérale et reste réservé aux administrateurs.

## Panneau Alert Manager

Le panel est réservé aux administrateurs et contient quatre sections :

1. **Vue d’ensemble** : sections distinctes pour les alertes actives, à venir et
   acquittées, avec valeur, condition, équipement, pièce et dates. Le nom de la
   source ouvre le dialogue natif
   « Plus d’informations ». Le temps restant est calculé dans le
   navigateur depuis `due_at` ; il n’est jamais écrit chaque seconde dans Recorder.
   Plusieurs alertes rattachées au même identifiant d’appareil sont réunies dans
   une tuile avec une ligne par source au sein d’une même section. Une entité sans
   appareil, ou un appareil qui ne porte plus qu’une alerte, conserve une tuile
   individuelle compacte. Chaque alerte active conserve sa propre action compacte
   **Acquitter** ou **Retirer l’acquittement** dans l’en-tête, y compris dans un
   groupe. Aucun bouton n’agit sur toutes les alertes d’un appareil.
   Le total suivi additionne les couples règle personnalisée/entité actifs et les
   entités uniques couvertes par au moins une surveillance automatique.
2. **Surveillance automatique** : activation, délais et seuil de batterie. Les
   cartes sont produites depuis les métadonnées du backend et seuls les packs
   actuellement disponibles sont proposés.
3. **Règles personnalisées** : création et modification dans un volet latéral
   structuré en sections, composé des éléments natifs Home Assistant. Un clic sur
   la ligne ouvre le volet ; l’activation, les sources, la condition, les valeurs,
   la temporisation et le message y sont regroupés clairement. L’interrupteur
   natif en fin de ligne reste disponible pour une activation rapide.
4. **Exclusions et paramètres** : labels, entités, appareils, délai global et délais
   particuliers. Les sélections utilisent les sélecteurs et la recherche natifs de
   Home Assistant.

## Packs automatiques

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
l’état principal ou un attribut de plusieurs entités avec une ou plusieurs valeurs.
Chaque
couple règle/entité a son propre cycle, son délai et son identifiant stable
`rule:<rule_uuid>:<entity_id>` :

- `equals` : égalité textuelle exacte avec au moins une valeur configurée, après
  suppression des espaces externes ;
- `not_equals` : aucune des valeurs configurées n’est égale à l’état courant ;
- `contains` : l’état courant contient au moins une des valeurs configurées ;
- `not_contains` : l’état courant ne contient aucune des valeurs configurées ;
- `above` : valeur numérique strictement supérieure ;
- `below` : valeur numérique strictement inférieure.

Les quatre opérateurs textuels acceptent une ou plusieurs valeurs ; les opérateurs
numériques acceptent exactement une valeur. Les conversions numériques refusent
les booléens, valeurs invalides, `NaN` et infinis. Une règle portant sur un attribut
absent n’est pas déclenchée. Les états principaux `unknown` et `unavailable` sont
laissés aux détections automatiques.

Exemples :

- `binary_sensor.chrony_en_cours_d_execution equals off` ;
- `sensor.solarflow_2400_pro_is_error equals 1` ;
- `sensor.ups_code_d_etat contains CHRG ou ERROR` ;
- `sensor.mode not_equals off ou idle` ;
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
d’alertes actives. Ses attributs séparent les alertes actives non acquittées,
acquittées et en attente :

```yaml
state: 2
attributes:
  active_count: 2
  acknowledge_count: 1
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
      condition_key: automatic.unavailable
      condition_params: {}
      detected_at: "2026-08-24T14:10:00+02:00"
      due_at: "2026-08-24T14:25:00+02:00"
      active_since: "2026-08-24T14:25:00+02:00"
      delay: 900
      acknowledged: false
  acknowledge:
    - id: connectivity:binary_sensor.unas_connectivity
      type: connectivity
      entity_id: binary_sensor.unas_connectivity
      name: Connectivité UNAS
      value: "off"
      condition: Connectivité coupée
      detected_at: "2026-08-25T16:15:00+02:00"
      due_at: "2026-08-25T16:30:00+02:00"
      active_since: "2026-08-25T16:30:00+02:00"
      delay: 900
      acknowledged: true
      acknowledged_at: "2026-08-25T16:30:00+02:00"
      acknowledged_by: "Loïc"
  pending:
    - id: battery:sensor.detecteur_entree_battery
      type: battery
      entity_id: sensor.detecteur_entree_battery
      value: 12
      unit: "%"
      condition: Batterie inférieure ou égale à 15 %
      condition_key: automatic.battery
      condition_params:
        threshold: "15"
      detected_at: "2026-08-24T14:20:00+02:00"
      due_at: "2026-08-24T14:35:00+02:00"
      delay: 900
```

Aucun historique résolu et aucun compte à rebours périodique ne sont enregistrés
dans les attributs. `device_id` est facultatif et n’est présent que pour une entité
rattachée à un appareil. Les listes `alerts`, `pending` et `acknowledge` restent
toujours des alertes individuelles : aucun groupe visuel n’est persisté ou exposé
au capteur. `alerts` contient les alertes actives non acquittées, tandis que
`acknowledge` contient les alertes actives acquittées. `acknowledge_count` donne
la taille de cette dernière liste.
`condition` est conservé pour les automatisations existantes. Les champs
`condition_key` et `condition_params`, présents pour les conditions générées par
Alert Manager, permettent au panneau de les afficher dans la langue de
l’utilisateur. Un message personnalisé reste inchangé et n’est jamais traduit.

Pour une alerte active non acquittée, `acknowledged` vaut `false`. Les champs
`acknowledged_at` et `acknowledged_by` ne sont présents qu’après acquittement.
`acknowledged_by` est absent lorsque l’action vient d’une automatisation ou du
système. Une alerte acquittée passe de `alerts` à `acknowledge`, mais reste active
et reste comptée dans `active_count` et dans l’état de `sensor.alert_manager` tant
que sa condition reste vraie.

## Acquittement et services

L’acquittement porte toujours sur une seule alerte `active`, ciblée par son
identifiant stable. Il ne résout pas l’alerte et ne change pas son compteur. Une
alerte `pending`, inconnue ou déjà résolue est refusée avec une erreur explicite.
Les actions répétées sont idempotentes : acquitter deux fois ou retirer deux fois
l’acquittement n’émet pas de nouvel événement.

Les deux services sont disponibles dans **Outils de développement → Actions** et
dans les automatisations :

```yaml
action: alert_manager.acknowledge
data:
  alert_id: unavailable:sensor.unas_cpu_usage
```

```yaml
action: alert_manager.unacknowledge
data:
  alert_id: unavailable:sensor.unas_cpu_usage
```

Le contexte Home Assistant détermine l’auteur affiché. Sans utilisateur associé,
le panneau affiche le libellé traduit « Automatisation ou système ». À la
résolution, les informations d’acquittement disparaissent avec l’occurrence. Si la
condition réapparaît, la nouvelle occurrence démarre non acquittée.

## Événements et notifications

À l’activation d’une alerte, Alert Manager émet
`alert_manager_alert_started`. À sa résolution, il émet
`alert_manager_alert_resolved` avec `resolved_at`. Une alerte déjà active avant un
redémarrage n’émet pas un second événement de démarrage.

Un changement réel d’acquittement émet aussi :

- `alert_manager_alert_acknowledged`, avec les données publiques complètes et
  `acknowledged_at`/`acknowledged_by` lorsque l’auteur est connu ;
- `alert_manager_alert_unacknowledged`, avec `unacknowledged_at`, l’auteur de
  l’action lorsqu’il est connu et les précédentes informations d’acquittement.

Ces événements ne sont jamais rejoués au redémarrage. Exemple d’automatisation
qui journalise les deux changements :

```yaml
alias: Journal des acquittements Alert Manager
triggers:
  - trigger: event
    event_type: alert_manager_alert_acknowledged
  - trigger: event
    event_type: alert_manager_alert_unacknowledged
actions:
  - action: logbook.log
    data:
      name: Alert Manager
      message: >-
        {{ trigger.event.event_type }} : {{ trigger.event.data.id }}
mode: queued
```

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

## Dépannage courant

- **Le panneau n’apparaît pas** : vérifier que l’intégration est ajoutée, que
  l’utilisateur est administrateur, puis vider le cache du navigateur après une
  mise à jour du frontend.
- **Le pack UniFi est absent** : au moins une entrée de l’intégration UniFi doit
  être chargée et non désactivée. Un `device_tracker` d’un autre fournisseur ne
  suffit pas.
- **Une entité désactivée remonte** : contrôler son entrée dans le registre des
  entités et l’appareil parent. L’attribut `restored: true` ne signifie pas que
  l’entité est désactivée.
- **Une alerte ne démarre pas immédiatement** : vérifier, dans cet ordre, la durée
  de règle, le délai particulier de l’entité, le délai du pack et le délai global.
- **La langue ne change pas** : recharger le panneau après avoir changé la langue
  du profil Home Assistant. Les noms d’entités, d’appareils, de pièces, de règles
  et les messages personnalisés restent volontairement inchangés.

## Persistance et performances

La configuration, les états `pending`/`active` et l’acquittement sont enregistrés
dans un `Store` Home Assistant versionné avec écritures atomiques. Au démarrage, la condition est
revérifiée avant de reprendre le délai ou l’état actif. Un état momentanément
absent ou `unknown` pendant le démarrage ne résout pas une alerte persistée ; une
valeur définitive ultérieure la confirme ou la résout. Une anomalie déjà présente
lors de la première installation commence avec son délai normal.
Les enregistrements V1.3 sans champs d’acquittement sont migrés de manière
idempotente et considérés comme non acquittés.

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

## Limites connues et fonctions reportées

- pas de snooze, répétition ou escalade ;
- pas d’historique des alertes résolues ni de stockage CSV ;
- pas de template Jinja, condition combinée ou hystérésis ;
- pas d’import automatique des anciennes automatisations ;
- pas de notification directe, application mobile, add-on, MQTT ou entité par
  alerte ;
- regroupement uniquement visuel, sans fusion des alertes ;
- configuration réservée aux administrateurs ;
- interface fournie uniquement en français et en anglais dans cette version.
