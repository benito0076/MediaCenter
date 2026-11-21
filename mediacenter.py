#!/usr/bin/env python3
"""Media Center minimaliste : films, séries + musique dans le navigateur. Python 3.8+, zéro dépendance.

Usage :  python mediacenter.py --films "D:\\Films" --series "D:\\Series" --musique "D:\\Musique"
Les dossiers sont mémorisés dans mediacenter.json ; ensuite `python mediacenter.py` suffit.
Affiches et résumés : TMDB si une clé est donnée (--tmdb CLE), sinon iTunes ; gardés dans mediacenter_cache.json.
"""
import argparse, hashlib, html, json, math, mimetypes, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, quote
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
SUIVI = {}  # nom de fichier vidéo -> {"t": position (s), "d": durée (s), "vu": bool}
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
JASSUB_DIR = RESSOURCES / "jassub"  # rendu stylé des .ass (libass en WebAssembly), servi en local
POLICES_DIR = BASE / "polices_cache"  # polices extraites des MKV
POLICES = {}  # chemin vidéo -> [fichiers de police]
AUDIO_DIR = BASE / "audio_cache"  # pistes audio converties pour le navigateur (AAC, stéréo ou 5.1)
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
LANGUES = {"fre": "Français", "fra": "Français", "fr": "Français", "eng": "Anglais", "en": "Anglais",
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
    return re.sub(r"[._\-]+", " ", stem).strip() or "Sous-titres"


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


def nom_piste(flux):
    """Flux ffprobe -> 'Français – Forced'"""
    tags = {k.lower(): v for k, v in flux.get("tags", {}).items()}
    lang = tags.get("language", "")
    return " – ".join(x for x in (LANGUES.get(lang, "" if lang == "und" else lang), tags.get("title", "")) if x) or "Intégrés"


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
        AUDIOS[chemin] = [{"nom": f"{k + 1}. " + nom_piste(f).replace("Intégrés", "Piste")
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
            "affiche": r.get("artworkUrl100", "").replace("100x100", "600x600")}


def choisir_tmdb(resultats, annee, champ="release_date"):  # séries : champ="first_air_date"
    if not resultats:
        return {}
    r = meilleur(resultats, annee, champ)
    return {"titre": r.get("title") or r.get("name", ""), "annee": (r.get(champ) or "")[:4], "resume": r.get("overview", ""),
            "affiche": "https://image.tmdb.org/t/p/w500" + r["poster_path"] if r.get("poster_path") else "",
            "source": "tmdb"}


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
    manquants = [x for x in a_faire if x[0] not in META or (cle and META[x[0]].get("source") != "tmdb")]
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
    e = SUIVI.get(Path(chemin).name, {})
    pct = min(100, int(100 * e["t"] / e["d"])) if e.get("t") and e.get("d") else 0
    attrs = f' data-pos="{e.get("t", 0)}"' + (' class="vu"' if e.get("vu") else "")
    return attrs, (f'<i class="bar" style="width:{pct}%"></i>' if pct else "") + '<b class="ck" title="Vu / pas vu">✓</b>'


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


PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Center</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#111;color:#eee}
header{position:sticky;top:0;z-index:1;background:#1b1b1b;padding:12px 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
a.tab{color:#aaa;text-decoration:none;padding:6px 12px;border-radius:6px}a.tab.on{background:#e50914;color:#fff}
input{flex:1;min-width:160px;padding:8px;border-radius:6px;border:0;background:#2a2a2a;color:#eee}
main{padding:16px}video,audio{width:100%;max-height:70vh;background:#000;border-radius:8px}video:not([src]){display:none}
video.ass::cue{color:transparent;background:transparent;text-shadow:none}
#vw{position:relative}#vw:fullscreen{background:#000;display:flex;align-items:center;justify-content:center}
#vw:fullscreen video{max-height:100vh;height:100%;border-radius:0}
#fs{position:absolute;top:8px;right:8px;background:#000a;color:#fff;border:0;border-radius:6px;font-size:18px;padding:2px 8px;cursor:pointer}
video:not([src])~#fs{display:none}
#dr{color:#bbb;max-width:80ch;line-height:1.5}
ul{list-style:none;padding:0}li{padding:10px;border-bottom:1px solid #222;cursor:pointer}
li:hover,li.on{background:#222}small{color:#888;margin-left:8px}
ul.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:16px}
ul.grid li{border:0;padding:6px;border-radius:8px}ul.grid small{display:block;margin:0}
[hidden]{display:none!important}
li{position:relative}.bar{position:absolute;left:0;bottom:0;height:3px;background:#e50914}
.ck{margin-left:auto;padding:0 8px;opacity:.25;cursor:pointer}li.vu .ck{opacity:1;color:#4caf50}li.vu{color:#999}
ul.grid .ck{position:absolute;top:12px;right:12px;background:#000b;border-radius:50%;padding:2px 7px}
ul:not(.grid) li{display:flex;align-items:center;gap:12px}
ul:not(.grid) img,ul:not(.grid) .ph{width:48px;height:48px;aspect-ratio:auto;font-size:20px;margin:0;flex:none}
.bt{margin:8px 6px 0 0;padding:6px 12px;border:0;border-radius:6px;background:#2a2a2a;color:#aaa;cursor:pointer}
#sv,#pv{color:#eee}
.qn+.qa{margin-left:0}.qn,.qa,.fi button{margin-left:auto;background:none;border:0;color:#888;font-size:20px;padding:0 10px;cursor:pointer}.qn:hover,.qa:hover,.fi button:hover{color:#fff}
#vt{margin:12px 0;padding:8px 12px;background:#2a1215;border:1px solid #e50914;border-radius:8px}#vt label{white-space:nowrap}
#vtv{vertical-align:middle;width:140px;accent-color:#e50914}
#amp{margin-top:8px}#pal{display:block;margin-top:8px;color:#aaa}#pae{color:#e50914}
#pied{margin-top:32px;color:#777;font-size:14px}#pied .bt{margin-left:8px}
#vts,#vta,#pas{background:#2a2a2a;color:#eee;border:0;border-radius:6px;padding:4px 6px;max-width:200px}
#tc{margin:12px 0;padding:8px 12px;background:#2a1215;border:1px solid #e50914;border-radius:8px}#tc .bt{font-size:18px}#tc label{white-space:nowrap}#tcv{vertical-align:middle;width:140px;accent-color:#e50914}
#fa{margin:12px 0;padding:8px 12px;background:#1b1b1b;border-radius:8px}#fa .bt{margin:0 0 0 8px;padding:2px 8px}
.fi{display:flex;align-items:center;padding:6px 0;cursor:grab;border-top:1px solid #262626}.fi:hover{color:#fff}
.fi button+button{margin-left:0}.fi.glisse{opacity:.4}.fi.cible{border-top:2px solid #e50914}.bt[aria-pressed=true]{background:#e50914;color:#fff}
#pc{width:220px;height:220px;object-fit:cover;border-radius:8px;display:block;margin-bottom:12px}
ul.grid img,.show{display:flex;gap:16px;align-items:flex-start;margin:16px 0}.show img{width:140px;border-radius:6px;flex:none}
.ph{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:6px;background:#222;
 display:flex;align-items:center;justify-content:center;font-size:40px;margin-bottom:6px}
</style>
<header><b>🎬 Media Center</b>
<a class="tab {films}" href="/?k=films">Films ({nfilms})</a><a class="tab {series}" href="/?k=series">Séries ({nseries})</a>
<a class="tab {musique}" href="/?k=musique">Musique ({nmusique})</a>
<input id="q" placeholder="Rechercher…" autofocus><button class="bt" id="rs" title="Chercher les nouveaux fichiers" aria-label="Actualiser la bibliothèque">🔄</button></header>
<main>{player}{intro}<ul id="l" class="{grid}">{items}</ul>{pied}</main>
<script>
const p=document.getElementById('p'),lis=[...document.querySelectorAll('li')];let cur=-1;
const vid='{kind}'!=='musique';let last=0,proprio=false,geste=0;const APPAREIL=Math.random().toString(36).slice(2);  // proprio : cet appareil joue (ou a joué) le morceau en cours
function envoi(l,data){navigator.sendBeacon('/suivi/{kind}/'+l.dataset.id,JSON.stringify(data))}
function save(){if(!vid){if(cur>=0&&proprio)navigator.sendBeacon('/encours',  // musique : morceau en cours, commun aux appareils
  JSON.stringify({k:lis[cur].dataset.k,t:p.currentTime||0,lecture:!p.paused,dev:APPAREIL,vol:p.volume}));return}
 if(window.etatVideo)etatVideo();  // télécommande : position toutes les 10 s
 if(cur<0||!(p.currentTime>1))return;const l=lis[cur];envoi(l,{t:p.currentTime,d:p.duration||0});
 l.dataset.pos=p.currentTime;if(p.duration&&p.currentTime>.9*p.duration){l.classList.add('vu');l.dataset.pos=0}}
p.ontimeupdate=()=>{if(Math.abs(p.currentTime-last)>10){last=p.currentTime;save()}};
p.onpause=save;addEventListener('pagehide',save);
document.querySelectorAll('.ck').forEach(b=>b.onclick=e=>{e.stopPropagation();const l=b.closest('li'),v=!l.classList.contains('vu');
 l.classList.toggle('vu',v);l.dataset.pos=0;const bar=l.querySelector('.bar');if(bar)bar.remove();envoi(l,{vu:v})});
function play(i,auto=true){if(i<0||i>=lis.length)return;save();lis.forEach(l=>l.classList.remove('on'));
 cur=i;const l=lis[i];l.classList.add('on');last=+l.dataset.pos||0;
 if(vid&&last>5)p.addEventListener('loadedmetadata',()=>p.currentTime=last,{once:true});  // reprise
 p.src='/media/{kind}/'+l.dataset.id;
 p.querySelectorAll('track').forEach(t=>t.remove());
 assOff();if(window.audioReset)audioReset(l);{const a=document.getElementById('amp');if(a)a.hidden=!AMPLI}
 if(vid)fetch('/pistes/{kind}/'+l.dataset.id).then(r=>r.json()).then(st=>{if(lis[cur]!==l)return;  // déjà passé à une autre vidéo
  const choix=Math.max(0,st.findIndex(s=>/fr|vf/i.test(s.nom)));  // français de préférence
  st.forEach((s,n)=>{const t=document.createElement('track');
   Object.assign(t,{kind:'subtitles',label:s.nom,default:n===choix,src:'/sub/{kind}/'+l.dataset.id+'/'+n});
   if(s.ass)t.dataset.ass='/ass/{kind}/'+l.dataset.id+'/'+n;p.appendChild(t)});setTimeout(majAss,300)});
 if(auto)p.play().catch(()=>{});  // interrompu par un changement de morceau : normal
 document.title=dt.textContent=l.dataset.t;dr.textContent=l.dataset.r||'';
 const pc=document.getElementById('pc');if(pc){pc.src=l.dataset.img||'';pc.hidden=!l.dataset.img}window.scrollTo(0,0)}
document.getElementById('rs').onclick=async e=>{const b=e.currentTarget;b.disabled=true;b.textContent='⏳';
 try{const r=await (await fetch('/rescan',{method:'POST'})).json();if(r.nouveaux)location.reload();else{b.textContent='✓';setTimeout(()=>{b.textContent='🔄';b.disabled=false},1500)}}
 catch(x){b.textContent='🔄';b.disabled=false}};
// Sous-titres .ass : rendu stylé par JASSUB par-dessus la vidéo ; la piste WebVTT simple reste en secours.
let jas=null,assUrl=null;
function assOff(){assUrl=null;if(jas){jas.destroy();jas=null}p.classList.remove('ass')}
async function majAss(){const t=[...p.querySelectorAll('track')].find(t=>t.track.mode==='showing'),url=t&&t.dataset.ass||null;
 if(url===assUrl)return;assOff();if(!url)return;assUrl=url;p.classList.add('ass');
 try{const id=lis[cur].dataset.id,[{default:JASSUB},fonts]=await Promise.all([import('/jassub/jassub.js'),
   fetch('/polices/{kind}/'+id).then(r=>r.json())]);
  if(assUrl!==url)return;
  jas=new JASSUB({video:p,subUrl:url,fonts,wasmUrl:'/jassub/wasm/jassub-worker-modern.wasm',
   wasmWorkerUrl:'/jassub/wasm/jassub-worker-modern.js'});await jas.ready}
 catch(e){console.warn('Rendu .ass indisponible, sous-titres simples :',e);if(assUrl===url){jas=null;p.classList.remove('ass')}}}
if(vid){p.textTracks.onchange=majAss;const vw=document.getElementById('vw'),
 fs=()=>document.fullscreenElement?document.exitFullscreen():vw.requestFullscreen();  // plein écran avec les sous-titres stylés
 document.getElementById('fs').onclick=fs;p.ondblclick=fs}
let distant=false;  // télécommande : un autre appareil joue, les clics le pilotent
function commande(cmd,k,pour,v){fetch('/commande'+(pour?'?pour='+pour:''),{method:'POST',body:JSON.stringify({cmd,k,v})}).catch(()=>{})}
let vdistant=false;  // télécommande vidéo : un autre appareil joue un film/épisode de cette même page
lis.forEach((l,i)=>l.onclick=()=>l.dataset.href?location.href=l.dataset.href:distant?commande('jouer',l.dataset.k)
 :vdistant?commande('jouer',l.dataset.id,'video'):play(i));
// ---- Pistes audio : le navigateur ne sait pas changer de piste ; une autre piste est convertie une fois par le PC (ffmpeg)
// puis jouée dans un lecteur audio caché, synchronisé avec l'image (le son d'origine de la vidéo est coupé).
if(vid){const pa=new Audio(),pas=document.getElementById('pas'),pal=document.getElementById('pal'),pae=document.getElementById('pae');
 let paActif=false,volPrec=1,demande=0,auListe=[];window.audioIdx=0;
 window.audioNoms=()=>auListe.map(a=>a.nom);
 const sync=()=>{if(paActif&&Math.abs(pa.currentTime-p.currentTime)>0.25)pa.currentTime=p.currentTime};
 p.addEventListener('play',()=>{if(paActif){sync();pa.play().catch(()=>{})}});
 for(const ev of ['pause','waiting'])p.addEventListener(ev,()=>{if(paActif)pa.pause()});
 p.addEventListener('playing',()=>{if(paActif){sync();pa.play().catch(()=>{})}});
 p.addEventListener('seeked',sync);p.addEventListener('ratechange',()=>{pa.playbackRate=p.playbackRate});
 setInterval(()=>{if(paActif&&!p.paused)sync()},1000);  // rattrape la dérive
 // Son d'origine coupé (p.muted) : le volume et le bouton muet du lecteur pilotent la piste convertie.
 p.addEventListener('volumechange',()=>{if(!paActif)return;if(!p.muted){if(p.volume!==volPrec)pa.muted=false;else pa.muted=!pa.muted;p.muted=true}
  pa.volume=volPrec=p.volume});
 function natif(){paActif=false;pa.pause();pa.removeAttribute('src');pa.load();p.muted=false}
 window.choisirAudio=async n=>{const l=lis[cur],id=l.dataset.id,jeton=++demande;audioIdx=n;pas.value=String(n);pae.textContent='';
  if(window.etatVideo)etatVideo();
  if(n===0&&!(auListe[0]||{}).convertir)return natif();  // piste d'origine lisible : rien à faire
  pae.textContent='préparation de la piste… (jusqu’à une minute la première fois)';
  for(;;){let e;try{e=(await (await fetch('/audio-etat/{kind}/'+id+'/'+n)).json()).etat}catch(x){e='erreur réseau'}
   if(jeton!==demande)return;if(e==='pret')break;if(e!=='en cours'){pae.textContent=e;return}await new Promise(r=>setTimeout(r,2000))}
  pa.src='/audio/{kind}/'+id+'/'+n;pa.volume=volPrec=p.volume;pa.muted=false;
  await new Promise(r=>pa.addEventListener('loadedmetadata',r,{once:true}));if(jeton!==demande)return;
  paActif=true;p.muted=true;pae.textContent='';sync();if(!p.paused)pa.play().catch(()=>{})};
 pas.onchange=()=>choisirAudio(+pas.value);
 window.audioReset=async l=>{demande++;natif();auListe=[];audioIdx=0;pal.hidden=true;pae.textContent='';
  try{auListe=await (await fetch('/audios/{kind}/'+l.dataset.id)).json()}catch(e){}if(lis[cur]!==l)return;
  pas.replaceChildren(...auListe.map((a,j)=>{const o=document.createElement('option');o.value=String(j);
   o.textContent=a.nom+(a.convertir?' – convertie':'');return o}));
  pal.hidden=auListe.length<2&&!(auListe[0]||{}).convertir;
  if((auListe[0]||{}).convertir)choisirAudio(0);  // son illisible par le navigateur (AC3, DTS…) : converti d'office
  if(window.etatVideo)etatVideo()}}
{const cv=document.getElementById('cv');if(cv)cv.onclick=async()=>{
 if(!confirm('Supprimer les pistes audio converties ? Elles seront reconverties si tu les rechoisis.'))return;
 try{const r=await (await fetch('/cache-audio',{method:'POST'})).json();
  document.getElementById('ct').textContent=Math.round(r.octets/1e6)+' Mo'+(r.octets?' (piste en cours d’écoute gardée)':'');cv.disabled=true}catch(e){}}}
// ---- Passthrough : le navigateur décode toujours le son ; mpv/VLC sur le PC l'envoie tel quel (Dolby/DTS) à l'ampli.
const AMPLI='{ampli}';
async function versAmpli(kind,id,t,piste,ici){const r=await fetch('/externe',{method:'POST',body:JSON.stringify({kind,id,t,piste})});
 if(!r.ok)return alert('Impossible d’ouvrir le lecteur '+AMPLI+' sur le PC.');if(ici)p.pause();else commande('pause','','video')}
if(vid&&AMPLI){document.getElementById('amp').title='Ouvre ce film dans '+AMPLI+' sur le PC, à la même position';
 document.getElementById('amp').onclick=()=>versAmpli('{kind}',+lis[cur].dataset.id,p.currentTime,window.audioIdx||0,true)}
// ---- Films / séries : l'appareil qui joue publie son état et exécute les ordres ; les autres affichent la télécommande.
if(vid){let vproprio=false,vtTouche=0,vtEnvoi=0,volV;
 const vt=document.getElementById('vt'),vtpp=document.getElementById('vtpp'),vtv=document.getElementById('vtv'),
  hms=s=>{s=Math.max(0,Math.floor(s));const h=Math.floor(s/3600),m=Math.floor(s/60)%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(s%60).padStart(2,'0')};
 window.etatVideo=()=>{if(!vproprio||cur<0)return;navigator.sendBeacon('/video',JSON.stringify({kind:'{kind}',id:+lis[cur].dataset.id,
  titre:lis[cur].dataset.t,t:p.currentTime||0,d:p.duration||0,lecture:!p.paused,vol:p.volume,page:location.search,dev:APPAREIL,
  st:[...p.textTracks].map(t=>t.label),sti:[...p.textTracks].findIndex(t=>t.mode==='showing'),au:audioNoms(),aui:audioIdx}))};
 p.textTracks.addEventListener('change',()=>etatVideo());p.textTracks.addEventListener('addtrack',()=>setTimeout(etatVideo,400));
 p.addEventListener('play',()=>{vproprio=true;etatVideo()});for(const ev of ['pause','seeked','loadedmetadata'])p.addEventListener(ev,()=>etatVideo());  // loadedmetadata : durée connue
 p.addEventListener('volumechange',()=>{clearTimeout(volV);volV=setTimeout(etatVideo,300)});
 setInterval(async()=>{if(!vproprio)return;try{for(const c of await (await fetch('/commande?dev='+APPAREIL)).json()){
  if(c.cmd==='lecture')p.play().catch(()=>{});else if(c.cmd==='pause')p.pause();else if(c.cmd==='volume')p.volume=c.v;
  else if(c.cmd==='deplacer')p.currentTime=Math.max(0,Math.min(p.duration||1e9,p.currentTime+c.v));
  else if(c.cmd==='audio'&&c.v<audioNoms().length)choisirAudio(c.v);
  else if(c.cmd==='soustitres')[...p.textTracks].forEach((t,j)=>t.mode=j===c.v?'showing':'disabled');  // déclenche aussi le rendu .ass
  else if(c.cmd==='suivant')suivant();else if(c.cmd==='jouer'){const i=lis.findIndex(l=>l.dataset.id===c.k);if(i>=0)play(i)}}}catch(e){}},1000);
 vt.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>commande('deplacer','','video',+b.dataset.v));
 const vtsv=document.getElementById('vtsv');if(vtsv)vtsv.onclick=()=>commande('suivant','','video');
 const envoyerVolV=()=>{vtTouche=Date.now();if(Date.now()-vtEnvoi>200){vtEnvoi=Date.now();commande('volume','','video',vtv.value/100)}};
 vtv.oninput=envoyerVolV;vtv.onchange=()=>{vtEnvoi=0;envoyerVolV()};
 const vts=document.getElementById('vts'),vtsl=document.getElementById('vtsl');let vtsListe='',vtsTouche=0;
 vts.onchange=()=>{vtsTouche=Date.now();commande('soustitres','','video',+vts.value)};
 const vta=document.getElementById('vta'),vtal=document.getElementById('vtal');let vtaListe='',vtaTouche=0;
 vta.onchange=()=>{vtaTouche=Date.now();commande('audio','','video',+vta.value)};
 const vtamp=document.getElementById('vtamp');let dernierEtat=null;
 vtamp.onclick=()=>{const e=dernierEtat;if(e)versAmpli(e.kind,e.id,e.t+(e.lecture&&e.age<30?e.age:0),e.aui||0,false)};
 async function suivreVideo(){try{const e=await (await fetch('/video?dev='+APPAREIL)).json();
  const visible=!!(e.titre&&!e.moi&&e.joignable&&p.paused);vt.hidden=!visible;vdistant=visible&&(e.page===location.search||e.page==='*')&&e.kind==='{kind}';  // * : mpv
  if(!visible)return;const t=e.t+(e.lecture&&e.age<30?e.age:0);
  document.getElementById('vtt').textContent='Sur un autre appareil : '+e.titre+' — '+hms(Math.min(t,e.d||t))+(e.d?' / '+hms(e.d):'')+(e.lecture?'':' (pause)');
  // État inversé tout de suite au clic : deux appuis rapides ne renvoient pas deux fois le même ordre.
  let lect=e.lecture;vtpp.textContent=lect?'⏸':'▶';vtpp.onclick=()=>{commande(lect?'pause':'lecture','','video');lect=!lect;vtpp.textContent=lect?'⏸':'▶'};
  dernierEtat=e;vtamp.hidden=!AMPLI||!!e.mpv;
  if(Date.now()-vtTouche>3000)vtv.value=Math.round((e.vol??1)*100);
  const st=e.st||[],cle=JSON.stringify(st);vtsl.hidden=!st.length;
  if(cle!==vtsListe){vtsListe=cle;vts.replaceChildren(...[['-1','Sans sous-titres'],...st.map((n,j)=>[String(j),n])].map(([v,n])=>{
   const o=document.createElement('option');o.value=v;o.textContent=n;return o}))}
  if(Date.now()-vtsTouche>3000)vts.value=String(e.sti??-1);
  const au=e.au||[],cleA=JSON.stringify(au);vtal.hidden=au.length<2;
  if(cleA!==vtaListe){vtaListe=cleA;vta.replaceChildren(...au.map((n,j)=>{const o=document.createElement('option');o.value=String(j);o.textContent=n;return o}))}
  if(Date.now()-vtaTouche>3000)vta.value=String(e.aui??0)}catch(e){}}
 suivreVideo();setInterval(suivreVideo,2000)}
// Musique : aléatoire (chaque morceau visible une fois) ; bouton répéter : non → tout → un seul morceau → non.
const al=document.getElementById('al'),rp=document.getElementById('rp');let alea=false,repete=0,joues=new Set(),hist=[];  // hist : morceaux joués en aléatoire, pour « précédent »
try{alea=localStorage.getItem('alea')==='1';repete=Math.min(2,+localStorage.getItem('repete')||0)}catch(e){}
const REPETE=['🔁 Répéter','🔁 Répéter tout','🔂 Répéter 1'];
function majRepete(){rp.textContent=REPETE[repete];rp.setAttribute('aria-pressed',repete>0);p.loop=repete===2;  // boucle native
 try{localStorage.setItem('repete',repete)}catch(e){}}
const visibles=()=>lis.map((_,i)=>i).filter(i=>!lis[i].hidden);
function hasard(){if(cur>=0)joues.add(cur);let v=visibles().filter(i=>!joues.has(i));
 if(!v.length){joues.clear();if(!repete)return -1;v=visibles().filter(i=>i!==cur||lis.length===1)}  // nouveau tour, sans rejouer le même
 return v.length?v[Math.floor(Math.random()*v.length)]:-1}
function bascule(b,cle,val){b.setAttribute('aria-pressed',val);try{localStorage.setItem(cle,val?'1':'0')}catch(e){}}
if(al){al.setAttribute('aria-pressed',alea);majRepete();
 al.onclick=()=>{alea=!alea;bascule(al,'alea',alea);joues.clear();hist=[];if(alea&&p.paused)play(hasard())};
 rp.onclick=()=>{repete=(repete+1)%3;majRepete()}}
// File d'attente : les morceaux ajoutés avec « + » passent avant la suite normale (ou aléatoire).
let file=[];const fa=document.getElementById('fa'),fl=document.getElementById('fl');
let glisse=null,derniere=null;
function deplacer(a,b){if(a==null||a===b||b<0||b>=file.length)return;file.splice(b,0,file.splice(a,1)[0]);majFile()}
function bouton(txt,titre,fn){const x=document.createElement('button');x.textContent=txt;x.title=x.ariaLabel=titre;
 x.onclick=e=>{e.stopPropagation();fn()};return x}
function majFile(envoyer=true){fa.hidden=!file.length;fl.replaceChildren(...file.map((i,k)=>{const d=document.createElement('div');
  d.className='fi';d.textContent=(k+1)+'. '+lis[i].dataset.t;d.onclick=()=>{file.splice(k,1);majFile();play(i)};
  // Glisser-déposer pour réorganiser ; ↑ ↓ pour le clavier et les écrans tactiles.
  d.draggable=true;d.ondragstart=e=>{glisse=k;d.classList.add('glisse');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',k)};
  d.ondragend=()=>{glisse=null;d.classList.remove('glisse')};
  d.ondragover=e=>{e.preventDefault();d.classList.add('cible')};d.ondragleave=()=>d.classList.remove('cible');
  d.ondrop=e=>{e.preventDefault();d.classList.remove('cible');deplacer(glisse,k)};
  d.append(bouton('↑','Monter',()=>deplacer(k,k-1)),bouton('↓','Descendre',()=>deplacer(k,k+1)),
   bouton('×','Retirer de la file',()=>{file.splice(k,1);majFile()}));return d}));
 if(envoyer){derniere=JSON.stringify(file.map(i=>lis[i].dataset.k));  // sauvegarde sur le PC, commune à tous les appareils
  fetch('/file',{method:'POST',body:derniere,keepalive:true}).catch(()=>{})}}
if(fa){document.querySelectorAll('.qa').forEach(b=>b.onclick=e=>{e.stopPropagation();file.push(+b.closest('li').dataset.id);majFile()});
 document.querySelectorAll('.qn').forEach(b=>b.onclick=e=>{e.stopPropagation();file.unshift(+b.closest('li').dataset.id);majFile()});
 document.getElementById('fv').onclick=()=>{file=[];majFile()};
 // File commune : relue sur le PC toutes les 5 s (identifiants stables ; morceaux disparus ignorés).
 // ponytail: le dernier qui écrit gagne ; deux appareils modifiant la file dans la même seconde peuvent s'écraser.
 const parK=new Map(lis.map((l,i)=>[l.dataset.k,i]));
 async function chargerFile(){try{const ks=await (await fetch('/file')).json(),j=JSON.stringify(ks);
  if(j===derniere||glisse!==null)return;derniere=j;file=ks.map(k=>parK.get(k)).filter(i=>i!==undefined);majFile(false)}catch(e){}}
 chargerFile();setInterval(chargerFile,5000);
 // Morceau en cours commun : un appareil à l'arrêt suit ce que joue un autre (même morceau, même position, en pause) ;
 // appuyer sur ▶ reprend alors la lecture ici. Les navigateurs interdisent de lancer le son tout seul.
 p.addEventListener('play',()=>{proprio=true;save()});
 for(const ev of ['pointerdown','keydown'])p.addEventListener(ev,()=>{geste=Date.now()});  // curseur déplacé à la main
 const tc=document.getElementById('tc'),tcpp=document.getElementById('tcpp');
 async function suivreEncours(){try{const e=await (await fetch('/encours?dev='+APPAREIL)).json(),i=parK.get(e.k);
  // Télécommande visible si un autre appareil, page ouverte, a le morceau en cours et que celui-ci ne joue pas ici.
  distant=!!(e.k&&!e.moi&&e.joignable&&p.paused);tc.hidden=!distant;
  if(distant&&i!==undefined){document.getElementById('tct').textContent='Sur un autre appareil : '+lis[i].dataset.t+(e.lecture?' (lecture)':' (pause)');
   let lect=e.lecture;tcpp.textContent=lect?'⏸':'▶';tcpp.onclick=()=>{commande(lect?'pause':'lecture');lect=!lect;tcpp.textContent=lect?'⏸':'▶'};
   if(Date.now()-tcvTouche>3000)tcv.value=Math.round((e.vol??1)*100)}  // pas pendant qu'on bouge le curseur
  if(!p.paused||Date.now()-geste<15000||i===undefined)return;const t=e.t+(e.lecture&&e.age<30?e.age:0);  // > 30 s sans nouvelles : appareil éteint
  if(i===cur&&Math.abs(p.currentTime-t)<3)return;proprio=false;
  if(i!==cur){p.addEventListener('loadedmetadata',()=>{p.currentTime=t},{once:true});play(i,false)}else p.currentTime=t}catch(e){}}
 tc.querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>commande(b.dataset.c));
 // Volume à distance : envoyé au plus toutes les 200 ms pendant qu'on fait glisser, et au relâchement.
 const tcv=document.getElementById('tcv');let tcvTouche=0,tcvEnvoi=0;
 const envoyerVol=()=>{tcvTouche=Date.now();if(Date.now()-tcvEnvoi>200){tcvEnvoi=Date.now();fetch('/commande',
  {method:'POST',body:JSON.stringify({cmd:'volume',v:tcv.value/100})}).catch(()=>{})}};
 tcv.oninput=envoyerVol;tcv.onchange=()=>{tcvEnvoi=0;envoyerVol()};
 let volT;p.addEventListener('volumechange',()=>{clearTimeout(volT);volT=setTimeout(save,300)});  // la télécommande voit le volume
 suivreEncours();setInterval(suivreEncours,2000);
 // Appareil qui joue : exécute les ordres de la télécommande (relevés chaque seconde).
 setInterval(async()=>{if(!proprio)return;try{for(const c of await (await fetch('/commande?dev='+APPAREIL)).json()){
  if(c.cmd==='lecture')p.play().catch(()=>{});else if(c.cmd==='pause')p.pause();else if(c.cmd==='suivant')suivant();
  else if(c.cmd==='precedent')precedent();else if(c.cmd==='jouer'&&parK.has(c.k))play(parK.get(c.k));
  else if(c.cmd==='volume')p.volume=c.v}}catch(e){}},1000)}
function suivant(){if(file.length){if(alea&&cur>=0)hist.push(cur);const n=file.shift();majFile();return play(n)}
 if(alea&&al){const n=hasard();if(n>=0&&cur>=0)hist.push(cur);return play(n)}
 let n=cur+1;while(n<lis.length&&lis[n].hidden)n++;if(n>=lis.length&&repete&&al)n=visibles()[0];play(n)}
// Précédent : après 3 s, revient au début du morceau ; sinon morceau d'avant (en aléatoire : celui joué juste avant).
function precedent(){const debut=()=>{p.currentTime=0};if(cur<0||p.currentTime>3)return debut();
 if(alea)return hist.length?play(hist.pop()):debut();
 let n=cur-1;while(n>=0&&lis[n].hidden)n--;if(n<0&&repete)n=visibles().pop();n>=0?play(n):debut()}
p.onended=()=>{if('{kind}'!=='films')suivant()};
const sv2=()=>distant?commande('suivant'):suivant(),pv2=()=>distant?commande('precedent'):precedent();  // à distance si besoin
if(al){document.getElementById('sv').onclick=sv2;  // marche aussi en « Répéter 1 » : on passe quand même au suivant
 document.getElementById('pv').onclick=pv2;
 try{navigator.mediaSession.setActionHandler('nexttrack',sv2);navigator.mediaSession.setActionHandler('previoustrack',pv2)}
 catch(e){}}  // touches ⏮ ⏭ du clavier / casque
q.oninput=()=>{const s=q.value.toLowerCase();lis.forEach(l=>l.hidden=!l.textContent.toLowerCase().includes(s))};
</script></html>"""


def carte_film(i, titre, chemin):
    m = META.get(Path(chemin).name) or {}
    t, a = m.get("titre") or titre, m.get("annee", "")
    img = f'<img src="{html.escape(m["affiche"])}" loading="lazy" alt="">' if m.get("affiche") else '<div class="ph">🎬</div>'
    attrs, extra = suivi(chemin)
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
            f'<button class="qn" title="Lire juste après" aria-label="Lire juste après">↱</button>'
            f'<button class="qa" title="Ajouter à la file d\'attente" aria-label="Ajouter à la file d\'attente">+</button></li>')


def carte_serie(nom, nb):
    m = META.get("serie:" + nom) or {}
    vus = sum(1 for _, d, c in LIB["series"] if d == nom and SUIVI.get(Path(c).name, {}).get("vu"))
    vus_txt = (f" · {vus} vu" + ("s" if vus > 1 else "")) if vus else ""
    img = f'<img src="{html.escape(m["affiche"])}" loading="lazy" alt="">' if m.get("affiche") else '<div class="ph">📺</div>'
    return (f'<li data-href="/?k=series&amp;s={html.escape(quote(nom))}">{img}{html.escape(nom)}'
            f'<small>{nb} épisode{"s" if nb > 1 else ""}{vus_txt}</small></li>')


def page_serie(nom):
    m = META.get("serie:" + nom) or {}
    r = html.escape(m.get("resume", ""))
    img = f'<img src="{html.escape(m["affiche"])}" alt="">' if m.get("affiche") else ""
    intro = f'<div class="show">{img}<div><h2 id="dt">{html.escape(nom)}</h2><p id="dr">{r}</p></div></div>'
    items = "".join(f'<li data-id="{i}" data-t="{html.escape(nom)} {html.escape(t)}" data-r="{r}"{a}>{html.escape(t)}{x}</li>'
                    for i in ordre("series") for t, d, c in [LIB["series"][i]] if d == nom for a, x in [suivi(c)])
    return intro, items


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
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
        kind = qs.get("k", ["films"])[0]
        kind = kind if kind in LIB else "films"
        intro, grid = '<h2 id="dt"></h2><p id="dr"></p>', kind == "films"
        if kind == "films":
            items = "".join(carte_film(i, *LIB[kind][i][::2]) for i in ordre(kind))
        elif kind == "series" and "s" in qs:
            intro, items = page_serie(qs["s"][0])
        elif kind == "series":
            nb = {}
            for _, d, _ in LIB["series"]:
                nb[d] = nb.get(d, 0) + 1
            items, grid = "".join(carte_serie(n, c) for n, c in sorted(nb.items(), key=lambda x: x[0].lower())), True
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
            '<div id="vt" hidden>🎛 <span id="vtt"></span><br><button class="bt" data-v="-10" aria-label="Reculer de 10 secondes">⏪ 10 s</button>'
            '<button class="bt" id="vtpp" aria-label="Lecture / pause (à distance)">⏯</button><button class="bt" data-v="30" aria-label="Avancer de 30 secondes">30 s ⏩</button>'
            + ('<button class="bt" id="vtsv" aria-label="Épisode suivant (à distance)">⏭ Épisode suivant</button>' if kind == "series" else "")
            + ' <label>🔊 <input id="vtv" type="range" min="0" max="100" value="100" aria-label="Volume (à distance)"></label>'
            ' <label id="vtsl" hidden>💬 <select id="vts" aria-label="Sous-titres (à distance)"></select></label>'
            ' <label id="vtal" hidden>🔈 <select id="vta" aria-label="Piste audio (à distance)"></select></label>'
            ' <button class="bt" id="vtamp" hidden>🔊 Sur l’ampli</button></div>')
        taille = taille_cache_audio() if kind != "musique" else 0
        pied = (f'<p id="pied">Pistes audio converties : <span id="ct">{taille / 1e6:.0f} Mo</span> '
                f'<button class="bt" id="cv">🗑 Vider le cache audio</button></p>' if taille else "")
        body = PAGE
        for k in LIB:  # compteur des séries = nombre de séries, pas d'épisodes
            n = len({d for _, d, _ in LIB[k]}) if k == "series" else len(LIB[k])
            body = body.replace("{" + k + "}", "on" if k == kind else "").replace("{n" + k + "}", str(n))
        body = (body.replace("{grid}", "grid" if grid else "").replace("{player}", player).replace("{intro}", intro)
                .replace("{items}", items).replace("{kind}", kind).replace("{pied}", pied)
                .replace("{ampli}", Path(LECTEUR[0]).stem if LECTEUR[0] else "")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, data, mime):
        if not data:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
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
        if urlparse(self.path).path == "/rescan":
            try:
                n = RESCAN[0]()
            except OSError as e:
                return self.send_error(500, str(e))
            return self.send_bytes(json.dumps({"nouveaux": n}).encode(), "application/json")
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
                SUIVI[nom] = maj_suivi(SUIVI.get(nom, {}), data)
                SUIVI_F.write_text(json.dumps(SUIVI, ensure_ascii=False), "utf-8")
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
    ap.add_argument("--reseau", action="store_true", help="accessible depuis la TV/téléphone du réseau local")
    ap.add_argument("--tmdb", metavar="CLE", help="clé TMDB (themoviedb.org) pour de meilleures affiches ; mémorisée")
    ap.add_argument("--lecteur-externe", metavar="CHEMIN",
                    help="mpv.exe ou vlc.exe pour la passthrough vers l'ampli (sinon trouvé tout seul) ; mémorisé")
    ap.add_argument("--cache-audio", type=float, metavar="GO",
                    help="taille max du cache des pistes audio converties, en Go (défaut 5) ; mémorisée")
    ap.add_argument("--hors-ligne", action="store_true", help="ne pas chercher les affiches sur internet")
    a = ap.parse_args()

    cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {}
    nouveau = {"films": a.films, "series": a.series, "musique": a.musique, "tmdb": a.tmdb, "cache_audio": a.cache_audio,
               "lecteur_externe": a.lecteur_externe}
    if any(nouveau.values()):
        cfg.update({k: v for k, v in nouveau.items() if v})
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    dossiers = {k: cfg.get(k, []) for k in LIB}
    if not any(dossiers.values()) and sys.stdin and sys.stdin.isatty():  # 1er lancement (double-clic sur le .exe)
        print("Premier lancement : indique tes dossiers (copier-coller le chemin, ou Entrée pour passer).")
        for k, nom in (("films", "films"), ("series", "séries TV"), ("musique", "musique")):
            d = input(f"  Dossier de {nom} : ").strip().strip('"')
            if d:
                cfg[k] = dossiers[k] = [d]
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    if not any(dossiers.values()):
        sys.exit('Indique tes dossiers : MediaCenter --films "D:\\Films" --series "D:\\Series" --musique "D:\\Musique"')
    for d in sum(dossiers.values(), []):
        if not Path(d).is_dir():
            print(f"⚠ Dossier introuvable : {d}")

    if CACHE.exists():
        META.update(json.loads(CACHE.read_text("utf-8")))
    if SUIVI_F.exists():
        SUIVI.update(json.loads(SUIVI_F.read_text("utf-8")))
    if ENCOURS_F.exists():
        try:
            ENCOURS.update(valider_encours(json.loads(ENCOURS_F.read_text("utf-8"))), lecture=False)  # rien ne joue au démarrage
        except (ValueError, KeyError, TypeError):
            pass
    if FILE_F.exists():
        try:
            FILE[:] = valider_file(json.loads(FILE_F.read_text("utf-8")))
        except ValueError:
            print("⚠ mediacenter_file.json illisible : file d'attente vide")
    LECTEUR[0] = trouver_lecteur(cfg.get("lecteur_externe"))
    if cfg.get("lecteur_externe") and not LECTEUR[0]:
        print(f"⚠ Lecteur externe introuvable : {cfg['lecteur_externe']}")
    CACHE_AUDIO_MAX[0] = int(max(0.1, cfg.get("cache_audio") or 5) * 1024 ** 3)
    nettoyer_cache_audio(CACHE_AUDIO_MAX[0], demarrage=True)
    scan(dossiers)
    print(f"{len(LIB['films'])} films, {len(LIB['series'])} épisodes, {len(LIB['musique'])} morceaux trouvés.")
    if not (FFMPEG and FFPROBE) and any(c.lower().endswith(".mkv") for k in ("films", "series") for _, _, c in LIB[k]):
        print("ℹ Pour les sous-titres intégrés aux MKV, installe ffmpeg (Windows : winget install ffmpeg) puis relance.")
    if not a.hors_ligne:
        threading.Thread(target=enrichir, args=(cfg.get("tmdb"),), daemon=True).start()
    threading.Thread(target=surveiller, args=(dossiers, not a.hors_ligne, cfg.get("tmdb")), daemon=True).start()
    RESCAN[0] = lambda: scan(dossiers)
    host = "0.0.0.0" if a.reseau else "127.0.0.1"
    url = f"http://localhost:{a.port}/"
    print(f"Ouvre {url}  (Ctrl+C pour quitter, relance pour rescanner)")
    threading.Timer(1, webbrowser.open, [url]).start()
    try:
        serveur = ThreadingHTTPServer((host, a.port), Handler)
    except OSError as e:
        sys.exit(f"Port {a.port} indisponible ({e}) : le Media Center est peut-être déjà lancé.")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")  # console Windows sans emoji : pas de plantage sur « ⚠ »
    except (AttributeError, ValueError):
        pass
    try:
        main()
    except SystemExit as e:
        if GELE and e.code not in (0, None):  # .exe lancé par double-clic : laisser lire le message avant fermeture
            print(e.code)
            input("Appuie sur Entrée pour fermer…")
            raise SystemExit(1)
        raise
