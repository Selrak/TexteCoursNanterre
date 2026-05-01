# Spécifications générales

Ce document recueille les directions générales du projet. Il doit être complété au fur et à mesure quand une nouvelle idée structurante apparaît.

Les détails d'implémentation directement lisibles dans le code ne sont pas recopiés ici. Ce document décrit les objectifs, les contraintes d'usage et les choix de produit qui doivent guider les évolutions.

## Objectif

Le projet reçoit l'URL d'un cours sur la plateforme de Nanterre.

Il doit ensuite trouver les séances du cours, extraire les sous-titres disponibles, puis lancer le post-traitement qui transforme ces sous-titres en texte exploitable.

## Authentification

Le projet utilise les cookies cachés quand ils sont disponibles et valides.

Si nécessaire, il doit utiliser une authentification par navigateur, mais cette étape doit rester intégrée au flux utilisateur principal autant que possible.

## Utilisateurs

Le développeur principal utilise souvent macOS Catalina avec Firefox.

L'utilisatrice principale utilise Windows 11 Famille sur un laptop Dell, avec Chrome. Elle ne connaît pas beaucoup l'informatique.

L'interface destinée à l'utilisatrice principale doit donc être très simple, explicite et sans mystère. Elle ne doit pas demander de comprendre les cookies, les fichiers cachés, les modes techniques ou les détails internes du téléchargement.

Dans l'interface utilisateur, le vocabulaire doit privilégier `coursenligne` plutôt que `Moodle`, car c'est le nom que l'utilisatrice connaît. Les termes techniques comme Moodle peuvent rester dans le code ou dans les diagnostics destinés au développement quand ils sont nécessaires.

## Diagnostic

Le développeur principal a besoin de logs et d'informations suffisamment précises pour diagnostiquer les échecs.

Les diagnostics doivent rester utiles sans exposer de secrets comme les cookies, jetons de session ou en-têtes d'authentification.
