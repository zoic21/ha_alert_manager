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
- **Des profils de notification facultatifs** pour les nouvelles alertes, rappels et retours à la normale, avec regroupement et exceptions par étiquette.
- **Recherche, filtres, tri, groupement et colonnes personnalisables**, avec une vue adaptée au mobile.
- **Des exclusions et temporisations** pour éviter que les situations normales ou les micro-coupures deviennent du bruit.
- **L’export YAML et des sauvegardes automatiques de la configuration**, avec une récupération guidée si la configuration enregistrée devient invalide.
- **Des entités et événements Home Assistant** pour alimenter vos propres dashboards et automatisations de notification.
- **Une interface en français et en anglais**.

Utilisez les profils intégrés pour envoyer des notifications via les entités `notify` natives de Home Assistant sans écrire d’automatisation, ou conservez vos propres automatisations basées sur les événements. Vous choisissez qui notifier, comment et quand.

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

Les sources **Transition** (`source: transition`) et **Transition attribut** (`source: attribute_transition`, avec `attribute`) observent un passage précis `from_value` → `to_value`. Le délai de déclenchement (`duration`, 0 seconde par défaut) impose un maintien continu à la valeur d’arrivée avant activation. Quitter cette valeur annule le maintien et nécessite une nouvelle transition correspondante. Les modifications d’autres attributs ne relancent pas le délai.

`auto_resolve` (600 secondes par défaut, minimum 1) démarre à l’activation. Quitter ensuite la valeur d’arrivée ne résout pas l’alerte. Une nouvelle transition confirmée prolonge l’échéance de la même alerte et conserve son acquittement. Les détails et l’historique conservent les valeurs observées et la dernière transition ; l’expiration est indiquée comme automatique et n’envoie aucune notification de retour à la normale. Le routage des nouvelles alertes et des rappels reste applicable.

La découverte initiale, le rechargement et la période de démarrage ne déduisent aucune transition. Les états unknown/unavailable et les attributs absents ne peuvent pas amorcer un maintien. Les maintiens en cours ne sont pas restaurés et une pause de surveillance nécessite une nouvelle transition ; les échéances actives/acquittées survivent au redémarrage. Le testeur indique qu’une valeur actuelle ne prouve pas un passage et ne modifie pas les alertes.

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

## Carte de dashboard

L’intégration ajoute **Alert Manager** au sélecteur de cartes du dashboard. Aucune
installation frontend HACS séparée ni ressource Lovelace manuelle n’est nécessaire.
Actualisez le navigateur après l’installation ou une mise à jour. La carte nécessite
un compte administrateur, comme le panneau Alert Manager.

L’éditeur visuel propose un nombre maximal de tuiles (5 par défaut, de 1 à 100) et un
filtre facultatif par étiquette. Les étiquettes correspondent à celles du pack/de la
règle ou de l’entité, comme dans le panneau. Les alertes actives non acquittées sont
filtrées puis regroupées par équipement avant application de la limite. Une alerte
ouvre son détail ; une tuile regroupée ouvre la liste filtrée sur l’équipement.
Le lien de débordement ouvre les alertes correspondant au filtre.

Les tuiles sont limitées à 300 px et passent à la ligne sur les écrans étroits.
L’éditeur propose aussi un alignement gauche/centre/droite (gauche par défaut) et une
couleur RVB facultative pour les icônes. Sans couleur personnalisée, le thème Home
Assistant s’applique.

```yaml
type: custom:alert-manager-card
max_tiles: 5
alignment: left
# icon_color: [255, 152, 0]
# Identifiant d’étiquette Home Assistant facultatif :
# label: maintenance
```

Sans alerte correspondante, la carte se masque via le mécanisme natif Home Assistant,
y compris son conteneur dans les vues standard Sections et Masonry. Les cartes de mise
en page personnalisées peuvent gérer la visibilité différemment. Le chargement, le
démarrage, la surveillance désactivée et l’indisponibilité restent visibles.
Un exemple sans données réelles apparaît uniquement dans l’éditeur.


## Surveillance automatique

Ouvrez **Configuration → Surveillance automatique** pour activer et configurer les packs qui surveillent les problèmes courants de Home Assistant :

