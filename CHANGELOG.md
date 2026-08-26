# Changelog

Toutes les évolutions notables d’Alert Manager sont documentées dans ce fichier.

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
