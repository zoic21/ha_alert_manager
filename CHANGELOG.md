# Changelog

Toutes les évolutions notables d’Alert Manager sont documentées dans ce fichier.

## 2.3.0-dev.11 — September 8, 2026

This is a development prerelease.

### Improvements

- Show the notification usage counting period once below the profile list and keep mobile Edit actions beside their profile.
- Keep the mobile history title and clear-history action on the same row.

## 2.3.0-dev.10 — September 8, 2026

This is a development prerelease.

### Improvements

- Add separate top-five pack and custom-rule rankings by occurrence count and cumulative duration.
- Add a top-five associated notification profile ranking using retained history, counting each profile once per occurrence across activation/reminder and resolution associations. This is not a delivery count.
- Open the native filtered history from all new rankings, including a new associated-profile facet.

## 2.3.0-dev.9 — September 8, 2026

This is a development prerelease.

### Improvements

- Remove the visible statistics title and place period controls at the left of the history action.
- Keep period controls and all four summary metrics in one card on desktop and mobile, retaining two metric columns on mobile.

## 2.3.0-dev.8 — September 8, 2026

This is a development prerelease.

### Improvements

- Center the desktop statistics dashboard within 1,400 pixels, combining period controls and the four summary values into one visual banner.
- Give the three ranking cards equal widths and align their sections using content-sized shared grid rows.
- Preserve the existing mobile layout and single page scroll.

## 2.3.0-dev.7 — September 8, 2026

This is a development prerelease.

### Improvements

- Replace the statistics table with a single scrolling dashboard: period controls, summary, and compact entity, device, and integration cards.
- Show separate top-five rankings by occurrence count and cumulative alert duration, with links to the filtered history.
- Arrange cards side by side on desktop and at full width on mobile, without internal scroll areas.

## 2.3.0-dev.6 — September 8, 2026

This is a development prerelease.

### Fixes

- Keep the three statistics top items side by side on mobile, with compact spacing and truncated long names.
- Keep the statistics title and history action on one row on mobile.
- Limit the mobile statistics header to 45% of the visible viewport and allow it to scroll independently, preserving access to the native table even on short screens.

## 2.3.0-dev.5 — September 8, 2026

This is a development prerelease.

### Improvements

- Keep statistics controls, summary values, and top items on one row when space allows, with centered wrapping on smaller screens.
- Show occurrence counts in parentheses beside top item names.
- Place the grouping selector before the period buttons.

## 2.3.0-dev.4 — September 8, 2026

This is a development prerelease.

### Improvements

- Add affected entity counts and top entity, device, and integration highlights to history statistics, including tied occurrence counts.
- Remove the retained-history note and its help control from the statistics header.
- Use the history table’s native facets and active-period date filter for statistics navigation, replacing the separate filter banner.
- Keep history facet selections tied to stable identifiers so identically named devices and rules remain distinct.

## 2.3.0-dev.3 — September 8, 2026

This is a development prerelease.

### Improvements

- Redesign history statistics with compact 7/30-day controls and a summary of occurrences, affected devices, and cumulative alert duration.
- Show entity names and rules separately, with native icons, compact duration labels, and exact durations on hover.
- Open the matching history when clicking a ranking row, preserving the selected time window and providing a visible, removable filter.
- Keep mobile rows compact and move calculation details behind an information button.
- Shorten the alert detail history label to “History”.

## 2.3.0-dev.2 — September 8, 2026

This is a development prerelease.

### Fixes

- Fix the history occurrence counter when opening alert details from native tables.
- Initialize the native date range picker before mounting it, preventing an undefined-date error during lazy loading.

### Improvements

- Move notification profile deletion into the profile editor menu.
- Show only the current match count in the custom rule test summary.
- List activation, reminder, and resolution profiles separately, with `-` when none match.
- Shorten French and English help text while preserving configuration semantics.

## 2.3.0-dev.1 — 8 septembre 2026

Cette version est une prérelease de développement.

### Améliorations

- Titres des notifications raccourcis, sans préfixe « Alert Manager », avec des
  libellés adaptés au singulier et au pluriel en français et en anglais.