| Surveillance | Condition d’alerte |
| --- | --- |
| Entités indisponibles | l’entité reste `unavailable` |
| Connectivité | un `binary_sensor` avec `device_class: connectivity` reste à `off` |
| Batterie faible | un capteur de batterie atteint le seuil configuré |
| UniFi | un `device_tracker` UniFi reste absent de `home` |
| Automatisations et scripts en erreur | une exécution d’`automation` ou de `script` se termine en erreur |
| Flapping / instabilité | la même anomalie se répète dans une fenêtre de détection |

Chaque surveillance peut être activée indépendamment. Les délais et exclusions se règlent depuis l’interface, et les seuils de batterie peuvent être adaptés lorsque certains appareils ont besoin de limites différentes.

Chaque pack peut porter des étiquettes Home Assistant (`automatic.<pack>.label_ids` en YAML), afin de sélectionner ses alertes dans les profils de notification et les exceptions par étiquette. Modifier les étiquettes d’un pack actualise ses alertes en cours ; l’historique conserve celles enregistrées à la résolution de l’alerte.

La surveillance des erreurs d’automatisation et de script n’a aucun délai par défaut. Une exécution suivante terminée avec succès résout l’alerte. Pour certaines automatisations ou certains scripts, il est possible d’exiger plusieurs cycles d’exécution consécutifs en erreur avant de la déclencher.

Le pack Flapping détecte les anomalies brèves mais répétées par source et entité, même si elles disparaissent avant le délai de déclenchement habituel. Il est désactivé par défaut : 5 occurrences en 1 heure déclenchent une alerte distincte, résolue après 30 minutes sans nouvelle occurrence. Ces réglages sont ajustables globalement, par pack source, par entité ou par règle personnalisée. Les packs Entités indisponibles et Connectivité sont présélectionnés comme sources ; les packs sources doivent être activés et les règles personnalisées peuvent participer via leur option de flapping.

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

Le bouton **Tester** de l’éditeur visuel évalue le brouillon sur les valeurs actuelles et affiche, pour chaque entité, la valeur lue, les résultats de comparaison et de condition Jinja, le message rendu et les erreurs éventuelles. Il indique aussi tous les profils qui notifieraient une nouvelle alerte pour chaque entité, selon les étiquettes du brouillon, de l’entité et de l’appareil, les profils activés et leurs exceptions ordonnées. Cet aperçu reste conditionnel au déclenchement réel et respecte le délai configuré. Le test n’enregistre rien, ne modifie pas les alertes ou leurs temporisations et n’envoie pas de notification. Pour une règle de variation sans référence compatible, le résultat reste indéterminé.

Les règles peuvent porter des étiquettes Home Assistant (`label_ids` en YAML), affichées dans le tableau. Pour les notifications, elles complètent les étiquettes de l’entité et de l’appareil : elles servent au filtre du profil et aux exceptions par étiquette.

Les champs de durée du panneau utilisent le sélecteur natif de Home Assistant (heures, minutes et secondes), y compris les réglages particuliers facultatifs et les rappels de notification. La configuration et le YAML conservent les valeurs en secondes ; vider une durée facultative conserve son comportement d’héritage ou de désactivation.

Sur ordinateur, la largeur des volets de règles et de configuration est redimensionnable. Ils s’adaptent aux écrans mobiles et demandent confirmation avant d’abandonner les modifications à la fermeture.

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

Lorsque ZHA est entièrement chargé, le même scan vérifie aussi les adresses `device_ieee` statiques des déclencheurs `zha_event` et des étapes `wait_for_trigger` des automatisations et scripts (syntaxes moderne et historique). Il vérifie l’enregistrement dans le registre Home Assistant pour ZHA, pas la disponibilité ni l’appartenance actuelle au réseau radio : les équipements désactivés, les télécommandes sans entités et les anciens équipements encore enregistrés sont considérés présents. Les autres intégrations Zigbee ne satisfont pas ces références. Les templates, entrées de blueprint et IEEE mal formés sont ignorés ; les blueprints ne sont pas développés. Sans ZHA, le contrôle ne s’applique pas ; si le chargement est incomplet ou les métadonnées indisponibles, le rapport indique un contrôle non exécuté sans signaler d’équipements manquants. Une adresse IEEE exacte peut être ignorée avec les exclusions de références existantes dans Configuration.

