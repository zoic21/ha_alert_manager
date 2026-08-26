<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇫🇷 <strong>Français</strong> | 🇬🇧 <a href="README.en.md">English</a>
</p>

# Alert Manager pour Home Assistant

Alert Manager centralise les anomalies Home Assistant dans un moteur événementiel,
un panel **Alertes** et un appareil de service regroupant trois capteurs d’alertes
et un switch de surveillance.

Version minimale prise en charge : **Home Assistant 2026.8**. Alert Manager est
une intégration communautaire non officielle, sans lien avec le projet Home
Assistant.

## Fonctionnalités V1.7

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
- tableau compact fondé sur le composant natif `ha-data-table` de Home Assistant,
  avec recherche, filtres, tri, groupement repliable et colonnes personnalisables,
  sans fusion des alertes ;
- acquittement persistant de chaque alerte active depuis le panneau ou les
  automatisations Home Assistant ;
- appareil `Alert Manager - Général`, switch de surveillance persistant et trois
  capteurs séparant les alertes actives, à venir et acquittées ;
- édition visuelle ou YAML des règles personnalisées, export YAML complet et
  import YAML de remplacement de la configuration ;
- historique persistant des alertes réellement activées puis résolues, limité par
  défaut à 100 événements et consultable dans un onglet dédié sans nouvelle
  entité ; une alerte revenue à la normale pendant son délai `pending` n’est pas
  historisée ;
- événements `alert_manager_alert_started` et
  `alert_manager_alert_resolved`, complétés par
  `alert_manager_alert_acknowledged` et
  `alert_manager_alert_unacknowledged` ;
- notification persistante de sécurité uniquement lorsque la surveillance est
  encore désactivée au chargement, et aucun polling global fréquent.

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

Le panel est réservé aux administrateurs et contient cinq sections :

1. **Vue d’ensemble** : un tableau compact unique réunit les alertes actives en
   rouge, à venir en orange et acquittées en bleu. Ses colonnes par défaut sont
   Statut, Appareil, Entité, Valeur, Condition, Détectée le et
   Active depuis/Temps restant. Le nom de l’entité ouvre le dialogue natif
   « Plus d’informations ». Le temps restant est calculé dans le navigateur
   depuis `due_at` et affiche un délai suspendu lorsque la surveillance est
   désactivée ; aucune valeur n’est écrite chaque seconde dans Recorder.
   La barre d’outils permet une recherche immédiate, des filtres cumulables, un
   groupement repliable par appareil, zone, règle ou statut, ainsi qu’un tri
   ascendant ou descendant. Les colonnes facultatives (ID d’entité, zone, règle,
   message…) peuvent être affichées, masquées et réordonnées. Leur ordre, leur
   visibilité, le groupement et le tri sont conservés localement pour
   l’utilisateur, sans modifier la configuration de l’intégration.
   Le mode sélection remplace la barre d’outils par une barre d’actions. Il
   permet de sélectionner les lignes visibles et d’acquitter ou désacquitter en
   masse. Une sélection mixte n’agit que sur les alertes compatibles : les
   alertes `pending` et les alertes déjà dans l’état demandé sont ignorées, et le
   retour indique le nombre réellement modifié.
   Le total suivi additionne les couples règle personnalisée/entité actifs et les
   entités uniques couvertes par au moins une surveillance automatique.
2. **Historique** : le même tableau natif liste les alertes résolues et les
   résolutions après acquittement. Chaque
   événement fige le nom de règle et d’entité, l’appareil, la zone, le message,
   la condition, la valeur de déclenchement et les dates. Recherche, filtres,
   groupement, tri et colonnes personnalisables restent disponibles. Aucune
   sélection ni action métier d’acquittement n’est proposée dans l’Historique.
   Les anomalies revenues à la normale avant leur activation ne sont pas des
   alertes effectives et ne sont donc pas ajoutées à l’historique.
3. **Surveillance automatique** : activation, délais et seuil de batterie. Les
   cartes sont produites depuis les métadonnées du backend et seuls les packs
   actuellement disponibles sont proposés.
4. **Règles personnalisées** : création et modification dans un volet latéral
   structuré en sections, composé des éléments natifs Home Assistant. Un clic sur
   la ligne ouvre le volet ; l’activation, les sources, la condition, les valeurs,
   la temporisation et le message y sont regroupés clairement. L’interrupteur
   natif en fin de ligne reste disponible pour une activation rapide.