- Édition YAML des profils de notification et actions Dupliquer et Tester dans
  leur menu ; affichage des profils correspondants dans le testeur de règle.
- Compteur cliquable des occurrences conservées dans les détails d’une alerte.
- Statistiques de récurrence et de fiabilité calculées à la demande dans l’historique.
- Statistiques légères de performance et d’activité sur 24 heures, en mémoire.

### Suppression incompatible

- Suppression de `sensor.alert_manager_device_main_active` et de l’événement
  `alert_manager_device_alert_started`, ainsi que de leur agrégation et de leurs
  temporisations dédiées. Les automatisations externes qui les utilisent doivent
  être adaptées aux profils de notification intégrés ou aux événements par alerte.
- L’ancienne entrée du capteur est retirée du registre, même si elle a été renommée.
  Aucun alias ni mécanisme de compatibilité n’est conservé. Les notifications
  intégrées, les compteurs par alerte, le regroupement par appareil de l’interface
  et l’historique restent inchangés.

## 2.2.0-rc.19 — 8 septembre 2026

### Corrigé

- Synchronisation de la constante de version utilisée pour le cache du panneau
  avec le manifeste et les métadonnées frontend, oubliée dans la RC18.
- Cette version reprend toutes les corrections de la RC18.

Cette version reste une prérelease.

## 2.2.0-rc.18 — 8 septembre 2026

### Corrigé

- Les exceptions de notification exigent désormais toutes les étiquettes
  sélectionnées (ET). La première exception correspondante reste prioritaire ;
  le filtre d’étiquettes du profil conserve son fonctionnement en OU.
- Les notifications de retour à la normale ne recopient plus l’ancien message
  d’erreur ni la condition de déclenchement, pour les automatisations, les scripts
  et les autres alertes. Les diagnostics restent disponibles dans l’historique.
- Les packs consommateurs d’occurrences reçoivent un instantané immuable des
  identifiants d’alertes, partagé par tout le lot après l’évaluation des sources.

### Maintenance

- Documentation de l’ordre des verrous de configuration et de notifications.
- Clarification de la date de vérification des acquittements et du calcul des
  identifiants lors des renommages, sans changement du comportement.

Cette version reste une prérelease.

## 2.2.0-rc.17 — 7 septembre 2026

### Corrigé

- Les alertes de flapping utilisent les étiquettes de leur propre pack, y compris
  après une nouvelle occurrence, une modification des étiquettes ou un redémarrage.
  Les identifiants, dates de détection et historiques existants sont préservés.
- Modifier les étiquettes d’une règle annule ses notifications encore en attente
  avec l’ancien routage, sans supprimer celles des autres règles.
- Les notifications déclenchées par une modification de configuration attendent
  la réussite de sa sauvegarde. Un échec d’écriture ne provoque plus l’envoi d’une
  notification pour une alerte annulée par le retour à la configuration précédente.

Cette version reste une prérelease.

## 2.2.0-rc.16 — 7 septembre 2026

### Amélioré

- Suppression du titre numéroté des exceptions de notification pour éviter son
  changement visuel lors du réordonnancement. Les boutons de déplacement et de
  suppression restent respectivement en haut à gauche et à droite.
- Réduction des espaces en haut de chaque exception et avant ses champs pour
  rendre les encadrés plus compacts, sur ordinateur comme sur mobile.

Cette version reste une prérelease.

## 2.2.0-rc.15 — 7 septembre 2026

### Ajouté

- Réordonnancement des exceptions de notification avec une poignée à trois traits
  devant chaque numéro : glisser-déposer natif Home Assistant sur ordinateur et
  mobile, et déplacement au clavier avec les flèches haut/bas ou début/fin.
- Les réglages restent attachés à leur exception et le nouvel ordre est appliqué
  après enregistrement. La fermeture sans enregistrer demande confirmation.

Cette version reste une prérelease.

## 2.2.0-rc.14 — 7 septembre 2026

### Corrigé