Lorsqu’un problème est trouvé, Alert Manager indique d’où il vient et permet, lorsque c’est possible, d’ouvrir directement l’automatisation, le script, le dashboard, le template ou l’autre objet Home Assistant concerné. Les résultats sont conservés entre les redémarrages et sont également exposés via `sensor.alert_manager_coherence_issue`, ce qui permet de surveiller l’échec d’un contrôle de cohérence comme n’importe quel autre problème.

Les analyses peuvent être lancées à la demande ou automatiquement chaque jour, chaque semaine ou chaque mois. L’analyse du dossier ESPHome peut être désactivée et certaines références connues peuvent être ignorées depuis la configuration.

Cette page donne également accès aux 50 dernières entités supprimées encore conservées par Home Assistant, avec leur date de suppression et leur intégration. La liste est lue directement dans le registre d’entités de Home Assistant : Alert Manager ne maintient pas son propre historique des suppressions.

Activez **Créer une alerte en cas d’incohérence** dans **Configuration → Analyse de cohérence** pour conserver une alerte immédiate tant que des problèmes subsistent. Elle utilise l’acquittement, l’historique et les profils de notification habituels. Les contrôles suivants mettent à jour la même alerte ; seul un contrôle complet confirmant le retour à la normale la résout. Un contrôle échoué ou incomplet ne peut pas la supprimer. L’activation reprend le dernier rapport sans lancer de contrôle ; la désactivation retire l’alerte et ses rappels sans annoncer un rétablissement. L’option est désactivée par défaut et disponible sous `coherence_alert_enabled` dans le YAML de configuration.

## Export et récupération de la configuration

Chaque volet de configuration propose aussi un **mode YAML** dans son menu à trois points : réglages particuliers des packs (seuils de batterie, erreurs d’exécution et instabilité), exclusions d’entités ou d’appareils et délais par entité. Le YAML contient uniquement le champ édité dans ce volet, avec les mêmes clés que les exports de configuration et des durées en secondes. Le changement d’éditeur conserve les valeurs non enregistrées et l’ordre des listes. Un YAML invalide, des champs inconnus ou des réglages invalides bloquent l’enregistrement et le retour au mode visuel ; fermer un volet modifié demande confirmation. Utilisez **Enregistrer** pour appliquer les changements. Les volets de détail et de diagnostic en lecture seule ne sont pas modifiables.

La configuration complète peut être exportée et importée en YAML. Alert Manager conserve également les trois derniers exports quotidiens valides de la configuration. Ils peuvent être téléchargés ou restaurés depuis la page Configuration.

Si la configuration enregistrée ne peut pas être chargée au démarrage, Alert Manager démarre de façon sûre avec les valeurs par défaut, affiche un avertissement persistant et laisse un administrateur choisir une sauvegarde. Aucune restauration n’est effectuée silencieusement. La restauration d’une sauvegarde complète remplace la configuration actuelle, les alertes en cours et l’historique.

## Cycle de vie d’une alerte

Une alerte peut être :

- **À venir** tant que sa temporisation est encore en cours ;
- **Active** lorsque la condition est présente depuis suffisamment longtemps ;
- **Acquittée** lorsque vous avez pris connaissance du problème mais qu’il n’est pas encore résolu ;
- **Résolue** lorsque la condition anormale disparaît.

Les alertes résolues peuvent être conservées dans l’historique, ce qui permet de repérer les problèmes récurrents au lieu de seulement voir ce qui ne va pas à l’instant présent.

Lorsque des occurrences sont conservées, le détail d’une alerte affiche leur nombre cliquable. Un clic ouvre l’historique filtré par l’identifiant stable de l’alerte ; ce filtre peut être modifié ou supprimé.

