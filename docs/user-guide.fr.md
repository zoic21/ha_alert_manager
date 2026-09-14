# Guide utilisateur Alert Manager

[Présentation et installation](../README.fr.md) · [English](user-guide.md)

## Surveillance automatique

Ouvrez **Configuration → Surveillance automatique** pour configurer les packs. Chacun peut être activé indépendamment et porter des étiquettes Home Assistant pour le filtrage et les notifications.

| Pack | Condition |
| --- | --- |
| Entités indisponibles | Une entité reste `unavailable`. |
| Connectivité | Un `binary_sensor` avec `device_class: connectivity` reste à `off`. |
| Batterie faible | Un capteur de batterie atteint le seuil configuré, 15 % par défaut. |
| UniFi | Un `device_tracker` du réseau UniFi reste absent de `home`. |
| Erreurs d’automatisation et de script | Une exécution se termine en erreur ; une exécution terminée avec succès résout l’alerte. |
| Flapping / instabilité | La même anomalie se répète dans une fenêtre de détection. |

Utilisez le délai global, les délais par pack et par entité ainsi que les exclusions par entité, équipement ou étiquette pour éviter les alertes sur des situations attendues. Les seuils de batterie peuvent être adaptés par équipement. Les erreurs d’automatisation ou de script n’ont aucun délai par défaut ; certaines entités peuvent nécessiter plusieurs cycles d’exécution consécutifs en erreur.

Le flapping est désactivé par défaut. Ses réglages sont **5 occurrences en 1 heure**, puis un retour à la normale après **30 minutes sans nouvelle occurrence**. Il peut détecter les anomalies brèves qui disparaissent avant le délai normal. Les sources présélectionnées sont l’indisponibilité et la connectivité ; leurs packs doivent être activés. Les réglages sont adaptables globalement, par pack source, par entité ou par règle personnalisée. Les détails conservent les dates des occurrences dans une section repliable, y compris dans l’historique résolu.

Modifier les étiquettes d’un pack actualise les alertes en cours ; l’historique conserve celles présentes à la résolution. Les étiquettes des règles complètent celles des entités et équipements pour les notifications ; elles ne sélectionnent pas dynamiquement les entités surveillées par une règle.

## Règles personnalisées

Créez les règles dans **Règles personnalisées**, avec l’éditeur visuel ou YAML. Une configuration accepte jusqu’à **500 règles**, avec **50 entités par règle**. Chaque entité sélectionnée est surveillée indépendamment. Les règles peuvent être dupliquées, porter des étiquettes Home Assistant et utiliser un message Jinja personnalisé.

| Opération | Source YAML | Utilisation |
| --- | --- | --- |
| Valeur | `value` | Comparer un état ou attribut : égalité, texte, seuil numérique, entre/dehors ou valeur inchangée. |
| Variation | `value_variation` | Mesurer une variation numérique depuis la référence enregistrée quand une condition Jinja devient vraie. |
| Transition | `value_transition` | Observer un passage précis `from_value` → `to_value`. |
| Aucun changement | `unchanged` | Détecter une entité qui ne se met plus à jour. |
| Jinja | `jinja` | Utiliser un template comme condition complète de la règle. |

Pour Valeur, Variation et Transition, `attribute` absent ou vide cible l’état ; renseigné, il cible cet attribut. Un attribut absent ne revient jamais à l’état. Les chemins imbriqués sont pris en charge ; les jokers comme `data.*.key` sont réservés aux comparaisons classiques.

`duration` impose le maintien de la condition. Les champs de durée utilisent le sélecteur heures/minutes/secondes de Home Assistant ; le YAML reste exprimé en secondes. Les messages sont figés à l’activation par défaut ; `update_message_when_active` permet leur actualisation tant que l’alerte reste active.

Le bouton **Tester** évalue le brouillon non enregistré sur les valeurs réelles et affiche comparaison, condition Jinja, message, erreurs et profils qui notifieraient une nouvelle alerte pour chaque entité. Il n’enregistre rien, ne modifie ni les alertes ni leurs délais et n’envoie aucune notification. Une variation sans référence compatible reste indéterminée ; une valeur actuelle ne suffit pas à prouver une transition.