- Suppression de la transition de 300 ms héritée de `ha-card` sur tous les
  volets des règles personnalisées et de la configuration : leur largeur
  suit immédiatement le déplacement de la poignée, comme le contenu principal.
- L’animation visuelle de la poignée de redimensionnement est conservée.

Cette version reste une prérelease.

## 2.2.0-rc.13 — 7 septembre 2026

### Corrigé

- Le bord gauche du contenu de configuration conserve la position de la page
  centrée lors de l’ouverture et du redimensionnement d’un volet. Seul le bord
  droit se réduit si nécessaire pour laisser la place au volet et à son espacement.
- Le contenu ne peut plus s’agrandir à l’ouverture du volet. Sa position
  s’adapte naturellement au redimensionnement du navigateur.

Cette version reste une prérelease.

## 2.2.0-rc.12 — 7 septembre 2026

### Corrigé

- Suppression du grand espace vide entre le contenu de configuration et son
  volet sur les écrans larges : les sections occupent toute la largeur restante,
  avec un espacement de 16 px jusqu’au volet redimensionnable.
- La page retrouve sa largeur limitée et son centrage à la fermeture du volet.
  Le comportement des écrans étroits reste inchangé.

Cette version reste une prérelease.

## 2.2.0-rc.11 — 7 septembre 2026

### Amélioré

- Tous les volets de configuration reprennent le redimensionnement en largeur
  des règles personnalisées : poignée, limites de largeur, réglage au clavier
  et double-clic pour retrouver la largeur initiale.
- Sur grand écran, le contenu principal se réduit à mesure que le volet
  s’élargit et retrouve sa largeur à la fermeture, y compris lors des mises
  à jour ciblées des volets. La largeur est conservée pendant la session.
- Les seuils responsive et les volets mobiles natifs restent identiques
  à ceux de l’éditeur de règles.

Cette version reste une prérelease.

## 2.2.0-rc.10 — 7 septembre 2026

### Corrigé

- Défilement automatique vers les nouvelles lignes de configuration : seuils
  de batterie, seuils d’erreur des automatisations et scripts, configurations
  de flapping et délais particuliers par entité.
- Même comportement pour l’ajout de valeurs multiples aux règles et de
  références ignorées de cohérence, en complément des exceptions de notification.
- Marge de 12 px autour des éléments révélés et défilement après restauration
  de la position du volet, sur mobile comme sur ordinateur.

Cette version reste une prérelease.

## 2.2.0-rc.9 — 7 septembre 2026

### Corrigé

- Flapping sur mobile : marges internes et espacement réduits pour laisser
  le champ d’occurrences et la fenêtre de détection sur la même ligne,
  sans couper le libellé du nombre d’occurrences.
- Exceptions de notification : marge de défilement pour que l’encadré ajouté
  ne soit plus collé au bord du volet.
- Valeurs numériques dans les tableaux et détails des alertes : utilisation
  du formatage natif Home Assistant, avec la précision d’affichage de l’entité
  et le format numérique de l’utilisateur. Les valeurs enregistrées restent
  intactes ; les anciennes unités sont conservées dans l’historique.

Cette version reste une prérelease.

## 2.2.0-rc.8 — 7 septembre 2026

### Corrigé

- Flapping, configurations particulières sur mobile : largeur du champ
  d’occurrences ajustée à son libellé, qui reste sur une seule ligne, pour
  placer la fenêtre de détection à côté lorsque l’espace disponible le permet.
  Le sélecteur de durée conserve sa largeur native.

Cette version reste une prérelease.

## 2.2.0-rc.7 — 7 septembre 2026

### Corrigé

- Flapping sur mobile : champ entité, interrupteur et corbeille sur la même
  ligne, avec les actions centrées verticalement sur le sélecteur.
- Exceptions de notification sur mobile : nouvelle alerte et retour à la
  normale côte à côte, avec les sélecteurs alignés.
- L’ajout d’une exception de notification fait défiler le volet jusqu’à
  la nouvelle exception lorsqu’elle n’est pas visible.
