#!/usr/bin/env python3
"""Media Center minimaliste : films, séries + musique dans le navigateur. Python 3.8+, zéro dépendance.

Usage :  python mediacenter.py --films "D:\\Films" --series "D:\\Series" --musique "D:\\Musique"
Les dossiers sont mémorisés dans mediacenter.json ; ensuite `python mediacenter.py` suffit.
Affiches et résumés : TMDB si une clé est donnée (--tmdb CLE), sinon iTunes ; gardés dans mediacenter_cache.json.
"""
import argparse, hashlib, hmac, html, io, json, math, mimetypes, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, webbrowser, zipfile
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, quote, unquote
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# .exe (PyInstaller) : données à côté du .exe, ressources (JASSUB) dans le dossier temporaire du .exe.
GELE = getattr(sys, "frozen", False)
BASE = Path(sys.executable).parent if GELE else Path(__file__).parent
RESSOURCES = Path(getattr(sys, "_MEIPASS", BASE))
CONFIG = BASE / "mediacenter.json"
CACHE = BASE / "mediacenter_cache.json"
SUIVI_F = BASE / "mediacenter_suivi.json"
FILE_F = BASE / "mediacenter_file.json"
FILE = []  # file d'attente musique commune à tous les appareils : ["dossier/fichier", …]
ENCOURS_F = BASE / "mediacenter_encours.json"
ENCOURS = {}  # morceau en cours, commun à tous les appareils : {"k", "t", "lecture", "dev", "quand"}
COMMANDES = {}  # télécommande : id d'appareil -> [commandes en attente]
RELEVE = {}  # id d'appareil -> heure du dernier relevé de commandes (= page ouverte, joignable)
ORDRES = {"lecture", "pause", "suivant", "precedent", "jouer", "volume", "deplacer", "soustitres", "audio"}
VIDEO = {}  # film/épisode en cours (pour la télécommande) : {"kind", "id", "titre", "t", "d", "lecture", "vol", "page", "dev", "quand"}
SUIVI = {}  # nom de fichier vidéo -> {"t": position (s), "d": durée (s), "vu": bool}  (profil « Principal »)
# Profils : chacun son « déjà vu », sa reprise et son accueil (fichier mediacenter_suivi_<…>.json) ; choisi par cookie.
PROFILS = []  # noms des profils en plus de « Principal »
SUIVIS = {"": SUIVI}
ACTUEL = threading.local()  # profil de la requête en cours
VERROU = threading.Lock()
EXT = {
    "films": {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v"},
    "series": {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v"},
    "musique": {".mp3", ".flac", ".ogg", ".m4a", ".wav", ".opus", ".aac"},
}
LIB = {"films": [], "series": [], "musique": []}  # (titre, sous-dossier ou nom de série, chemin absolu)
META = {}  # nom de fichier -> {"titre", "annee", "resume", "affiche"} ; "serie:<nom>" -> idem ; "album:<dossier>" -> {"affiche"} ; {} = introuvable
COVERS = {}  # dossier de musique -> image locale (cover.jpg…), ou morceau avec pochette intégrée, ou None
IMG = {".jpg", ".jpeg", ".png", ".webp"}
SUBS = {}  # chemin vidéo -> [fichiers .srt/.vtt/.ass]
WEB_DIR = RESSOURCES / "web"  # pages de l'interface
HLSJS_DIR = RESSOURCES / "hlsjs"  # hls.js : lecture des vidéos converties à la volée (HLS)
JASSUB_DIR = RESSOURCES / "jassub"  # rendu stylé des .ass (libass en WebAssembly), servi en local
POLICES_DIR = BASE / "polices_cache"  # polices extraites des MKV
POLICES = {}  # chemin vidéo -> [fichiers de police]
AUDIO_DIR = BASE / "audio_cache"  # pistes audio converties pour le navigateur (AAC, stéréo ou 5.1)
ACCES = {"jeton": None}  # PIN pour les autres appareils (--pin) : jeton attendu dans le cookie « mc »
ECHECS = {}  # adresse -> [nombre d'erreurs de PIN, heure de la première]
AJOUT = {}  # chemin -> date du fichier (téléchargement)
CFG = {}  # réglages chargés au démarrage (pour la page de diagnostic)
RESCAN = [lambda: 0]  # bouton 🔄 : analyse immédiate des dossiers (défini dans main)
LECTEUR = [None]  # lecteur externe (mpv ou VLC) pour la passthrough vers l'ampli
PILOTE = {}  # mpv ou VLC lancé par le Media Center : {"type", "proc", "kind", "id", "titre", (VLC) "port", "mdp", "aui", "sti"}
MPV_IPC = r"\\.\pipe\mediacenter-mpv" if os.name == "nt" else os.path.join(tempfile.gettempdir(), "mediacenter-mpv.sock")
CACHE_AUDIO_MAX = [5 * 1024 ** 3]  # taille max du cache audio (octets), réglable avec --cache-audio
AUDIOS = {}  # chemin vidéo -> [{"nom", "convertir"}] (pistes audio, via ffprobe)
EXTRACTIONS = {}  # fichier de sortie -> "en cours" | message d'erreur
NON_LU = {"ac3", "eac3", "dts", "truehd", "mlp", "pcm_bluray", "pcm_dvd"}  # codecs audio que les navigateurs ne lisent pas
FONT_EXT = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}
for _ext, _type in ((".js", "text/javascript"), (".wasm", "application/wasm"), (".woff2", "font/woff2"),
                    (".ttf", "font/ttf"), (".otf", "font/otf")):
    mimetypes.add_type(_type, _ext)  # le registre Windows donne parfois text/plain pour .js : modules refusés
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")  # optionnels : sous-titres intégrés
PISTES = {}  # chemin vidéo -> [(nom, n° de piste de sous-titres)] (intégrées, format texte)
VTT = {}  # (chemin vidéo, n° de piste) -> WebVTT extrait  # ponytail: en mémoire, vidé au redémarrage
TEXTE = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}  # PGS/VobSub = images : non convertibles
# --- Langue de l'interface (français d'origine, espagnol) : seuls les textes de l'interface sont traduits,
# jamais les titres de la bibliothèque.
LANGUE = ["fr"]
ES = {
    'lang="fr"': 'lang="es"', "Accueil": "Inicio", "Films (": "Películas (", "Séries (": "Series (", "Musique (": "Música (",
    "Rechercher…": "Buscar…", "Chercher les nouveaux fichiers": "Buscar archivos nuevos",
    "Actualiser la bibliothèque": "Actualizar la biblioteca", "Code d'accès": "Código de acceso", "Entrer": "Entrar",
    "Code incorrect.": "Código incorrecto.", "Trop d'essais : réessaie dans 5 minutes.": "Demasiados intentos: vuelve a probar en 5 minutos.",
    "préparation de la piste… (jusqu’à une minute la première fois)": "preparando la pista… (hasta un minuto la primera vez)",
    "erreur réseau": "error de red", " – convertie": " – convertida",
    "Supprimer les pistes audio converties ? Elles seront reconverties si tu les rechoisis.":
        "¿Borrar las pistas de audio convertidas? Se volverán a convertir si las eliges de nuevo.",
    " Mo'": " MB'", " (piste en cours d’écoute gardée)": " (se conserva la pista que se está escuchando)",
    "Impossible d’ouvrir le lecteur ": "No se pudo abrir el reproductor ", " sur le PC.": " en el PC.",
    "Ouvre ce film dans ": "Abre esta película en ", " sur le PC, à la même position": " en el PC, en la misma posición",
    "Sur un autre appareil : ": "En otro dispositivo: ", " (pause)": " (pausa)", " (lecture)": " (reproduciendo)",
    "Sans sous-titres": "Sin subtítulos", "🔁 Répéter tout": "🔁 Repetir todo", "🔂 Répéter 1": "🔂 Repetir 1",
    "🔁 Répéter": "🔁 Repetir", "'Monter'": "'Subir'", "'Descendre'": "'Bajar'", "Retirer de la file": "Quitar de la cola",
    "/fr|vf/i": "/\\b(es|spa|esp)\\b|español|castellano|latino|spanish/i",  # sous-titres choisis par défaut
    "⏮ Précédent": "⏮ Anterior", "⏭ Suivant": "⏭ Siguiente", "🔀 Aléatoire": "🔀 Aleatorio",
    "Morceau précédent (ou début du morceau)": "Canción anterior (o inicio de la canción)", "Morceau suivant": "Canción siguiente",
    "Précédent (à distance)": "Anterior (a distancia)", "Lecture / pause (à distance)": "Reproducir / pausa (a distancia)",
    "Suivant (à distance)": "Siguiente (a distancia)", "Volume (à distance)": "Volumen (a distancia)", "À suivre": "A continuación",
    "Vider la file": "Vaciar la cola", "Plein écran (double-clic)": "Pantalla completa (doble clic)",
    "Piste audio (à distance)": "Pista de audio (a distancia)", '"Piste audio"': '"Pista de audio"',
    "🔊 Lire sur l’ampli (passthrough)": "🔊 Reproducir en el amplificador (passthrough)",
    "Reculer de 10 secondes": "Retroceder 10 segundos", "Avancer de 30 secondes": "Avanzar 30 segundos",
    "⏭ Épisode suivant": "⏭ Episodio siguiente", "Épisode suivant (à distance)": "Episodio siguiente (a distancia)",
    "Sous-titres (à distance)": "Subtítulos (a distancia)", "🔊 Sur l’ampli": "🔊 En el amplificador",
    "Pistes audio converties : ": "Pistas de audio convertidas: ", "🗑 Vider le cache audio": "🗑 Vaciar la caché de audio",
    "Lire juste après": "Reproducir a continuación", "Ajouter à la file d'attente": "Añadir a la cola", "Vu / pas vu": "Visto / no visto",
    "▶ Reprendre": "▶ Seguir viendo", "⏭ Épisodes suivants": "⏭ Próximos episodios", "🆕 Ajoutés récemment": "🆕 Añadidos recientemente",
    "Rien pour l’instant : lance un film ou une série, ils apparaîtront ici.":
        "Nada por ahora: pon una película o una serie y aparecerán aquí.",
    "Ouvrir le Media Center": "Abrir Media Center", "Démarrer avec Windows": "Iniciar con Windows", "Quitter": "Salir",
    "Premier lancement : choisis tes dossiers de films, de séries et de musique.\n(Annuler pour passer un dossier.)":
        "Primer inicio: elige tus carpetas de películas, series y música.\n(Cancelar para omitir una carpeta.)",
    "Dossier de films": "Carpeta de películas", "Dossier de séries TV": "Carpeta de series", "Dossier de musique": "Carpeta de música",
    "Langue : Español": "Idioma: Français", 
    "lancé avec Python (pas de mise à jour automatique)": "lanzado con Python (sin actualización automática)",
    "Mise à jour": "Actualización", "version disponible": "versión disponible", 
    "aucun dossier configuré": "ninguna carpeta configurada",
    "absent : vidéos AVI/HEVC, pistes et sous-titres des MKV, son AC3/DTS indisponibles":
        "falta: vídeos AVI/HEVC, pistas y subtítulos de los MKV y sonido AC3/DTS no disponibles",
    "Lecteur pour l'ampli": "Reproductor para el amplificador", "ni mpv ni VLC : pas de passthrough": "ni mpv ni VLC: sin passthrough",
    "clé acceptée": "clave aceptada", "clé refusée": "clave rechazada", 
    "Mises à jour (GitHub)": "Actualizaciones (GitHub)", 
    "seulement ce PC (lancer avec --reseau pour la TV et le téléphone)": "solo este PC (lanzar con --reseau para la TV y el teléfono)",
    "Cache audio": "Caché de audio", "Nouveau profil…": "Nuevo perfil…", "Profil": "Perfil",
    "Nom du nouveau profil :": "Nombre del nuevo perfil:", "Manque :": "Falta:", "Installer": "Instalar",
    "Télécharger": "Descargar", "ffmpeg (vidéos AVI/HEVC, sous-titres et pistes audio des MKV, son AC3/DTS)":
        "ffmpeg (vídeos AVI/HEVC, subtítulos y pistas de audio de los MKV, sonido AC3/DTS)",
    "un lecteur pour l'ampli (passthrough Dolby/DTS)": "un reproductor para el amplificador (passthrough Dolby/DTS)",
    "Installation en cours… (quelques minutes)": "Instalando… (unos minutos)", "Nouvelle version disponible":
        "Nueva versión disponible", "actuelle": "actual", "Mettre à jour": "Actualizar", "Voir": "Ver",
    "Téléchargement de la nouvelle version…": "Descargando la nueva versión…", "Redémarrage…": "Reiniciando…", "Installation terminée.": "Instalación terminada.", "Trier ": "Ordenar ", ">Titre<": ">Título<",
    ">Ajoutés récemment<": ">Añadidas recientemente<", "Année (récents)": "Año (recientes)", "Année (anciens)": "Año (antiguas)",
    "Genre <": "Género <", ">Tous<": ">Todos<", " Non vus": " No vistas", "🌐 Español": "🌐 Français",
}
# Mots isolés : seulement via tr() sur des textes précis (jamais dans traduire() : « vu » est aussi un nom de classe
# dans le JavaScript, « Action » est dans setActionHandler…).
MOTS_ES = {"épisode": "episodio", "épisodes": "episodios", "vu": "visto", "vus": "vistos", "Français": "Francés",
           "Anglais": "Inglés", "Espagnol": "Español", "Allemand": "Alemán", "Italien": "Italiano", "Portugais": "Portugués",
           "Intégrés": "Integrados", "Piste": "Pista", "Sous-titres": "Subtítulos",
           "Diagnostic": "Diagnóstico", "Version": "Versión", "Dossier": "Carpeta", "fichiers": "archivos", "introuvable": "no encontrada", "Dossiers": "Carpetas", "Affiches": "Pósters", "injoignable": "inaccesible", "joignable": "accesible", "Réseau": "Red", "activé": "activado", "aucun": "ninguno", "Films": "Películas", "Sauvegarde": "Copia de seguridad", "Exporter": "Exportar", "Importer": "Importar",
           "Réglages, profils, « déjà vu », reprises, file d'attente, listes et affiches.": "Ajustes, perfiles, «visto», progreso, cola, listas y pósters.",
           "Restauré. Redémarre le Media Center si tu as changé de dossiers ou de code.": "Restaurado. Reinicia el Media Center si cambiaste carpetas o el código.",
           "Fichier refusé": "Archivo rechazado", "Séries": "Series", "Musique": "Música"}
_MOTIF_ES = re.compile("|".join(re.escape(k) for k in sorted(ES, key=len, reverse=True)))


def tr(texte):
    """Texte de l'interface dans la langue choisie."""
    return ES.get(texte, MOTS_ES.get(texte, texte)) if LANGUE[0] == "es" else texte


def traduire(texte):
    """Traduit un gabarit de l'interface (pages web, boutons) en une passe ; jamais appliqué aux titres de la bibliothèque."""
    return _MOTIF_ES.sub(lambda m: ES[m.group()], texte) if LANGUE[0] == "es" else texte