Une erreur de rendu Jinja est indéterminée, pas un retour à la normale : elle conserve les alertes, échéances en attente et dernier message valide. Un changement d’une dépendance relance l’évaluation. Pour une variation, seule une condition explicitement fausse termine la fenêtre de référence. Les erreurs apparaissent dans le testeur et les journaux.

Les anciennes sources YAML sont migrées à l’import : `state`/`attribute` vers `value`, les variantes de variation vers `value_variation`, celles de transition vers `value_transition`, et `none` vers `jinja`. Utilisez les noms normalisés des exemples pour les nouvelles règles.

### Comportement des transitions

Une règle de transition nécessite un passage réellement observé ; la découverte initiale, le rechargement et le démarrage n’en déduisent pas. Un état unknown/unavailable ou un attribut absent ne peut pas amorcer un maintien.

Avec `duration` supérieur à zéro, la valeur d’arrivée doit être conservée pendant ce délai. La quitter annule le maintien ; modifier un autre attribut ne relance pas le délai. Après activation, l’alerte expire au bout de `auto_resolve` secondes (**600 par défaut**, minimum 1), même si l’état change ensuite. Une nouvelle transition confirmée prolonge l’échéance de la même alerte et conserve son acquittement.

L’expiration automatique est enregistrée dans l’historique mais n’envoie **aucune notification de retour à la normale**. Les notifications d’activation et rappels restent applicables. Les maintiens non confirmés ne survivent pas à un redémarrage ou une pause de surveillance ; les échéances actives/acquittées survivent aux redémarrages. Après une pause, une nouvelle activation nécessite une nouvelle transition.

### Exemples

Remplacez les identifiants d’entités par les vôtres. Ces exemples se collent dans l’éditeur YAML d’une règle.

#### Consommation élevée pendant deux heures

```yaml
name: "Consommation du réfrigérateur"
enabled: true
entity_ids:
  - sensor.fridge_power
source: value
operator: above
value: "200"
duration: 7200
```

#### Un thermostat qui chauffe sans réchauffer la pièce

La référence est enregistrée quand le thermostat indique `hvac_action: heating`. La règle déclenche après deux heures si la température a augmenté de moins de 0,2 °C. Dans le message, `value` est la variation mesurée.

```yaml
name: "Efficacité du chauffage"
enabled: true
entity_ids:
  - climate.living_room
source: value_variation
attribute: current_temperature
operator: below
value: "0.2"
duration: 7200
condition_template: "{{ state_attr(entity_id, 'hvac_action') == 'heating' }}"
message: "Le chauffage est actif depuis 2 h, mais la température n’a augmenté que de {{ value | float(0) | round(1) }} °C."
update_message_when_active: false
```

#### Messages Bayrol avec filtrage des états attendus

La comparaison examine les clés des messages du tableau `data`, tandis que la condition Jinja exige la présence de débit.

```yaml
name: "Alerte Bayrol"
enabled: true
entity_ids:
  - sensor.bayrol_messages
source: value
attribute: data.*.key
operator: not_contains
value:
  - al_no_flow_bnc
  - al_start_delay
  - enjoy
duration: 5400
condition_template: "{{ is_state('binary_sensor.bayrol_flow_contact', 'on') }}"
message: >-
  {% for item in state_attr(entity_id, 'data') or [] %}
    {% if item.key not in ['al_no_flow_bnc', 'enjoy', 'al_start_delay'] %}
      {{ item.message | replace('\n', ' ') }}
    {% endif %}
  {% endfor %}
update_message_when_active: false
```

#### Fin de cycle visible pendant dix minutes

```yaml
name: "Cycle de lavage terminé"
enabled: true
entity_ids:
  - sensor.washing_machine_state
source: value_transition
from_value: running
to_value: finished
duration: 0
auto_resolve: 600
```

## Carte de dashboard

L’intégration ajoute **Alert Manager** au sélecteur de cartes. Aucune installation frontend HACS supplémentaire ni ressource Lovelace manuelle n’est nécessaire. Actualisez le navigateur après une installation ou une mise à jour.