- Historique : ajout de l’action Supprimer dans le menu du détail d’une alerte.
  Après confirmation et suppression réussie, le détail se ferme et le bandeau
  de confirmation apparaît sur la page d’historique.

Cette version reste une prérelease.

## 2.2.0-rc.6 — 7 septembre 2026

### Corrigé

- Notifications mobiles : résolution de l’action à partir de la configuration
  de l’application associée à l’entité, y compris si l’entité a été renommée.
  Le lien de navigation est transmis dans les données du clic.
- L’envoi générique de secours n’ajoute plus le lien au texte de la notification.

Cette version reste une prérelease.

## 2.2.0-rc.5 — 7 septembre 2026

### Corrigé

- Flapping : nombre d’occurrences et fenêtre de détection côte à côte lorsque
  la largeur disponible le permet, avec les champs alignés.
- Exceptions de notification : étiquettes sur toute la largeur, puis nouvelle
  alerte et retour à la normale côte à côte sur grand écran.

Cette version reste une prérelease.

## 2.2.0-rc.4 — 7 septembre 2026

### Corrigé

- Les notifications de résolution ouvrent l’historique, y compris lorsqu’elles
  regroupent plusieurs alertes résolues.
- Configuration du flapping : nombre d’occurrences placé avant les durées et
  champs de même largeur ; champ d’occurrences plus compact pour les automatisations.
- Cohérence : suppression des copies inutiles du rapport dans l’event loop.

Cette version reste une prérelease.

## 2.2.0-rc.3 — 7 septembre 2026

### Corrigé

- Flapping : interrupteur sans libellé visible, avec nom accessible et infobulle,
  et actions regroupées près de l’entité, y compris lorsque l’analyse est inactive.
- Les durées utilisent toute la largeur de l’encadré et ne passent sur deux
  colonnes que lorsque la place disponible le permet.
- Alignement des champs et poubelles des packs batterie et automatisations ;
  suppression du libellé « Seuil global » incorrect sur les seuils particuliers.
- Conservation de la sélection d’entité en pleine largeur sur mobile.

Cette version reste une prérelease.

## 2.2.0-beta.10 — 6 septembre 2026

### Corrigé

- La fermeture d’un volet de configuration modifié demande confirmation pour les
  réglages des packs, les délais par entité et les exclusions, comme les profils
  de notification. Confirmer restaure le contenu du volet à son ouverture sans
  supprimer les autres modifications en attente.
- Refuser l’abandon après un geste de fermeture mobile réaffiche le volet avec
  ses modifications. Les volets inchangés se ferment sans confirmation.

## 2.2.0-beta.9 — 6 septembre 2026

### Corrigé

- Les retraits de lignes dans les volets de configuration utilisent une icône
  poubelle commune avec une infobulle et un libellé accessible : seuils des packs,
  configurations de flapping, délais par entité, exceptions de notification et
  listes de valeurs des règles.
- Sur mobile, le champ Appareil des configurations particulières de flapping
  occupe toute la largeur de l’encadré. Sa disposition desktop est conservée.

## 2.2.0-beta.8 — 6 septembre 2026

### Corrigé

- Sur mobile, les boutons Retirer des seuils d’automatisation et des occurrences
  de flapping s’alignent avec le champ visible : l’espace vide réservé aux erreurs
  n’ajoute plus de hauteur. Les messages de validation restent affichés.
- Les configurations particulières de flapping utilisent le même encadré que
  les délais par entité. La disposition desktop reste inchangée.

## 2.2.0-beta.7 — 6 septembre 2026

### Corrigé

- Sur mobile, les seuils par automatisation ou script et les délais par entité
  affichent leur bouton de retrait à côté du champ, avec un alignement vertical.
- Les configurations particulières de flapping présentent les durées avant le
  nombre d’occurrences. Sur mobile, les durées sont côte à côte lorsque la largeur
  disponible le permet ; les occurrences et le bouton Retirer partagent une ligne.
- Le volet batterie est plus compact sur mobile et propose uniquement les
  appareils ayant un capteur de batterie numérique.
