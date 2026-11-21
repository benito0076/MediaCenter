# Media Center

Films, séries et musique dans le navigateur, sur le PC, la TV et le téléphone. Un seul fichier Python (ou un `.exe` Windows), sans installation.

## Installation (Windows) — le plus simple : le .exe
1. Télécharger **[MediaCenter.exe](https://github.com/benito0076/MediaCenter/releases/latest/download/MediaCenter.exe)** (toujours la dernière version, sans compte GitHub), le mettre dans un dossier à lui (ex. `C:\MediaCenter`). Il se mettra ensuite à jour tout seul.
2. Double-clic : au premier lancement, choisir les dossiers de films, séries et musique. Le navigateur s'ouvre sur http://localhost:8765.
3. Le Media Center reste **près de l'horloge** (icône rouge ▶) : *Ouvrir*, *Actualiser la bibliothèque*, *Démarrer avec Windows* (lancement discret à l'ouverture de session), *Quitter*. Un nouveau double-clic ouvre simplement le navigateur. Les messages vont dans `mediacenter.log`, à côté du .exe.

Windows SmartScreen peut avertir (programme non signé) : *Informations complémentaires* → *Exécuter quand même*. Options en ligne de commande : `MediaCenter.exe --reseau --pin 1234`, `--tmdb CLE`, `--demarrage-auto oui|non`, `--sans-navigateur`…

**Avec Python** (sans le .exe) : `python mediacenter.py --films "D:\Films" --series "D:\Series" --musique "D:\Musique"` la première fois, puis `MediaCenter.bat`.

## Langue / Idioma
Interface en **français** ou en **espagnol** : celle de Windows par défaut, bouton **🌐** en haut pour changer (ou `--langue es|fr`). Les sous-titres choisis d'office suivent la langue. Seule l'interface est traduite, jamais les titres de ta bibliothèque.

## Télécommande de la TV / clavier
Sur un navigateur de TV ou au clavier : **flèches** pour aller d'une affiche / d'un morceau à l'autre (repère blanc), **Entrée** pour lancer, **Retour / Échap** pour revenir, **Espace** pour lecture / pause. Sur un morceau, **→** atteint ses boutons ↱ et +.

## Profils
Menu **👤** en haut : chaque personne a son « déjà vu », sa reprise et son accueil (*➕ Nouveau profil*). Chaque navigateur retient son profil ; la musique, la file d'attente et la télécommande restent communes.

