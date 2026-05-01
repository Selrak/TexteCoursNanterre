# docs/CODEX_MANIFEST.md

# Traiter texte cours – CODEX_MANIFEST

Ce script devra prendre en entrée du texte VTT de cette forme : 

"WEBVTT

1
00:00:00.000 --> 00:00:00.760
de vous suivre.

2
00:00:01.900 --> 00:00:05.180
Donc, je vous propose ce

3
00:00:05.340 --> 00:00:10.140
semestre un cours sur les

4
00:00:10.500 --> 00:00:12.080
certitudes des lumières.

5
00:00:12.380 --> 00:00:15.420
C'est un cours qui a un double

6
00:00:15.580 --> 00:00:18.200
objectif. Il s'agit d'une part

7
00:00:18.360 --> 00:00:23.040
de travailler effectivement le
concept de certitude à travers

8
00:00:23.200 --> 00:00:27.480
un certain nombre de textes
majeurs de la philosophie et

9
00:00:27.640 --> 00:00:28.400
de la science moderne.

10
00:00:28.640 --> 00:00:31.860
Donc, vous avez vu, parce que
j'ai pas sans doute prévu tout

11
00:00:32.019 --> 00:00:34.860
à fait assez de plans,
mais vous avez vu si vous en
"
(ainsi de suite)
donc
le titre WEBVTT (parfois absent)
puis de maniére répétée :
- une ligne vide
- un compteur incrémentant par pas de 1 à partir de 1
- une ligne avec des horodatages
- un certain nombre de lignes de texte

Le script devra pour un seul tel fichier
- Sortir tout le texte en omettant les lignes vides, le titre WEBVTT si présent, le compteur incrémental, et les horodatages
- De manière optionelle : appeler l'API chatGPT pour proposer des découpages en paragraphes avec titres de parties et bornes temporelles de la partie.
L'appel à l'API sera tel que la seule sortie demandée sera les horodatages de chaque partie et leur titre, sans recracher tout le texte.

Si une question porte sur une erreur ou un problème d'une exécution récente de l'interface Tkinter, lire d'abord le fichier de log de session le plus récent dans `ubicast_course_downloader/downloads/logs/`.
Ce fichier reprend la sortie visible de la zone "Activité" avec un horodatage à la seconde sur chaque ligne.

Si l'utilisateur donne une nouvelle idée générale ou une nouvelle direction de produit, Codex doit la documenter dans `SPECIFICATIONS.md`.

Quand un problème est résolu ou qu'une fonctionnalité est terminée, Codex ne doit pas créer de commit ni pousser automatiquement. Codex doit attendre que l'utilisateur confirme, après un test physique de l'application, que tout est conforme à ce qu'il veut. Le commit et le push ne doivent être faits qu'après cette confirmation explicite.