- Le texte « Calcul en cours… » du total suivi reste compact au démarrage.
- Le délai de retour à la normale du flapping dispose d’une explication.

## 2.2.0-beta.6 — 6 septembre 2026

### Corrigé

- Le bouton de suppression de l’historique reste désactivé lorsque celui-ci est
  vide, y compris après un changement d’onglet et un rafraîchissement de l’interface.
- La réévaluation affiche son résultat dans les détails de l’alerte. La fenêtre
  reste ouverte pour lire le résultat si l’alerte n’est plus en cours.
- L’icône de désacquittement utilise une icône Home Assistant valide.
- Le compteur de notifications des détails d’alerte est intitulé « Notifications ».

## 2.2.0-beta.5 — 6 septembre 2026

### Corrigé

- Sur mobile, le bouton Enregistrer de la page Configuration utilise le
  décalage natif Home Assistant au-dessus des onglets. Sa position desktop
  reste inchangée.
- Les étiquettes des exceptions de notification utilisent les badges natifs
  avec couleur et icône.

### Ajouté

- Une exception peut sélectionner plusieurs étiquettes : une seule correspondance
  suffit (logique OU). La première exception correspondante reste prioritaire.
- Les anciennes exceptions à une seule étiquette restent acceptées et sont
  normalisées lors de la validation, y compris pour l’import YAML.

## 2.2.0-beta.4 — 6 septembre 2026

### Corrigé

- Les volets de configuration sont montés hors de la page à onglets, comme
  l’éditeur de règles : leur barre d’actions passe au-dessus de la navigation
  mobile au lieu d’être masquée par celle-ci.
- Ce montage s’applique à l’ouverture, au rafraîchissement et au changement
  de disposition. La saisie, la validation et la fermeture des volets restent
  prises en charge après leur déplacement.

## 2.2.0-beta.3 — 6 septembre 2026

### Corrigé

- Les actions d’enregistrement restent fixes en bas de tous les volets de
  configuration, y compris les profils de notification et les règles personnalisées.
- Le contenu des volets mobiles défile dans l’espace disponible sans entraîner
  la page sous-jacente en fin de défilement.
- Les labels des règles et des alertes affichent leur couleur et leur icône
  avec le composant natif Home Assistant, y compris après un chargement différé.
- La carte des détails d’une alerte conserve sa hauteur et ne coupe plus sa
  dernière ligne dans les fenêtres de faible hauteur.

## 2.2.0-beta.2 — 6 septembre 2026

### Corrigé

- Rétablissement des dates de détection et d’activation dans les détails des
  alertes : les composants de date natifs reçoivent le contexte Home Assistant.
- Conservation d’une date lisible tant que le composant natif n’est pas chargé
  ou ne dispose pas encore du contexte nécessaire à son rendu. Le correctif
  couvre aussi les dates d’acquittement, de résolution et de notification.

## 2.2.0-dev16 — 4 septembre 2026

### Modifié

- Les profils de notification affichent désormais leur nom sur une première ligne,
  puis leur état et leur utilisation sur les dernières 24 heures sur une seconde
  ligne compacte. Les détails techniques redondants ont été retirés de la liste.
- La persistance du runtime évite les écritures de snapshots inchangés, sérialise
  les données hors de la boucle d’événements et diffère la sauvegarde des alertes
  en attente récentes.

### Tests

- Ajout et mise à jour des tests couvrant la présentation compacte des profils et
  l’optimisation des écritures de stockage.

## 2.2.0-dev15 — 4 septembre 2026

### Ajouté

- Chaque profil de notification affiche dans Configuration son nombre
  d’utilisations sur les dernières 24 heures.
- Les utilisations réussies sont conservées après redémarrage dans 24 compteurs
  horaires bornés par profil, sans polling ni nouvelle entité Home Assistant.

### Tests

- Ajout de tests couvrant les nouvelles alertes, résolutions, rappels, échecs,
  notifications de test, restauration du stockage et affichage frontend.

## 2.2.0-dev14 — 4 septembre 2026

### Modifié