## Trier et filtrer
Films et Séries : **Trier** (titre, ajoutés récemment, année), **Genre** (d'après TMDB / iTunes) et **Non vus**. Les choix sont gardés par navigateur.

## Outils manquants et mises à jour
Sur le PC, un bandeau signale s'il manque **ffmpeg** ou un lecteur pour l'ampli, avec un bouton **Installer** (winget, l'installateur de Windows) : l'outil est pris en compte sans redémarrer. Une fois par jour, le .exe regarde s'il existe une **nouvelle version** (releases GitHub du dépôt) : bouton **Mettre à jour** → téléchargement, remplacement du .exe et relance automatiques. Ces boutons ne marchent que depuis le PC lui-même.

## Chromecast
Dans Chrome **sur le PC** (http://localhost:8765), avec le Media Center lancé en `--reseau` : bouton **📺 Chromecast** sous la vidéo → la TV lit le film directement depuis le PC, à la même position, avec les sous-titres. Les formats que le Chromecast ne lit pas (MKV, AVI, HEVC…) sont convertis à la volée (ffmpeg). Le code d'accès (`--pin`) est transmis automatiquement. *Non testé sur un vrai Chromecast.*

## Signature du .exe (optionnel, payant)
Pour que Windows SmartScreen ne prévienne plus, il faut un **certificat de signature de code** (≈ 100 à 400 € / an, à ton nom). Une fois acheté : dans le dépôt GitHub, *Settings → Secrets and variables → Actions*, ajouter `WINDOWS_CERT_PFX` (le fichier .pfx encodé en base64) et `WINDOWS_CERT_PASSWORD`. Le .exe sera alors signé automatiquement à chaque fabrication.

## Accueil
La page d'accueil montre **▶ Reprendre** (ce qui a été commencé, barre de progression), **⏭ Épisodes suivants** (l'épisode d'après le dernier vu, pour chaque série) et **🆕 Ajoutés récemment** ; un clic lance la lecture directement.

## Nouveaux téléchargements
Les dossiers sont revus **toutes les 5 minutes** : un film, un épisode ou un album téléchargé apparaît tout seul (affiche et résumé compris). Bouton **🔄** en haut pour le faire tout de suite. (Un fichier supprimé reste listé jusqu'au prochain redémarrage.)

## Vidéos que le navigateur ne lit pas (AVI, HEVC/H.265…)
Avec ffmpeg, elles sont **converties à la volée** par le PC, par morceaux de 6 secondes (HLS) : lecture immédiate, avance/retour n'importe où, sous-titres, reprise et télécommande comme pour les autres. Le PC travaille pendant la lecture (conversion H.264) : prévoir un processeur correct pour du 1080p.

## Accès depuis la TV / le téléphone : code d'accès
`--reseau` rend le Media Center accessible depuis le Wi-Fi (`http://IP-du-PC:8765`). Ajoute **`--pin 1234`** (mémorisé ; `--pin aucun` pour l'enlever) : chaque nouvel appareil demande le code une fois puis s'en souvient ; le PC lui-même n'en demande jamais. 10 codes faux → bloqué 5 minutes.

## Grandes bibliothèques
Des milliers de morceaux s'affichent sans ralentir (seules les lignes visibles sont dessinées). Les polices extraites des MKV inutilisées depuis 60 jours sont supprimées au démarrage.

## Affiches et résumés
Au lancement, les affiches et résumés (en français) sont récupérés sur iTunes, gratuitement et sans compte, en arrière-plan : rafraîchis la page pour les voir apparaître. Comptez ~3 s par film la première fois (limite d'iTunes), ensuite tout est mémorisé dans `mediacenter_cache.json`. **Meilleure couverture avec TMDB (recommandé)** : crée un compte gratuit sur [themoviedb.org](https://www.themoviedb.org/signup), puis *Paramètres → API → Demander une clé* (usage personnel). Copie la « Clé d'API » (ou le « Jeton d'accès en lecture ») et lance une fois :
```
python mediacenter.py --tmdb TA_CLE
```
La clé est mémorisée dans `mediacenter.json`. TMDB est rapide (pas d'attente de 3 s) et repasse automatiquement sur les films déjà traités par iTunes.

Le titre est deviné à partir du nom du fichier (`Inception.2010.1080p.mkv` → *Inception*, 2010). Film mal reconnu : renomme le fichier `Titre (Année).mkv`, retire sa ligne de `mediacenter_cache.json` et relance.

## Séries TV
Les épisodes sont regroupés par série grâce au nom du fichier (`Breaking.Bad.S01E02…`, `Kaamelott 1x02…`) ou, à défaut, au nom du dossier de la série (`Series/Breaking Bad/Saison 1/…`). Clic sur une série → liste des épisodes dans l'ordre ; l'épisode suivant démarre automatiquement. Affiche et résumé de la série : TMDB si une clé est donnée, sinon iTunes.

## Reprise de lecture et « déjà vu »
Films et épisodes reprennent là où tu les as arrêtés (barre rouge sous le titre). Passé 90 % (générique), ils sont marqués **vus** ✓ ; clique sur le ✓ pour cocher/décocher à la main. Le suivi est enregistré sur le PC (`mediacenter_suivi.json`), donc partagé entre le PC, la TV et le téléphone en mode `--reseau`.

## Pistes audio (VF / VO…)
Les navigateurs ne savent pas changer de piste audio. Avec ffmpeg installé, un menu **🔈 Audio** apparaît sous la vidéo dès qu'un film a plusieurs pistes : la piste choisie est convertie une fois par le PC (jusqu'à une minute la première fois, ensuite immédiat) puis jouée en synchronisation avec l'image. Les films dont le son est en **AC3 / DTS / TrueHD** (muets dans le navigateur) sont convertis d'office. Le **son surround est gardé** : une piste 5.1 reste en 5.1 (une 7.1 est ramenée en 5.1, les canaux arrière mélangés aux surrounds) ; si ton PC n'a que deux haut-parleurs, le navigateur la remixe lui-même en stéréo. Le menu indique le format (« Français (ac3, 5.1) »). Les pistes converties sont gardées dans `audio_cache/` (~150 Mo par piste de film en stéréo, ~300 Mo en 5.1), **5 Go au plus** : au-delà, les pistes écoutées il y a le plus longtemps sont supprimées automatiquement (elles seront reconverties si besoin). Pour changer la limite : `python mediacenter.py --cache-audio 20` (en Go, mémorisé). Pour tout libérer d'un coup : bouton **🗑 Vider le cache audio** en bas des pages Films et Séries (la piste d'un film en cours de lecture est gardée).

## Passthrough vers l'ampli home cinéma
Un navigateur décode toujours le son lui-même : impossible d'envoyer le Dolby / DTS d'origine à un ampli depuis une page web. Le Media Center tournant sur le PC branché à l'ampli, il peut en revanche ouvrir le film dans **mpv** (recommandé : AC3, E-AC3, DTS, DTS-HD MA et TrueHD) ou **VLC** sur ce PC, en plein écran, **à la même position et avec la même piste audio**, son envoyé tel quel à l'ampli par HDMI ou S/PDIF :
- installe mpv (`winget install mpv`) ou VLC, puis relance le Media Center : il les trouve tout seul (sinon `--lecteur-externe "C:\chemin\mpv.exe"`, mémorisé) ;
- bouton **🔊 Lire sur l'ampli (passthrough)** sous la vidéo, ou **🔊 Sur l'ampli** dans la télécommande du téléphone ; la lecture dans le navigateur se met en pause ;
- côté Windows : régler la sortie son sur l'ampli (HDMI) ; avec VLC, activer si besoin la passthrough HDMI dans ses préférences audio.
**Avec mpv comme avec VLC, la télécommande du Media Center continue de marcher** (téléphone, ou la page restée ouverte sur le PC) : bandeau « … (mpv) » avec ⏯, ⏪ 10 s / 30 s ⏩, volume, sous-titres, piste audio, épisode suivant, et toucher un autre film / épisode le lance dans mpv. (VLC est piloté par son interface web, activée par le Media Center au lancement, accessible seulement depuis le PC et protégée par un mot de passe tiré au hasard. VLC ne dit pas quelle piste audio / sous-titres est active : le menu affiche le dernier choix fait depuis la télécommande.)

## Sous-titres
Les fichiers `.srt` / `.vtt` / `.ass` / `.ssa` sont détectés automatiquement : même nom que la vidéo (`Film.2020.srt`, `Film.2020.fr.srt`, `Film.2020.en.srt`) ou, si la vidéo est seule dans son dossier, tout `.srt` du dossier et d'un sous-dossier `Subs/`. Le français est activé par défaut ; change de langue ou coupe-les avec le bouton du lecteur (⋮ → Sous-titres, ou CC). Les accents des vieux `.srt` (Windows-1252) sont gérés.

**Animés (`.ass` / `.ssa`) : rendu stylé** avec [JASSUB](https://github.com/ThaUnknown/jassub) (libass, le moteur de VLC/mpv, en WebAssembly) : polices, couleurs, contours, positions, panneaux, karaoké, comme dans un lecteur dédié. Marche pour les `.ass` à côté de la vidéo et, avec ffmpeg, pour ceux intégrés aux MKV.
- Polices : celles jointes au MKV (extraites une fois dans `polices_cache/`) et celles d'un dossier `Fonts/` à côté de la vidéo ; sinon une police par défaut.
- Plein écran : bouton ⛶ en haut à droite de la vidéo ou double-clic (le plein écran natif du navigateur cacherait les sous-titres stylés).
- Navigateur trop ancien ou erreur : retour automatique aux sous-titres simples (texte + italique).

JASSUB est fourni dans le dossier `jassub/` (version 2.5.38, licence LGPL, voir `jassub/LICENSE`), pré-assemblé avec esbuild : rien à installer, marche sans internet.

**Sous-titres intégrés aux MKV** (et MP4) : installer [ffmpeg](https://ffmpeg.org) une fois, puis relancer :
```
winget install ffmpeg
```
Les pistes texte (SRT, ASS, …) apparaissent alors dans le menu sous-titres (« Français », « Anglais – SDH »…). Elles mettent quelques secondes à s'afficher la première fois (ffmpeg lit le fichier). Les sous-titres en image (PGS des Blu-ray, VobSub des DVD) ne peuvent pas être affichés par le navigateur.

## Lecture aléatoire et répéter tout (musique)
Bouton **⏮ Précédent** : si le morceau joue depuis plus de 3 s, il revient à son début ; sinon il passe au morceau d'avant (en aléatoire : celui joué juste avant). Bouton **⏭ Suivant** (les deux marchent aussi avec les touches ⏮ ⏭ du clavier ou du casque) : passe au morceau suivant en respectant l'aléatoire et « Répéter tout » ; en « Répéter 1 », il passe quand même au suivant, qui tourne alors en boucle. Bouton **🔀 Aléatoire** : chaque morceau est joué une fois dans un ordre au hasard, puis la lecture s'arrête. Bouton **🔁 Répéter**, à chaque clic : *Répéter tout* (à la fin de la liste, on recommence au début ; en aléatoire, nouveau tirage sans rejouer tout de suite le même morceau) → *🔂 Répéter 1* (le morceau en cours tourne en boucle) → désactivé. Les deux respectent la recherche (tape un artiste ou un album pour ne jouer que celui-ci) et restent activés au prochain lancement.

### Morceau en cours synchronisé entre appareils
Le morceau en cours est **commun à tous les appareils** et enregistré sur le PC (`mediacenter_encours.json`). Un appareil à l'arrêt affiche ce que joue un autre (même morceau, position suivie toutes les 5 s), **en pause** : appuie sur ▶ pour continuer l'écoute ici, puis mets l'autre en pause (passage de relais). Même chose après un rechargement ou au prochain lancement : tout est prêt à la bonne seconde. Les navigateurs interdisent de lancer le son tout seul, d'où le ▶. Un appareil qui joue n'est jamais interrompu par un autre.

### Télécommande depuis le téléphone
Lance le Media Center avec `--reseau` et ouvre `http://IP-du-PC:8765/?k=musique` sur le téléphone. Quand le PC (ou la TV) joue, un bandeau rouge **🎛 Sur un autre appareil** apparaît sur le téléphone : ⏮ ⏯ ⏭ et le curseur de volume 🔊 pilotent le PC (le curseur suit aussi le volume réglé sur le PC), et toucher un morceau de la liste le lance **sur le PC**. Les boutons ⏮ Précédent / ⏭ Suivant et la file d'attente (+, ↱) agissent aussi sur le PC. Pour écouter sur le téléphone à la place, appuie sur ▶ du lecteur du téléphone : c'est alors le PC qui devient télécommande. Le bandeau disparaît si la page du PC est fermée.

### Télécommande pour les films et séries
Même principe sur les onglets Films et Séries : quand la TV (ou le PC) joue un film ou un épisode, le téléphone affiche un bandeau **🎛 Sur un autre appareil : titre — 0:41 / 2:00** avec ⏪ 10 s, ⏯, 30 s ⏩, le volume 🔊, le menu **💬 sous-titres** (choisir une langue ou « Sans sous-titres » ; les `.ass` gardent leur rendu stylé), le menu **🔈 piste audio** (VF / VO…) et, pour les séries, **⏭ Épisode suivant**. Si le téléphone est sur la même page que la TV (la liste des films, ou la même série), toucher un film ou un épisode le lance **sur la TV**. Le plein écran doit être activé sur la TV elle-même (les navigateurs ne l'autorisent pas à distance).

### File d'attente
Le **+** au bout de chaque morceau l'ajoute à la fin de la file **À suivre** (affichée sous les boutons) ; le **↱** le place en tête (« lire juste après » : il passera dès la fin du morceau en cours). Ces morceaux passent avant la suite normale ou aléatoire, dans l'ordre d'ajout, même s'ils sont masqués par la recherche. Pour changer l'ordre, **glisse-dépose** un morceau sur un autre, ou utilise **↑ ↓** (clavier, écran tactile). Clic sur un morceau de la file : il joue tout de suite ; **×** le retire ; **Vider la file** efface tout. La file est **commune à tous les appareils** (PC, TV, téléphone en mode `--reseau`) et enregistrée sur le PC (`mediacenter_file.json`) : ajoute un morceau depuis le téléphone, il apparaît sur le PC en 5 secondes au plus. Elle survit au rechargement et au redémarrage du Media Center (même si de nouveaux morceaux ont été ajoutés ; ceux supprimés entre-temps sont simplement retirés). Si deux appareils modifient la file dans la même seconde, la dernière modification l'emporte.

## Pochettes d'albums
Pour chaque dossier d'album, le Media Center utilise l'image présente dans le dossier (`cover.jpg`, `folder.jpg`, `front.png`… sinon la première image trouvée). À défaut, il prend la pochette intégrée aux fichiers (MP3, FLAC, M4A). S'il n'y en a toujours pas, il cherche la pochette sur iTunes d'après le nom du dossier (`Artiste - Album` ou `Artiste/Album`), en arrière-plan, et la mémorise dans `mediacenter_cache.json`.

Options : `--hors-ligne` (pas de recherche internet), `--port 9000`, `--reseau` (accès depuis la TV / le téléphone via `http://IP-du-PC:8765`).
Nouveaux fichiers téléchargés : relancer le programme pour rescanner.

## Limites
Sans ffmpeg, seules les vidéos lisibles par le navigateur passent (MP4/WebM/MKV en H.264, VP9, AV1) ; avec ffmpeg, tout est converti au besoin (vidéo à la volée, son AC3/DTS, sous-titres des MKV).