```yaml
type: custom:alert-manager-card
max_tiles: 5
alignment: left
# icon_color: red
# label: maintenance
```

`max_tiles` accepte 1 à 100 (5 par défaut). `alignment` accepte `left`, `center` ou `right`. `icon_color`, facultatif, utilise la palette native Home Assistant ; sinon, le thème s’applique. `label` est un identifiant d’étiquette Home Assistant. Ces options sont aussi disponibles dans l’éditeur visuel.

Les alertes actives non acquittées correspondant au filtre sont regroupées par équipement avant application de la limite. Une tuile d’alerte unique ouvre son détail ; une tuile regroupée ouvre la liste filtrée sur l’équipement. La bulle **+N** ouvre les alertes correspondantes et compte les alertes restantes, pas les équipements. Les tuiles passent à la ligne sur écran étroit et sont limitées à 300 px.

Sans alerte correspondante, la carte et son conteneur se masquent dans les vues standard Sections et Masonry ; les mises en page personnalisées peuvent se comporter différemment. Au démarrage, les alertes actives connues restent visibles avec un **sablier** pendant leur réévaluation. Il partage la bulle de débordement et ouvre l’Accueil filtré. Sur mobile, la bulle reste à côté de la dernière alerte visible, qui se rétrécit pour lui laisser la place. Un démarrage sans alerte correspondante n’affiche rien.

Le chargement, la surveillance désactivée et l’indisponibilité restent visibles. Les exemples d’alertes n’apparaissent que dans l’éditeur, hors démarrage. Tous les utilisateurs connectés peuvent lire la carte, l’Accueil, l’Historique, les détails et les statistiques historiques. Les autres onglets et toutes les modifications, dont l’acquittement, nécessitent un administrateur ; les autres utilisateurs ne chargent pas la configuration de l’intégration.

## Cycle des alertes et historique

Une alerte est **À venir** pendant son délai, **Active** après confirmation, **Acquittée** quand le problème est connu mais pas résolu, puis **Résolue** lorsque sa condition disparaît. Les alertes acquittées restent visibles mais ne comptent plus comme actives. Une condition en attente qui disparaît n’entre pas dans l’historique.

Désactiver la surveillance suspend la détection et les délais en attente, expose des compteurs à zéro et reporte le traitement des expirations d’acquittement temporaire jusqu’à la reprise. La reprise évalue les conditions actuelles sans créer de doublons.

Les tableaux proposent recherche, filtres, tri, groupement par équipement, colonnes personnalisables et sélection multiple. Les détails affichent les valeurs au déclenchement et actuelles, un accès contextuel à l’entité, les notifications et un compteur cliquable d’occurrences précédentes. Ce compteur ouvre l’Historique filtré sur le même identifiant stable d’alerte.

**Réévaluer**, dans le menu d’une alerte en cours, vérifie l’état actuel de son entité, y compris ses autres alertes. Les délais et protections habituels sont conservés ; la surveillance doit être activée et le démarrage terminé. Sélectionnez des entrées d’historique, ou utilisez **Supprimer** dans leurs détails, pour effacer des occurrences après confirmation sans modifier les alertes en cours.

### Acquittement temporaire

Le menu des détails propose **Acquitter temporairement…** pour 15 min, 30 min, 1 h, 24 h ou une durée personnalisée jusqu’à un an. Le temps restant est affiché ; un clic donne l’échéance exacte. L’acquittement classique n’a pas de limite.

À l’expiration, une alerte toujours présente redevient active avec le même identifiant et la même date de début. Les profils autorisant les notifications de nouvelle alerte peuvent notifier à nouveau, même sans rappels configurés. Une résolution ou un désacquittement manuel annule l’échéance. Elle survit au redémarrage et est traitée après la réconciliation ; une pause de surveillance ne la décale pas.

### Statistiques historiques