def langue_systeme():
    """Langue de Windows (ou du système) : espagnol si c'est de l'espagnol, sinon français."""
    if os.name == "nt":
        try:
            import ctypes
            return "es" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x0A else "fr"  # 0x0A = espagnol
        except (AttributeError, OSError):
            pass
    import locale
    noms = [os.environ.get(v, "") for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")] + [locale.getlocale()[0] or ""]
    return "es" if any(n.lower().startswith(("es", "spanish")) for n in noms) else "fr"


LANGUES = {"fre": "Français", "fra": "Français", "fr": "Français", "eng": "Anglais", "en": "Anglais", "es": "Espagnol",
           "spa": "Espagnol", "ger": "Allemand", "deu": "Allemand", "ita": "Italien", "por": "Portugais"}

JUNK = re.compile(r"\b(2160p|1080p|720p|480p|4k|uhd|hdr|bluray|bdrip|brrip|webrip|web ?dl|web|hdtv|dvdrip|hdrip|"
                  r"x264|x265|h264|h265|hevc|10bit|aac|ac3|dts|truefrench|french|vff|vfq|vf|vostfr|multi|subfrench|"
                  r"extended|remastered|proper|repack)\b.*", re.I)


def nettoyer(stem):
    """'Le.Film.2024.1080p.x264-GRP' -> ('Le Film', '2024')"""
    s = re.sub(r"\[.*?\]|\{.*?\}", " ", re.sub(r"[._]+", " ", stem))
    annees = [m for m in re.finditer(r"\(?\b(19\d\d|20\d\d)\b\)?", s) if m.start() > 0]  # '2001 l'odyssée…'
    annee = ""
    if annees:
        annee, s = annees[-1][1], s[:annees[-1].start()]
    return re.sub(r"\s+", " ", JUNK.sub("", s)).strip(" -()"), annee


ALBUM_JUNK = re.compile(r"\b(flac|mp3|aac|alac|\d+ ?kbps|320|256|192|v0|web|cd|24 ?bit|16 ?bit|\d+(\.\d+)? ?khz|"
                        r"hi ?res|lossless|remaster(ed)?|deluxe|edition)\b", re.I)


def nettoyer_album(dossier):
    """'Daft Punk - Discovery (2001) [FLAC]/CD1' -> 'Daft Punk Discovery'"""
    parts = [x for x in re.split(r"[\\/]", dossier) if not re.fullmatch(r"\s*(cd|disc|disque) ?\d+\s*", x, re.I)]
    s = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}", " ", " ".join(parts[-2:]))  # ponytail: 2 derniers niveaux = Artiste/Album
    return re.sub(r"\s+", " ", ALBUM_JUNK.sub(" ", re.sub(r"[._\-]+", " ", s))).strip()


def pochette_locale(dossier):
    imgs = sorted(f for f in dossier.iterdir() if f.suffix.lower() in IMG and f.is_file())
    pref = [f for f in imgs if re.match(r"(cover|folder|front|album)", f.stem, re.I)]
    return str((pref or imgs)[0]) if imgs else None


def _id3(f):
    h = f.read(10)
    if h[:3] != b"ID3":
        return None
    ver, flags = h[3], h[5]
    ss = lambda b: b[0] << 21 | b[1] << 14 | b[2] << 7 | b[3]  # entier « synchsafe »
    data = f.read(ss(h[6:10]))
    if flags & 0x80 and ver < 4:
        data = data.replace(b"\xff\x00", b"\xff")
    i = (ss(data[:4]) if ver == 4 else int.from_bytes(data[:4], "big") + 4) if flags & 0x40 else 0
    idlen, hdr = (3, 6) if ver == 2 else (4, 10)
    while i + hdr <= len(data) and data[i:i + idlen].strip(b"\0"):
        fid, raw = data[i:i + idlen], data[i + idlen:i + hdr - (2 if ver > 2 else 0)]
        taille = ss(raw) if ver == 4 else int.from_bytes(raw, "big")
        corps, i = data[i + hdr:i + hdr + taille], i + hdr + taille
        if fid not in (b"APIC", b"PIC"):
            continue
        j = (corps.index(b"\0", 1) + 1 if fid == b"APIC" else 4) + 1  # type MIME/format, puis type d'image
        if corps[0] in (1, 2):  # description en UTF-16 : terminée par \0\0 aligné
            while corps[j:j + 2] != b"\0\0":
                j += 2
            j += 2
        else:
            j = corps.index(b"\0", j) + 1
        return corps[j:]


def _flac(f):
    if f.read(4) != b"fLaC":
        return None
    while True:
        h = f.read(4)
        if len(h) < 4:
            return None
        taille = int.from_bytes(h[1:4], "big")
        if h[0] & 0x7F == 6:  # bloc PICTURE
            b, i = f.read(taille), 4
            i += 4 + int.from_bytes(b[i:i + 4], "big")  # type MIME
            i += 4 + int.from_bytes(b[i:i + 4], "big") + 16  # description, dimensions
            return b[i + 4:i + 4 + int.from_bytes(b[i:i + 4], "big")]
        if h[0] & 0x80:
            return None
        f.seek(taille, 1)


def _mp4(f, fin, chemin=(b"moov", b"udta", b"meta", b"ilst", b"covr", b"data")):
    while f.tell() + 8 <= fin:
        debut, h = f.tell(), f.read(8)
        taille, typ = int.from_bytes(h[:4], "big"), h[4:]
        if taille == 1:
            taille = int.from_bytes(f.read(8), "big")
        elif taille == 0:
            taille = fin - debut
        if taille < 8:
            return None
        if typ == chemin[0]:
            if len(chemin) == 1:
                return f.read(debut + taille - f.tell())[8:]  # 8 octets : type + langue
            if typ == b"meta":
                f.seek(4, 1)
            return _mp4(f, debut + taille, chemin[1:])
        f.seek(debut + taille)


def pochette_integree(chemin):
    """Pochette intégrée à un MP3 (ID3), FLAC ou M4A -> (octets, type MIME) ou None."""
    ext = Path(chemin).suffix.lower()
    try:
        with open(chemin, "rb") as f:
            img = _flac(f) if ext == ".flac" else _mp4(f, os.path.getsize(chemin)) if ext == ".m4a" else _id3(f)
    except (OSError, ValueError, IndexError):  # fichier abîmé ou balises exotiques : pas de pochette
        return None
    return (img, "image/png" if img[:4] == b"\x89PNG" else "image/jpeg") if img else None


EP = re.compile(r"\b[Ss](\d{1,2}) ?[Ee](\d{1,3})|\b(\d{1,2})x(\d{2,3})\b")


def episode(stem, dossiers):
    """'The.Office.S02E05.Le.Bal.720p' -> ('The Office', 'S02E05 – Le Bal') ; dossiers = sous-dossiers depuis la racine."""
    s = re.sub(r"[._]+", " ", stem)
    m = EP.search(s)
    dossier = nettoyer(dossiers[0])[0] if dossiers else ""
    if not m:  # pas de SxxEyy : rangé dans la série de son dossier
        return dossier or "Divers", nettoyer(stem)[0] or stem
    reste = nettoyer(s[m.end():])[0]
    ep = f"S{int(m[1] or m[3]):02}E{int(m[2] or m[4]):02}" + (f" – {reste}" if reste else "")
    return nettoyer(s[:m.start()])[0] or dossier or "Divers", ep


def sous_titres(video, seule):
    """Sous-titres d'une vidéo : même nom (Film.fr.srt) ; si elle est seule dans son dossier, tous ceux du dossier
    et d'un sous-dossier Subs/."""
    dossiers = [video.parent] + [d for d in video.parent.iterdir()
                                 if d.is_dir() and d.name.lower() in ("subs", "subtitles", "sous-titres", "st")]
    return [str(f) for d in dossiers for f in sorted(d.iterdir())
            if f.suffix.lower() in (".srt", ".vtt", ".ass", ".ssa") and f.is_file()
            and (seule or f.name.lower().startswith(video.stem.lower()))]


def nom_sous_titre(fichier, video):
    """'Film.2020.fr.srt' -> 'fr' ; 'Subs/2_French.srt' -> '2 French'"""
    stem = Path(fichier).stem
    if stem.lower().startswith(Path(video).stem.lower()):
        stem = stem[len(Path(video).stem):]
    return re.sub(r"[._\-]+", " ", stem).strip() or tr("Sous-titres")


def lire_texte(chemin):
    b = Path(chemin).read_bytes()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16")
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:  # vieux .srt français : Windows-1252
        return b.decode("cp1252", errors="replace")


def ass_temps(t):
    """'0:01:02.50' (centièmes) -> '00:01:02.500'"""
    h, m, sec = t.strip().split(":")
    return f"{int(h):02}:{int(m):02}:{float(sec):06.3f}"


def ass_vers_vtt(texte):
    """Sous-titres .ass/.ssa (animés) -> WebVTT : texte et italique gardés, styles/positions/karaoké perdus."""
    champs, cues, dans_events = [], [], False
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if ligne.startswith("["):
            dans_events = ligne.lower() == "[events]"
        elif dans_events and ligne.lower().startswith("format:"):
            champs = [c.strip().lower() for c in ligne[7:].split(",")]
        elif dans_events and champs and ligne.lower().startswith("dialogue:"):
            v = dict(zip(champs, ligne[9:].split(",", len(champs) - 1)))
            t = v.get("text", "")
            haut = " line:0" if re.search(r"\\an[789]", t) else ""  # panneaux / notes en haut de l'écran
            if re.search(r"\\p[1-9]", t):  # dessin vectoriel (panneaux typesettés) : illisible en texte
                continue
            t = re.sub(r"\{[^}]*\\i1[^}]*\}", "<i>", t)
            t = re.sub(r"\{[^}]*\\i0?[^}0-9]*\}", "</i>", t)
            t = re.sub(r"\{[^}]*\}", "", t).replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ").strip()
            if t.replace("<i>", "").replace("</i>", "").strip():
                try:
                    cues.append((ass_temps(v["start"]), ass_temps(v["end"]) + haut, t))
                except (KeyError, ValueError):
                    continue
    cues.sort(key=lambda c: c[0])
    return "WEBVTT\n\n" + "".join(f"{a} --> {b}\n{t}\n\n" for a, b, t in cues)


def vers_vtt(texte):
    """.srt / .vtt / .ass -> WebVTT"""
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    if texte.lstrip().startswith("WEBVTT"):
        return texte
    if re.search(r"^\[events\]", texte, re.I | re.M):
        return ass_vers_vtt(texte)
    texte = re.sub(r"\{\\[^}]*\}", "", texte)  # balises de style ASS ({\an8}…)
    texte = re.sub(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})", lambda m: f"{int(m[1]):02}:{m[2]}:{m[3]}.{m[4]}", texte)
    return "WEBVTT\n\n" + texte


def nom_piste(flux, defaut="Intégrés"):
    """Flux ffprobe -> 'Français – Forced'"""
    tags = {k.lower(): v for k, v in flux.get("tags", {}).items()}
    lang = tags.get("language", "")
    return " – ".join(x for x in (tr(LANGUES.get(lang, "" if lang == "und" else lang)), tags.get("title", "")) if x) or tr(defaut)


def pistes_audio(chemin):
    """Pistes audio d'une vidéo : [{"nom", "convertir", "canaux"}] ; convertir = le navigateur ne sait pas la lire telle quelle."""
    if not FFPROBE:
        return []
    if chemin not in AUDIOS:
        try:
            out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries",
                                  "stream=codec_name,channels:stream_tags=language,title", "-of", "json", chemin],
                                 capture_output=True, timeout=30).stdout
            flux = json.loads(out or b"{}").get("streams", [])
        except (OSError, ValueError, subprocess.TimeoutExpired):
            flux = []
        AUDIOS[chemin] = [{"nom": f"{k + 1}. " + nom_piste(f, "Piste")
                                  + f" ({f.get('codec_name', '?')}{', ' + nom_canaux(f.get('channels', 2)) if f.get('channels', 2) > 2 else ''})",
                           "convertir": f.get("codec_name") in NON_LU, "canaux": f.get("channels", 2)} for k, f in enumerate(flux)]
    return AUDIOS[chemin]