Le bouton **Statistiques** dans Historique classe les alertes, entités, appareils, intégrations ou règles sur les **7 ou 30 derniers jours**, avec le nombre d’occurrences et les durées actives totale et moyenne. Le calcul est réalisé à la demande à partir de l’historique résolu conservé, indépendamment des filtres du tableau historique ; les durées sont limitées à la période et incluent le temps acquitté. Les alertes simultanées sont cumulées séparément : le total ne mesure pas l’indisponibilité d’un appareil. L’historique supprimé ou expiré et les alertes en cours sont exclus. Une synthèse affiche les occurrences, les entités et appareils concernés, et la durée cumulée. L’entité, l’appareil et l’intégration les plus fréquents sont mis en avant, avec indication des ex æquo. Cliquer sur une ligne ou un élément mis en avant ouvre l’historique correspondant ; les filtres habituels de catégorie et de période d’activité du tableau permettent de modifier ou réinitialiser la sélection.

Sélectionnez des lignes du tableau Historique, ou utilisez **Supprimer** dans le menu du détail d’une occurrence passée, pour les supprimer après confirmation sans affecter les alertes en cours.

Un clic sur une alerte ouvre son détail, notamment la valeur qui l’a déclenchée et sa valeur actuelle, avec un accès contextuel à l’entité Home Assistant concernée lorsqu’il est disponible. Les valeurs numériques respectent la précision d’affichage de l’entité et le format numérique de l’utilisateur dans Home Assistant, sans modifier les valeurs enregistrées.

Utilisez **Réévaluer** dans le menu du détail d’une alerte en cours pour vérifier à nouveau l’état actuel de son entité. Cette action réévalue aussi les autres alertes de cette entité, préserve les délais et protections habituels et résout les alertes via le fonctionnement normal de l’historique et des notifications. La surveillance doit être activée et le démarrage terminé.

## Être notifié sans être spammé

### Profils de notification intégrés

Dans **Configuration → Notifications**, créez un profil nommé, sélectionnez une ou plusieurs **entités `notify`** et choisissez les envois pour les nouvelles alertes et les retours à la normale. Les rappels peuvent être désactivés ou répétés selon un intervalle configurable d’au moins une minute. Chaque profil peut être activé indépendamment.

Le menu à trois points du profil permet de passer entre l’éditeur visuel et le **mode YAML**, exceptions ordonnées comprises. L’interrupteur sans libellé dans l’en-tête active ou désactive le profil. Un YAML invalide bloque l’enregistrement et le retour à l’éditeur visuel ; fermer un éditeur modifié demande confirmation.

Le même menu propose **Dupliquer** pour préparer une copie indépendante avec un nom suggéré, en conservant les destinataires, les réglages et l’ordre des exceptions. La copie n’est créée qu’à l’enregistrement ; les compteurs d’utilisation et l’état des notifications en cours ne sont pas copiés.

Enregistrez le profil, puis utilisez **Tester** dans son menu à trois points pour envoyer une vraie notification de test à ses destinataires sans créer d’alerte. Les profils acceptent des entités de notification, pas des actions ou scripts arbitraires ; les canaux disponibles uniquement sous forme d’action restent utilisables dans vos propres automatisations.

### Étiquettes et exceptions

Un profil peut couvrir toutes les alertes ou seulement celles qui correspondent à au moins une étiquette sélectionnée. La sélection combine les étiquettes de l’entité, de son appareil et de la règle personnalisée ou du pack automatique à l’origine de l’alerte.

Les exceptions exigent que **toutes les étiquettes sélectionnées correspondent (ET)** et remplacent les réglages de nouvelle alerte, de retour à la normale ou de rappel. La **première exception correspondante dans l’ordre de la liste** est prioritaire ; les paramètres laissés en héritage conservent les valeurs par défaut du profil. En YAML, les exceptions utilisent `selector_ids` ; les anciennes exceptions à une étiquette utilisant `selector_id` restent acceptées.

### Regroupement, rappels et navigation mobile

Les notifications de nouvelle alerte et de retour à la normale sont regroupées séparément par profil. Le délai global de regroupement est de **30 secondes par défaut**, réglable entre **10 et 300 secondes**. Les nouveaux lots utilisent ce délai ; ceux déjà en attente conservent leur échéance. Si une alerte se résout avant l’envoi de sa notification initiale en attente, cette paire nouvelle alerte/retour à la normale non envoyée est supprimée.

