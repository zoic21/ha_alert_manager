# Changelog

Toutes les évolutions notables d’Alert Manager sont documentées dans ce fichier.

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