Utilisez **Statistiques** dans l’Historique pour classer alertes, entités, équipements, intégrations ou règles sur **7 ou 30 jours**. Les résultats donnent occurrences et durées actives cumulées/moyennes, nombres d’entités et équipements touchés, et éléments les plus fréquents. Un clic sur un classement ou un élément mis en avant ouvre l’historique correspondant.

Les calculs sont effectués à la demande à partir de **l’historique résolu conservé**, indépendamment des filtres du tableau. Les alertes en cours et occurrences supprimées/expirées sont exclues. Les durées sont limitées à la période choisie et incluent le temps acquitté. Les alertes simultanées contribuent séparément : ces totaux **ne mesurent pas l’indisponibilité d’un équipement**.

## Notifications

Dans **Configuration → Notifications**, créez des profils avec une ou plusieurs **entités `notify`**. Choisissez les notifications de nouvelle alerte et de résolution, ainsi que les rappels facultatifs (intervalle minimum : une minute). Chaque profil possède un interrupteur d’activation. Les canaux exposés uniquement comme actions ou scripts restent utilisables via vos automatisations basées sur les événements.

Le menu trois points propose **Mode YAML**, **Dupliquer** et **Tester**. La duplication conserve réglages, destinataires et ordre des exceptions, mais la copie n’est créée qu’à l’enregistrement et ne reprend ni les compteurs d’utilisation ni l’état d’exécution. Le test envoie une vraie notification avec le profil enregistré, sans créer d’alerte.

### Étiquettes et exceptions ordonnées

Un profil peut couvrir toutes les alertes ou correspondre à **au moins une étiquette sélectionnée (OU)**. La sélection combine les étiquettes d’entité, d’équipement, de règle et de pack. Une exception exige **toutes ses étiquettes (ET)**. La **première exception correspondante dans l’ordre de la liste** gagne ; les valeurs héritées conservent les réglages du profil. Les exceptions peuvent adapter séparément nouvelles alertes, résolutions et rappels. En YAML, elles utilisent `selector_ids` ; l’ancien `selector_id` reste accepté.

### Regroupement et rappels

Les nouvelles alertes et résolutions sont regroupées séparément par profil. Le délai vaut **30 secondes par défaut**, réglable de **10 à 300 secondes**. Le modifier affecte les nouveaux lots, pas ceux déjà en attente. Lorsqu’une alerte disparaît avant l’envoi de son activation en attente, le couple activation/résolution non envoyé est abandonné.

Les rappels sont regroupés par profil et s’arrêtent à l’acquittement ou à la résolution. Après un redémarrage, ils attendent la réconciliation des alertes ; les échéances dépassées repartent sur l’intervalle configuré, sans rejouer les rappels manqués.

Les titres distinguent 🚨 nouvelles alertes, 🔔 rappels et ✅ retours à la normale. Avec les cibles Companion prises en charge, un appui ouvre l’alerte unique en cours, l’Accueil pour plusieurs alertes ou l’Historique pour les résolutions. Les cibles génériques reçoivent titre et message sans URL de navigation brute ajoutée.

### Détails des envois

Les détails séparent les notifications d’activation et de rappel ; l’historique conserve aussi les résolutions, profils correspondants et derniers envois. Un lot compte une fois par profil et alerte dès qu’au moins une cible réussit. Les tests et échecs complets sont exclus. Ces détails survivent au redémarrage, restent masqués pour les alertes en attente et ne comptent pas les notifications envoyées par des automatisations externes.

Les compteurs d’utilisation des profils couvrent l’heure actuelle et les 23 précédentes depuis le démarrage. Ils restent uniquement en mémoire et sont remis à zéro au redémarrage/rechargement ; un envoi groupé compte une fois même avec plusieurs cibles.

## Cohérence de la configuration

**Cohérence** vérifie les références statiques dans les automatisations, scripts, dashboards, templates, ESPHome et règles personnalisées, y compris les règles désactivées et références Jinja statiques. Les références dynamiques et le texte simple des messages sont ignorés. Les résultats indiquent la source et proposent une navigation contextuelle quand elle est possible, notamment vers l’éditeur d’une règle.

