#!/usr/bin/env python3
"""Media Center minimaliste : films, séries + musique dans le navigateur. Python 3.8+, zéro dépendance.

Usage :  python mediacenter.py --films "D:\\Films" --series "D:\\Series" --musique "D:\\Musique"
Les dossiers sont mémorisés dans mediacenter.json ; ensuite `python mediacenter.py` suffit.
Affiches et résumés : TMDB si une clé est donnée (--tmdb CLE), sinon iTunes ; gardés dans mediacenter_cache.json.
"""
import argparse, html, json, math, mimetypes, os, re, sys, threading, time, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CONFIG = Path(__file__).with_name("mediacenter.json")
CACHE = Path(__file__).with_name("mediacenter_cache.json")
SUIVI_F = Path(__file__).with_name("mediacenter_suivi.json")
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


def scan(dossiers):
    for kind, roots in dossiers.items():
        items = []
        for root in roots:
            root = Path(root)
            for p in root.rglob("*"):
                if p.suffix.lower() in EXT[kind] and p.is_file():
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
        LIB[kind] = sorted(items, key=lambda i: (i[1].lower(), i[0].lower()))


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


PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Center</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#111;color:#eee}
header{position:sticky;top:0;z-index:1;background:#1b1b1b;padding:12px 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
a.tab{color:#aaa;text-decoration:none;padding:6px 12px;border-radius:6px}a.tab.on{background:#e50914;color:#fff}
input{flex:1;min-width:160px;padding:8px;border-radius:6px;border:0;background:#2a2a2a;color:#eee}
main{padding:16px}video,audio{width:100%;max-height:70vh;background:#000;border-radius:8px}video:not([src]){display:none}
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
#pc{width:220px;height:220px;object-fit:cover;border-radius:8px;display:block;margin-bottom:12px}
ul.grid img,.show{display:flex;gap:16px;align-items:flex-start;margin:16px 0}.show img{width:140px;border-radius:6px;flex:none}
.ph{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:6px;background:#222;
 display:flex;align-items:center;justify-content:center;font-size:40px;margin-bottom:6px}
</style>
<header><b>🎬 Media Center</b>
<a class="tab {films}" href="/?k=films">Films ({nfilms})</a><a class="tab {series}" href="/?k=series">Séries ({nseries})</a>
<a class="tab {musique}" href="/?k=musique">Musique ({nmusique})</a>
<input id="q" placeholder="Rechercher…" autofocus></header>
<main>{player}{intro}<ul id="l" class="{grid}">{items}</ul></main>
<script>
const p=document.getElementById('p'),lis=[...document.querySelectorAll('li')];let cur=-1;
const vid='{kind}'!=='musique';let last=0;
function envoi(l,data){navigator.sendBeacon('/suivi/{kind}/'+l.dataset.id,JSON.stringify(data))}
function save(){if(!vid||cur<0||!(p.currentTime>1))return;const l=lis[cur];envoi(l,{t:p.currentTime,d:p.duration||0});
 l.dataset.pos=p.currentTime;if(p.duration&&p.currentTime>.9*p.duration){l.classList.add('vu');l.dataset.pos=0}}
p.ontimeupdate=()=>{if(Math.abs(p.currentTime-last)>10){last=p.currentTime;save()}};
p.onpause=save;addEventListener('pagehide',save);
document.querySelectorAll('.ck').forEach(b=>b.onclick=e=>{e.stopPropagation();const l=b.closest('li'),v=!l.classList.contains('vu');
 l.classList.toggle('vu',v);l.dataset.pos=0;const bar=l.querySelector('.bar');if(bar)bar.remove();envoi(l,{vu:v})});
function play(i){if(i<0||i>=lis.length)return;save();lis.forEach(l=>l.classList.remove('on'));
 cur=i;const l=lis[i];l.classList.add('on');last=+l.dataset.pos||0;
 if(vid&&last>5)p.addEventListener('loadedmetadata',()=>p.currentTime=last,{once:true});  // reprise
 p.src='/media/{kind}/'+l.dataset.id;p.play();
 document.title=dt.textContent=l.dataset.t;dr.textContent=l.dataset.r||'';
 const pc=document.getElementById('pc');if(pc){pc.src=l.dataset.img||'';pc.hidden=!l.dataset.img}window.scrollTo(0,0)}
lis.forEach((l,i)=>l.onclick=()=>l.dataset.href?location.href=l.dataset.href:play(i));
p.onended=()=>{if('{kind}'!=='films'){let n=cur+1;while(n<lis.length&&lis[n].hidden)n++;play(n)}};
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
    return (f'<li data-id="{i}" data-t="{html.escape(titre)}" data-img="{html.escape(src)}">{img}'
            f'<span>{html.escape(titre)}<small>{html.escape(dossier)}</small></span></li>')


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
                    for i, (t, d, c) in enumerate(LIB["series"]) if d == nom for a, x in [suivi(c)])
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
        if url.path != "/":
            return self.send_error(404)
        qs = parse_qs(url.query)
        kind = qs.get("k", ["films"])[0]
        kind = kind if kind in LIB else "films"
        intro, grid = '<h2 id="dt"></h2><p id="dr"></p>', kind == "films"
        if kind == "films":
            items = "".join(carte_film(i, t, c) for i, (t, _, c) in enumerate(LIB[kind]))
        elif kind == "series" and "s" in qs:
            intro, items = page_serie(qs["s"][0])
        elif kind == "series":
            nb = {}
            for _, d, _ in LIB["series"]:
                nb[d] = nb.get(d, 0) + 1
            items, grid = "".join(carte_serie(n, c) for n, c in sorted(nb.items(), key=lambda x: x[0].lower())), True
        else:
            premier = {}
            items = "".join(ligne_musique(i, t, d, c, premier) for i, (t, d, c) in enumerate(LIB[kind]))
        player = '<img id="pc" hidden alt=""><audio id="p" controls></audio>' if kind == "musique" else '<video id="p" controls></video>'
        body = PAGE
        for k in LIB:  # compteur des séries = nombre de séries, pas d'épisodes
            n = len({d for _, d, _ in LIB[k]}) if k == "series" else len(LIB[k])
            body = body.replace("{" + k + "}", "on" if k == kind else "").replace("{n" + k + "}", str(n))
        body = (body.replace("{grid}", "grid" if grid else "").replace("{player}", player).replace("{intro}", intro)
                .replace("{items}", items).replace("{kind}", kind)).encode()
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
    ap.add_argument("--hors-ligne", action="store_true", help="ne pas chercher les affiches sur internet")
    a = ap.parse_args()

    cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {}
    nouveau = {"films": a.films, "series": a.series, "musique": a.musique, "tmdb": a.tmdb}
    if any(nouveau.values()):
        cfg.update({k: v for k, v in nouveau.items() if v})
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    dossiers = {k: cfg.get(k, []) for k in LIB}
    if not any(dossiers.values()):
        sys.exit('Indique tes dossiers : python mediacenter.py --films "D:\\Films" --series "D:\\Series" --musique "D:\\Musique"')
    for d in sum(dossiers.values(), []):
        if not Path(d).is_dir():
            print(f"⚠ Dossier introuvable : {d}")

    if CACHE.exists():
        META.update(json.loads(CACHE.read_text("utf-8")))
    if SUIVI_F.exists():
        SUIVI.update(json.loads(SUIVI_F.read_text("utf-8")))
    scan(dossiers)
    print(f"{len(LIB['films'])} films, {len(LIB['series'])} épisodes, {len(LIB['musique'])} morceaux trouvés.")
    if not a.hors_ligne:
        threading.Thread(target=enrichir, args=(cfg.get("tmdb"),), daemon=True).start()
    host = "0.0.0.0" if a.reseau else "127.0.0.1"
    url = f"http://localhost:{a.port}/"
    print(f"Ouvre {url}  (Ctrl+C pour quitter, relance pour rescanner)")
    threading.Timer(1, webbrowser.open, [url]).start()
    try:
        ThreadingHTTPServer((host, a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