- La page Configuration utilise désormais un seul bouton d’enregistrement
  flottant, masqué tant qu’aucun réglage général ou automatique n’a été modifié,
  sur le modèle de l’éditeur d’automatisations de Home Assistant.
- La surveillance automatique est regroupée dans une carte unique, alignée sur
  les autres sections de Configuration. Les packs sont présentés comme des
  sections internes séparées, sans cartes imbriquées.

### Tests

- Ajout de tests frontend couvrant l’état modifié, la sauvegarde commune des
  deux formulaires et la structure sans cartes imbriquées.

## 2.2.0-dev13 — 4 septembre 2026

### Modifié

- La surveillance automatique est maintenant intégrée à la page Configuration
  et n’occupe plus un onglet distinct.
- Les accès rapides de Configuration permettent d’atteindre directement la
  surveillance automatique et sont réorganisés en deux rangées équilibrées.
- L’ancienne URL de l’onglet Surveillance automatique ouvre désormais la page
  Configuration afin de préserver les favoris existants.

### Tests

- Mise à jour des tests frontend couvrant les onglets, la composition de la page
  Configuration, ses accès rapides et la compatibilité de l’ancienne URL.

## 2.0.0-dev13 — 28 août 2026

### Modifié

- La page Configuration est maintenant organisée en blocs distincts pour
  l’affichage des alertes, l’analyse de cohérence, les exclusions et
  l’historique. Sa largeur est plafonnée sur les grands écrans et la mise en
  page repasse en une colonne sur mobile.
- Les références ignorées par l’analyse de cohérence utilisent les chips
  natives de Home Assistant. Une référence peut être ajoutée avec le bouton,
  la touche Entrée ou une virgule, puis supprimée directement depuis sa chip.
- Les labels, entités et appareils exclus sont regroupés dans le même bloc afin
  de ne plus mélanger les réglages de cohérence, d’alerte et d’historique.

### Tests

- Ajout de tests frontend couvrant le rendu compact, l’ajout normalisé, la
  déduplication, la validation, la suppression et la sérialisation des
  références ignorées.

## 1.7.2 — 27 août 2026

### Corrigé

- Correction de la sauvegarde des champs **Message** et **Condition Jinja supplémentaire** des règles personnalisées. Les `ha-selector` de Home Assistant sont des composants contrôlés : leur propriété `value` ne se met pas à jour automatiquement lorsque l’éditeur Jinja interne émet `value-changed`. Alert Manager réinjecte maintenant explicitement la nouvelle valeur dans le sélecteur et utilise le brouillon de règle comme source de vérité lors de la sauvegarde.
- La suppression volontaire du contenu de ces champs reste correctement enregistrée comme valeur vide (`null` côté stockage).

### Tests

- Ajout d’un test reproduisant le comportement réel du sélecteur Template Home Assistant avec une propriété hôte restée vide après saisie.
- Ajout d’un test vérifiant la synchronisation de la valeur des sélecteurs contrôlés.

## 1.7.1 — 27 août 2026

### Corrigé

- Lors de la création d’une règle personnalisée, la condition Jinja supplémentaire
  est désormais récupérée depuis le brouillon de l’éditeur lorsque le composant
  `ha-selector` de Home Assistant n’expose pas encore sa nouvelle valeur via sa
  propriété `.value` au moment de la sauvegarde. Le texte saisi n’est donc plus
  remplacé par une valeur vide à la création de la règle.

### Tests

- Un test frontend reproduit le cas où le sélecteur Jinja a déjà mis à jour le
  brouillon mais expose encore une propriété `.value` indisponible au moment de
  la sauvegarde.

## 1.7.0-dev27 — 27 août 2026

### Corrigé

- Les attributs des capteurs de cycle de vie n’embarquent plus les métadonnées
  récupérables depuis `entity_id` : nom, identifiant et nom d’appareil, zone,
  intégration et unité. Les informations figées utiles aux automatisations sont
  conservées sous une forme compacte.
