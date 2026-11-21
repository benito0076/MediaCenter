#!/usr/bin/env python3
"""Media Center minimaliste : films + musique dans le navigateur. Python 3.8+, zéro dépendance.

Usage :  python mediacenter.py --films "D:\\Films" --musique "D:\\Musique"
Les dossiers sont mémorisés dans mediacenter.json ; ensuite `python mediacenter.py` suffit.
Affiches et résumés : récupérés sur iTunes (gratuit, sans clé) et gardés dans mediacenter_cache.json.
"""
import argparse, html, json, mimetypes, os, re, sys, threading, time, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import urlopen

CONFIG = Path(__file__).with_name("mediacenter.json")
CACHE = Path(__file__).with_name("mediacenter_cache.json")
EXT = {
    "films": {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v"},
    "musique": {".mp3", ".flac", ".ogg", ".m4a", ".wav", ".opus", ".aac"},
}
LIB = {"films": [], "musique": []}  # chaque entrée : (titre, sous-dossier, chemin absolu)
META = {}  # nom de fichier -> {"titre", "annee", "resume", "affiche"} ; {} = introuvable

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


def scan(dossiers):
    for kind, roots in dossiers.items():
        items = []
        for root in roots:
            root = Path(root)
            for p in root.rglob("*"):
                if p.suffix.lower() in EXT[kind] and p.is_file():
                    titre = nettoyer(p.stem)[0] if kind == "films" else re.sub(r"[._]+", " ", p.stem).strip()
                    dossier = str(p.parent.relative_to(root))
                    items.append((titre or p.stem, "" if dossier == "." else dossier, str(p)))
        LIB[kind] = sorted(items, key=lambda i: (i[1].lower(), i[0].lower()))


def choisir(resultats, annee):
    if not resultats:
        return {}
    r = next((x for x in resultats if annee and x.get("releaseDate", "").startswith(annee)), resultats[0])
    return {"titre": r.get("trackName", ""), "annee": r.get("releaseDate", "")[:4],
            "resume": r.get("longDescription") or r.get("shortDescription", ""),
            "affiche": r.get("artworkUrl100", "").replace("100x100", "600x600")}


def chercher(titre, annee):
    q = urlencode({"term": titre, "media": "movie", "entity": "movie", "country": "fr", "lang": "fr_fr", "limit": 10})
    with urlopen("https://itunes.apple.com/search?" + q, timeout=10) as r:
        return choisir(json.load(r).get("results", []), annee)


def enrichir():
    manquants = [Path(p) for _, _, p in LIB["films"] if Path(p).name not in META]
    if manquants:
        print(f"Recherche des affiches pour {len(manquants)} films (en arrière-plan)…")
    for p in manquants:
        try:
            META[p.name] = chercher(*nettoyer(p.stem))
        except (OSError, ValueError) as e:  # pas d'internet : on réessaiera au prochain lancement
            print(f"⚠ Affiche non récupérée pour {p.name} : {e}")
            continue
        CACHE.write_text(json.dumps(META, ensure_ascii=False), "utf-8")
        time.sleep(3)  # ponytail: iTunes limite à ~20 requêtes/min ; 1re fois lente si grosse collection


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
ul.grid img,.ph{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:6px;background:#222;
 display:flex;align-items:center;justify-content:center;font-size:40px;margin-bottom:6px}
</style>
<header><b>🎬 Media Center</b>
<a class="tab {f}" href="/?k=films">Films ({nf})</a><a class="tab {m}" href="/?k=musique">Musique ({nm})</a>
<input id="q" placeholder="Rechercher…" autofocus></header>
<main>{player}<h2 id="dt"></h2><p id="dr"></p><ul id="l" class="{grid}">{items}</ul></main>
<script>
const p=document.getElementById('p'),lis=[...document.querySelectorAll('li')];let cur=-1;
function play(i){if(i<0||i>=lis.length)return;lis.forEach(l=>l.classList.remove('on'));
 cur=i;const l=lis[i];l.classList.add('on');p.src='/media/{kind}/'+l.dataset.id;p.play();
 document.title=dt.textContent=l.dataset.t;dr.textContent=l.dataset.r||'';window.scrollTo(0,0)}
lis.forEach((l,i)=>l.onclick=()=>play(i));
p.onended=()=>{if('{kind}'==='musique'){let n=cur+1;while(n<lis.length&&lis[n].hidden)n++;play(n)}};
q.oninput=()=>{const s=q.value.toLowerCase();lis.forEach(l=>l.hidden=!l.textContent.toLowerCase().includes(s))};
</script></html>"""


def carte_film(i, titre, chemin):
    m = META.get(Path(chemin).name) or {}
    t, a = m.get("titre") or titre, m.get("annee", "")
    img = f'<img src="{html.escape(m["affiche"])}" loading="lazy" alt="">' if m.get("affiche") else '<div class="ph">🎬</div>'
    return (f'<li data-id="{i}" data-t="{html.escape(t)}{" (" + a + ")" if a else ""}" data-r="{html.escape(m.get("resume", ""))}">'
            f'{img}{html.escape(t)}<small>{a}</small></li>')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        m = re.fullmatch(r"/media/(films|musique)/(\d+)", url.path)
        if m:
            return self.send_media(m[1], int(m[2]))
        if url.path != "/":
            return self.send_error(404)
        kind = parse_qs(url.query).get("k", ["films"])[0]
        kind = kind if kind in LIB else "films"
        if kind == "films":
            items = "".join(carte_film(i, t, c) for i, (t, _, c) in enumerate(LIB[kind]))
        else:
            items = "".join(
                f'<li data-id="{i}" data-t="{html.escape(t)}">{html.escape(t)}<small>{html.escape(d)}</small></li>'
                for i, (t, d, _) in enumerate(LIB[kind]))
        tag = "video" if kind == "films" else "audio"
        body = (PAGE.replace("{f}", "on" if kind == "films" else "").replace("{m}", "on" if kind == "musique" else "")
                .replace("{nf}", str(len(LIB["films"]))).replace("{nm}", str(len(LIB["musique"])))
                .replace("{grid}", "grid" if kind == "films" else "")
                .replace("{player}", f'<{tag} id="p" controls></{tag}>').replace("{items}", items)
                .replace("{kind}", kind)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_media(self, kind, idx):
        # Seuls les fichiers indexés sont servis (par numéro) : pas de traversée de chemin possible.
        if idx >= len(LIB[kind]):
            return self.send_error(404)
        path = LIB[kind][idx][2]
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

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description="Media Center : films et musique")
    ap.add_argument("--films", action="append", help="dossier de films (répétable)")
    ap.add_argument("--musique", action="append", help="dossier de musique (répétable)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reseau", action="store_true", help="accessible depuis la TV/téléphone du réseau local")
    ap.add_argument("--hors-ligne", action="store_true", help="ne pas chercher les affiches sur internet")
    a = ap.parse_args()

    cfg = json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {"films": [], "musique": []}
    if a.films or a.musique:
        cfg = {"films": a.films or cfg["films"], "musique": a.musique or cfg["musique"]}
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    if not (cfg["films"] or cfg["musique"]):
        sys.exit('Indique tes dossiers : python mediacenter.py --films "D:\\Films" --musique "D:\\Musique"')
    for d in cfg["films"] + cfg["musique"]:
        if not Path(d).is_dir():
            print(f"⚠ Dossier introuvable : {d}")

    if CACHE.exists():
        META.update(json.loads(CACHE.read_text("utf-8")))
    scan(cfg)
    print(f"{len(LIB['films'])} films, {len(LIB['musique'])} morceaux trouvés.")
    if not a.hors_ligne:
        threading.Thread(target=enrichir, daemon=True).start()
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
