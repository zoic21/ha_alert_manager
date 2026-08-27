# Changelog

Toutes les évolutions notables d’Alert Manager sont documentées dans ce fichier.

## 1.7.0-dev17 — 27 août 2026

### Corrigé

- Sur mobile, la seconde ligne de chaque alerte reprend désormais toutes les
  colonnes secondaires choisies dans « Personnaliser la vue », dans leur ordre
  d’affichage et séparées par un point médian. Cela s’applique à la vue
  d’ensemble comme à l’historique, y compris au compte à rebours dynamique.
- Le bouton retour utilise systématiquement l’historique réel du navigateur. Il
  revient donc à la page Home Assistant précédemment consultée même lorsque
  celle-ci n’est pas renseignée dans `history.state`.

### Tests

- 146 tests backend et 69 tests frontend couvrent la composition mobile selon
  les colonnes visibles et le retour sans métadonnée de navigation Home
  Assistant.

## 1.7.0-dev16 — 27 août 2026

### Modifié

- `sensor.alert_manager_device_main_active` regroupe désormais les appareils
  portant le même nom dans une seule entrée `devices`. Le champ compatible
  `device_id` conserve le premier identifiant trié et le nouveau champ
  `device_ids` expose tous les appareils regroupés.
- `alert_manager_device_alert_started` suit le même groupe nominal : l’arrivée
  d’une alerte sur un second appareil de même nom ne réémet pas l’événement tant
  que le groupe reste actif.
- Le tri initial de la vue d’ensemble utilise le statut en ordre ascendant afin
  d’afficher les alertes actives avant les alertes à venir et acquittées.
  L’ancien tri par défaut « détectée le, décroissant » est migré vers ce nouvel
  ordre ; les autres tris personnalisés restent conservés localement.

### Tests

- 146 tests backend et 69 tests frontend couvrent le regroupement de plusieurs
  identifiants d’appareil sous un même nom et le nouvel ordre initial.

## 1.7.0-dev15 — 27 août 2026

### Corrigé

- Le délai de 10 secondes concerne maintenant uniquement l’affichage des alertes
  **à venir**. Une condition transitoire qui disparaît avant cette échéance ne
  fait plus clignoter la liste pending, tandis qu’une alerte arrivée à échéance
  est affichée immédiatement comme active.
- Le réglage est renommé `pending_display_delay` et les configurations
  `active_display_delay` créées par la dev14 sont migrées automatiquement, y
  compris dans les imports YAML.
- Les entités sans appareil sont désormais comptées individuellement par
  `sensor.alert_manager_device_main_active`. Leur identifiant et leur nom
  d’entité servent de repli dans `devices` et dans l’événement
  `alert_manager_device_alert_started`.
- La dernière ligne des règles personnalisées conserve la même hauteur que les
  autres. La surcharge locale de 60 px, incompatible avec le calcul natif
  `autoHeight` de Home Assistant, a été retirée.

### Tests

- 145 tests backend et 69 tests frontend couvrent notamment les conditions
  transitoires, la migration dev14, les entités sans appareil et la hauteur
  native du tableau.

## 1.7.0-dev14 — 27 août 2026

### Ajouté

- Le nouveau réglage persistant `active_display_delay`, fixé à 10 secondes par
  défaut, retarde l’exposition d’une alerte déjà active dans le Dashboard et
  `sensor.alert_manager_main_active`. Le délai ajouté est plafonné par le délai
  propre de l’alerte ; une règle sans temporisation reste donc immédiate.
- Le capteur `sensor.alert_manager_device_main_active` compte les appareils du
  registre possédant au moins une alerte active affichée. Son attribut `devices`
  fournit les identifiants, noms, zones, compteurs et alertes de chaque appareil.
- L’événement `alert_manager_device_alert_started` est émis uniquement lorsqu’un
  appareil entre dans l’ensemble actif. Une alerte supplémentaire sur le même
  appareil ne crée aucun doublon. La documentation inclut une automatisation de
  notification mobile basée sur cet événement.

### Corrigé et optimisé

- Le Dashboard met désormais à jour les compteurs et les données du composant
  natif en place lors de l’ajout ou du retrait d’une ligne, sans reconstruire la
  page et faire clignoter le tableau.
- L’ouverture et la fermeture du volet d’une règle personnalisée conservent
  l’instance existante de `ha-data-table`, son tri et sa position de défilement.
