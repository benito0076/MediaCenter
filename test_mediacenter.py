"""python test_mediacenter.py"""
from mediacenter import nettoyer, choisir, choisir_tmdb, nettoyer_album, pochette_integree, episode, maj_suivi, srt_vers_vtt, lire_texte, sous_titres, nom_sous_titre, nom_piste
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

assert episode("The.Office.S02E05.Le.Bal.720p.WEB-DL", ("The Office",)) == ("The Office", "S02E05 – Le Bal")
assert episode("s01e01", ("Breaking Bad (2008)", "Saison 1")) == ("Breaking Bad", "S01E01")
assert episode("Kaamelott 3x12 FRENCH", ()) == ("Kaamelott", "S03E12")
assert episode("Episode special", ("Lost",)) == ("Lost", "Episode special")
tv = [{"name": "Lost", "first_air_date": "2004-09-22", "overview": "Crash…", "poster_path": "/l.jpg"}]
assert choisir_tmdb(tv, "", "first_air_date")["titre"] == "Lost"
assert choisir_tmdb(tv, "", "first_air_date")["annee"] == "2004"

assert maj_suivi({}, {"t": 600, "d": 3000}) == {"t": 600, "d": 3000}
assert maj_suivi({"t": 600, "d": 3000}, {"t": 2900, "d": 3000}) == {"t": 0, "d": 3000, "vu": True}  # générique
assert maj_suivi({"t": 600, "vu": True}, {"vu": False}) == {"t": 0, "vu": False}
for mauvais in ({"t": float("nan")}, {"t": -1}, {}):
    try:
        maj_suivi({}, mauvais)
        raise AssertionError(mauvais)
    except (ValueError, KeyError):
        pass

srt = "1\r\n00:00:01,500 --> 0:00:03,000\r\n{\\an8}<i>Salut</i>\r\n"
assert srt_vers_vtt(srt) == "WEBVTT\n\n1\n00:00:01.500 --> 00:00:03.000\n<i>Salut</i>\n"
assert srt_vers_vtt("WEBVTT\n\nx") == "WEBVTT\n\nx"
with tempfile.TemporaryDirectory() as d:
    from pathlib import Path
    D = Path(d)
    (D / "Saison").mkdir(); (D / "Film").mkdir(); (D / "Film" / "Subs").mkdir()
    for f in ["Saison/Ep.S01E01.mkv", "Saison/Ep.S01E01.fr.srt", "Saison/Ep.S01E02.mkv", "Saison/autre.srt",
              "Film/Film.mkv", "Film/Subs/2_French.srt", "Film/Subs/notes.txt"]:
        (D / f).write_bytes(b"")
    assert sous_titres(D / "Saison/Ep.S01E01.mkv", False) == [str(D / "Saison/Ep.S01E01.fr.srt")]
    assert sous_titres(D / "Saison/Ep.S01E02.mkv", False) == []
    assert sous_titres(D / "Film/Film.mkv", True) == [str(D / "Film/Subs/2_French.srt")]
    assert nom_sous_titre(D / "Saison/Ep.S01E01.fr.srt", D / "Saison/Ep.S01E01.mkv") == "fr"
    assert nom_sous_titre(D / "Film/Subs/2_French.srt", D / "Film/Film.mkv") == "2 French"
    (D / "a.srt").write_bytes("Déjà vu".encode("cp1252")); assert lire_texte(D / "a.srt") == "Déjà vu"
    (D / "b.srt").write_bytes("Déjà vu".encode("utf-8-sig")); assert lire_texte(D / "b.srt") == "Déjà vu"
    (D / "c.srt").write_bytes("Déjà vu".encode("utf-16")); assert lire_texte(D / "c.srt") == "Déjà vu"

assert nom_piste({"tags": {"language": "fre", "title": "Forced"}}) == "Français – Forced"
assert nom_piste({"tags": {"LANGUAGE": "eng"}}) == "Anglais"
assert nom_piste({"tags": {"language": "und"}}) == "Intégrés"
assert nom_piste({}) == "Intégrés"

# Sans ffmpeg installé : pas de pistes intégrées, pas d'erreur.
import mediacenter
mediacenter.FFPROBE = None
assert mediacenter.pistes_integrees("film.mkv") == []
print("OK")
