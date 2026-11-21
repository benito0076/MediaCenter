"""python test_mediacenter.py"""
from mediacenter import nettoyer, choisir, choisir_tmdb, nettoyer_album, pochette_integree
import os, tempfile

assert nettoyer("Le.Film.2024.1080p.x264-GRP") == ("Le Film", "2024")
assert nettoyer("Inception (2010) [MULTI] 1080p") == ("Inception", "2010")
assert nettoyer("2001.L'Odyssee.de.l'espace.1968.BluRay") == ("2001 L'Odyssee de l'espace", "1968")
assert nettoyer("Blade Runner 2049 (2017) TRUEFRENCH") == ("Blade Runner 2049", "2017")
assert nettoyer("Amelie_VOSTFR_WEB-DL") == ("Amelie", "")
assert nettoyer("Mon film de vacances") == ("Mon film de vacances", "")

res = [{"trackName": "Dune", "releaseDate": "1984-12-14", "artworkUrl100": "x/100x100bb.jpg"},
       {"trackName": "Dune", "releaseDate": "2021-09-15", "longDescription": "Paul…", "artworkUrl100": "y/100x100bb.jpg"}]
assert choisir(res, "2021") == {"titre": "Dune", "annee": "2021", "resume": "Paul…", "affiche": "y/600x600bb.jpg"}
assert choisir(res, "")["annee"] == "1984"
assert choisir([], "2021") == {}
tm = [{"title": "Dune", "release_date": "1984-12-14", "overview": "", "poster_path": None},
      {"title": "Dune", "release_date": "2021-09-15", "overview": "Paul…", "poster_path": "/abc.jpg"}]
assert choisir_tmdb(tm, "2021") == {"titre": "Dune", "annee": "2021", "resume": "Paul…",
                                    "affiche": "https://image.tmdb.org/t/p/w500/abc.jpg", "source": "tmdb"}
assert choisir_tmdb(tm, "")["affiche"] == ""
assert choisir_tmdb([], "") == {}
assert nettoyer_album("Daft Punk - Discovery (2001) [FLAC]") == "Daft Punk Discovery"
assert nettoyer_album("Daft Punk/Discovery/CD1") == "Daft Punk Discovery"
assert nettoyer_album("Stromae\\Racine Carree 320kbps") == "Stromae Racine Carree"

# Pochettes intégrées : ID3v2.3 (description UTF-16) et FLAC construits à la main.
IMG = b"\xff\xd8\xff\xe0fausse-image-jpeg"
apic = b"\x01image/jpeg\0\x03" + "é".encode("utf-16") + b"\0\0" + IMG
id3 = b"ID3\x03\0\0" + bytes([0, 0, 0, 10 + len(apic)]) + b"APIC" + len(apic).to_bytes(4, "big") + b"\0\0" + apic
pic = (3).to_bytes(4, "big") + (10).to_bytes(4, "big") + b"image/jpeg" + (0).to_bytes(4, "big") + bytes(16) + len(IMG).to_bytes(4, "big") + IMG
flac = b"fLaC" + b"\x00" + (34).to_bytes(3, "big") + bytes(34) + b"\x86" + len(pic).to_bytes(3, "big") + pic
with tempfile.TemporaryDirectory() as d:
    for nom, contenu in (("a.mp3", id3 + b"audio"), ("b.flac", flac), ("c.mp3", b"audio sans balise")):
        open(os.path.join(d, nom), "wb").write(contenu)
    assert pochette_integree(os.path.join(d, "a.mp3")) == (IMG, "image/jpeg")
    assert pochette_integree(os.path.join(d, "b.flac")) == (IMG, "image/jpeg")
    assert pochette_integree(os.path.join(d, "c.mp3")) is None
print("OK")