def trouver_lecteur(force=None):
    """mpv (meilleure passthrough : TrueHD/DTS-HD compris) sinon VLC, dans le PATH ou aux emplacements Windows habituels."""
    candidats = [force] if force else [shutil.which("mpv"), shutil.which("mpvnet"), shutil.which("vlc"),
                                       r"C:\Program Files\mpv\mpv.exe", r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                                       r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"]
    return next((c for c in candidats if c and Path(c).is_file()), None)


def commande_externe(lecteur, fichier, t, piste, ipc=None, http=None):
    """Ligne de commande du lecteur externe : plein écran, à la bonne position, bonne piste audio, son envoyé
    tel quel (Dolby / DTS) à l'ampli par HDMI ou S/PDIF, qui le décode lui-même."""
    fichier = str(Path(fichier).resolve())
    if "mpv" in Path(lecteur).stem.lower():
        return [lecteur, "--fs", f"--start={t:.0f}", f"--aid={piste + 1}", "--audio-spdif=ac3,eac3,dts,dts-hd,truehd",
                *([f"--input-ipc-server={ipc}"] if ipc else []), "--", fichier]
    sortie = ["--mmdevice-passthrough=2"] if os.name == "nt" else ["--spdif"]  # VLC Windows : 2 = HDMI
    pilotage = ["--extraintf=http", "--http-host=127.0.0.1", f"--http-port={http[0]}", f"--http-password={http[1]}"] if http else []
    langue = ["--language=en"] if os.name == "nt" and http else []  # noms des pistes en anglais (lus par etat_vlc)
    return [lecteur, "--fullscreen", f"--start-time={t:.0f}", f"--audio-track={piste}", *sortie, *pilotage, *langue,
            "--play-and-exit", fichier]


def valider_externe(data):
    kind, i, t, piste = data["kind"], int(data["id"]), float(data.get("t", 0)), data.get("piste", 0)
    if not (kind in ("films", "series") and 0 <= i < len(LIB[kind]) and math.isfinite(t) and 0 <= t < 1e6
            and piste in range(100)):
        raise ValueError("demande invalide")
    return kind, i, LIB[kind][i][2], t, piste


def jeton_pin(pin, sel):
    return hashlib.sha256(f"{sel}|{pin}".encode()).hexdigest()[:32]


def trop_d_essais(ip, maintenant=None):
    """Après 10 PIN faux en 5 minutes, l'adresse est bloquée jusqu'à la fin des 5 minutes."""
    maintenant = maintenant or time.time()
    n, depuis = ECHECS.get(ip, (0, maintenant))
    if maintenant - depuis > 300:
        ECHECS.pop(ip, None)
        return False
    return n >= 10


def noter_echec(ip):
    n, depuis = ECHECS.get(ip, (0, time.time()))
    ECHECS[ip] = [n + 1, depuis]


PAGE_PIN = (WEB_DIR / "pin.html").read_text("utf-8")  # page du code d'accès


def profil_actif():
    p = getattr(ACTUEL, "profil", "")
    return p if p in PROFILS else ""


def fichier_suivi(profil):
    return SUIVI_F if not profil else BASE / f"mediacenter_suivi_{hashlib.sha1(profil.encode()).hexdigest()[:10]}.json"


def S():
    """Suivi (déjà vu, reprise) du profil de la requête en cours."""
    p = profil_actif()
    if p not in SUIVIS:
        f = fichier_suivi(p)
        SUIVIS[p] = json.loads(f.read_text("utf-8")) if f.exists() else {}
    return SUIVIS[p]


def valider_profil(nom):
    nom = nom.strip()
    if not (0 < len(nom) <= 30 and re.fullmatch(r"[\w .'-]+", nom) and nom != "Principal"):
        raise ValueError("nom de profil invalide")
    return nom


def html_profils():
    actif = profil_actif()
    options = [("", "👤 Principal")] + [(p, "👤 " + p) for p in PROFILS] + [("__nouveau", "➕ " + tr("Nouveau profil…"))]
    return (f'<select id="pf" title="{tr("Profil")}" data-question="{html.escape(tr("Nom du nouveau profil :"))}">'
            + "".join(f'<option value="{html.escape(v)}"{" selected" if v == actif else ""}>{html.escape(t)}</option>'
                      for v, t in options) + "</select>")


def accueil():
    """Rangées de l'accueil : [(titre, [(lien, affiche, titre, sous-titre, % vu)])]."""
    nom = lambda kind, i: Path(LIB[kind][i][2]).name
    affiche = lambda kind, i: (META.get(nom(kind, i) if kind == "films" else "serie:" + LIB[kind][i][1]) or {}).get("affiche", "")
    lien = lambda kind, i: (f"/?k=films&jouer={i}" if kind == "films"
                            else f"/?k=series&s={quote(LIB[kind][i][1])}&jouer={i}")

    def carte(kind, i, sous=""):
        e = S().get(nom(kind, i), {})
        pct = int(100 * e["t"] / e["d"]) if e.get("t") and e.get("d") else 0
        titre = (META.get(nom(kind, i)) or {}).get("titre") or LIB[kind][i][0] if kind == "films" else LIB[kind][i][1]
        return lien(kind, i), affiche(kind, i), titre, sous or ("" if kind == "films" else LIB[kind][i][0]), pct

    videos = [(k, i) for k in ("films", "series") for i in range(len(LIB[k]))]
    reprendre = sorted(((S()[nom(k, i)].get("quand", 0), k, i) for k, i in videos
                        if S().get(nom(k, i), {}).get("t") and not S()[nom(k, i)].get("vu")), reverse=True)
    deja = {(k, i) for _, k, i in reprendre}
    suivants, eps = [], {}
    for i in ordre("series"):
        eps.setdefault(LIB["series"][i][1], []).append(i)
    for liste in eps.values():
        vus = [n for n, i in enumerate(liste) if S().get(nom("series", i), {}).get("vu")]
        if vus and max(vus) + 1 < len(liste):
            i = liste[max(vus) + 1]
            if ("series", i) not in deja and not S().get(nom("series", i), {}).get("vu"):
                suivants.append((S()[nom("series", liste[max(vus)])].get("quand", 0), i))
    recents, series_vues = [], set()
    for k, i in sorted(videos, key=lambda x: AJOUT.get(LIB[x[0]][x[1]][2], 0), reverse=True):
        if k == "series":  # une seule carte par série
            if LIB[k][i][1] in series_vues:
                continue
            series_vues.add(LIB[k][i][1])
        recents.append(carte(k, i))
        if len(recents) == 20:
            break
    return [(tr("▶ Reprendre"), [carte(k, i) for _t, k, i in reprendre[:20]]),
            (tr("⏭ Épisodes suivants"), [carte("series", i) for _t, i in sorted(suivants, reverse=True)[:20]]),
            (tr("🆕 Ajoutés récemment"), recents)]


def html_accueil():
    rangs = "".join(
        f'<h3>{titre}</h3><div class="rang">' + "".join(
            f'<a class="carte" href="{html.escape(l)}">'
            + (f'<img src="{html.escape(a)}" loading="lazy" alt="">' if a else '<div class="ph">🎬</div>')
            + f'<span>{html.escape(t)}</span><small>{html.escape(st)}</small>'
            + (f'<i class="bar" style="width:{pct}%"></i>' if pct else "") + "</a>" for l, a, t, st, pct in cartes) + "</div>"
        for titre, cartes in accueil() if cartes)
    return rangs or '<p class="vide">' + tr("Rien pour l’instant : lance un film ou une série, ils apparaîtront ici.") + '</p>'


def commande_demarrage():
    """Ligne lancée à l'ouverture de session Windows : sans navigateur (le Media Center attend près de l'horloge)."""
    if GELE:
        return f'"{sys.executable}" --sans-navigateur'
    py = Path(sys.executable).with_name("pythonw.exe")  # pas de fenêtre de console au démarrage
    return f'"{py if py.exists() else sys.executable}" "{Path(__file__).resolve()}" --sans-navigateur'


def demarrage_auto(etat=None):
    """Lit (etat=None) ou règle le lancement au démarrage de Windows (clé « Run » de l'utilisateur, sans droits admin)."""
    import winreg
    # CreateKeyEx ouvre la clé, ou la crée si elle n'existe pas encore (session Windows toute neuve)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
        if etat is None:
            try:
                return winreg.QueryValueEx(k, "MediaCenter")[0] == commande_demarrage()
            except FileNotFoundError:
                return False
        if etat:
            winreg.SetValueEx(k, "MediaCenter", 0, winreg.REG_SZ, commande_demarrage())
        else:
            try:
                winreg.DeleteValue(k, "MediaCenter")
            except FileNotFoundError:
                pass
        return etat


def image_icone():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), 14, fill=(229, 9, 20))
    d.polygon([(24, 16), (24, 48), (50, 32)], fill="white")
    return img


def icone_barre(url):
    """Icône près de l'horloge (si pystray est là, c'est-à-dire dans le .exe) ; renvoie False sinon."""
    try:
        import pystray  # peut aussi échouer sans écran (Linux sans affichage) : pas seulement ImportError
        img = image_icone()
    except Exception as e:
        if not isinstance(e, ImportError):
            print(f"⚠ Icône près de l'horloge indisponible : {e}")
        return False
    menu = [pystray.MenuItem(tr("Ouvrir le Media Center"), lambda: webbrowser.open(url), default=True),
            pystray.MenuItem(tr("Actualiser la bibliothèque"), lambda: print(f"{RESCAN[0]()} nouveau(x) fichier(s)."))]
    if os.name == "nt":
        menu.append(pystray.MenuItem(tr("Démarrer avec Windows"), lambda: demarrage_auto(not demarrage_auto()),
                                     checked=lambda item: demarrage_auto()))
    menu.append(pystray.MenuItem(tr("Quitter"), lambda icon: (icon.stop(), os._exit(0))))  # arrête aussi le serveur
    try:
        pystray.Icon("MediaCenter", img, "Media Center", pystray.Menu(*menu)).run()
    except Exception as e:  # pas de bureau (session de service…) : le serveur continue sans icône
        print(f"⚠ Icône près de l'horloge indisponible : {e}")
        return False
    return True


def demander_dossiers_fenetre(cfg, dossiers):
    """1er lancement du .exe sans console : choix des dossiers dans les fenêtres habituelles de Windows."""
    import tkinter
    from tkinter import filedialog, messagebox
    racine = tkinter.Tk()
    racine.withdraw()
    messagebox.showinfo("Media Center", tr("Premier lancement : choisis tes dossiers de films, de séries et de musique.\n"
                                          "(Annuler pour passer un dossier.)"))
    for k, nom in (("films", "films"), ("series", "séries TV"), ("musique", "musique")):
        d = filedialog.askdirectory(title=tr(f"Dossier de {nom}"), mustexist=True)
        if d:
            cfg[k] = dossiers[k] = [d]
    racine.destroy()


def message_erreur(texte):
    """Erreur bloquante : dans une fenêtre si pas de console (.exe), sinon à l'écran."""
    if sys.stdin is None or not sys.stdin.isatty():
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk()
            r.withdraw()
            messagebox.showerror("Media Center", texte)
            r.destroy()
            return
        except Exception:  # pas d'affichage : le message reste dans mediacenter.log
            pass
    print(texte)


GABARITS = {}


def gabarit():
    """Page de l'interface dans la langue choisie (traduite une seule fois)."""
    if LANGUE[0] not in GABARITS:
        GABARITS[LANGUE[0]] = traduire(PAGE).replace("{autre_langue}", "🌐 Français" if LANGUE[0] == "es" else "🌐 Español")
    return GABARITS[LANGUE[0]]


class Serveur(ThreadingHTTPServer):
    # Sous Windows, SO_REUSEADDR laisse un 2e programme s'accrocher au même port : il faut au contraire que le
    # 2e lancement échoue, pour qu'il se contente d'ouvrir le navigateur sur le premier.
    allow_reuse_address = os.name != "nt"
    allow_reuse_port = False


def titre_lib(kind, i):
    titre, dossier, _ = LIB[kind][i]
    return f"{dossier} {titre}" if kind == "series" else titre


def fermer_pilote():
    proc = PILOTE["proc"]
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(proc.pid, __import__("signal").SIGTERM)
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def pilote_actif():
    return bool(PILOTE.get("proc")) and PILOTE["proc"].poll() is None


def mpv_ipc(commandes):
    """Envoie des commandes JSON à mpv (--input-ipc-server) et renvoie leurs résultats, dans l'ordre (None si refusée)."""
    lignes = "".join(json.dumps({"command": c, "request_id": k}) + "\n" for k, c in enumerate(commandes)).encode()
    if os.name == "nt":  # tube nommé Windows
        f = open(MPV_IPC, "r+b", buffering=0)  # ponytail: pas de délai max sur un tube Windows ; mpv répond en quelques ms
        f.write(lignes)
    else:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(2)
        s.connect(MPV_IPC)
        s.sendall(lignes)
        f = s.makefile("rb")
    with f:
        reponses = {}
        while len(reponses) < len(commandes):
            ligne = f.readline()
            if not ligne:
                raise OSError("mpv a fermé la connexion")
            m = json.loads(ligne)
            if "request_id" in m:  # les autres lignes sont des événements de mpv
                reponses[m["request_id"]] = m.get("data") if m.get("error") == "success" else None
    return [reponses[k] for k in range(len(commandes))]


def nom_piste_mpv(p):
    return " – ".join(x for x in (LANGUES.get(p.get("lang", ""), p.get("lang", "")), p.get("title", "")) if x) or f"Piste {p.get('id')}"


def vlc_http(**params):
    """Interface web de VLC (--extraintf=http, locale au PC, mot de passe tiré au hasard) : envoie un ordre, renvoie l'état."""
    req = Request(f"http://127.0.0.1:{PILOTE['port']}/requests/status.json?" + urlencode(params),
                  headers={"Authorization": "Basic " + __import__("base64").b64encode(f":{PILOTE['mdp']}".encode()).decode()})
    with urlopen(req, timeout=2) as r:
        return json.load(r)


def pistes_vlc(d):
    """Flux audio / sous-titres listés par VLC 3 (« Stream N ») -> ([(id, nom)], [(id, nom)])."""
    flux = sorted(((int(k.split()[-1]), v) for k, v in d.get("information", {}).get("category", {}).items()
                   if k.startswith("Stream ") and k.split()[-1].isdigit()), key=lambda x: x[0])
    nom = lambda v: " – ".join(x for x in (LANGUES.get(v.get("Language", "").lower()[:3], v.get("Language", "")),
                                            v.get("Description", "")) if x) or "Piste"
    return ([(i, nom(v) + f" ({v.get('Codec', '?').split(' (')[0]})") for i, v in flux if v.get("Type") == "Audio"],
            [(i, nom(v)) for i, v in flux if v.get("Type") == "Subtitle"])


def etat_vlc():
    e = {"kind": PILOTE["kind"], "id": PILOTE["id"], "titre": PILOTE["titre"] + " (VLC)", "t": 0, "d": 0, "lecture": True,
         "vol": PILOTE.get("vol", 1), "page": "*", "st": [], "sti": -1, "au": [], "aui": 0, "age": 0, "moi": False,
         "joignable": True, "mpv": True}  # « mpv » : lecteur externe (pas de bouton « Sur l'ampli »)
    try:
        d = vlc_http()
    except (OSError, ValueError):
        return e  # VLC démarre encore
    auds, subs = pistes_vlc(d)
    # VLC 3 ne dit pas quelle piste est active : on retient le dernier choix fait depuis la télécommande.
    e.update(t=d.get("time") or 0, d=d.get("length") or 0, lecture=d.get("state") != "paused",
             au=[f"{k + 1}. {n}" for k, (_, n) in enumerate(auds)], aui=min(PILOTE.get("aui", 0), max(0, len(auds) - 1)),
             st=[n for _, n in subs], sti=PILOTE.get("sti", -1) if PILOTE.get("sti", -1) < len(subs) else -1)
    if d.get("volume"):
        e["vol"] = min(1, d["volume"] / 256)  # 256 = 100 %
    return e


def commande_vlc(c):
    cmd, v = c["cmd"], c["v"]
    if cmd in ("lecture", "pause"):
        vlc_http(command="pl_forceresume" if cmd == "lecture" else "pl_forcepause")
    elif cmd == "deplacer":
        vlc_http(command="seek", val=f"{v:+.0f}")
    elif cmd == "volume":
        vlc_http(command="volume", val=round(v * 256))
        PILOTE["vol"] = v
    elif cmd in ("soustitres", "audio"):
        auds, subs = pistes_vlc(vlc_http())
        pistes = subs if cmd == "soustitres" else auds
        if v == -1 or int(v) < len(pistes):
            vlc_http(command="subtitle_track" if cmd == "soustitres" else "audio_track", val=-1 if v == -1 else pistes[int(v)][0])
            PILOTE["sti" if cmd == "soustitres" else "aui"] = int(v)
    elif cmd in ("jouer", "suivant"):
        lib, actuel = LIB[PILOTE["kind"]], PILOTE["id"]
        i = int(c["k"]) if cmd == "jouer" else episode_suivant(PILOTE["kind"], actuel)
        if i is None or not 0 <= i < len(lib):
            return
        # start-time=0 : sinon la position de départ du lancement s'appliquerait aussi au nouveau fichier
        vlc_http(command="in_play", input=Path(lib[i][2]).resolve().as_uri(), option="start-time=0")
        PILOTE.update(id=i, titre=titre_lib(PILOTE["kind"], i), aui=0, sti=-1)


def etat_pilote():
    return etat_mpv() if PILOTE["type"] == "mpv" else etat_vlc()


def commande_pilote(c):
    return commande_mpv(c) if PILOTE["type"] == "mpv" else commande_vlc(c)


def etat_mpv():
    """État de mpv au format de la télécommande vidéo (même bandeau sur le téléphone)."""
    e = {"kind": PILOTE["kind"], "id": PILOTE["id"], "titre": PILOTE["titre"] + " (mpv)", "t": 0, "d": 0, "lecture": True, "vol": 1,
         "page": "*", "st": [], "sti": -1, "au": [], "aui": 0, "age": 0, "moi": False, "joignable": True, "mpv": True}
    try:
        t, d, pause, vol, pistes = mpv_ipc([["get_property", x] for x in ("time-pos", "duration", "pause", "volume", "track-list")])
    except (OSError, ValueError):
        return e  # mpv démarre encore
    subs = [p for p in pistes or [] if p.get("type") == "sub"]
    auds = [p for p in pistes or [] if p.get("type") == "audio"]
    e.update(t=t or 0, d=d or 0, lecture=not pause, vol=min(1, (vol if vol is not None else 100) / 100),
             st=[nom_piste_mpv(p) for p in subs], sti=next((k for k, p in enumerate(subs) if p.get("selected")), -1),
             au=[f"{k + 1}. {nom_piste_mpv(p)} ({p.get('codec', '?')})" for k, p in enumerate(auds)],
             aui=next((k for k, p in enumerate(auds) if p.get("selected")), 0))
    return e


def commande_mpv(c):
    """Exécute un ordre de la télécommande dans mpv."""
    cmd, v = c["cmd"], c["v"]
    if cmd in ("lecture", "pause"):
        mpv_ipc([["set_property", "pause", cmd == "pause"]])
    elif cmd == "deplacer":
        mpv_ipc([["seek", v, "relative"]])
    elif cmd == "volume":
        mpv_ipc([["set_property", "volume", round(v * 100)]])
    elif cmd in ("soustitres", "audio"):
        typ = "sub" if cmd == "soustitres" else "audio"
        pistes = [p for p in mpv_ipc([["get_property", "track-list"]])[0] or [] if p.get("type") == typ]
        if v == -1 or int(v) < len(pistes):
            mpv_ipc([["set_property", "sid" if typ == "sub" else "aid", "no" if v == -1 else pistes[int(v)]["id"]]])
    elif cmd in ("jouer", "suivant"):
        lib, actuel = LIB[PILOTE["kind"]], PILOTE["id"]
        i = int(c["k"]) if cmd == "jouer" else episode_suivant(PILOTE["kind"], actuel)
        if i is None or not 0 <= i < len(lib):  # fin de la série / du film
            return
        # Les options du lancement (position de départ, piste audio) s'appliqueraient aussi au nouveau fichier.
        mpv_ipc([["set_property", "options/start", "none"], ["set_property", "options/aid", "auto"],
                 ["loadfile", str(Path(lib[i][2]).resolve())]])
        PILOTE.update(id=i, titre=titre_lib(PILOTE["kind"], i))