- La table des règles active le mode natif `autoHeight` de Home Assistant, ce qui
  supprime la ligne vide résiduelle après la dernière règle sans règle CSS
  spécifique.
- Les nouvelles échéances `visible_at` sont persistées, restaurées et
  replanifiées après redémarrage ou import de configuration. Une alerte résolue
  avant son exposition ne génère ni ligne active ni événement d’appareil.

### Tests

- 142 tests backend et 69 tests frontend couvrent le délai d’exposition, sa
  compatibilité avec les anciens exports, le compteur d’appareils, la
  déduplication des événements et les mises à jour natives des tableaux.

## 1.7.0-dev12 — 27 août 2026

### Corrigé

- L’intégration source est désormais conservée dans l’historique lors de la
  résolution d’une alerte et reste donc disponible après la disparition de
  l’entité.
- Une correction d’horloge NTP vers le passé après un acquittement ne produit
  plus d’entrée d’historique temporellement incohérente et illisible au
  redémarrage.
- Les règles refusent strictement les types invalides pour leur activation,
  leur version, leur nom, leur attribut et leur message ; la chaîne `"false"`
  ne peut notamment plus activer une règle par effet de vérité implicite.
- Des préférences de tableau locales absentes ou corrompues ne bloquent plus le
  démarrage du panel.
- Une période contenant une date JavaScript invalide est ignorée sans
  exception ni perte du filtre précédent.
- La soumission d’un formulaire au clavier respecte maintenant la validation
  native Home Assistant, comme le clic sur son bouton d’enregistrement.
- Un changement de langue pendant le chargement des traductions déclenche bien
  le chargement de la dernière langue demandée.

### Interface et optimisation

- Les messages d’état utilisent `ha-alert`, les panneaux et compteurs utilisent
  `ha-card`, et la liste des règles utilise désormais `ha-data-table` avec tri,
  navigation au clavier et interrupteurs Home Assistant natifs.
- L’ancien tableau HTML, les styles personnalisés de cartes et de messages,
  les sélecteurs inutilisés et les règles mobiles redondantes ont été retirés.
- Le contrôle statique du frontend interdit désormais le retour des principaux
  contrôles HTML personnalisés et des anciennes règles CSS remplacées par les
  composants Home Assistant.

### Tests

- 139 tests backend et 68 tests frontend couvrent notamment les nouvelles
  validations, l’historique, les dates invalides, les préférences corrompues,
  les changements rapides de langue et les composants natifs.

## 1.7.0-dev11 — 27 août 2026

### Corrigé

- Le compte à rebours des alertes en cours d’activation est de nouveau actualisé
  automatiquement chaque seconde dans le tableau natif Home Assistant.
- La mise à jour traverse maintenant les Shadow DOM de
  `hass-tabs-subpage-data-table` et `ha-data-table` pour atteindre les cellules
  virtualisées portant `data-due`.
- Seul le texte du compte à rebours est modifié chaque seconde : le tableau
  complet n’est pas recalculé ni rerendu.

### Tests

- Couverture d’une cellule `pending` imbriquée dans les deux composants natifs et
  de l’absence de progression lorsque la surveillance est désactivée.

## 1.7.0-dev10 — 27 août 2026

### Corrigé

- Les colonnes du composant natif `ha-data-table` ne sont plus limitées par des
  largeurs maximales fixes.
- Les colonnes visibles se répartissent maintenant sur toute la largeur
  disponible selon leur poids, aussi bien dans le Dashboard que dans
  l’Historique.
- Les largeurs minimales sont conservées pour garantir la lisibilité et le
  défilement horizontal lorsque l’écran est étroit ou que de nombreuses colonnes
  sont activées.

### Tests

- Couverture de la répartition flexible sans `maxWidth`, des largeurs minimales
  et des proportions particulières des colonnes Entité et chronologiques.

## 1.7.0-dev9 — 27 août 2026

### Corrigé

- Les colonnes optionnelles déclarent maintenant leur état Home Assistant natif
  `defaultHidden` pour le Dashboard et l’Historique.
- « Rétablir les valeurs par défaut » applique immédiatement les six colonnes
  prévues, sans afficher temporairement toutes les colonnes jusqu’au rechargement
  de la page.