Lorsque ZHA est entièrement chargé, l’analyse vérifie aussi les références `device_ieee` statiques des déclencheurs `zha_event` et étapes `wait_for_trigger` dans le registre des appareils ZHA de Home Assistant. Elle vérifie les appareils enregistrés, **pas leur disponibilité ni leur présence radio**. Les appareils désactivés et télécommandes sans entité comptent comme présents. Templates, entrées de blueprint et valeurs IEEE mal formées sont ignorés ; les blueprints ne sont pas développés. Des métadonnées ZHA incomplètes produisent une vérification ignorée, pas des appareils manquants.

Lancez une analyse manuelle ou planifiez-la chaque jour, semaine ou mois. L’analyse ESPHome peut être désactivée et les exclusions de références peuvent contenir des adresses IEEE ZHA exactes. Les rapports survivent au redémarrage. La page montre aussi les 50 dernières entités supprimées encore conservées dans le registre Home Assistant, sans maintenir un historique de suppression séparé.

Activez **Créer une alerte pour les problèmes de cohérence** dans **Configuration → Analyse de cohérence** pour conserver une alerte immédiate tant que des problèmes subsistent. Elle utilise les acquittements, l’historique et les profils habituels. Seule une vérification complète confirmant le retour à la normale la résout ; une analyse incomplète ou en erreur ne peut pas l’effacer. L’activation utilise le dernier rapport sans lancer d’analyse. La désactivation retire l’alerte et ses rappels sans annoncer de résolution. Les problèmes sont aussi exposés par `sensor.alert_manager_coherence_issue`.

## Configuration, YAML et récupération

Les volets de configuration et profils proposent un **Mode YAML** dans leur menu trois points. Le passage visuel/YAML conserve les valeurs non enregistrées et l’ordre des listes. Un YAML invalide, une clé inconnue ou un réglage invalide bloque l’enregistrement et le retour à l’éditeur visuel. Le YAML d’un volet ne contient que son champ ; **Enregistrer** applique les modifications. Les détails et diagnostics en lecture seule ne sont pas éditables. Fermer un éditeur modifié demande confirmation ; les volets sont redimensionnables sur ordinateur.

La configuration complète peut être exportée/importée en YAML. Alert Manager conserve les **trois dernières sauvegardes quotidiennes valides de configuration**, téléchargeables et restaurables depuis Configuration.

Une configuration enregistrée invalide entraîne un démarrage avec des valeurs sûres, une alerte persistante et le choix d’une sauvegarde par un administrateur ; aucune restauration n’est silencieuse. **Restaurer une sauvegarde complète remplace la configuration actuelle, les alertes en cours et l’historique.**

### Diagnostics internes

Configuration affiche le nombre d’évaluations des règles personnalisées, leurs temps moyen/maximum/cumulé, les transitions d’alertes et les envois réussis des profils. Exactement 24 agrégats horaires sont conservés en mémoire, sans persistance. La période commence au démarrage ou à la plus ancienne heure conservée. Tests, packs automatiques et analyses de cohérence sont exclus du chronométrage des règles ; cela **ne mesure pas la charge de la boucle d’événements Home Assistant**. L’activité compte les transitions, pas le nombre courant d’alertes.

## Entités et événements Home Assistant

| Entité | Utilisation |
| --- | --- |
| `switch.alert_manager_main_monitoring` | Activer ou suspendre la surveillance. |
| `sensor.alert_manager_main_active` | Nombre d’alertes actives non acquittées. |
| `sensor.alert_manager_main_pending` | Nombre d’alertes en attente. |
| `sensor.alert_manager_main_acknowledge` | Nombre d’alertes acquittées. |
| `sensor.alert_manager_coherence_issue` | Problèmes de cohérence. |

Les événements sont `alert_manager_alert_started`, `alert_manager_alert_resolved`, `alert_manager_alert_acknowledged` et `alert_manager_alert_unacknowledged`. Les actions d’acquittement sont `alert_manager.acknowledge` et `alert_manager.unacknowledge`.

Les profils intégrés sont facultatifs ; ces entités, événements et actions restent disponibles pour vos dashboards et automatisations.