5. **Configuration** : labels, entités, appareils, délai global, délais
   particuliers et rétention de l’historique. Les sélections utilisent les
   sélecteurs et la recherche natifs de Home Assistant.

### Rétention et effacement de l’historique

Dans **Configuration → Paramètres généraux**, juste sous **Délai global**, le
réglage **Nombre d’événements historiques conservés** accepte de `0` à `1000`.
L’action **Effacer l’historique** est placée face au champ ; l’unique bouton
commun d’enregistrement de la configuration, en bas à droite, sauvegarde aussi
ce réglage. Une nouvelle installation conserve `100` événements. `0` supprime les
événements existants lors de l’enregistrement puis désactive la conservation des
prochaines résolutions. À chaque résolution et à chaque diminution de la limite,
les événements les plus anciens en excès sont supprimés immédiatement.

**Effacer l’historique** demande une confirmation indiquant que l’opération est
irréversible. Cette action ne touche jamais les alertes actives, à venir ou
acquittées.

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
Les entités créées par Alert Manager sont aussi refusées comme sources de règles
personnalisées, y compris lorsqu’elles ont été renommées dans Home Assistant.

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

### Édition visuelle et YAML

L’éditeur visuel reste le mode par défaut. Dans le volet de création ou de
modification, ouvrir le menu trois points en haut à droite puis choisir
**Modifier en YAML**. Le même volet affiche alors l’éditeur YAML Home Assistant ;
**Modifier visuellement** analyse et valide le YAML avant de remplir le
formulaire. Un YAML invalide reste dans l’éditeur YAML et n’est jamais
enregistré. L’identifiant d’une règle existante reste géré par le backend,
immuable et volontairement absent du YAML éditable.

```yaml
name: Température baie élevée
enabled: true
entity_ids:
  - sensor.hygrometrie_baie_informatique_temperature
source: state
operator: above
value: 33
duration: 900
message: null
```

`entity_ids` est une liste obligatoire : chaque source est suivie
indépendamment. `source` vaut `state` ou `attribute` ; `attribute` est requis
uniquement dans ce second cas. `duration` est exprimée en secondes. `equals`,
`not_equals`, `contains` et `not_contains` acceptent une valeur scalaire ou une
liste YAML ; `above` et `below` exigent une unique valeur numérique finie. Cette
syntaxe ne correspond volontairement **pas** aux conditions YAML des
automatisations Home Assistant : aucun template, groupe `and`/`or`/`not`, aucune
condition arbitraire et aucun moteur de conditions d’automatisation ne sont
utilisés.

### Export et import complet de configuration

Dans **Configuration**, les actions **Exporter en YAML** et
**Importer un YAML** gèrent la configuration entière. L’export télécharge
`alert-manager-config.yaml`, encodé en UTF-8, avec le format `version: 1`, les
paramètres généraux, tags d’exclusion, délais globaux et particuliers,
état du switch de surveillance, configuration des packs automatiques et toutes
les règles personnalisées. Les
identifiants internes des règles ne sont pas exportés et sont recréés par le
backend lors de l’import. Il n’exporte jamais les alertes actives ou à venir,
acquittements, timers, dates de détection/activation ni historique d’exécution.
La limite de rétention et les événements historiques ne sont ni exportés ni
importés : un import conserve le réglage et l’historique locaux.

L’import n’accepte que les versions complètes supportées et refuse les champs
inconnus, dupliqués ou runtime. Le fichier est validé intégralement avant toute
écriture, affiche le nombre de règles, packs activés et délais particuliers, puis
demande une confirmation explicite. **L’import remplace entièrement la
configuration actuelle : ce n’est pas une fusion.** Les alertes runtime ne sont
réconciliées qu’après un import valide et la persistance est atomique. Un export
V1.5 dépourvu de `monitoring_enabled` reste accepté et active la surveillance par
défaut.

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

## Appareil et switch de surveillance

L’appareil de service `Alert Manager - Général`, identifié de façon stable par la
catégorie `main`, regroupe les quatre entités de cette version :

- `switch.alert_manager_main_monitoring` ;
- `sensor.alert_manager_main_active` ;
- `sensor.alert_manager_main_pending` ;
- `sensor.alert_manager_main_acknowledge`.