- L’ordre natif sans préférence reste identique à l’ordre par défaut Alert
  Manager.

### Tests

- Couverture des colonnes visibles et masquées nativement après restauration,
  séparément pour le Dashboard et l’Historique.

## 1.7.0-dev8 — 27 août 2026

### Modifié

- Les colonnes par défaut du Dashboard sont désormais Statut, Entité, Appareil,
  Règle, Intégration et Active depuis/Temps restant.
- Les colonnes par défaut de l’Historique sont Statut, Entité, Appareil, Règle,
  Intégration et Détectée le.
- La colonne Intégration est ajoutée au tableau et au dialogue natif de
  personnalisation des colonnes.
- L’action « Restaurer les colonnes par défaut » et la migration des anciens
  défauts utilisent cette nouvelle configuration sans écraser les préférences
  réellement personnalisées.
- Les compteurs Alertes actives, Alertes à venir et Alertes acquittées du
  Dashboard sont cliquables et appliquent immédiatement le filtre Statut
  correspondant.

### Tests

- Couverture des nouveaux défauts, de leur restauration, de la migration des
  préférences, de la colonne Intégration et du filtrage depuis les compteurs.

## 1.7.0-dev7 — 27 août 2026

### Corrigé

- Chaque filtre de date utilise désormais un unique `ha-date-range-picker`, le
  composant natif de la page Historique Home Assistant.
- Le sélecteur propose les périodes rapides Home Assistant, un calendrier et les
  heures de début et de fin dans la même fenêtre.
- Une période début/fin compte comme un seul filtre actif et conserve la
  précision horaire choisie.
- Le composant natif est chargé à la demande lorsque le panel est ouvert sans
  passage préalable par la page Historique.

### Tests

- Couverture du rendu, de l’hydratation et des événements du sélecteur de période
  natif, du comptage unitaire et des limites horaires.

## 1.7.0-dev6 — 27 août 2026

### Corrigé

- Le filtre d’état d’acquittement est retiré du Dashboard car il faisait doublon
  avec les statuts Active et Acquittée.
- L’Historique ne propose plus les filtres Statut et État d’acquittement, qui
  n’apportaient aucune distinction utile sur des événements tous résolus.
- Les bornes des filtres de dates utilisent désormais le sélecteur natif Home
  Assistant `{ date: {} }`, qui charge `ha-date-input` et son dialogue calendrier
  standard.

### Tests

- Couverture de l’absence des filtres redondants et de l’hydratation du sélecteur
  de date natif.

## 1.7.0-dev5 — 27 août 2026

### Corrigé

- Les filtres à choix multiples s’affichent désormais dans tous les contextes du
  panel à partir de composants Home Assistant déjà chargés, sans dépendre des
  filtres internes propres à la page Entités.
- Les filtres couvrent en priorité le statut, l’appareil, la règle,
  l’intégration, les étiquettes, le domaine et la zone, en plus de l’entité, de
  l’acquittement et des dates.
- Les étiquettes de l’entité sont affichées sous son nom et participent à la
  recherche et au filtrage.
- La colonne Entité précède désormais la colonne Appareil, y compris lors de la
  migration des préférences par défaut de `dev4`.
- La marge injectée par `ha-data-table` sur la première icône est neutralisée afin
  de centrer exactement le pictogramme dans son fond circulaire.

### Tests

- Couverture des nouvelles facettes, des métadonnées de registre, des étiquettes,
  de la migration de l’ordre des colonnes et du centrage de l’icône.

## 1.7.0-dev4 — 27 août 2026

### Corrigé

- Le Dashboard et l’Historique utilisent désormais le conteneur natif Home
  Assistant `hass-tabs-subpage-data-table`, et non plus une barre d’outils
  reconstruite dans Alert Manager.
- Le volet de filtres affiche l’effacement global dans son en-tête ainsi qu’un
  compteur et une action d’effacement sur chaque catégorie active.
- La personnalisation des colonnes ouvre le dialogue natif Home Assistant avec
  visibilité, glisser-déposer et restauration des valeurs par défaut.
- Le mode sélection remplace la barre supérieure de la sous-page. Son bouton est
  placé entre les filtres et la recherche, comme dans la liste des entités.
- La recherche occupe automatiquement toute la largeur restante.
- En affichage étroit, seules l’icône de statut et l’entité restent en colonnes,
  avec la condition affichée en information secondaire sous le nom.