def nettoyer_polices(jours=60):
    """Supprime les polices extraites des MKV qui n'ont pas servi depuis `jours` jours."""
    if not POLICES_DIR.is_dir():
        return
    limite = time.time() - jours * 86400
    for d in POLICES_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < limite:
            shutil.rmtree(d, ignore_errors=True)


VIDEO_OK = {"h264", "vp8", "vp9", "av1"}  # codecs vidéo lus par les navigateurs
CONTENEURS_OK = {".mp4", ".m4v", ".webm", ".mkv", ".mov"}
LECTURE = {}  # chemin -> {"hls": conversion nécessaire, "duree": s}
SEG = 6  # durée d'un morceau HLS (s)


def besoin_conversion(chemin):
    """Le navigateur ne sait pas lire cette vidéo (AVI, HEVC/H.265, MPEG-4 Part 2, H.264 10 bits…) : conversion à la volée."""
    if not (FFMPEG and FFPROBE):
        return False
    if chemin not in LECTURE:
        try:
            out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                  "stream=codec_name,pix_fmt:format=duration", "-of", "json", chemin],
                                 capture_output=True, timeout=30).stdout
            info = json.loads(out or b"{}")
            v = (info.get("streams") or [{}])[0]
            codec, pix, duree = v.get("codec_name"), v.get("pix_fmt") or "", float(info.get("format", {}).get("duration") or 0)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            codec, pix, duree = None, "", 0
        hls = codec is not None and duree > 0 and (Path(chemin).suffix.lower() not in CONTENEURS_OK or codec not in VIDEO_OK
                                                   or (codec == "h264" and "10" in pix))
        LECTURE[chemin] = {"hls": hls, "duree": duree}
    return LECTURE[chemin]["hls"]


def playlist_hls(duree, suffixe=""):
    """Liste HLS « à la demande » : tous les morceaux de SEG s sont annoncés, chacun est converti quand on le demande.
    suffixe : « ?mc=… » repris sur chaque morceau (Chromecast, qui n'a pas le cookie du code d'accès)."""
    lignes = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{SEG}", "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for k in range(max(1, math.ceil(duree / SEG))):
        lignes += [f"#EXTINF:{min(SEG, duree - k * SEG):.3f},", f"{k}.ts{suffixe}"]
    return "\n".join(lignes + ["#EXT-X-ENDLIST", ""])


