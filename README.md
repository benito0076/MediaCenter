# Media Center

Un seul fichier Python, aucune dépendance. Liste tes films et ta musique, recherche, lecture dans le navigateur (avance/retour rapide, enchaînement automatique des morceaux).

## Installation (Windows)
1. Installer [Python 3](https://www.python.org/downloads/) (cocher « Add Python to PATH »).
2. Télécharger ce dossier.
3. Première fois, dans un terminal ouvert dans ce dossier :
   ```
   python mediacenter.py --films "D:\Films" --musique "D:\Musique"
   ```
   (`--films` / `--musique` répétables pour plusieurs dossiers.)
4. Ensuite : double-clic sur `MediaCenter.bat`. Le navigateur s'ouvre sur http://localhost:8765.

## Affiches et résumés
Au lancement, les affiches et résumés (en français) sont récupérés sur iTunes, gratuitement et sans compte, en arrière-plan : rafraîchis la page pour les voir apparaître. Comptez ~3 s par film la première fois (limite d'iTunes), ensuite tout est mémorisé dans `mediacenter_cache.json`. **Meilleure couverture avec TMDB (recommandé)** : crée un compte gratuit sur [themoviedb.org](https://www.themoviedb.org/signup), puis *Paramètres → API → Demander une clé* (usage personnel). Copie la « Clé d'API » (ou le « Jeton d'accès en lecture ») et lance une fois :
```
python mediacenter.py --tmdb TA_CLE
```
La clé est mémorisée dans `mediacenter.json`. TMDB est rapide (pas d'attente de 3 s) et repasse automatiquement sur les films déjà traités par iTunes.

Le titre est deviné à partir du nom du fichier (`Inception.2010.1080p.mkv` → *Inception*, 2010). Film mal reconnu : renomme le fichier `Titre (Année).mkv`, retire sa ligne de `mediacenter_cache.json` et relance.

Options : `--hors-ligne` (pas de recherche internet), `--port 9000`, `--reseau` (accès depuis la TV / le téléphone via `http://IP-du-PC:8765`).
Nouveaux fichiers téléchargés : relancer le programme pour rescanner.

## Limites
Le navigateur lit nativement MP4/WebM, MP3/FLAC/OGG/M4A/WAV. Les **MKV** passent dans Chrome/Edge si la vidéo est en H.264 ; les **AVI** et certains codecs audio (DTS, AC3) ne sont pas lus — pour ceux-là, utiliser VLC, ou [Jellyfin](https://jellyfin.org) qui transcode à la volée.