- L’en-tête de la colonne Statut est vide et son icône est centrée dans son fond
  circulaire.

### Tests

- Couverture du conteneur natif, de ses événements de recherche, tri, groupement,
  sélection et personnalisation, des filtres réinitialisables et du rendu mobile.

## 1.7.0-dev3 — 26 août 2026

### Corrigé

- Toutes les pages du panel utilisent désormais toute la largeur disponible,
  sans limite centrale à 1400 px.
- La barre d’outils des tableaux repose sur les composants natifs Home
  Assistant `ha-assist-chip`, `ha-dropdown`, `ha-dropdown-item`, `ha-button` et
  `ha-icon-button` au lieu de boutons et menus HTML personnalisés.
- Le filtre est présenté dans un volet latéral compact calqué sur la liste des
  entités, avec `ha-expansion-panel`, `ha-list`, `ha-check-list-item` et les
  champs de date natifs.
- Les menus de groupement, de tri et de colonnes, ainsi que le menu trois-points
  de l’éditeur de règle, utilisent désormais les menus déroulants Home
  Assistant.

### Tests

- Ajout de contrôles frontend sur les composants natifs, l’ouverture du volet
  de filtres, les événements des menus et la mise en page pleine largeur.

## 1.7.0-dev2 — 26 août 2026

### Corrigé

- Remplacement du tableau HTML personnalisé par le composant natif Home
  Assistant `ha-data-table`, qui assure désormais la virtualisation des lignes,
  les groupes repliables et les cases de sélection.
- Utilisation du composant natif `ha-input-search` dans la barre d’outils des
  tableaux.
- Les anomalies revenues à la normale pendant leur délai `pending` ne sont plus
  ajoutées à l’historique. Les éventuelles entrées expérimentales de ce type
  enregistrées par `1.7.0-dev` sont supprimées au prochain chargement.

### Tests

- Adaptation des tests frontend au contrat de propriétés et d’événements de
  `ha-data-table`.
- Non-régression backend vérifiant explicitement qu’une alerte annulée avant
  activation ne produit aucun événement historique.

## 1.7.0-dev — 26 août 2026

### Ajouté

- Tableau compact commun au Dashboard et à l’Historique, inspiré de la liste des
  entités Home Assistant, avec colonnes personnalisables et ouverture native de
  « Plus d’informations ».
- Recherche instantanée sur les métadonnées complètes, filtres cumulables et
  réinitialisables, groupement repliable par appareil, zone, règle ou statut et
  tri typé ascendant/décroissant.
- Préférences locales distinctes par tableau pour l’ordre et la visibilité des
  colonnes, le groupement, la clé de tri et son sens.
- Mode de sélection multiple du Dashboard avec sélection des lignes visibles et
  acquittement/désacquittement de masse limité aux alertes compatibles.

### Modifié

- Remplacement complet des cartes d’alertes et d’historique par des lignes de
  tableau, y compris sur mobile où le défilement horizontal reste disponible.
- Conservation de la valeur ayant initialement déclenché une occurrence, même si
  la source prend ensuite une autre valeur toujours anormale.
- Suspension visuelle du compte à rebours lorsque la surveillance est désactivée,
  sans progression artificielle du délai.

### Tests

- Couverture frontend du rendu, de la recherche, des filtres, du groupement, du
  tri, des colonnes, de la persistance locale, de la sélection mixte et des
  actions de masse.
- Couverture backend de la valeur de déclenchement immuable, en complément des
  suites de non-régression existantes.

## 1.6.3 — 26 août 2026

### Corrigé

- Centrage vertical précis de l’action **Effacer l’historique** sur la surface
  visible du champ de limite de rétention.
- Alignement sur la hauteur visible de `56 px` du champ Home Assistant, sans
  décaler le libellé ni le texte d’aide.

## 1.6.2 — 26 août 2026

### Corrigé

- Placement de l’aide du délai global directement sous son champ de saisie.
- Alignement vertical exact de l’action **Effacer l’historique** avec le champ
  de limite de rétention.
- Simplification du balisage et des règles CSS de la section des paramètres
  généraux, avec une grille explicite et responsive pour la rétention.

## 1.6.1 — 26 août 2026

### Corrigé

- Restauration de l’alignement du délai global et des labels exclus des
  surveillances automatiques dans **Paramètres généraux**.