Le switch est actif par défaut et son état est stocké avec la configuration. À
`off`, le moteur ne crée plus d’alerte, ne fait pas progresser les alertes
`pending`, gèle leur temps restant, annule leurs timers et conserve toutes les
occurrences existantes. Les trois capteurs affichent alors `0` avec une liste
`alerts` vide, sans effacer les données internes. Le panneau affiche un
avertissement avec un bouton de réactivation. À `on`, le décompte reprend au même
point, la situation courante est réévaluée, les timers utiles sont recréés une
seule fois et seules les transitions réelles émettent un événement.

Si l’intégration est chargée alors que le switch est désactivé, Home Assistant
crée la notification persistante
`alert_manager_main_monitoring_disabled`. Elle indique comment réactiver
`Surveillance Alert Manager`, ne se duplique pas lors des rechargements et est
supprimée dès la reprise.

## Capteurs, attributs et migration V1.5

`sensor.alert_manager` est supprimé du registre des entités lors de la migration
et remplacé sans capteur de compatibilité durable :

| Nouvelle entité | État | Contenu de `attributes.alerts` |
| --- | ---: | --- |
| `sensor.alert_manager_main_active` | nombre d’actives non acquittées | actives non acquittées uniquement |
| `sensor.alert_manager_main_pending` | nombre d’alertes à venir | `pending` uniquement |
| `sensor.alert_manager_main_acknowledge` | nombre d’actives acquittées | actives acquittées uniquement |

Une occurrence n’apparaît jamais dans deux capteurs. Chaque capteur n’expose
qu’un attribut `alerts`, toujours une liste. Exemple d’alerte de règle :

```yaml
state: 1
attributes:
  alerts:
    - id: rule:4f9d…:sensor.baie_temperature
      type: rule
      rule_id: 4f9d…
      rule_name: Température baie élevée
      entity_id: sensor.baie_temperature
      name: Température baie
      device_id: 0123456789abcdef0123456789abcdef
      device_name: Sonde baie
      area: Bureau
      integration: mqtt
      value: 34.2
      unit: °C
      condition: État supérieur à 33 °C pendant 15 min
      condition_key: rule.generated
      condition_params:
        source: state
        attribute: null
        operator: above
        expected: "33"
        unit: °C
        duration: 900
      detected_at: "2026-08-26T10:00:00+02:00"
      due_at: "2026-08-26T10:15:00+02:00"
      delay: 900
      active_since: "2026-08-26T10:15:00+02:00"
      acknowledged: false
```

Une alerte `pending` n’a ni `active_since` ni champ d’acquittement ; son temps
restant se calcule à partir de `due_at`. Une alerte acquittée ajoute
`acknowledged: true`, `acknowledged_at` et, lorsqu’un utilisateur est connu,
`acknowledged_by`. Les champs `rule_id` et `rule_name` ne sont présents que pour
les règles personnalisées. Les métadonnées d’appareil, de zone, d’intégration et
d’unité restent facultatives. Aucun historique résolu, groupe visuel ou compte à
rebours périodique n’est enregistré dans les attributs.

Les automatisations et cartes qui lisaient `sensor.alert_manager` doivent cibler
le nouveau capteur correspondant et remplacer les anciennes listes `alerts`,
`pending` ou `acknowledge` par l’unique `attributes.alerts`. Par exemple :

```jinja
{{ state_attr('sensor.alert_manager_main_pending', 'alerts') | default([], true) }}
```

Exemple d’automatisation basée sur le nouveau compteur actif :

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.alert_manager_main_active
    above: 0
actions:
  - action: persistent_notification.create
    data:
      title: Alert Manager
      message: >-
        {{ states('sensor.alert_manager_main_active') }} alerte(s) active(s)
```

## Acquittement et services

L’acquittement porte toujours sur une seule alerte `active`, ciblée par son
identifiant stable. Il ne résout pas l’alerte, mais la retire du compteur des
alertes non acquittées. Une
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

L’intégration n’envoie aucune notification d’alerte. La seule notification créée
directement est l’avertissement de sécurité lorsque la surveillance est encore
désactivée au chargement.

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
- **Aucune alerte ne progresse** : vérifier que
  `switch.alert_manager_main_monitoring` est à `on`.
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
planifié par alerte en attente. Les capteurs ne sont réécrits que si leur contenu
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
- pas d’export CSV de l’historique ;
- pas de template Jinja, condition combinée ou hystérésis, y compris en YAML ;
- pas d’import automatique des anciennes automatisations ;
- pas de notification d’alerte directe, application mobile, add-on, MQTT ou
  entité par alerte ;
- aucune action métier dans l’Historique ;
- configuration réservée aux administrateurs ;
- interface fournie uniquement en français et en anglais dans cette version.