- Les attributs des capteurs sont plafonnés à 15 000 octets. Si une quantité
  exceptionnelle d’alertes dépasse encore ce budget, la liste est tronquée et
  le nombre restant est exposé dans `alerts_omitted` ou `devices_omitted`, sans
  jamais dépasser la limite Recorder de 16 Kio.
- Le panneau récupère désormais les lignes complètes par WebSocket après un
  changement des capteurs. Il ne dépend donc plus des attributs compacts ou
  éventuellement tronqués pour afficher les alertes.
- Chaque capteur écrit son état uniquement lorsque sa propre partition change ;
  une modification des alertes actives ne réécrit plus inutilement les capteurs
  à venir et acquittés, et inversement.
- Un sélecteur Home Assistant déjà configuré ne reçoit plus un nouvel objet
  `hass` à chaque changement d’état. Cela empêchait la sélection d’une entité de
  rester stable sur les installations de production très actives.
- L’événement `alert_manager_device_alert_started` expose uniquement
  `device_ids` et ne contient plus le champ singulier redondant `device_id`.

### Tests

- Les tests couvrent un capteur contenant 100 alertes avec des messages de
  1 024 caractères, le plafond Recorder, la récupération WebSocket complète,
  la stabilité du sélecteur et l’absence de `device_id` dans les attributs et
  événements appareil.

## 1.7.0-dev26 — 27 août 2026

### Corrigé

- Les modifications du sélecteur Entités d’une règle personnalisée sont
  désormais conservées, aussi bien à la création qu’à l’édition. Le frontend
  accepte les deux formats renvoyés par le composant Home Assistant pour une
  sélection unique ou multiple et récupère la valeur directement depuis le
  sélecteur lorsque l’événement ne la fournit pas.
- La même normalisation protège les autres sélecteurs multiples de la page de
  configuration contre un effacement involontaire.

### Tests

- Deux tests frontend couvrent l’ajout de
  `binary_sensor.filtration_piscine`, le remplacement d’une ancienne entité,
  une sélection multiple et l’événement sans valeur explicite.

## 1.7.0-dev25 — 27 août 2026

### Modifié

- Le champ Message des règles personnalisées utilise désormais le sélecteur
  `template` natif de Home Assistant, comme la condition Jinja supplémentaire.
  Il accepte une saisie multiligne et conserve les retours à la ligne lors de
  l’enregistrement et de la réouverture du volet.

### Tests

- Les tests frontend vérifient la configuration des deux éditeurs Jinja natifs
  et la sérialisation d’un message multiligne.

## 1.7.0-dev24 — 27 août 2026

### Corrigé

- La modification explicite du message d’une règle actualise désormais les
  occurrences déjà actives. Le template Jinja est rendu une fois lors de
  l’enregistrement, puis reste figé malgré les changements ultérieurs des
  entités qu’il consulte.

### Tests

- Un test de non-régression couvre l’ajout d’un message Jinja à une alerte déjà
  active et vérifie que son rendu reste ensuite figé.

## 1.7.0-dev22 — 27 août 2026

### Corrigé

- Les packs automatiques ne contiennent plus aucun texte localisé en dur. Ils
  retournent uniquement une clé de traduction structurée et ses paramètres.
- Le backend traduit les conditions et messages automatiques dans la langue
  globale de Home Assistant pour les capteurs et événements, avec un repli
  anglais si le catalogue est momentanément indisponible.
- La colonne Message affiche maintenant la condition traduite des alertes
  automatiques au lieu de `—`. Le panneau effectue sa propre traduction dans la
  langue de l’utilisateur, y compris pour l’historique existant.

### Tests

- Les tests couvrent les messages français et anglais dans les enregistrements,
  capteurs, événements et tableaux, ainsi que l’absence de texte localisé dans
  les sources des packs.

## 1.7.0-dev21 — 27 août 2026

### Modifié

- Le pack batterie n’utilise plus l’attribut `low_battery_level`. Son seuil
  effectif suit désormais uniquement la priorité seuil par appareil → seuil
  global, dans le moteur comme dans les métadonnées et l’interface.