- Suppression du titre et du texte descriptif Historique dans cette section.
- Enregistrement de la limite de rétention par l’unique bouton commun placé en
  bas à droite ; l’effacement irréversible reste une action distincte face au
  champ de rétention.

## 1.6.0 — 26 août 2026

### Ajouté

- Historique persistant et atomique des alertes actives résolues dans un stockage
  indépendant des alertes runtime.
- Nouvel onglet administrateur **Historique**, avec cartes grises, groupement par
  appareil, dépliage progressif et informations figées au moment de la résolution.
- Rétention configurable de 0 à 1000 événements, valeur par défaut 100, réduction
  immédiate des événements les plus anciens et action d’effacement irréversible
  avec confirmation.
- Commandes WebSocket administrateur pour lire l’historique, lire/modifier sa
  configuration et l’effacer.
- Traductions françaises et anglaises, documentation et tests backend/frontend.
- Réglage de rétention placé dans **Paramètres généraux**, sous le délai global,
  avec les actions d’enregistrement et d’effacement alignées face au champ.

### Garanties

- Les alertes annulées pendant `pending` ne sont pas archivées.
- Une erreur d’écriture de l’historique ne bloque pas la résolution d’une alerte
  et ne peut pas corrompre le stockage runtime.
- Aucun changement des entités, événements et services existants ; aucune entité
  Home Assistant supplémentaire.
- L’historique et sa limite de rétention sont exclus de l’import/export YAML, qui
  conserve ces données locales.

## 1.5.9-dev5 — 26 août 2026

### Corrigé

- Alignement à gauche des blocs « Condition » et « Active depuis » dans les
  lignes d’alertes groupées, comme sur les cartes non groupées.
- Bundle frontend distribué régénéré avec cette correction.

## 1.5.9-dev4 — 26 août 2026

### Modifié

- Affichage vertical de la condition et de la date d’activation dans les lignes
  d’alertes groupées, comme sur les cartes individuelles.
- Bouton d’affichage des autres alertes réduit à un lien texte compact, placé en
  bas à gauche sans encadrement au survol.
- Source frontend et bundle distribué synchronisés pour cette version.

## 1.5.9-dev3 — 26 août 2026

### Modifié

- Affichage par défaut de la première alerte uniquement dans les groupes, avec
  révélation progressive des alertes suivantes via un bouton.
- Alignement à gauche du temps restant et de la date d’activation dans les lignes
  d’alertes groupées.
- Ajout des traductions françaises et anglaises du contrôle d’affichage des
  alertes supplémentaires.
- Synchronisation de la version du manifest, du backend et du frontend en
  `1.5.9-dev3`.
## 1.5.8 — 26 août 2026

### Corrigé

- Correction du positionnement horizontal du volet de création ou modification
  d’une règle personnalisée sur les écrans larges.
- Source frontend et bundle distribué régénérés et synchronisés pour garantir
  un build reproductible dans la CI.

## 1.5.5 — 26 août 2026

### Corrigé

- Rapprochement du volet de création ou modification d’une règle et de la liste
  des règles ; l’espace disponible est désormais conservé entre le volet et le
  bord droit de l’écran sur les affichages larges.
- Exclusion systématique des entités Alert Manager de la surveillance
  automatique, même avant leur inscription dans le registre des entités.
- Interdiction de sélectionner ou d’enregistrer une entité Alert Manager comme
  source d’une règle personnalisée, y compris après renommage ou via YAML.
- Nettoyage sans effet de bord des anciennes règles internes devenues invalides.

## 1.5.5-dev2 — 26 août 2026

### Corrigé

- Gel réel du temps restant des alertes `pending` pendant toute la désactivation
  de la surveillance, y compris après un redémarrage ou un rechargement ; le
  décompte reprend au même point lors de la réactivation.
- Remise temporaire à zéro des trois capteurs d’alertes et de leur attribut
  `alerts` lorsque la surveillance est désactivée, sans supprimer les occurrences
  internes conservées pour la reprise.
- Largeur de la page **Règles personnalisées** alignée sur les autres pages du
  panneau.

## 1.5.5-dev — 26 août 2026

### Ajouté

- Appareil de service stable `Alert Manager - Général`, prévu pour accueillir
  ultérieurement d’autres catégories sans renommer la catégorie `main`.
