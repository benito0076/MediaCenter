# Media Center

Un seul fichier Python, aucune dépendance. Liste tes films et ta musique, recherche, lecture dans le navigateur (avance/retour rapide, enchaînement automatique des morceaux).

## Installation (Windows)
1. Installer [Python 3](https://www.python.org/downloads/) (cocher « Add Python to PATH »).
2. Télécharger ce dossier.
3. Première fois, dans un terminal ouvert dans ce dossier :
   ```
   python mediacenter.py --films "D:\Films" --series "D:\Series" --musique "D:\Musique"
   ```
   (`--films` / `--series` / `--musique` répétables pour plusieurs dossiers ; on peut en ajouter un plus tard, les autres sont gardés.)
4. Ensuite : double-clic sur `MediaCenter.bat`. Le navigateur s'ouvre sur http://localhost:8765.

## Affiches et résumés
Au lancement, les affiches et résumés (en français) sont récupérés sur iTunes, gratuitement et sans compte, en arrière-plan : rafraîchis la page pour les voir apparaître. Comptez ~3 s par film la première fois (limite d'iTunes), ensuite tout est mémorisé dans `mediacenter_cache.json`. **Meilleure couverture avec TMDB (recommandé)** : crée un compte gratuit sur [themoviedb.org](https://www.themoviedb.org/signup), puis *Paramètres → API → Demander une clé* (usage personnel). Copie la « Clé d'API » (ou le « Jeton d'accès en lecture ») et lance une fois :
```
python mediacenter.py --tmdb TA_CLE
```
La clé est mémorisée dans `mediacenter.json`. TMDB est rapide (pas d'attente de 3 s) et repasse automatiquement sur les films déjà traités par iTunes.

Le titre est deviné à partir du nom du fichier (`Inception.2010.1080p.mkv` → *Inception*, 2010). Film mal reconnu : renomme le fichier `Titre (Année).mkv`, retire sa ligne de `mediacenter_cache.json` et relance.

## Séries TV
Les épisodes sont regroupés par série grâce au nom du fichier (`Breaking.Bad.S01E02…`, `Kaamelott 1x02…`) ou, à défaut, au nom du dossier de la série (`Series/Breaking Bad/Saison 1/…`). Clic sur une série → liste des épisodes dans l'ordre ; l'épisode suivant démarre automatiquement. Affiche et résumé de la série : TMDB si une clé est donnée, sinon iTunes.

## Pochettes d'albums
Pour chaque dossier d'album, le Media Center utilise l'image présente dans le dossier (`cover.jpg`, `folder.jpg`, `front.png`… sinon la première image trouvée). À défaut, il prend la pochette intégrée aux fichiers (MP3, FLAC, M4A). S'il n'y en a toujours pas, il cherche la pochette sur iTunes d'après le nom du dossier (`Artiste - Album` ou `Artiste/Album`), en arrière-plan, et la mémorise dans `mediacenter_cache.json`.

Options : `--hors-ligne` (pas de recherche internet), `--port 9000`, `--reseau` (accès depuis la TV / le téléphone via `http://IP-du-PC:8765`).
Nouveaux fichiers téléchargés : relancer le programme pour rescanner.

## Limites
Le navigateur lit nativement MP4/WebM, MP3/FLAC/OGG/M4A/WAV. Les **MKV** passent dans Chrome/Edge si la vidéo est en H.264 ; les **AVI** et certains codecs audio (DTS, AC3) ne sont pas lus — pour ceux-là, utiliser VLC, ou [Jellyfin](https://jellyfin.org) qui transcode à la volée.
