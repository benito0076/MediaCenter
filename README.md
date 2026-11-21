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

Options : `--port 9000`, `--reseau` (accès depuis la TV / le téléphone via `http://IP-du-PC:8765`).
Nouveaux fichiers téléchargés : relancer le programme pour rescanner.

## Limites
Le navigateur lit nativement MP4/WebM, MP3/FLAC/OGG/M4A/WAV. Les **MKV** passent dans Chrome/Edge si la vidéo est en H.264 ; les **AVI** et certains codecs audio (DTS, AC3) ne sont pas lus — pour ceux-là, utiliser VLC, ou [Jellyfin](https://jellyfin.org) qui transcode à la volée.