- Switch persistant `switch.alert_manager_main_monitoring`, actif par défaut,
  avec suspension réelle des détections et timers puis réévaluation sans doublon
  à la reprise.
- Notification persistante FR/EN, à identifiant stable, lorsque l’intégration est
  chargée avec la surveillance désactivée.
- Métadonnées `rule_id` et `rule_name` dans les attributs des alertes issues de
  règles personnalisées.

### Modifié

- Remplacement cassant de `sensor.alert_manager` par trois capteurs exclusifs :
  `sensor.alert_manager_main_active`, `sensor.alert_manager_main_pending` et
  `sensor.alert_manager_main_acknowledge`.
- Mise à jour du panneau, des traductions, de la documentation FR/EN, des exemples
  d’automatisation et de l’export/import YAML.
- Import toujours compatible avec les exports V1.5 sans
  `monitoring_enabled` ; la surveillance est alors activée par défaut.

### Garanties conservées

- Alertes existantes conservées pendant la suspension, événements de démarrage
  et résolution sans répétition, services d’acquittement, identifiants, packs,
  exclusions, délais et suivi multi-entités inchangés.

### Limite volontaire

- L’ancienne entité agrégée est supprimée sans quatrième capteur de compatibilité
  durable ; les cartes et automatisations doivent migrer vers le capteur d’état
  correspondant.

## 1.5.0-dev3 — 26 août 2026

### Modifié

- Renommage de l’onglet « Exclusions et paramètres » en « Configuration ».
- Suppression des identifiants internes des règles dans l’export YAML complet ;
  ils sont désormais recréés par le backend lors de l’import.
- Correction du menu trois-points du volet de règle avec le slot natif
  `actionItems` de Home Assistant et suppression du nom en sous-titre lors de
  la modification d’une règle.

## 1.5.0-dev2 — 25 août 2026

### Optimisé

- Mise en cache des registres Home Assistant et des ensembles d’exclusion sur le
  chemin d’évaluation des changements d’état, sans modifier les règles de suivi.
- Réutilisation d’un mécanisme commun de restauration de la configuration, des
  alertes et des timers en attente.

### Corrigé

- Restauration complète en mémoire si l’enregistrement d’un réglage, d’une
  création, d’une modification ou d’une suppression de règle échoue.
- Validation explicite des règles incomplètes afin de renvoyer une erreur lisible
  au lieu d’une erreur interne.
- Durcissement des imports YAML face aux clés non textuelles, scalaires non
  sérialisables, chaînes Unicode invalides et documents anormalement volumineux.
- Nettoyage persistant des configurations et alertes corrompues détectées au
  démarrage, pour éviter de retraiter la même donnée invalide à chaque relance.
- Suppression des chargements WebSocket et timers de rafraîchissement en double
  lors d’une reconnexion très rapide du panneau.

### Garanties conservées

- Aucun changement du moteur fonctionnel, des identifiants, des événements, des
  services d’acquittement ou du cycle `normal → pending → active`.

## 1.5.0-dev1 — 25 août 2026

### Ajouté

- Édition YAML des règles personnalisées dans le volet existant, via le menu
  trois-points, en complément de l’éditeur visuel.
- Validation backend commune pour les règles visuelles et YAML, avec rejet des
  YAML incomplets, syntaxiquement invalides ou incohérents.
- Export YAML complet, déterministe et versionné de la configuration
  persistante.
- Import YAML complet avec aperçu, confirmation explicite, validation stricte,
  remplacement atomique et reconstruction du suivi par entité.
- Commandes WebSocket administrateur dédiées à la validation YAML, à l’export et
  à l’import.
- Documentation FR/EN, traductions et couverture de tests pour ces flux.

### Garanties conservées

- Le moteur de règles Alert Manager reste indépendant des conditions
  d’automatisation Home Assistant.
- Les IDs stables des règles et des alertes règle/entité sont préservés à
  l’import.
- L’export exclut volontairement les alertes runtime, acquittements, timers,
  dates et historique.
- Le cycle indépendant `normal → pending → active`, l’entité unique
  `sensor.alert_manager` et les services d’acquittement restent inchangés.

### Limites assumées

- Le YAML de règle ne prend pas en charge les templates, groupes `and`/`or`/`not`
  ou conditions arbitraires Home Assistant.
