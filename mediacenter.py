#!/usr/bin/env python3
"""Media Center minimaliste : films + musique dans le navigateur. Python 3.8+, zéro dépendance.

Usage :  python mediacenter.py --films "D:\\Films" --musique "D:\\Musique"
Les dossiers sont mémorisés dans mediacenter.json ; ensuite `python mediacenter.py` suffit.
"""
import argparse, html, json, mimetypes, os, re, sys, threading, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

CONFIG = Path(__file__).with_name("mediacenter.json")
EXT = {
    "films": {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v"},
    "musique": {".mp3", ".flac", ".ogg", ".m4a", ".wav", ".opus", ".aac"},
}
LIB = {"films": [], "musique": []}  # chaque entrée : (titre, sous-dossier, chemin absolu)


def scan(dossiers):
    for kind, roots in dossiers.items():
        items = []
        for root in roots:
            root = Path(root)
            for p in root.rglob("*"):
                if p.suffix.lower() in EXT[kind] and p.is_file():
                    titre = re.sub(r"[._]+", " ", p.stem).strip()
                    dossier = str(p.parent.relative_to(root))
                    items.append((titre, "" if dossier == "." else dossier, str(p)))
        LIB[kind] = sorted(items, key=lambda i: (i[1].lower(), i[0].lower()))


PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Center</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#111;color:#eee}
header{position:sticky;top:0;background:#1b1b1b;padding:12px 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
a.tab{color:#aaa;text-decoration:none;padding:6px 12px;border-radius:6px}a.tab.on{background:#e50914;color:#fff}
input{flex:1;min-width:160px;padding:8px;border-radius:6px;border:0;background:#2a2a2a;color:#eee}
main{padding:16px}video,audio{width:100%;max-height:70vh;background:#000;border-radius:8px}
ul{list-style:none;padding:0}li{padding:10px;border-bottom:1px solid #222;cursor:pointer}
li:hover,li.on{background:#222}small{color:#888;margin-left:8px}
</style>
<header><b>🎬 Media Center</b>
<a class="tab {f}" href="/?k=films">Films ({nf})</a><a class="tab {m}" href="/?k=musique">Musique ({nm})</a>
<input id="q" placeholder="Rechercher…" autofocus></header>
<main>{player}<ul id="l">{items}</ul></main>
<script>
const p=document.getElementById('p'),lis=[...document.querySelectorAll('li')];let cur=-1;
function play(i){if(i<0||i>=lis.length)return;lis.forEach(l=>l.classList.remove('on'));
 cur=i;lis[i].classList.add('on');p.src='/media/{kind}/'+lis[i].dataset.id;p.play();
 document.title=lis[i].dataset.t;window.scrollTo(0,0)}
lis.forEach((l,i)=>l.onclick=()=>play(i));
p.onended=()=>{if('{kind}'==='musique'){let n=cur+1;while(n<lis.length&&lis[n].hidden)n++;play(n)}};
q.oninput=()=>{const s=q.value.toLowerCase();lis.forEach(l=>l.hidden=!l.textContent.toLowerCase().includes(s))};
</script></html>"""


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
        items = "".join(
            f'<li data-id="{i}" data-t="{html.escape(t)}">{html.escape(t)}<small>{html.escape(d)}</small></li>'
            for i, (t, d, _) in enumerate(LIB[kind])
        )
        tag = "video" if kind == "films" else "audio"
        body = (PAGE.replace("{f}", "on" if kind == "films" else "").replace("{m}", "on" if kind == "musique" else "")
                .replace("{nf}", str(len(LIB["films"]))).replace("{nm}", str(len(LIB["musique"])))
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

    scan(cfg)
    print(f"{len(LIB['films'])} films, {len(LIB['musique'])} morceaux trouvés.")
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