Les rappels arrivés à échéance sont regroupés par profil et s’arrêtent lorsqu’une alerte est acquittée ou résolue. Après un redémarrage, ils attendent la fin de la réconciliation des alertes. Seules les alertes confirmées reprennent leurs rappels ; une échéance déjà dépassée repart sur l’intervalle du profil, sans rattrapage des rappels manqués.

Les titres distinguent les **🚨 nouvelles alertes**, les **🔔 rappels** et les **✅ retours à la normale**. Avec une cible compatible de l’application Home Assistant Companion, toucher une notification ouvre le détail d’une alerte en cours unique, la vue d’ensemble pour plusieurs alertes en cours ou l’**Historique** pour les retours à la normale. L’envoi générique transmet le titre et le message sans ajouter d’URL de navigation brute au texte.

### Suivi des notifications par alerte

Chaque profil affiche ses envois réussis pour l’heure courante et les 23 heures précédentes (fenêtre d’environ 24 heures), depuis le démarrage de l’intégration. Ces compteurs restent uniquement en mémoire et sont remis à zéro au redémarrage/rechargement. Un envoi groupé compte une seule fois même avec plusieurs destinataires ; les tests et les échecs complets sont exclus.

Les détails d’une alerte affichent les notifications de ses profils intégrés : nombre d’envois (rappels compris), profils correspondants même sans rappel et date du dernier envoi. Un lot compte une fois par profil et par alerte, dès qu’au moins une cible a été notifiée ; les tests et les échecs complets sont exclus. L’historique conserve séparément les envois de retour à la normale, leurs profils et leur dernière date. Ces informations survivent aux redémarrages ; elles sont masquées pour les alertes à venir et les anciens envois ne sont pas reconstitués. Les notifications envoyées par des automatisations externes ne sont pas comptabilisées.

### Utiliser vos propres automatisations de notification

Les profils intégrés sont facultatifs. Les événements Home Assistant par alerte restent disponibles pour vos propres automatisations de notification.

## Entités et événements Home Assistant

Alert Manager expose plusieurs entités afin que son état puisse aussi être utilisé en dehors du panneau intégré :

- `switch.alert_manager_main_monitoring`
- `sensor.alert_manager_main_active`
- `sensor.alert_manager_main_pending`
- `sensor.alert_manager_main_acknowledge`
- `sensor.alert_manager_coherence_issue`

Événements utiles :

- `alert_manager_alert_started`
- `alert_manager_alert_resolved`
- `alert_manager_alert_acknowledged`
- `alert_manager_alert_unacknowledged`

L’acquittement est également disponible via `alert_manager.acknowledge` et `alert_manager.unacknowledge`.

Le menu ⋮ de la fiche d’une alerte active propose aussi **Acquitter temporairement…** : 15 min, 30 min, 1 h, 24 h ou une durée personnalisée en minutes, heures ou jours (maximum un an). La fiche reste ouverte et affiche le temps restant, avec la date exacte au clic. L’acquittement normal reste sans limite de durée.

À l’échéance, une alerte toujours en cours redevient active sans changer d’identité ni de date de début. Les profils autorisant l’envoi des nouvelles alertes sont notifiés à nouveau, même sans rappel configuré. Une résolution ou un désacquittement manuel annule l’échéance. Celle-ci survit au redémarrage et est traitée après la réconciliation de démarrage ; si la surveillance est désactivée, elle attend sa réactivation sans décaler la date prévue.

### Diagnostic de fonctionnement

La configuration propose un bloc compact indiquant le nombre d’évaluations des règles personnalisées, leurs temps moyen/maximal/total, les transitions d’alertes et les envois de profils réussis. Une évaluation mesurée correspond à un couple règle/entité, condition comprise, sans attente asynchrone. Les tests, packs automatiques et scans de cohérence sont exclus des temps ; ce n’est pas une mesure de la charge de la boucle événementielle de Home Assistant. L’activité compte les transitions réelles (y compris les occurrences répétées), pas les alertes présentes ; les activations immédiates ne comptent pas comme passages à venir et les alertes restaurées ne sont pas recomptées. Exactement 24 agrégats horaires restent en mémoire, sans échantillons, persistance ni timer de rotation. La période affichée commence au démarrage de l’intégration ou au début de la plus ancienne heure conservée, selon la date la plus récente.

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