- Le message Jinja d’une règle reste dynamique pendant l’état à venir, puis son
  dernier rendu est figé au passage en actif. Les changements ultérieurs des
  entités référencées ne modifient plus le message de cette occurrence.
- L’aide des champs Jinja précise qu’ils utilisent l’environnement complet de
  templates Home Assistant et peuvent consulter toutes les entités, sans pour
  autant permettre l’appel de services ou l’exécution de code Python.

### Tests

- Les tests couvrent l’absence de prise en compte de `low_battery_level`, la mise
  à jour du message à venir et son immutabilité après activation.

## 1.7.0-dev20 — 27 août 2026

### Ajouté

- Le champ `message` des règles personnalisées accepte désormais les templates
  Jinja Home Assistant. Le rendu fournit `entity_id`, `state` et `value`, est
  validé avant enregistrement et se réactualise lorsqu’une entité référencée
  change. Les messages simples restent compatibles sans modification.

### Corrigé

- Les libellés et l’aide de la condition Jinja s’affichent correctement dans le
  volet d’ajout et d’édition au lieu de montrer leurs clés de traduction.
- L’aide « Laisser le délai vide pour utiliser le délai global. » est maintenant
  attachée au champ « Délai propre au pack » et s’affiche immédiatement sous son
  input, y compris lorsque le pack expose d’autres options.

### Tests

- 156 tests backend et 69 tests frontend couvrent notamment le rendu Jinja du
  message, ses dépendances et sa validation, les traductions de l’éditeur et le
  placement de l’aide du délai.

## 1.7.0-dev19 — 27 août 2026

### Ajouté

- Les règles personnalisées acceptent une `condition_template` Jinja facultative.
  Lorsqu’elle est définie, elle doit rendre `true` en plus de la comparaison
  existante pour créer ou maintenir l’alerte. Le backend valide sa syntaxe,
  fournit `entity_id`, `state` et `value`, et réévalue la règle quand une entité
  référencée par le template change.
- Le pack batteries déclare désormais lui-même ses champs supplémentaires dans
  ses métadonnées. Il expose notamment `device_thresholds`, une table
  appareil → seuil éditable avec les sélecteurs Home Assistant. Le seuil propre
  à l’appareil est prioritaire sur `low_battery_level`, puis sur le seuil global.

### Modifié

- `sensor.alert_manager_device_main_active` n’expose plus les tableaux globaux
  `messages` et `rules`. Chaque entrée de `devices` conserve ses propres tableaux,
  correspondant exactement aux alertes de ce groupe.
- `alert_manager_device_alert_started` attend désormais 10 secondes sans nouvelle
  alerte pour le même groupe avant son émission. Toute alerte supplémentaire
  pendant ce délai redémarre la temporisation ; l’événement final contient les
  tableaux stabilisés `messages` et `rules` du groupe.

### Tests

- 154 tests backend et 69 tests frontend couvrent les seuils batterie par
  appareil, les métadonnées déclaratives du pack, la condition Jinja et ses
  dépendances, le debounce d’événement ainsi que la nouvelle forme du capteur.

## 1.7.0-dev18 — 27 août 2026

### Corrigé

- Le bouton retour et son lien de secours figé vers les intégrations sont
  supprimés. Toutes les pages du panneau sont maintenant déclarées comme pages
  principales et affichent le bouton menu natif de Home Assistant.
- La clé de cache du bundle frontend est renouvelée pour garantir le chargement
  de ce correctif lors d’une réinstallation de la release dev18 republiée.

### Ajouté

- `sensor.alert_manager_device_main_active` expose les attributs globaux
  `messages` et `rules`, sous forme de tableaux uniques pour toutes les alertes
  appareil actives. Chaque entrée de `devices` contient également ses propres
  tableaux `messages` et `rules` afin de conserver le détail par appareil.

### Tests

- 147 tests backend et 69 tests frontend couvrent l’absence complète de lien de
  retour, l’affichage du menu natif et les nouveaux tableaux d’attributs,
  notamment lorsque plusieurs identifiants d’appareil partagent le même nom.

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