def commande_segment(chemin, k):
    """ffmpeg : morceau k (H.264 + AAC stéréo, MPEG-TS) avec les horodatages du film entier (avance/retour exacts)."""
    debut = k * SEG
    return [FFMPEG, "-v", "error", "-ss", str(debut), "-i", chemin, "-t", str(SEG), "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-vf", "scale='min(1920,iw)':-2",
            "-force_key_frames", "expr:gte(t,0)", "-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", "160k",
            "-output_ts_offset", str(debut), "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "pipe:1"]


# --- Installation des outils (ffmpeg, VLC) par winget, depuis la page, sur le PC seulement ---
OUTILS_WINGET = {"ffmpeg": "Gyan.FFmpeg", "vlc": "VideoLAN.VLC"}
INSTALLS = {}  # outil -> "en cours" | "ok" | "erreur : …"


def commande_winget(outil):
    return [shutil.which("winget") or "winget", "install", "-e", "--id", OUTILS_WINGET[outil], "--silent",
            "--accept-package-agreements", "--accept-source-agreements"]


def rafraichir_outils():
    """Après une installation : relit le PATH de Windows (mis à jour par winget) et retrouve ffmpeg / VLC."""
    global FFMPEG, FFPROBE
    if os.name == "nt":
        import winreg
        chemins = []
        for racine, cle in ((winreg.HKEY_CURRENT_USER, "Environment"),
                            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(racine, cle) as k:
                    chemins.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
        chemins.append(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"))  # outils « portables » de winget
        os.environ["PATH"] = os.pathsep.join(chemins + [os.environ.get("PATH", "")])
    FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not LECTEUR[0]:
        LECTEUR[0] = trouver_lecteur()


def installer(outil):
    try:
        r = subprocess.run(commande_winget(outil), capture_output=True, timeout=1800)
        rafraichir_outils()
        ok = FFMPEG and FFPROBE if outil == "ffmpeg" else LECTEUR[0]
        INSTALLS[outil] = "ok" if ok else f"erreur : {r.stdout.decode(errors='replace')[-200:] or 'outil introuvable après installation'}"
    except (OSError, subprocess.TimeoutExpired) as e:
        INSTALLS[outil] = f"erreur : {e}"


# --- Mises à jour : le .exe connaît son numéro (fabrication GitHub) ; une fois par jour, il regarde la dernière
# version publiée (Releases) et propose de se mettre à jour. Lancé avec Python (VERSION = 0) : rien à faire ici.
VERSION = int((RESSOURCES / "version.txt").read_text().strip() or 0) if (RESSOURCES / "version.txt").exists() else 0
URL_MAJ = os.environ.get("MEDIACENTER_MAJ_URL", "https://api.github.com/repos/benito0076/MediaCenter/releases/latest")
MAJ = {}  # {"version", "page", "exe"} si une version plus récente existe ; "etat" pendant la mise à jour


def lire_release(d):
    """Réponse de l'API GitHub -> (numéro, page, lien du .exe)."""
    n = int(re.sub(r"\D", "", d.get("tag_name", "")) or 0)
    exe = next((a.get("browser_download_url") for a in d.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
    return n, d.get("html_url", ""), exe


def verifier_maj():
    if not VERSION:
        return
    try:
        req = Request(URL_MAJ, headers={"Accept": "application/vnd.github+json", "User-Agent": "MediaCenter"})
        with urlopen(req, timeout=10) as r:
            n, page, exe = lire_release(json.load(r))
        if n > VERSION and exe:
            MAJ.update(version=n, page=page, exe=exe)
    except (OSError, ValueError, AttributeError):
        pass  # pas d'internet : on réessaiera demain


def surveiller_maj():
    while True:
        verifier_maj()
        time.sleep(86400)


def appliquer_maj():
    """Télécharge le nouveau .exe à côté de l'actuel ; un petit script attend la fermeture du Media Center,
    remplace le fichier et le relance. En cas d'échec, l'ancien .exe reste en place."""
    try:
        if os.name != "nt" or not GELE:
            raise OSError("mise à jour automatique : seulement pour le .exe Windows")
        exe = Path(sys.executable)
        neuf = exe.with_name(exe.stem + ".new.exe")
        with urlopen(Request(MAJ["exe"], headers={"User-Agent": "MediaCenter"}), timeout=600) as r, open(neuf, "wb") as f:
            shutil.copyfileobj(r, f)
        if neuf.stat().st_size < 1_000_000:
            raise OSError("téléchargement incomplet")
        bat, journal = exe.with_name("maj_mediacenter.bat"), exe.with_name("maj_mediacenter.log")
        # Le .exe reste verrouillé tant que le Media Center tourne : on retente le remplacement chaque seconde
        # (ping sert de minuterie : « timeout » refuse de tourner sans console), puis on relance. Chaque étape est notée.
        bat.write_text(f"""@echo off
chcp 65001 >nul
echo debut %date% %time% > "{journal}"
set /a essais=0
:copie
move /y "{neuf}" "{exe}" >nul 2>&1 && goto relance
set /a essais+=1
if %essais% geq 60 (echo echec du remplacement >> "{journal}" & goto fin)
ping -n 2 127.0.0.1 >nul
goto copie
:relance
echo remplace apres %essais% essai(s) >> "{journal}"
start "" "{exe}"
echo relance >> "{journal}"
:fin
del "%~f0"
""", encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        MAJ["etat"] = "redémarrage"
        threading.Timer(1, os._exit, [0]).start()  # laisse le temps de répondre à la page
    except (OSError, KeyError) as e:
        MAJ["etat"] = f"erreur : {e}"


def tester_url(url, entetes=None):
    """« ok », ou la raison de l'échec (pour le diagnostic)."""
    try:
        with urlopen(Request(url, headers={"User-Agent": "MediaCenter", **(entetes or {})}), timeout=6) as r:
            r.read(200)
        return "ok"
    except HTTPError as e:
        return f"HTTP {e.code}"
    except (OSError, ValueError) as e:
        return str(getattr(e, "reason", e))[:120]


def diagnostic(complet=True):
    """[(état, sujet, détail)] : ✅ bon, ⚠ à voir, ❌ problème. complet : tests réseau (internet) compris."""
    L = [("✅" if VERSION else "ℹ️", tr("Version"), f"build {VERSION}" if VERSION else tr("lancé avec Python (pas de mise à jour automatique)"))]
    if VERSION and MAJ.get("version"):
        L.append(("⚠️", tr("Mise à jour"), f'{tr("version disponible")} : build {MAJ["version"]}'))
    for k, nom in (("films", "Films"), ("series", "Séries"), ("musique", "Musique")):
        for d in CFG.get(k, []):
            ok = Path(d).is_dir()
            n = sum(1 for _t, _d, c in LIB[k] if c.startswith(str(Path(d))))
            L.append(("✅" if ok else "❌", f'{tr("Dossier")} {tr(nom)}', f"{d} — {n} {tr('fichiers')}" if ok else f"{d} : {tr('introuvable')}"))
    if not any(CFG.get(k) for k in LIB):
        L.append(("❌", tr("Dossiers"), tr("aucun dossier configuré")))
    L.append(("✅" if FFMPEG and FFPROBE else "⚠️", "ffmpeg", FFMPEG or tr("absent : vidéos AVI/HEVC, pistes et sous-titres des MKV, son AC3/DTS indisponibles")))
    L.append(("✅" if LECTEUR[0] else "⚠️", tr("Lecteur pour l'ampli"), LECTEUR[0] or tr("ni mpv ni VLC : pas de passthrough")))
    fiches = [Path(c).name for _t, _d, c in LIB["films"]] + ["serie:" + d for d in {d for _t, d, _c in LIB["series"]}]
    avec = sum(1 for f in fiches if (META.get(f) or {}).get("affiche"))
    if fiches:
        L.append(("✅" if avec == len(fiches) else "⚠️", tr("Affiches"), f"{avec} / {len(fiches)}"))
    if complet:
        cle = CFG.get("tmdb")
        if cle:
            ent = {"Authorization": "Bearer " + cle} if cle.startswith("eyJ") else {}
            r = tester_url("https://api.themoviedb.org/3/configuration" + ("" if ent else "?api_key=" + quote(cle)), ent)
            L.append(("✅" if r == "ok" else "❌", "TMDB", tr("clé acceptée") if r == "ok" else
                      (tr("clé refusée") if r == "HTTP 401" else f'{tr("injoignable")} ({r})')))
        else:
            r = tester_url("https://itunes.apple.com/search?term=avatar&media=movie&limit=1")
            L.append(("✅" if r == "ok" else "❌", "iTunes", tr("joignable") if r == "ok" else f'{tr("injoignable")} ({r})'))
        if VERSION:
            r = tester_url(URL_MAJ)
            L.append(("✅" if r == "ok" else "⚠️", tr("Mises à jour (GitHub)"), tr("joignable") if r == "ok" else f'{tr("injoignable")} ({r})'))
    L.append(("✅" if RESEAU[0] else "ℹ️", tr("Réseau"), f"http://{ip_lan()}:{PORT[0]}" if RESEAU[0] else tr("seulement ce PC (lancer avec --reseau pour la TV et le téléphone)")))
    L.append(("✅" if ACCES["jeton"] else ("⚠️" if RESEAU[0] else "ℹ️"), tr("Code d'accès"), tr("activé") if ACCES["jeton"] else tr("aucun")))
    L.append(("ℹ️", tr("Cache audio"), f"{taille_cache_audio() / 1e6:.0f} Mo / {CACHE_AUDIO_MAX[0] / 1e9:.0f} Go"))
    return L


def html_diagnostic(sur_le_pc):
    lignes = "".join(f"<tr><td>{e}</td><td>{html.escape(s)}</td><td>{html.escape(str(d))}</td></tr>" for e, s, d in diagnostic())
    sauvegarde = "" if not sur_le_pc else (
        f'<h3>💾 {tr("Sauvegarde")}</h3><p>{tr("Réglages, profils, « déjà vu », reprises, file d\'attente, listes et affiches.")}</p>'
        f'<a class="bt" href="/sauvegarde">{tr("Exporter")}</a> <label class="bt">{tr("Importer")}'
        '<input type="file" id="imp" accept=".zip" hidden></label> <small id="imp_etat"></small>'
        """<script>imp.onchange=async()=>{const r=await fetch('/restaurer',{method:'POST',body:imp.files[0]});"""
        f"""imp_etat.textContent=r.ok?'{tr("Restauré. Redémarre le Media Center si tu as changé de dossiers ou de code.")}'"""
        f""":'{tr("Fichier refusé")} ('+r.status+')'}}</script>""")
    return f'<h2>🩺 {tr("Diagnostic")}</h2><table id="diag">{lignes}</table>{sauvegarde}'


def bandeau_maj():
    if not MAJ.get("version"):
        return ""
    return (f'<div id="maj">🆕 {tr("Nouvelle version disponible")} ({MAJ["version"]}, {tr("actuelle")} {VERSION}) '
            f'<button class="bt" id="majok">{tr("Mettre à jour")}</button> '
            f'<a href="{html.escape(MAJ["page"])}" target="_blank">{tr("Voir")}</a> <small id="maj_etat"></small></div>')


def bandeau_outils():
    """Sur le PC seulement : ce qui manque, avec un bouton « Installer » si winget est là."""
    manque = [(o, t) for o, t, ok in (("ffmpeg", "ffmpeg (vidéos AVI/HEVC, sous-titres et pistes audio des MKV, son AC3/DTS)",
                                       FFMPEG and FFPROBE),
                                      ("vlc", "un lecteur pour l'ampli (passthrough Dolby/DTS)", LECTEUR[0])) if not ok]
    if not manque:
        return bandeau_maj()
    winget = bool(shutil.which("winget"))
    lignes = "".join(f'<div>⚙ {tr("Manque :")} {tr(t)} '
                     + (f'<button class="bt" data-installer="{o}">{tr("Installer")}</button>' if winget else
                        f'<a href="{"https://ffmpeg.org/download.html" if o == "ffmpeg" else "https://www.videolan.org"}" target="_blank">'
                        f'{tr("Télécharger")}</a>') + "</div>" for o, t in manque)
    return bandeau_maj() + f'<div id="outils">{lignes}<small id="outils_etat"></small></div>'


# --- Chromecast : la TV lit directement depuis le PC (il faut --reseau) ; le code d'accès passe dans l'adresse.
RESEAU = [False]
PORT = [8765]


def ip_lan():
    """Adresse du PC sur le réseau local (aucune donnée n'est envoyée : sert seulement à choisir l'interface)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
            so.connect(("192.0.2.1", 9))
            return so.getsockname()[0]
    except OSError:
        return ""


def infos_cast(kind, i):
    """Adresse à donner au Chromecast : le fichier tel quel s'il le lit (MP4/WebM), sinon la conversion à la volée (HLS)."""
    chemin = LIB[kind][i][2]
    base, q = f"http://{ip_lan()}:{PORT[0]}", (f"?mc={ACCES['jeton']}" if ACCES["jeton"] else "")
    hls = FFMPEG and FFPROBE and (besoin_conversion(chemin) or Path(chemin).suffix.lower() not in (".mp4", ".m4v", ".webm"))
    if hls:
        return {"url": f"{base}/hls/{kind}/{i}/index.m3u8{q}", "type": "application/x-mpegurl", "hls": True, "base": base, "q": q}
    return {"url": f"{base}/media/{kind}/{i}{q}", "type": mimetypes.guess_type(chemin)[0] or "video/mp4", "hls": False,
            "base": base, "q": q}


def nom_canaux(n):
    return {3: "2.1", 4: "4.0", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}.get(n, f"{n} canaux")


def options_conversion(canaux):
    """AAC pour le navigateur : le surround est gardé (jusqu'au 5.1 ; le 6.1/7.1 est ramené en 5.1), sinon stéréo.
    Le navigateur repasse lui-même en stéréo si l'ordinateur n'a que 2 haut-parleurs."""
    if canaux > 2:
        return ["-ac", "6" if canaux >= 6 else str(canaux), "-b:a", "384k"]
    return ["-ac", "2", "-b:a", "192k"]


def nettoyer_cache_audio(limite, demarrage=False, garder=None):
    """Garde le cache audio sous `limite` octets en supprimant les pistes utilisées il y a le plus longtemps
    (sauf `garder`, la piste qu'on vient de convertir : sinon une limite trop petite la reconvertirait sans fin)."""
    if not AUDIO_DIR.is_dir():
        return
    if demarrage:  # conversions interrompues (PC éteint pendant une conversion)
        for f in AUDIO_DIR.glob("*.tmp.m4a"):
            f.unlink(missing_ok=True)
    fichiers = sorted((f for f in AUDIO_DIR.glob("*.m4a") if not f.name.endswith(".tmp.m4a")),
                      key=lambda f: f.stat().st_mtime)  # date de dernière utilisation (mise à jour à chaque lecture)
    total = sum(f.stat().st_size for f in fichiers)
    for f in fichiers:
        if total <= limite:
            break
        if f == garder:
            continue
        try:
            taille = f.stat().st_size
            f.unlink()
            total -= taille
        except OSError:  # en cours de lecture (Windows verrouille le fichier) : on passe au suivant
            pass


def taille_cache_audio():
    return sum(f.stat().st_size for f in AUDIO_DIR.glob("*.m4a")) if AUDIO_DIR.is_dir() else 0


def vider_cache_audio():
    """Bouton « Vider » : tout supprimer, sauf la piste en cours d'écoute (film joué en ce moment) et les conversions en cours."""
    garder = None
    if VIDEO and time.time() - RELEVE.get(VIDEO.get("dev"), 0) < 5 and VIDEO["id"] < len(LIB[VIDEO["kind"]]):  # page encore ouverte
        garder = fichier_audio(LIB[VIDEO["kind"]][VIDEO["id"]][2], VIDEO.get("aui", 0))
    nettoyer_cache_audio(0, garder=garder)
    return taille_cache_audio()


def fichier_audio(chemin, n):
    # « surround » : les anciennes conversions stéréo ne sont pas réutilisées (le nettoyage auto les supprimera)
    return AUDIO_DIR / (hashlib.sha1(f"{chemin}|{n}|surround".encode()).hexdigest()[:16] + ".m4a")


def extraire_audio(chemin, n):
    """Lance (une fois) la conversion de la piste audio n en AAC stéréo ; renvoie "pret", "en cours" ou une erreur."""
    sortie = fichier_audio(chemin, n)
    if sortie.exists():
        try:
            os.utime(sortie)  # marque la piste comme utilisée récemment (nettoyage du cache)
        except OSError:
            pass
        return "pret"
    with VERROU:
        etat = EXTRACTIONS.get(sortie)
        if etat is None:
            EXTRACTIONS[sortie] = etat = "en cours"
            threading.Thread(target=_convertir_audio, args=(chemin, n, sortie), daemon=True).start()
    return etat


def _convertir_audio(chemin, n, sortie):
    AUDIO_DIR.mkdir(exist_ok=True)
    tmp = sortie.with_suffix(".tmp.m4a")
    try:  # ~150 Mo par piste de film en stéréo, ~300 Mo en 5.1 ; cache limité par nettoyer_cache_audio
        canaux = (pistes_audio(chemin)[n:n + 1] or [{}])[0].get("canaux", 2)
        r = subprocess.run([FFMPEG, "-v", "error", "-y", "-i", chemin, "-map", f"0:a:{n}", "-vn", "-c:a", "aac",
                            *options_conversion(canaux), "-movflags", "+faststart", str(tmp)], capture_output=True, timeout=3600)
        if r.returncode:
            raise OSError(r.stderr.decode(errors="replace")[-200:])
        tmp.replace(sortie)
        nettoyer_cache_audio(CACHE_AUDIO_MAX[0], garder=sortie)
        EXTRACTIONS.pop(sortie, None)
    except (OSError, subprocess.TimeoutExpired) as e:
        EXTRACTIONS[sortie] = f"erreur : {e}"
        print(f"⚠ Piste audio non convertie ({Path(chemin).name}) : {e}")


def pistes_integrees(chemin):
    if not FFPROBE:
        return []
    if chemin not in PISTES:
        try:
            out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "s", "-show_entries",
                                  "stream=codec_name:stream_tags=language,title", "-of", "json", chemin],
                                 capture_output=True, timeout=30).stdout
            flux = json.loads(out or b"{}").get("streams", [])
        except (OSError, ValueError, subprocess.TimeoutExpired):
            flux = []
        PISTES[chemin] = [(nom_piste(f), i, f["codec_name"]) for i, f in enumerate(flux) if f.get("codec_name") in TEXTE]
    return PISTES[chemin]


def extraire_piste(chemin, piste, fmt="webvtt"):
    """Piste intégrée -> WebVTT, ou ASS brut (fmt="ass") pour le rendu stylé."""
    if (chemin, piste, fmt) not in VTT:  # ffmpeg doit lire tout le fichier : quelques secondes sur un gros MKV
        codec = ["-c:s", "copy"] if fmt == "ass" else []
        r = subprocess.run([FFMPEG, "-v", "error", "-i", chemin, "-map", f"0:s:{piste}", *codec, "-f", fmt, "-"],
                           capture_output=True, timeout=600)
        if r.returncode:
            raise OSError(r.stderr.decode(errors="replace")[-300:])
        VTT[chemin, piste, fmt] = r.stdout.decode("utf-8", errors="replace")
    return VTT[chemin, piste, fmt]


def infos_pistes(chemin):
    """Toutes les pistes de sous-titres d'une vidéo (fichiers externes puis intégrées) : [{"nom", "ass"}]."""
    ext = [{"nom": nom_sous_titre(f, chemin), "ass": Path(f).suffix.lower() in (".ass", ".ssa")} for f in SUBS.get(chemin, [])]
    return ext + [{"nom": n, "ass": codec in ("ass", "ssa")} for n, _, codec in pistes_integrees(chemin)]


def polices(chemin):
    """Polices pour le rendu .ass : dossier Fonts/ à côté de la vidéo + polices jointes au MKV (extraites une fois)."""
    if chemin in POLICES:
        return POLICES[chemin]
    v, res = Path(chemin), []
    try:
        for d in v.parent.iterdir():
            if d.is_dir() and d.name.lower() in ("fonts", "polices", "attachments"):
                res += sorted(str(f) for f in d.iterdir() if f.suffix.lower() in FONT_EXT and f.is_file())
    except OSError:
        pass
    if FFMPEG and FFPROBE and v.suffix.lower() == ".mkv":
        try:
            out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "t", "-show_entries",
                                  "stream=index:stream_tags=filename", "-of", "json", chemin],
                                 capture_output=True, timeout=30).stdout
            jointes = [(f["index"], Path({k.lower(): x for k, x in f.get("tags", {}).items()}.get("filename", "")).suffix.lower())
                       for f in json.loads(out or b"{}").get("streams", [])]
            jointes = [(i, e) for i, e in jointes if e in FONT_EXT]
            dest = POLICES_DIR / hashlib.sha1(chemin.encode()).hexdigest()[:16]
            if jointes and not (dest.is_dir() and any(dest.iterdir())):
                dest.mkdir(parents=True, exist_ok=True)
                # Noms de fichiers choisis ici (pas ceux du MKV) : pas d'écriture hors du cache.
                args = [a for k, (i, e) in enumerate(jointes) for a in (f"-dump_attachment:{i}", str(dest / f"{k}{e}"))]
                subprocess.run([FFMPEG, "-v", "error", "-y", *args, "-i", chemin], capture_output=True, timeout=120)
                # ffmpeg finit en erreur « aucune sortie » après l'extraction : normal, on regarde les fichiers.
            if jointes and dest.is_dir():
                res += sorted(str(f) for f in dest.iterdir())
                os.utime(dest)  # date de dernière utilisation (nettoyage au bout de 60 jours)
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
            print(f"⚠ Polices non extraites ({v.name}) : {e}")
    POLICES[chemin] = res
    return res


def ordre(kind):
    """Numéros de LIB[kind] dans l'ordre d'affichage (dossier puis titre). LIB ne fait que grandir (voir scan)."""
    lib = LIB[kind]
    return sorted(range(len(lib)), key=lambda i: (lib[i][1].lower(), lib[i][0].lower()))


def episode_suivant(kind, actuel):
    o = ordre(kind)
    k = o.index(actuel) + 1
    return o[k] if k < len(o) and LIB[kind][o[k]][1] == LIB[kind][actuel][1] else None


def scan(dossiers):
    """Ajoute les nouveaux fichiers à la bibliothèque et renvoie leur nombre.
    Les numéros (positions dans LIB) ne changent jamais pendant que le programme tourne : une page ouverte ou une vidéo
    en cours ne peut pas se retrouver sur un autre fichier. Un fichier supprimé reste listé jusqu'au redémarrage."""
    nouveaux = 0
    for kind, roots in dossiers.items():
        connus = {c for _, _, c in LIB[kind]}
        items = []
        for root in roots:
            root = Path(root)
            for p in root.rglob("*"):
                if p.suffix.lower() in EXT[kind] and str(p) not in connus and p.is_file():
                    dossier = str(p.parent.relative_to(root))
                    dossier = "" if dossier == "." else dossier
                    if kind == "series":
                        dossier, titre = episode(p.stem, p.parent.relative_to(root).parts)
                    else:
                        titre = nettoyer(p.stem)[0] if kind == "films" else re.sub(r"[._]+", " ", p.stem).strip()
                    items.append((titre or p.stem, dossier, str(p)))
                    AJOUT[str(p)] = p.stat().st_mtime  # pour « Ajoutés récemment »
                    if kind == "musique":
                        if str(p.parent) not in COVERS:
                            COVERS[str(p.parent)] = pochette_locale(p.parent)
                        if not COVERS[str(p.parent)] and pochette_integree(str(p)):
                            COVERS[str(p.parent)] = str(p)
        LIB[kind] += sorted(items, key=lambda i: (i[1].lower(), i[0].lower()))
        nouveaux += len(items)
        if kind != "musique":  # sous-titres revus pour toutes les vidéos : un .srt ajouté après coup est trouvé
            par_dossier = {}
            for _, _, c in LIB[kind]:
                par_dossier[str(Path(c).parent)] = par_dossier.get(str(Path(c).parent), 0) + 1
            for _, _, c in LIB[kind]:
                try:
                    SUBS[c] = sous_titres(Path(c), par_dossier[str(Path(c).parent)] == 1)
                except OSError:
                    pass
    return nouveaux


def surveiller(dossiers, en_ligne, cle, minutes=5):
    """Revoit les dossiers régulièrement : les nouveaux téléchargements apparaissent sans redémarrer."""
    while True:
        time.sleep(minutes * 60)
        try:
            n = scan(dossiers)
        except OSError as e:
            print(f"⚠ Analyse des dossiers impossible : {e}")
            continue
        if n:
            print(f"{n} nouveau(x) fichier(s) ajouté(s).")
            if en_ligne:
                enrichir(cle)


def meilleur(resultats, annee, champ_date):
    return next((x for x in resultats if annee and (x.get(champ_date) or "").startswith(annee)), resultats[0])


def choisir(resultats, annee):  # format iTunes
    if not resultats:
        return {}
    r = meilleur(resultats, annee, "releaseDate")
    return {"titre": r.get("trackName") or r.get("collectionName", ""), "annee": r.get("releaseDate", "")[:4],
            "resume": r.get("longDescription") or r.get("shortDescription", ""),
            "affiche": r.get("artworkUrl100", "").replace("100x100", "600x600"),
            "genres": [r["primaryGenreName"]] if r.get("primaryGenreName") else []}


# Genres TMDB (identifiants fixes) -> noms ; traduits en espagnol à l'affichage (GENRES_ES, à part de ES :
# « Action » apparaît dans le code JavaScript, il ne doit pas passer par traduire()).
GENRES_TMDB = {28: "Action", 12: "Aventure", 16: "Animation", 35: "Comédie", 80: "Crime", 99: "Documentaire", 18: "Drame",
               10751: "Familial", 14: "Fantastique", 36: "Histoire", 27: "Horreur", 10402: "Musique", 9648: "Mystère",
               10749: "Romance", 878: "Science-Fiction", 10770: "Téléfilm", 53: "Thriller", 10752: "Guerre", 37: "Western",
               10759: "Action & Aventure", 10762: "Enfants", 10763: "Actualités", 10764: "Téléréalité",
               10765: "Science-Fiction & Fantastique", 10766: "Feuilleton", 10767: "Talk-show", 10768: "Guerre & Politique"}
GENRES_ES = {"Action": "Acción", "Aventure": "Aventura", "Animation": "Animación", "Comédie": "Comedia", "Crime": "Crimen",
             "Documentaire": "Documental", "Drame": "Drama", "Familial": "Familia", "Fantastique": "Fantasía", "Histoire": "Historia",
             "Horreur": "Terror", "Musique": "Música", "Mystère": "Misterio", "Science-Fiction": "Ciencia ficción",
             "Téléfilm": "Película de TV", "Guerre": "Bélica", "Action & Aventure": "Acción y aventura", "Enfants": "Infantil",
             "Actualités": "Noticias", "Téléréalité": "Reality", "Science-Fiction & Fantastique": "Ciencia ficción y fantasía",
             "Feuilleton": "Telenovela", "Guerre & Politique": "Bélica y política"}


def tr_genre(g):
    return GENRES_ES.get(g, g) if LANGUE[0] == "es" else g


def choisir_tmdb(resultats, annee, champ="release_date"):  # séries : champ="first_air_date"
    if not resultats:
        return {}
    r = meilleur(resultats, annee, champ)
    return {"titre": r.get("title") or r.get("name", ""), "annee": (r.get(champ) or "")[:4], "resume": r.get("overview", ""),
            "affiche": "https://image.tmdb.org/t/p/w500" + r["poster_path"] if r.get("poster_path") else "",
            "genres": [GENRES_TMDB[g] for g in r.get("genre_ids", []) if g in GENRES_TMDB], "source": "tmdb"}


def chercher_itunes(titre, annee, quoi="movie"):
    media, entity = ("movie", "movie") if quoi == "movie" else ("tvShow", "tvSeason")
    q = urlencode({"term": titre, "media": media, "entity": entity, "country": "fr", "lang": "fr_fr", "limit": 10})
    with urlopen("https://itunes.apple.com/search?" + q, timeout=10) as r:
        return choisir(json.load(r).get("results", []), annee)


def chercher_tmdb(titre, annee, cle, quoi="movie"):
    q, h = {"query": titre, "language": "fr-FR"}, {"Accept": "application/json"}
    if cle.startswith("eyJ"):  # « jeton d'accès en lecture » (long) plutôt que « clé d'API » (courte)
        h["Authorization"] = "Bearer " + cle
    else:
        q["api_key"] = cle
    url = f"https://api.themoviedb.org/3/search/{quoi}?" + urlencode(q)
    with urlopen(Request(url, headers=h), timeout=10) as r:
        return choisir_tmdb(json.load(r).get("results", []), annee, "release_date" if quoi == "movie" else "first_air_date")


def chercher_album(terme):
    q = urlencode({"term": terme, "media": "music", "entity": "album", "country": "fr", "limit": 1})
    with urlopen("https://itunes.apple.com/search?" + q, timeout=10) as r:
        res = json.load(r).get("results", [])
    return {"affiche": res[0].get("artworkUrl100", "").replace("100x100", "600x600")} if res else {}


def sauver():
    CACHE.write_text(json.dumps(META, ensure_ascii=False), "utf-8")


def enrichir(cle=None):
    a_faire = [(Path(c).name, *nettoyer(Path(c).stem), "movie") for _, _, c in LIB["films"]]
    a_faire += [("serie:" + n, n, "", "tv") for n in dict.fromkeys(d for _, d, _ in LIB["series"])]
    # Avec TMDB, on repasse aussi sur ce qu'iTunes a trouvé (ou pas).
    # Avec TMDB (rapide), on repasse aussi sur les fiches sans genre (mises en cache avant l'ajout des filtres).
    manquants = [x for x in a_faire if x[0] not in META or (cle and (META[x[0]].get("source") != "tmdb"
                                                                    or (META[x[0]] and "genres" not in META[x[0]])))]
    if manquants:
        print(f"Recherche des affiches ({'TMDB' if cle else 'iTunes'}) pour {len(manquants)} films/séries (en arrière-plan)…")
    for cle_meta, titre, annee, quoi in manquants:
        try:
            info = chercher_tmdb(titre, annee, cle, quoi) if cle else chercher_itunes(titre, annee, quoi)
        except HTTPError as e:
            if e.code == 401:
                print("⚠ Clé TMDB refusée : vérifie-la (python mediacenter.py --tmdb CLE)")
                break
            print(f"⚠ Affiche non récupérée pour {cle_meta} : {e}")
            continue
        except (OSError, ValueError) as e:  # pas d'internet : on réessaiera au prochain lancement
            print(f"⚠ Affiche non récupérée pour {cle_meta} : {e}")
            continue
        # TMDB n'a rien trouvé : on garde ce qu'iTunes avait, marqué comme déjà tenté.
        META[cle_meta] = info or ({**META.get(cle_meta, {}), "source": "tmdb"} if cle else {})
        sauver()
        time.sleep(0.1 if cle else 3)  # ponytail: iTunes limite à ~20 requêtes/min ; 1re fois lente si grosse collection

    # Albums sans image locale : pochette iTunes d'après le nom du dossier.
    albums = sorted({d for _, d, c in LIB["musique"] if d and not COVERS.get(str(Path(c).parent))
                     and "album:" + d not in META})
    if albums:
        print(f"Recherche des pochettes pour {len(albums)} albums (en arrière-plan)…")
    for d in albums:
        try:
            META["album:" + d] = chercher_album(nettoyer_album(d))
        except (OSError, ValueError) as e:
            print(f"⚠ Pochette non récupérée pour {d} : {e}")
            continue
        sauver()
        time.sleep(3)


def maj_suivi(e, data):
    """Nouvel état de suivi d'une vidéo après un envoi du navigateur : {"t", "d"} ou {"vu": bool}."""
    e = dict(e)
    if "vu" in data:  # case cochée à la main
        e.update(vu=bool(data["vu"]), t=0)
        return e
    t, d = float(data["t"]), float(data.get("d") or 0)
    if not (math.isfinite(t) and math.isfinite(d) and 0 <= t < 1e6 and 0 <= d < 1e6):
        raise ValueError("position invalide")
    if d:
        e["d"] = d
    if d and t > 0.9 * d:  # générique de fin atteint : vu, et la prochaine fois on repart du début
        e.update(vu=True, t=0)
    else:
        e["t"] = round(t, 1)
    return e


def suivi(chemin):
    """(attributs du <li>, HTML de la barre de progression + case « vu »)"""
    e = S().get(Path(chemin).name, {})
    pct = min(100, int(100 * e["t"] / e["d"])) if e.get("t") and e.get("d") else 0
    attrs = f' data-pos="{e.get("t", 0)}"' + (' class="vu"' if e.get("vu") else "")
    return attrs, (f'<i class="bar" style="width:{pct}%"></i>' if pct else "") + f'<b class="ck" title="{tr("Vu / pas vu")}">✓</b>'


def charger_etat():
    """Profils, affiches, « déjà vu », reprises, file d'attente : au démarrage et après l'import d'une sauvegarde."""
    cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {}
    PROFILS[:] = [p for p in cfg.get("profils", []) if isinstance(p, str)]
    if CACHE.exists():
        META.update(json.loads(CACHE.read_text("utf-8")))
    SUIVI.clear()
    SUIVIS.clear()
    SUIVIS[""] = SUIVI  # les autres profils sont relus à la demande (S())
    if SUIVI_F.exists():
        SUIVI.update(json.loads(SUIVI_F.read_text("utf-8")))
    ENCOURS.clear()
    if ENCOURS_F.exists():
        try:
            ENCOURS.update(valider_encours(json.loads(ENCOURS_F.read_text("utf-8"))), lecture=False)  # rien ne joue au démarrage
        except (ValueError, KeyError, TypeError):
            pass
    FILE.clear()
    if FILE_F.exists():
        try:
            FILE[:] = valider_file(json.loads(FILE_F.read_text("utf-8")))
        except ValueError:
            print("⚠ mediacenter_file.json illisible : file d'attente vide")


# Sauvegarde : tous les mediacenter*.json (réglages, profils, déjà vu, reprises, file, listes, affiches) dans un .zip.
NOM_SAUVEGARDE = re.compile(r"mediacenter(_[a-z0-9_]+)?\.json")  # pas de « / » : rien ne s'écrit hors du dossier


def exporter_sauvegarde():
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BASE.glob("mediacenter*.json")):
            if NOM_SAUVEGARDE.fullmatch(f.name):
                z.write(f, f.name)
    return tampon.getvalue()


def importer_sauvegarde(donnees):
    """Vérifie tout le .zip avant d'écrire quoi que ce soit ; renvoie le nombre de fichiers restaurés."""
    fichiers = {}
    with zipfile.ZipFile(io.BytesIO(donnees)) as z:
        for info in z.infolist():
            if not NOM_SAUVEGARDE.fullmatch(info.filename) or info.file_size > 200 * 1024 ** 2:
                raise ValueError(f"fichier inattendu : {info.filename}")
            fichiers[info.filename] = z.read(info)
            json.loads(fichiers[info.filename])
    if "mediacenter.json" not in fichiers:
        raise ValueError("ce n'est pas une sauvegarde du Media Center")
    with VERROU:
        for nom, contenu in fichiers.items():
            (BASE / nom).write_bytes(contenu)
        charger_etat()
    return len(fichiers)


def valider_file(data):
    """Corps envoyé par le navigateur -> liste de clés de morceaux, ou ValueError."""
    if not (isinstance(data, list) and len(data) <= 5000 and all(isinstance(k, str) and len(k) < 2000 for k in data)):
        raise ValueError("file d'attente invalide")
    return data


def valider_encours(data):
    """{"k": clé, "t": position, "lecture": bool, "dev": id d'appareil} envoyé par le navigateur, ou ValueError."""
    k, t, lecture, dev, vol = data["k"], float(data["t"]), data["lecture"], data.get("dev", ""), float(data.get("vol", 1))
    if not (isinstance(k, str) and len(k) < 2000 and math.isfinite(t) and 0 <= t < 1e6 and isinstance(lecture, bool)
            and isinstance(dev, str) and len(dev) < 100 and 0 <= vol <= 1):
        raise ValueError("morceau en cours invalide")
    return {"k": k, "t": round(t, 1), "lecture": lecture, "dev": dev, "vol": round(vol, 2), "quand": time.time()}


def valider_commande(data):
    """{"cmd": ordre, "k": clé du morceau (« jouer »), "v": volume 0–1 (« volume »)} de la télécommande, ou ValueError."""
    cmd, k, v = data["cmd"], data.get("k", ""), float(data.get("v", 0))
    if (cmd not in ORDRES or not isinstance(k, str) or len(k) >= 2000 or (cmd == "jouer" and not k)
            or not (-3600 <= v <= 3600 if cmd == "deplacer" else v in range(-1, 100) if cmd == "soustitres"
                    else v in range(100) if cmd == "audio"
                    else 0 <= v <= 1)):  # NaN refusé aussi ; deplacer : secondes ; soustitres : n° de piste, -1 = aucun
        raise ValueError("commande invalide")
    return {"cmd": cmd, "k": k, "v": v}


def valider_video(data):
    """État du lecteur vidéo envoyé par l'appareil qui joue un film/épisode, ou ValueError."""
    v = {"kind": data["kind"], "id": int(data["id"]), "titre": data["titre"], "t": float(data["t"]), "d": float(data.get("d") or 0),
         "lecture": data["lecture"], "vol": float(data.get("vol", 1)), "page": data.get("page", ""), "dev": data.get("dev", ""),
         "st": data.get("st", []), "sti": data.get("sti", -1),  # sous-titres : noms des pistes, n° de celle affichée (-1 = aucune)
         "au": data.get("au", []), "aui": data.get("aui", 0)}  # pistes audio : noms, n° de celle choisie
    if not (v["kind"] in ("films", "series") and v["id"] >= 0 and isinstance(v["titre"], str) and len(v["titre"]) < 500
            and all(math.isfinite(v[x]) and 0 <= v[x] < 1e6 for x in ("t", "d")) and isinstance(v["lecture"], bool)
            and 0 <= v["vol"] <= 1 and all(isinstance(v[x], str) and len(v[x]) < 500 for x in ("page", "dev"))
            and isinstance(v["st"], list) and len(v["st"]) < 50 and all(isinstance(x, str) and len(x) < 200 for x in v["st"])
            and v["sti"] in range(-1, len(v["st"]))
            and isinstance(v["au"], list) and len(v["au"]) < 50 and all(isinstance(x, str) and len(x) < 200 for x in v["au"])
            and (v["aui"] in range(len(v["au"])) or v["aui"] == 0)):
        raise ValueError("état vidéo invalide")
    return {**v, "t": round(v["t"], 1), "quand": time.time()}


def etat_public(etat, moi):
    """État partagé tel qu'envoyé aux appareils : âge, « c'est moi ? », joignable ; l'id des autres n'est pas divulgué."""
    e = dict(etat)
    if e:
        e["age"] = round(time.time() - e.pop("quand"), 1)
        dev = e.pop("dev", "")
        e["moi"] = dev == moi
        e["joignable"] = time.time() - RELEVE.get(dev, 0) < 5
    return e


def accepter_encours(actuel, nouveau):
    """Un appareil qui se met en pause n'écrase pas un autre appareil qui joue encore (passage de relais)."""
    return not (actuel.get("lecture") and not nouveau["lecture"] and actuel.get("dev") != nouveau["dev"]
                and nouveau["quand"] - actuel["quand"] < 30)


# Interface : web/page.html (structure), web/style.css, web/app.js ; les {repères} sont remplis à chaque page.
PAGE = ((WEB_DIR / "page.html").read_text("utf-8").replace("{css}", (WEB_DIR / "style.css").read_text("utf-8"))
        .replace("{js}", (WEB_DIR / "app.js").read_text("utf-8") + (WEB_DIR / "nav.js").read_text("utf-8")))
NAV_JS = (WEB_DIR / "nav.js").read_text("utf-8")  # aussi sur l'accueil


def attrs_filtres(m, annee, ajout):
    """data-* pour trier / filtrer côté navigateur : année, date d'ajout, genres."""
    return (f' data-annee="{html.escape(str(annee or ""))}" data-ajout="{int(ajout or 0)}"'
            f' data-genres="{html.escape("|".join(m.get("genres", [])))}"')


def carte_film(i, titre, chemin):
    m = META.get(Path(chemin).name) or {}
    t, a = m.get("titre") or titre, m.get("annee", "")
    img = f'<img src="{html.escape(m["affiche"])}" loading="lazy" alt="">' if m.get("affiche") else '<div class="ph">🎬</div>'
    attrs, extra = suivi(chemin)
    attrs += attrs_filtres(m, a or nettoyer(Path(chemin).stem)[1], AJOUT.get(chemin))
    return (f'<li data-id="{i}" data-t="{html.escape(t)}{" (" + a + ")" if a else ""}" data-r="{html.escape(m.get("resume", ""))}"{attrs}>'
            f'{img}{html.escape(t)}<small>{a}</small>{extra}</li>')


def ligne_musique(i, titre, dossier, chemin, premier):
    parent = str(Path(chemin).parent)
    # Une seule URL par album pour que le navigateur ne télécharge l'image qu'une fois.
    src = f"/cover/{premier.setdefault(parent, i)}" if COVERS.get(parent) else (META.get("album:" + dossier) or {}).get("affiche", "")
    img = f'<img src="{html.escape(src)}" loading="lazy" alt="">' if src else '<div class="ph">🎵</div>'
    cle = html.escape(dossier + "/" + Path(chemin).name)  # identifiant stable (les numéros changent au rescan)
    return (f'<li data-id="{i}" data-k="{cle}" data-t="{html.escape(titre)}" data-img="{html.escape(src)}">{img}'
            f'<span>{html.escape(titre)}<small>{html.escape(dossier)}</small></span>'
            f'<button class="qn" title="{tr("Lire juste après")}" aria-label="{tr("Lire juste après")}">↱</button>'
            f'<button class="qa" title="{tr(QA)}" aria-label="{tr(QA)}">+</button></li>')


QA = "Ajouter à la file d'attente"


def carte_serie(nom, nb):
    m = META.get("serie:" + nom) or {}
    vus = sum(1 for _, d, c in LIB["series"] if d == nom and S().get(Path(c).name, {}).get("vu"))
    vus_txt = f" · {vus} {tr('vus' if vus > 1 else 'vu')}" if vus else ""
    img = f'<img src="{html.escape(m["affiche"])}" loading="lazy" alt="">' if m.get("affiche") else '<div class="ph">📺</div>'
    ajout = max((AJOUT.get(c, 0) for _t, d, c in LIB["series"] if d == nom), default=0)
    attrs = attrs_filtres(m, m.get("annee", ""), ajout) + f' data-nonvu="{1 if vus < nb else 0}"'
    return (f'<li data-href="/?k=series&amp;s={html.escape(quote(nom))}" data-t="{html.escape(nom)}"{attrs}>{img}{html.escape(nom)}'
            f'<small>{nb} {tr("épisodes" if nb > 1 else "épisode")}{vus_txt}</small></li>')


def barre_filtres(kind):
    """Tri, genre et « non vus » au-dessus de la grille (films, séries)."""
    cles = [Path(c).name for _t, _d, c in LIB["films"]] if kind == "films" else ["serie:" + d for d in {d for _t, d, _c in LIB["series"]}]
    genres = sorted({g for k in cles for g in (META.get(k) or {}).get("genres", [])}, key=lambda g: tr_genre(g).lower())
    options = "".join(f'<option value="{html.escape(g)}">{html.escape(tr_genre(g))}</option>' for g in genres)
    return traduire(f'<div id="filtres"><label>Trier <select id="tri"><option value="titre">Titre</option>'
                    f'<option value="ajout">Ajoutés récemment</option><option value="annee">Année (récents)</option>'
                    f'<option value="annee_asc">Année (anciens)</option></select></label>'
                    + (f' <label>Genre <select id="genre"><option value="">Tous</option>{options}</select></label>' if genres else "")
                    + ' <label><input type="checkbox" id="nonvus"> Non vus</label></div>')


def page_serie(nom):
    m = META.get("serie:" + nom) or {}
    r = html.escape(m.get("resume", ""))
    img = f'<img src="{html.escape(m["affiche"])}" alt="">' if m.get("affiche") else ""
    intro = f'<div class="show">{img}<div><h2 id="dt">{html.escape(nom)}</h2><p id="dr">{r}</p></div></div>'
    items = "".join(f'<li data-id="{i}" data-t="{html.escape(nom)} {html.escape(t)}" data-r="{r}"{a}>{html.escape(t)}{x}</li>'
                    for i in ordre("series") for t, d, c in [LIB["series"][i]] if d == nom for a, x in [suivi(c)])
    return intro, items


class Handler(BaseHTTPRequestHandler):
    def autorise(self):
        """Le PC lui-même passe toujours ; les autres appareils doivent avoir donné le PIN (s'il y en a un)."""
        if not ACCES["jeton"] or self.client_address[0] in ("127.0.0.1", "::1"):
            return True
        c = SimpleCookie(self.headers.get("Cookie", ""))
        if "mc" in c and hmac.compare_digest(c["mc"].value, ACCES["jeton"]):
            return True
        q = parse_qs(urlparse(self.path).query).get("mc", [""])[0]  # Chromecast : le code est dans l'adresse
        return bool(q) and hmac.compare_digest(q, ACCES["jeton"])

    def cors(self):
        """Le récepteur Chromecast lit vidéos, listes HLS et sous-titres depuis une autre origine."""
        if re.match(r"/(media|hls|sub)/", urlparse(self.path).path):
            self.send_header("Access-Control-Allow-Origin", "*")

    def page_pin(self, erreur="", code=200):
        corps = traduire(PAGE_PIN).replace("{erreur}", tr(erreur)).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def lire_profil(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        ACTUEL.profil = unquote(c["profil"].value) if "profil" in c else ""

    def do_GET(self):
        self.lire_profil()
        if urlparse(self.path).path in ("/manifest.json", "/icone-192.png", "/icone-512.png"):
            return self.send_file(str(WEB_DIR / urlparse(self.path).path[1:]))  # sans le code : le navigateur les lit sans cookie
        if not self.autorise():
            return self.page_pin() if urlparse(self.path).path == "/" else self.send_error(401)
        self.get_autorise()

    def get_autorise(self):
        url = urlparse(self.path)
        # Seuls les fichiers indexés sont servis (par numéro) : pas de traversée de chemin possible.
        m = re.fullmatch(r"/(media/films|media/series|media/musique|cover)/(\d+)", url.path)
        if m:
            kind, idx = ("musique" if m[1] == "cover" else m[1][6:]), int(m[2])
            if idx >= len(LIB[kind]):
                return self.send_error(404)
            path = LIB[kind][idx][2]
            if m[1] != "cover":
                return self.send_file(path)
            cover = COVERS.get(str(Path(path).parent))
            if cover and Path(cover).suffix.lower() in EXT["musique"]:
                return self.send_bytes(*(pochette_integree(cover) or (b"", "")))
            return self.send_file(cover)
        if url.path == "/hlsjs/hls.light.min.js":
            return self.send_file(str(HLSJS_DIR / "hls.light.min.js"))
        m = re.fullmatch(r"/(lecture|hls)/(films|series)/(\d+)(?:/(index\.m3u8|\d+\.ts))?", url.path)
        if m and int(m[3]) < len(LIB[m[2]]) and (m[1] == "hls") == bool(m[4]):
            chemin = LIB[m[2]][int(m[3])][2]
            if m[1] == "lecture":
                return self.send_bytes(json.dumps({"hls": besoin_conversion(chemin)}).encode(), "application/json")
            besoin_conversion(chemin)
            duree = LECTURE.get(chemin, {}).get("duree", 0)
            if not FFMPEG or duree <= 0:
                return self.send_error(404)
            if m[4] == "index.m3u8":
                mc = parse_qs(url.query).get("mc", [""])[0]
                return self.send_bytes(playlist_hls(duree, f"?mc={quote(mc)}" if mc else "").encode(), "application/vnd.apple.mpegurl")
            k = int(m[4][:-3])
            if k * SEG >= duree:
                return self.send_error(404)
            return self.send_segment(commande_segment(chemin, k))
        m = re.fullmatch(r"/jassub/((?:worker/|wasm/)?[\w.-]+)", url.path)
        if m:
            f = JASSUB_DIR / m[1]
            return self.send_file(str(f) if f.is_file() else None)
        m = re.fullmatch(r"/(audios|audio|audio-etat)/(films|series)/(\d+)(?:/(\d+))?", url.path)
        if m and int(m[3]) < len(LIB[m[2]]) and (m[1] != "audios") == bool(m[4]):
            chemin = LIB[m[2]][int(m[3])][2]
            if m[1] == "audios":
                return self.send_bytes(json.dumps(pistes_audio(chemin), ensure_ascii=False).encode(), "application/json")
            n = int(m[4])
            if not FFMPEG or n >= len(pistes_audio(chemin)):
                return self.send_error(404)
            if m[1] == "audio-etat":  # lance la conversion si besoin ; le navigateur interroge jusqu'à « pret »
                return self.send_bytes(json.dumps({"etat": extraire_audio(chemin, n)}).encode(), "application/json")
            f = fichier_audio(chemin, n)
            return self.send_file(str(f) if f.exists() else None)
        m = re.fullmatch(r"/(pistes|polices|sub|ass|police)/(films|series)/(\d+)(?:/(\d+))?", url.path)
        if m and int(m[3]) < len(LIB[m[2]]) and (m[1] in ("sub", "ass", "police")) == bool(m[4]):
            chemin = LIB[m[2]][int(m[3])][2]
            if m[1] in ("pistes", "polices"):
                liste = infos_pistes(chemin) if m[1] == "pistes" else [
                    f"/police/{m[2]}/{m[3]}/{k}" for k in range(len(polices(chemin)))]
                return self.send_bytes(json.dumps(liste, ensure_ascii=False).encode(), "application/json")
            n = int(m[4])
            if m[1] == "police":
                return self.send_file(polices(chemin)[n] if n < len(polices(chemin)) else None)
            ext, integ = SUBS.get(chemin, []), pistes_integrees(chemin)
            fmt = "ass" if m[1] == "ass" else "webvtt"
            try:
                if n < len(ext):
                    texte = lire_texte(ext[n])
                    if fmt == "ass" and Path(ext[n]).suffix.lower() not in (".ass", ".ssa"):
                        return self.send_error(404)
                elif n - len(ext) < len(integ):
                    if fmt == "ass" and integ[n - len(ext)][2] not in ("ass", "ssa"):
                        return self.send_error(404)
                    texte = extraire_piste(chemin, integ[n - len(ext)][1], fmt)
                else:
                    return self.send_error(404)
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"⚠ Sous-titres illisibles ({Path(chemin).name}) : {e}")
                return self.send_error(404)
            if fmt == "ass":
                return self.send_bytes(texte.encode(), "text/plain; charset=utf-8")
            return self.send_bytes(vers_vtt(texte).encode(), "text/vtt; charset=utf-8")
        m = re.fullmatch(r"/cast/(films|series)/(\d+)", url.path)
        if m and int(m[2]) < len(LIB[m[1]]):
            return self.send_bytes(json.dumps(infos_cast(m[1], int(m[2]))).encode(), "application/json")
        if url.path == "/sauvegarde":  # PC seulement : la config contient le code d'accès
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                return self.send_error(403)
            data = exporter_sauvegarde()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="mediacenter-{time.strftime("%Y-%m-%d")}.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if url.path == "/diagnostic":
            return self.page_simple(html_diagnostic(self.client_address[0] in ("127.0.0.1", "::1")))
        if url.path == "/maj-etat":
            return self.send_bytes(json.dumps({"etat": MAJ.get("etat", "")}).encode(), "application/json")
        if url.path == "/installer-etat":
            return self.send_bytes(json.dumps(INSTALLS).encode(), "application/json")
        if url.path == "/file":
            return self.send_bytes(json.dumps(FILE, ensure_ascii=False).encode(), "application/json")
        if url.path == "/commande":  # relevé par l'appareil qui joue, chaque seconde
            dev = parse_qs(url.query).get("dev", [""])[0][:100]
            with VERROU:
                RELEVE[dev] = time.time()
                liste = COMMANDES.pop(dev, [])
            return self.send_bytes(json.dumps(liste, ensure_ascii=False).encode(), "application/json")
        if url.path == "/video" and pilote_actif():  # mpv / VLC joue sur le PC : la télécommande le pilote
            return self.send_bytes(json.dumps(etat_pilote(), ensure_ascii=False).encode(), "application/json")
        if url.path in ("/encours", "/video"):
            e = etat_public(ENCOURS if url.path == "/encours" else VIDEO, parse_qs(url.query).get("dev", [""])[0])
            return self.send_bytes(json.dumps(e, ensure_ascii=False).encode(), "application/json")
        if url.path != "/":
            return self.send_error(404)
        qs = parse_qs(url.query)
        kind = qs.get("k", ["accueil"])[0]
        kind = kind if kind in LIB else "accueil"
        if kind == "accueil":
            return self.page_accueil()
        intro, grid = '<h2 id="dt"></h2><p id="dr"></p>', kind == "films"
        if kind == "films":
            items = "".join(carte_film(i, *LIB[kind][i][::2]) for i in ordre(kind))
            intro = barre_filtres("films") + intro
        elif kind == "series" and "s" in qs:
            intro, items = page_serie(qs["s"][0])
        elif kind == "series":
            nb = {}
            for _, d, _ in LIB["series"]:
                nb[d] = nb.get(d, 0) + 1
            items, grid = "".join(carte_serie(n, c) for n, c in sorted(nb.items(), key=lambda x: x[0].lower())), True
            intro = barre_filtres("series") + intro
        else:
            premier = {}
            items = "".join(ligne_musique(i, *LIB[kind][i], premier) for i in ordre(kind))
        player = ('<img id="pc" hidden alt=""><audio id="p" controls></audio><button id="pv" class="bt" title="Morceau précédent (ou début du morceau)">⏮ Précédent</button><button id="sv" class="bt" title="Morceau suivant">⏭ Suivant</button><button id="al" class="bt" aria-pressed="false">🔀 Aléatoire</button><button id="rp" class="bt" aria-pressed="false">🔁 Répéter</button>'
                  '<div id="tc" hidden>🎛 <span id="tct"></span><br><button class="bt" data-c="precedent" aria-label="Précédent (à distance)">⏮</button>'
                  '<button class="bt" id="tcpp" aria-label="Lecture / pause (à distance)">⏯</button><button class="bt" data-c="suivant" aria-label="Suivant (à distance)">⏭</button>'
                  ' <label>🔊 <input id="tcv" type="range" min="0" max="100" value="100" aria-label="Volume (à distance)"></label></div>'
                  '<div id="fa" hidden><b>À suivre</b> <button id="fv" class="bt">Vider la file</button><div id="fl"></div></div>') if kind == "musique" else ('<div id="vw"><video id="p" controls controlslist="nofullscreen"></video>'
                                                                                         '<button id="fs" title="Plein écran (double-clic)">⛶</button></div>'
            '<label id="pal" hidden>🔈 Audio <select id="pas" aria-label="Piste audio"></select> <span id="pae"></span></label>'
            '<button id="amp" class="bt" hidden>🔊 Lire sur l’ampli (passthrough)</button>'
            '<button id="cast" class="bt" hidden>📺 Chromecast</button>'
            '<div id="vt" hidden>🎛 <span id="vtt"></span><br><button class="bt" data-v="-10" aria-label="Reculer de 10 secondes">⏪ 10 s</button>'
            '<button class="bt" id="vtpp" aria-label="Lecture / pause (à distance)">⏯</button><button class="bt" data-v="30" aria-label="Avancer de 30 secondes">30 s ⏩</button>'
            + ('<button class="bt" id="vtsv" aria-label="Épisode suivant (à distance)">⏭ Épisode suivant</button>' if kind == "series" else "")
            + ' <label>🔊 <input id="vtv" type="range" min="0" max="100" value="100" aria-label="Volume (à distance)"></label>'
            ' <label id="vtsl" hidden>💬 <select id="vts" aria-label="Sous-titres (à distance)"></select></label>'
            ' <label id="vtal" hidden>🔈 <select id="vta" aria-label="Piste audio (à distance)"></select></label>'
            ' <button class="bt" id="vtamp" hidden>🔊 Sur l’ampli</button></div>')
        taille = taille_cache_audio() if kind != "musique" else 0
        pied = traduire(f'<p id="pied">Pistes audio converties : <span id="ct">{taille / 1e6:.0f} Mo</span> '
                        f'<button class="bt" id="cv">🗑 Vider le cache audio</button></p>' if taille else "")
        player = traduire(player)
        body = gabarit()
        body = body.replace("{accueil}", "").replace("{profils}", html_profils()).replace(
            "{outils}", bandeau_outils() if self.client_address[0] in ("127.0.0.1", "::1") else "")
        for k in LIB:  # compteur des séries = nombre de séries, pas d'épisodes
            n = len({d for _, d, _ in LIB[k]}) if k == "series" else len(LIB[k])
            body = body.replace("{" + k + "}", "on" if k == kind else "").replace("{n" + k + "}", str(n))
        body = (body.replace("{grid}", "grid" if grid else "").replace("{player}", player).replace("{intro}", intro)
                .replace("{items}", items).replace("{kind}", kind).replace("{pied}", pied)
                .replace("{ampli}", Path(LECTEUR[0]).stem if LECTEUR[0] else "").replace("{cast}", "1" if RESEAU[0] else "").replace("{ffmpeg}", "1" if FFMPEG and FFPROBE else "")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def page_accueil(self):
        outils = bandeau_outils() if self.client_address[0] in ("127.0.0.1", "::1") else ""
        return self.page_simple(outils + html_accueil(), "accueil")

    def page_simple(self, contenu, onglet="", script=""):
        """Page sans lecteur (accueil, diagnostic) : en-tête commun + contenu."""
        body = gabarit()[:gabarit().index("<main>")].replace("{accueil}", "on" if onglet == "accueil" else "")
        body = body.replace("{profils}", html_profils())
        for k in LIB:
            n = len({d for _, d, _ in LIB[k]}) if k == "series" else len(LIB[k])
            body = body.replace("{" + k + "}", "").replace("{n" + k + "}", str(n))
        body = (body + "<main>" + contenu + "</main><script>" + script + """
const cartes=[...document.querySelectorAll('.carte')];
q.oninput=()=>{const s=q.value.toLowerCase();cartes.forEach(c=>c.hidden=!c.textContent.toLowerCase().includes(s))};
document.getElementById('rs').onclick=async()=>{await fetch('/rescan',{method:'POST'});location.reload()};
document.getElementById('lg').onclick=async()=>{await fetch('/langue',{method:'POST'});location.reload()};
""" + traduire(NAV_JS) + """</script></html>""").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_segment(self, cmd):
        """Envoie la sortie de ffmpeg au fur et à mesure ; si le navigateur abandonne (avance rapide), ffmpeg est arrêté."""
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.cors()
            self.end_headers()
            while morceau := proc.stdout.read(65536):
                self.wfile.write(morceau)
        except (ConnectionError, BrokenPipeError):
            pass
        finally:
            proc.kill()
            proc.wait()

    def send_bytes(self, data, mime):
        if not data:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.cors()
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path):
        if not path:
            return self.send_error(404)
        try:
            size = os.path.getsize(path)
        except OSError:
            return self.send_error(404)
        start, end = 0, size - 1
        r = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if r and (r[1] or r[2]):  # Range = indispensable pour avancer/reculer dans la vidéo
            if r[1]:
                start, end = int(r[1]), int(r[2]) if r[2] else size - 1
            else:
                start = max(0, size - int(r[2]))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                return self.end_headers()
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.cors()
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionError, BrokenPipeError):
            pass  # le navigateur a coupé (seek / pause) : normal

    def do_POST(self):
        self.lire_profil()
        if urlparse(self.path).path == "/connexion":
            ip = self.client_address[0]
            if trop_d_essais(ip):
                return self.page_pin("Trop d'essais : réessaie dans 5 minutes.", 429)
            n = int(self.headers.get("Content-Length") or 0)
            pin = parse_qs(self.rfile.read(min(n, 1000)).decode(errors="replace")).get("pin", [""])[0]
            if not ACCES["jeton"] or not hmac.compare_digest(jeton_pin(pin, ACCES["sel"]), ACCES["jeton"]):
                noter_echec(ip)
                time.sleep(1)  # ralentit les essais au hasard
                return self.page_pin("Code incorrect.", 403)
            ECHECS.pop(ip, None)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"mc={ACCES['jeton']}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
            return self.end_headers()
        if not self.autorise():
            return self.send_error(401)
        self.post_autorise()

    def post_autorise(self):
        if urlparse(self.path).path == "/externe":  # ouvre le film dans mpv/VLC sur le PC (passthrough vers l'ampli)
            n = int(self.headers.get("Content-Length") or 0)
            if not LECTEUR[0]:
                return self.send_error(404)
            try:
                if n > 2000:
                    raise ValueError("trop gros")
                kind, i, fichier, t, piste = valider_externe(json.loads(self.rfile.read(n)))
                est_mpv = "mpv" in Path(LECTEUR[0]).stem.lower()
                if pilote_actif():
                    fermer_pilote()  # un seul lecteur à la fois
                http = None
                if not est_mpv:  # VLC : interface web locale, port libre et mot de passe au hasard
                    with socket.socket() as so:
                        so.bind(("127.0.0.1", 0))
                        http = (so.getsockname()[1], __import__("secrets").token_urlsafe(16))
                proc = subprocess.Popen(commande_externe(LECTEUR[0], fichier, t, piste, MPV_IPC if est_mpv else None, http),
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        env={**os.environ, "LANGUAGE": "en", "LC_ALL": "C"} if http and os.name != "nt" else None,
                                        start_new_session=os.name != "nt")  # groupe à part : fermé en entier (lanceurs snap/flatpak)
                PILOTE.clear()
                PILOTE.update(type="mpv" if est_mpv else "vlc", proc=proc, kind=kind, id=i, titre=titre_lib(kind, i), aui=piste)
                if http:
                    PILOTE.update(port=http[0], mdp=http[1])
            except (ValueError, KeyError, TypeError) as e:
                return self.send_error(400, str(e))
            except OSError as e:
                print(f"⚠ Lecteur externe impossible à lancer : {e}")
                return self.send_error(500)
            self.send_response(204)
            return self.end_headers()
        if urlparse(self.path).path == "/maj":  # bouton « Mettre à jour » : sur le PC seulement
            if self.client_address[0] not in ("127.0.0.1", "::1") or not MAJ.get("exe"):
                return self.send_error(403)
            MAJ["etat"] = "téléchargement"
            threading.Thread(target=appliquer_maj, daemon=True).start()
            self.send_response(202)
            return self.end_headers()
        m = re.fullmatch(r"/installer/(ffmpeg|vlc)", urlparse(self.path).path)
        if m:  # seulement depuis le PC lui-même : un autre appareil ne peut pas lancer d'installation
            if self.client_address[0] not in ("127.0.0.1", "::1") or not shutil.which("winget"):
                return self.send_error(403)
            with VERROU:
                if INSTALLS.get(m[1]) != "en cours":
                    INSTALLS[m[1]] = "en cours"
                    threading.Thread(target=installer, args=(m[1],), daemon=True).start()
            self.send_response(202)
            return self.end_headers()
        if urlparse(self.path).path == "/profils":  # « ➕ Nouveau profil »
            n = int(self.headers.get("Content-Length") or 0)
            try:
                nom = valider_profil(self.rfile.read(min(n, 200)).decode("utf-8", errors="replace"))
            except ValueError:
                return self.send_error(400)
            with VERROU:
                if nom not in PROFILS:
                    PROFILS.append(nom)
                    cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {}
                    cfg["profils"] = PROFILS
                    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
            self.send_response(204)
            return self.end_headers()
        if urlparse(self.path).path == "/langue":  # bouton 🌐 : bascule français / espagnol (mémorisé)
            LANGUE[0] = "fr" if LANGUE[0] == "es" else "es"
            cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {}
            cfg["langue"] = LANGUE[0]
            CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
            AUDIOS.clear()  # noms des pistes recalculés dans la nouvelle langue
            PISTES.clear()
            self.send_response(204)
            return self.end_headers()
        if urlparse(self.path).path == "/rescan":
            try:
                n = RESCAN[0]()
            except OSError as e:
                return self.send_error(500, str(e))
            return self.send_bytes(json.dumps({"nouveaux": n}).encode(), "application/json")
        if urlparse(self.path).path == "/restaurer":  # import d'une sauvegarde : PC seulement
            n = int(self.headers.get("Content-Length") or 0)
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                return self.send_error(403)
            if not 0 < n <= 300 * 1024 ** 2:
                return self.send_error(413)
            try:
                k = importer_sauvegarde(self.rfile.read(n))
            except (ValueError, zipfile.BadZipFile) as e:
                return self.send_error(400, str(e))
            return self.send_bytes(json.dumps({"fichiers": k}).encode(), "application/json")
        if urlparse(self.path).path == "/cache-audio":
            return self.send_bytes(json.dumps({"octets": vider_cache_audio()}).encode(), "application/json")
        if urlparse(self.path).path == "/video":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                if n > 5000:
                    raise ValueError("trop gros")
                nouveau = valider_video(json.loads(self.rfile.read(n)))
            except (ValueError, KeyError, TypeError):
                return self.send_error(400)
            with VERROU:
                if accepter_encours(VIDEO, nouveau):  # même règle de passage de relais que la musique
                    VIDEO.clear()
                    VIDEO.update(nouveau)
            self.send_response(204)
            return self.end_headers()
        if urlparse(self.path).path == "/commande":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                if n > 5000:
                    raise ValueError("trop gros")
                c = valider_commande(json.loads(self.rfile.read(n)))
            except (ValueError, KeyError, TypeError, AttributeError):
                return self.send_error(400)
            pour_video = parse_qs(urlparse(self.path).query).get("pour", [""])[0] == "video"
            if pour_video and pilote_actif():
                try:
                    commande_pilote(c)
                except (OSError, ValueError, KeyError, IndexError) as e:
                    print(f"⚠ Commande refusée par le lecteur : {e}")
                    return self.send_error(409)
                self.send_response(204)
                return self.end_headers()
            with VERROU:
                cible = (VIDEO if pour_video else ENCOURS).get("dev")
                if not cible or time.time() - RELEVE.get(cible, 0) > 5:
                    return self.send_error(409)  # personne ne joue (ou page fermée)
                COMMANDES.setdefault(cible, []).append(c)
                del COMMANDES[cible][:-20]
            self.send_response(204)
            return self.end_headers()
        if urlparse(self.path).path == "/encours":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                if n > 5000:
                    raise ValueError("trop gros")
                nouveau = valider_encours(json.loads(self.rfile.read(n)))
                with VERROU:
                    if not accepter_encours(ENCOURS, nouveau):
                        self.send_response(204)
                        return self.end_headers()
                    ENCOURS.clear()
                    ENCOURS.update(nouveau)
                    ENCOURS_F.write_text(json.dumps(ENCOURS, ensure_ascii=False), "utf-8")
            except (ValueError, KeyError, TypeError):
                return self.send_error(400)
            self.send_response(204)
            return self.end_headers()
        if urlparse(self.path).path == "/file":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                if n > 2_000_000:
                    raise ValueError("trop gros")
                nouvelle = valider_file(json.loads(self.rfile.read(n)))
                with VERROU:
                    FILE[:] = nouvelle
                    FILE_F.write_text(json.dumps(FILE, ensure_ascii=False), "utf-8")
            except ValueError:
                return self.send_error(400)
            self.send_response(204)
            return self.end_headers()
        m = re.fullmatch(r"/suivi/(films|series)/(\d+)", urlparse(self.path).path)
        n = int(self.headers.get("Content-Length") or 0)
        if not m or n > 1000 or int(m[2]) >= len(LIB[m[1]]):
            return self.send_error(400)
        nom = Path(LIB[m[1]][int(m[2])][2]).name
        try:
            data = json.loads(self.rfile.read(n))
            with VERROU:
                suivi_p = S()
                suivi_p[nom] = {**maj_suivi(suivi_p.get(nom, {}), data), "quand": time.time()}  # « Reprendre » : plus récent d'abord
                fichier_suivi(profil_actif()).write_text(json.dumps(suivi_p, ensure_ascii=False), "utf-8")
        except (ValueError, TypeError, KeyError, AttributeError):
            return self.send_error(400)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description="Media Center : films, séries et musique")
    ap.add_argument("--films", action="append", help="dossier de films (répétable)")
    ap.add_argument("--series", action="append", help="dossier de séries TV (répétable)")
    ap.add_argument("--musique", action="append", help="dossier de musique (répétable)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur au lancement")
    ap.add_argument("--demarrage-auto", choices=("oui", "non"), help="lancer le Media Center à l'ouverture de session Windows")
    ap.add_argument("--reseau", action="store_true", help="accessible depuis la TV/téléphone du réseau local")
    ap.add_argument("--tmdb", metavar="CLE", help="clé TMDB (themoviedb.org) pour de meilleures affiches ; mémorisée")
    ap.add_argument("--lecteur-externe", metavar="CHEMIN",
                    help="mpv.exe ou vlc.exe pour la passthrough vers l'ampli (sinon trouvé tout seul) ; mémorisé")
    ap.add_argument("--cache-audio", type=float, metavar="GO",
                    help="taille max du cache des pistes audio converties, en Go (défaut 5) ; mémorisée")
    ap.add_argument("--langue", choices=("es", "fr"), help="langue de l'interface (par défaut celle de Windows) ; mémorisée")
    ap.add_argument("--pin", metavar="CODE", help="code demandé aux autres appareils (TV, téléphone) ; « aucun » pour l'enlever ; mémorisé")
    ap.add_argument("--hors-ligne", action="store_true", help="ne pas chercher les affiches sur internet")
    a = ap.parse_args()

    if a.demarrage_auto:
        if os.name != "nt":
            sys.exit("--demarrage-auto : seulement sous Windows.")
        demarrage_auto(a.demarrage_auto == "oui")
        print(f"Démarrage avec Windows : {a.demarrage_auto}.")
    cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {}
    nouveau = {"films": a.films, "series": a.series, "musique": a.musique, "tmdb": a.tmdb, "cache_audio": a.cache_audio,
               "lecteur_externe": a.lecteur_externe, "pin": a.pin, "langue": a.langue}
    if any(nouveau.values()):
        cfg.update({k: v for k, v in nouveau.items() if v})
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    CFG.update(cfg)
    LANGUE[0] = cfg.get("langue") or langue_systeme()
    dossiers = {k: cfg.get(k, []) for k in LIB}
    if not any(dossiers.values()) and sys.stdin and sys.stdin.isatty():  # 1er lancement (double-clic sur le .exe)
        print("Premier lancement : indique tes dossiers (copier-coller le chemin, ou Entrée pour passer).")
        for k, nom in (("films", "films"), ("series", "séries TV"), ("musique", "musique")):
            d = input(f"  Dossier de {nom} : ").strip().strip('"')
            if d:
                cfg[k] = dossiers[k] = [d]
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    elif not any(dossiers.values()) and GELE and (sys.stdin is None or not sys.stdin.isatty()):  # .exe sans console
        demander_dossiers_fenetre(cfg, dossiers)
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    if not any(dossiers.values()):
        sys.exit('Indique tes dossiers : MediaCenter --films "D:\\Films" --series "D:\\Series" --musique "D:\\Musique"')
    for d in sum(dossiers.values(), []):
        if not Path(d).is_dir():
            print(f"⚠ Dossier introuvable : {d}")

    charger_etat()
    LECTEUR[0] = trouver_lecteur(cfg.get("lecteur_externe"))
    if cfg.get("lecteur_externe") and not LECTEUR[0]:
        print(f"⚠ Lecteur externe introuvable : {cfg['lecteur_externe']}")
    CACHE_AUDIO_MAX[0] = int(max(0.1, cfg.get("cache_audio") or 5) * 1024 ** 3)
    nettoyer_cache_audio(CACHE_AUDIO_MAX[0], demarrage=True)
    nettoyer_polices()
    scan(dossiers)
    print(f"{len(LIB['films'])} films, {len(LIB['series'])} épisodes, {len(LIB['musique'])} morceaux trouvés.")
    if not (FFMPEG and FFPROBE) and any(c.lower().endswith(".mkv") for k in ("films", "series") for _, _, c in LIB[k]):
        print("ℹ Pour les sous-titres intégrés aux MKV, installe ffmpeg (Windows : winget install ffmpeg) puis relance.")
    if not a.hors_ligne:
        threading.Thread(target=enrichir, args=(cfg.get("tmdb"),), daemon=True).start()
    threading.Thread(target=surveiller, args=(dossiers, not a.hors_ligne, cfg.get("tmdb")), daemon=True).start()
    threading.Thread(target=surveiller_maj, daemon=True).start()
    RESCAN[0] = lambda: scan(dossiers)
    if cfg.get("pin") and cfg["pin"] != "aucun":
        cfg.setdefault("sel", __import__("secrets").token_hex(8))
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
        ACCES.update(jeton=jeton_pin(cfg["pin"], cfg["sel"]), sel=cfg["sel"])
    elif a.reseau:
        print("ℹ Accès réseau sans code : n'importe qui sur ton Wi-Fi peut ouvrir le Media Center. Ajoute --pin 1234 pour en demander un.")
    RESEAU[0], PORT[0] = a.reseau, a.port
    host = "0.0.0.0" if a.reseau else "127.0.0.1"
    url = f"http://localhost:{a.port}/"
    try:
        serveur = Serveur((host, a.port), Handler)
    except OSError:  # déjà lancé (2e double-clic) : on ouvre simplement le navigateur dessus
        print(f"Le Media Center tourne déjà : ouverture de {url}")
        if not a.sans_navigateur:
            webbrowser.open(url)
        return
    print(f"Ouvre {url}  (Ctrl+C ou « Quitter » près de l'horloge pour arrêter)")
    if not a.sans_navigateur:
        threading.Timer(1, webbrowser.open, [url]).start()
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        if not icone_barre(url):  # sans icône (Python lancé à la main) : comme avant, Ctrl+C pour quitter
            while fil.is_alive():
                fil.join(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:  # .exe sans console : les messages vont dans mediacenter.log
        journal = BASE / "mediacenter.log"
        if journal.exists() and journal.stat().st_size > 1_000_000:
            journal.unlink()
        sys.stdout = sys.stderr = open(journal, "a", encoding="utf-8", buffering=1)
        print(f"--- {time.strftime('%Y-%m-%d %H:%M')}")
    try:
        sys.stdout.reconfigure(errors="replace")  # console Windows sans emoji : pas de plantage sur « ⚠ »
    except (AttributeError, ValueError):
        pass
    try:
        main()
    except SystemExit as e:
        if GELE and e.code not in (0, None):  # .exe : afficher le message avant de fermer
            message_erreur(str(e.code))
            raise SystemExit(1)
        raise
