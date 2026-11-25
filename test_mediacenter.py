"""python test_mediacenter.py"""
from mediacenter import nettoyer, choisir, choisir_tmdb, nettoyer_album, pochette_integree, episode, maj_suivi, vers_vtt, lire_texte, sous_titres, nom_sous_titre, nom_piste
import os, tempfile, time

assert nettoyer("Le.Film.2024.1080p.x264-GRP") == ("Le Film", "2024")
assert nettoyer("Inception (2010) [MULTI] 1080p") == ("Inception", "2010")
assert nettoyer("2001.L'Odyssee.de.l'espace.1968.BluRay") == ("2001 L'Odyssee de l'espace", "1968")
assert nettoyer("Blade Runner 2049 (2017) TRUEFRENCH") == ("Blade Runner 2049", "2017")
assert nettoyer("Amelie_VOSTFR_WEB-DL") == ("Amelie", "")
assert nettoyer("Mon film de vacances") == ("Mon film de vacances", "")

res = [{"trackName": "Dune", "releaseDate": "1984-12-14", "artworkUrl100": "x/100x100bb.jpg"},
       {"trackName": "Dune", "releaseDate": "2021-09-15", "longDescription": "Paul…", "artworkUrl100": "y/100x100bb.jpg"}]
assert choisir(res, "2021") == {"titre": "Dune", "annee": "2021", "resume": "Paul…", "affiche": "y/600x600bb.jpg", "genres": []}
assert choisir(res, "")["annee"] == "1984"
assert choisir([], "2021") == {}
tm = [{"title": "Dune", "release_date": "1984-12-14", "overview": "", "poster_path": None},
      {"title": "Dune", "release_date": "2021-09-15", "overview": "Paul…", "poster_path": "/abc.jpg", "genre_ids": [878, 12, 99999]}]
assert choisir_tmdb(tm, "2021") == {"titre": "Dune", "annee": "2021", "resume": "Paul…",
                                    "affiche": "https://image.tmdb.org/t/p/w500/abc.jpg", "fond": "", "genres": ["Science-Fiction", "Aventure"], "source": "tmdb"}
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
assert vers_vtt(srt) == "WEBVTT\n\n1\n00:00:01.500 --> 00:00:03.000\n<i>Salut</i>\n"
assert vers_vtt("WEBVTT\n\nx") == "WEBVTT\n\nx"
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
with tempfile.TemporaryDirectory() as d:
    D = Path(d)
    (D / "Fonts").mkdir()
    for f in ["Ep.mkv", "Ep.fr.ass", "Ep.en.srt", "Fonts/A.ttf", "Fonts/b.OTF", "Fonts/lisez-moi.txt"]:
        (D / f).write_bytes(b"")
    v = str(D / "Ep.mkv")
    mediacenter.SUBS[v] = mediacenter.sous_titres(Path(v), True)
    assert mediacenter.infos_pistes(v) == [{"nom": "en", "ass": False}, {"nom": "fr", "ass": True}]
    assert [Path(f).name for f in mediacenter.polices(v)] == ["A.ttf", "b.OTF"]

ASS = """[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:05.20,0:00:07.00,Default,,0,0,0,,Deuxième, avec virgule\\NNouvelle ligne
Comment: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,commentaire ignoré
Dialogue: 0,0:00:01.50,0:00:03.00,Default,,0,0,0,,{\\an8\\fad(200,200)}{\\i1}Bonjour{\\i0} Naruto
Dialogue: 0,0:00:02.00,0:00:03.00,Sign,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100{\\p0}
Dialogue: 0,1:02:03.00,1:02:04.00,Default,,0,0,0,,{\\k20}Ka{\\k30}ra\\hoke
"""
assert vers_vtt(ASS) == ("WEBVTT\n\n00:00:01.500 --> 00:00:03.000 line:0\n<i>Bonjour</i> Naruto\n\n"
                         "00:00:05.200 --> 00:00:07.000\nDeuxième, avec virgule\nNouvelle ligne\n\n"
                         "01:02:03.000 --> 01:02:04.000\nKara oke\n\n"), vers_vtt(ASS)

assert mediacenter.valider_file(["A/1.mp3", "B/2.flac"]) == ["A/1.mp3", "B/2.flac"]
for mauvais in ({"a": 1}, [1, 2], "texte", ["x" * 3000]):
    try:
        mediacenter.valider_file(mauvais)
        raise AssertionError(mauvais)
    except ValueError:
        pass
e = mediacenter.valider_encours({"k": "A/1.mp3", "t": 12.34, "lecture": True})
assert (e["k"], e["t"], e["lecture"]) == ("A/1.mp3", 12.3, True) and e["quand"] > 0
for mauvais in ({"k": "A", "t": "nan", "lecture": True}, {"k": 1, "t": 1, "lecture": True}, {"k": "A", "t": 1, "lecture": "oui"},
                {"k": "A", "t": -5, "lecture": False}, {"t": 1}):
    try:
        mediacenter.valider_encours(mauvais)
        raise AssertionError(mauvais)
    except (ValueError, KeyError):
        pass
joue = {"k": "A", "t": 5, "lecture": True, "dev": "tel", "quand": 100.0}
assert not mediacenter.accepter_encours(joue, {"k": "A", "t": 3, "lecture": False, "dev": "pc", "quand": 105.0})  # relais
assert mediacenter.accepter_encours(joue, {"k": "A", "t": 9, "lecture": False, "dev": "tel", "quand": 105.0})  # sa propre pause
assert mediacenter.accepter_encours(joue, {"k": "B", "t": 0, "lecture": True, "dev": "pc", "quand": 105.0})  # l'autre lance
assert mediacenter.accepter_encours(joue, {"k": "A", "t": 3, "lecture": False, "dev": "pc", "quand": 140.0})  # tél muet > 30 s
assert mediacenter.accepter_encours({}, {"k": "A", "t": 3, "lecture": False, "dev": "pc", "quand": 1.0})
assert mediacenter.valider_commande({"cmd": "jouer", "k": "A/1.mp3"}) == {"cmd": "jouer", "k": "A/1.mp3", "v": 0}
assert mediacenter.valider_commande({"cmd": "pause"}) == {"cmd": "pause", "k": "", "v": 0}
assert mediacenter.valider_commande({"cmd": "volume", "v": 0.35})["v"] == 0.35
for mauvais in ({"cmd": "formater"}, {"cmd": "jouer"}, {"cmd": "jouer", "k": 5}, {}, {"cmd": "volume", "v": 3},
                {"cmd": "volume", "v": "nan"}, {"cmd": "volume", "v": -0.1}):
    try:
        mediacenter.valider_commande(mauvais)
        raise AssertionError(mauvais)
    except (ValueError, KeyError):
        pass
assert mediacenter.valider_commande({"cmd": "deplacer", "v": -10})["v"] == -10
for mauvais in ({"cmd": "deplacer", "v": 99999}, {"cmd": "volume", "v": -10}):
    try:
        mediacenter.valider_commande(mauvais)
        raise AssertionError(mauvais)
    except ValueError:
        pass
v = mediacenter.valider_video({"kind": "series", "id": 3, "titre": "Lost S01E02", "t": 61.27, "d": 2580, "lecture": True,
                               "vol": 0.5, "page": "?k=series&s=Lost", "dev": "tv"})
assert (v["kind"], v["id"], v["t"], v["page"]) == ("series", 3, 61.3, "?k=series&s=Lost")
for mauvais in ({**v, "kind": "musique"}, {**v, "id": -1}, {**v, "t": float("inf")}, {**v, "vol": 2}, {**v, "titre": 5}):
    try:
        mediacenter.valider_video(mauvais)
        raise AssertionError(mauvais)
    except (ValueError, TypeError):
        pass
assert mediacenter.valider_commande({"cmd": "soustitres", "v": -1})["v"] == -1
assert mediacenter.valider_commande({"cmd": "soustitres", "v": 2})["v"] == 2
for mauvais in ({"cmd": "soustitres", "v": 1.5}, {"cmd": "soustitres", "v": -2}):
    try:
        mediacenter.valider_commande(mauvais)
        raise AssertionError(mauvais)
    except ValueError:
        pass
v = mediacenter.valider_video({"kind": "films", "id": 0, "titre": "Dune", "t": 1, "lecture": True, "st": ["fr", "en"], "sti": 1})
assert (v["st"], v["sti"]) == (["fr", "en"], 1)
for mauvais in ({**v, "sti": 2}, {**v, "st": [1]}, {**v, "st": "fr"}):
    try:
        mediacenter.valider_video(mauvais)
        raise AssertionError(mauvais)
    except (ValueError, TypeError):
        pass
assert mediacenter.valider_commande({"cmd": "audio", "v": 1})["v"] == 1
for mauvais in ({"cmd": "audio", "v": -1}, {"cmd": "audio", "v": 0.5}):
    try:
        mediacenter.valider_commande(mauvais)
        raise AssertionError(mauvais)
    except ValueError:
        pass
v = mediacenter.valider_video({"kind": "films", "id": 0, "titre": "Dune", "t": 1, "lecture": True, "au": ["1. Français", "2. Anglais"], "aui": 1})
assert (v["au"], v["aui"]) == (["1. Français", "2. Anglais"], 1)
try:
    mediacenter.valider_video({**v, "aui": 5})
    raise AssertionError("aui hors limites")
except ValueError:
    pass
# Nettoyage du cache audio : on supprime les pistes utilisées il y a le plus longtemps jusqu'à passer sous la limite.
with tempfile.TemporaryDirectory() as d:
    ancien, mediacenter.AUDIO_DIR = mediacenter.AUDIO_DIR, Path(d)
    try:
        for k, nom in enumerate(["a.m4a", "b.m4a", "c.m4a", "d.m4a"]):  # a = plus ancien usage, d = plus récent
            (Path(d) / nom).write_bytes(b"x" * 100)
            os.utime(Path(d) / nom, (1000 + k, 1000 + k))
        (Path(d) / "e.tmp.m4a").write_bytes(b"x" * 100)  # conversion en cours : jamais supprimée hors démarrage
        mediacenter.nettoyer_cache_audio(250)
        assert sorted(f.name for f in Path(d).iterdir()) == ["c.m4a", "d.m4a", "e.tmp.m4a"]
        mediacenter.nettoyer_cache_audio(1000, demarrage=True)
        assert sorted(f.name for f in Path(d).iterdir()) == ["c.m4a", "d.m4a"]
        mediacenter.nettoyer_cache_audio(10, garder=Path(d) / "d.m4a")  # limite minuscule : la piste neuve reste
        assert sorted(f.name for f in Path(d).iterdir()) == ["d.m4a"]
        mediacenter.AUDIO_DIR = Path(d) / "absent"
        mediacenter.nettoyer_cache_audio(0)  # dossier absent : rien à faire, pas d'erreur
    finally:
        mediacenter.AUDIO_DIR = ancien
assert mediacenter.options_conversion(2) == ["-ac", "2", "-b:a", "192k"]
assert mediacenter.options_conversion(1) == ["-ac", "2", "-b:a", "192k"]
assert mediacenter.options_conversion(6) == ["-ac", "6", "-b:a", "384k"]
assert mediacenter.options_conversion(8) == ["-ac", "6", "-b:a", "384k"]  # 7.1 -> 5.1
assert mediacenter.options_conversion(3) == ["-ac", "3", "-b:a", "384k"]
assert (mediacenter.nom_canaux(6), mediacenter.nom_canaux(8), mediacenter.nom_canaux(10)) == ("5.1", "7.1", "10 canaux")
c = mediacenter.commande_externe("/usr/bin/mpv", "/films/Dune.mkv", 1234.6, 1)
assert c == ["/usr/bin/mpv", "--fs", "--start=1235", "--aid=2", "--audio-spdif=ac3,eac3,dts,dts-hd,truehd", "--",
             str(Path("/films/Dune.mkv").resolve())], c  # chemin absolu à la façon du système (D:\\films\\… sous Windows)
c = mediacenter.commande_externe("C:/VLC/vlc.exe", "/films/-bizarre.mkv", 60, 0)
assert c[:4] == ["C:/VLC/vlc.exe", "--fullscreen", "--start-time=60", "--audio-track=0"] and c[-1].endswith("-bizarre.mkv"), c
assert mediacenter.trouver_lecteur("/chemin/qui/nexiste/pas.exe") is None
mediacenter.LIB["films"] = [("Dune", "", "/films/Dune.mkv")]
assert mediacenter.valider_externe({"kind": "films", "id": 0, "t": 10, "piste": 1}) == ("films", 0, "/films/Dune.mkv", 10.0, 1)
assert mediacenter.commande_externe("/usr/bin/mpv", "/f.mkv", 0, 0, "/tmp/x.sock")[-3:] == [
    "--input-ipc-server=/tmp/x.sock", "--", str(Path("/f.mkv").resolve())]
for mauvais in ({"kind": "films", "id": 5}, {"kind": "musique", "id": 0}, {"kind": "films", "id": 0, "t": -1},
                {"kind": "films", "id": 0, "piste": "1; rm -rf"}):
    try:
        mediacenter.valider_externe(mauvais)
        raise AssertionError(mauvais)
    except (ValueError, KeyError):
        pass
c = mediacenter.commande_externe("/usr/bin/vlc", "/f.mkv", 5, 1, http=(8800, "mdp"))
assert "--http-port=8800" in c and "--http-password=mdp" in c and "--http-host=127.0.0.1" in c and c[-1].endswith("f.mkv"), c
etat = {"information": {"category": {"meta": {}, "Stream 0": {"Type": "Video"},
        "Stream 2": {"Type": "Audio", "Language": "English", "Codec": "Vorbis Audio (vorb)"},
        "Stream 1": {"Type": "Audio", "Language": "French", "Codec": "A52 Audio (aka AC3) (a52 )"},
        "Stream 3": {"Type": "Subtitle", "Language": "French", "Codec": "Text subtitles (subt)"}}}}
assert mediacenter.pistes_vlc(etat) == ([(1, "Français (A52 Audio)"), (2, "Anglais (Vorbis Audio)")], [(3, "Français")])
assert mediacenter.pistes_vlc({}) == ([], [])
# Analyse incrémentale : les nouveaux fichiers s'ajoutent sans changer les numéros existants ; affichage trié.
with tempfile.TemporaryDirectory() as d:
    D = Path(d)
    (D / "Lost").mkdir()
    (D / "Lost" / "Lost.S01E02.mkv").write_bytes(b"")
    (D / "Zorro.2000.mkv").write_bytes(b"")
    for k in mediacenter.LIB:
        mediacenter.LIB[k] = []
    assert mediacenter.scan({"series": [d]}) == 2
    avant = list(mediacenter.LIB["series"])
    (D / "Lost" / "Lost.S01E01.mkv").write_bytes(b"")
    assert mediacenter.scan({"series": [d]}) == 1 and mediacenter.scan({"series": [d]}) == 0
    assert mediacenter.LIB["series"][:2] == avant  # numéros existants inchangés
    o = mediacenter.ordre("series")
    assert [mediacenter.LIB["series"][i][:2] for i in o] == [("Zorro", "Divers"), ("S01E01", "Lost"), ("S01E02", "Lost")]
    e1 = next(i for i, x in enumerate(mediacenter.LIB["series"]) if x[0] == "S01E01")
    e2 = next(i for i, x in enumerate(mediacenter.LIB["series"]) if x[0] == "S01E02")
    assert mediacenter.episode_suivant("series", e1) == e2 and mediacenter.episode_suivant("series", e2) is None
with tempfile.TemporaryDirectory() as d:
    ancien, mediacenter.POLICES_DIR = mediacenter.POLICES_DIR, Path(d)
    try:
        for nom, age in (("vieux", 90), ("recent", 5)):
            (Path(d) / nom).mkdir()
            (Path(d) / nom / "0.ttf").write_bytes(b"x")
            t = time.time() - age * 86400
            os.utime(Path(d) / nom, (t, t))
        mediacenter.nettoyer_polices()
        assert [x.name for x in Path(d).iterdir()] == ["recent"]
    finally:
        mediacenter.POLICES_DIR = ancien
assert mediacenter.jeton_pin("1234", "sel") == mediacenter.jeton_pin("1234", "sel") != mediacenter.jeton_pin("1235", "sel")
mediacenter.ECHECS.clear()
for _ in range(9):
    mediacenter.noter_echec("1.2.3.4")
assert not mediacenter.trop_d_essais("1.2.3.4")
mediacenter.noter_echec("1.2.3.4")
assert mediacenter.trop_d_essais("1.2.3.4") and not mediacenter.trop_d_essais("5.6.7.8")
assert not mediacenter.trop_d_essais("1.2.3.4", time.time() + 301)  # débloqué après 5 minutes
# Accueil : reprendre (le plus récent d'abord), épisode suivant après le dernier vu, ajoutés récemment (1 carte par série)
m = mediacenter
m.LIB.update(films=[("Dune", "", "/f/Dune.mkv"), ("Alien", "", "/f/Alien.mkv")], musique=[],
             series=[("S01E01", "Lost", "/s/L1.mkv"), ("S01E02", "Lost", "/s/L2.mkv"), ("S01E03", "Lost", "/s/L3.mkv"),
                     ("S01E01", "Dark", "/s/D1.mkv")])
m.SUIVI.clear()
m.SUIVI.update({"Dune.mkv": {"t": 600, "d": 6000, "quand": 10}, "Alien.mkv": {"t": 100, "d": 6000, "quand": 20},
                "L1.mkv": {"vu": True, "t": 0, "quand": 5}, "D1.mkv": {"vu": True, "t": 0, "quand": 1}})
m.AJOUT.clear()
m.AJOUT.update({"/f/Dune.mkv": 1, "/f/Alien.mkv": 2, "/s/L1.mkv": 3, "/s/L2.mkv": 9, "/s/L3.mkv": 4, "/s/D1.mkv": 8})
m.META.update({"Dune.mkv": {"affiche": "d.jpg"}, "serie:Lost": {"affiche": "l.jpg"}, "serie:Dark": {"affiche": "k.jpg"}})
rangs = dict(m.accueil())
assert [c[2] for c in rangs["▶ Reprendre"]] == ["Alien", "Dune"]  # plus récent d'abord
assert rangs["▶ Reprendre"][1][4] == 10 and rangs["▶ Reprendre"][1][0] == "/?k=films&jouer=0"  # 10 % vu
assert [(c[2], c[3]) for c in rangs["⏭ Épisodes suivants"]] == [("Lost", "S01E02")]  # Dark : plus d'épisode après
assert rangs["⏭ Épisodes suivants"][0][0] == "/?k=series&s=Lost&jouer=1"
assert [c[2] for c in rangs["🆕 Ajoutés récemment"]] == ["Lost", "Dark", "Dune"]  # Lost une seule fois ; Alien sans affiche
assert [c[2] for c in rangs["📺 Séries"]] == ["Dark", "Lost"]
for k in ("Dune.mkv", "serie:Lost", "serie:Dark"): m.META.pop(k)
pl = mediacenter.playlist_hls(15.5)
assert pl.splitlines()[-1] == "#EXT-X-ENDLIST" and pl.count(".ts") == 3 and "#EXTINF:3.500," in pl, pl
c = mediacenter.commande_segment("/f.avi", 2)
assert c[c.index("-ss") + 1] == "12" and c[c.index("-output_ts_offset") + 1] == "12" and c[c.index("-t") + 1] == "6"
try:
    img = mediacenter.image_icone()
    assert img.size == (64, 64) and img.getpixel((32, 32))[:3] == (255, 255, 255) and img.getpixel((8, 32))[:3] == (229, 9, 20)
except ImportError:
    pass  # Pillow absent : pas d'icône, rien à vérifier
assert "--sans-navigateur" in mediacenter.commande_demarrage()
if os.name == "nt":  # vraie clé de registre de l'utilisateur : posée puis retirée
    avant = mediacenter.demarrage_auto()
    assert mediacenter.demarrage_auto(True) and mediacenter.demarrage_auto()
    assert not mediacenter.demarrage_auto(False) and not mediacenter.demarrage_auto()
    mediacenter.demarrage_auto(avant)
# Un 2e serveur sur le même port doit échouer (Windows compris), pour que le 2e lancement ouvre juste le navigateur.
from http.server import BaseHTTPRequestHandler
s1 = mediacenter.Serveur(("127.0.0.1", 0), BaseHTTPRequestHandler)
try:
    mediacenter.Serveur(("127.0.0.1", s1.server_address[1]), BaseHTTPRequestHandler)
    raise AssertionError("deux serveurs sur le même port")
except OSError:
    pass
finally:
    s1.server_close()
# Langue : seule l'interface est traduite ; détection de l'espagnol par le système
m = mediacenter
if os.name != "nt":
    ancien = dict(os.environ)
    try:
        for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
            os.environ.pop(v, None)
        os.environ["LANG"] = "es_ES.UTF-8"
        assert m.langue_systeme() == "es"
        os.environ["LANG"] = "fr_FR.UTF-8"
        assert m.langue_systeme() == "fr"
    finally:
        os.environ.clear()
        os.environ.update(ancien)
m.LANGUE[0] = "es"
assert m.tr("Vu / pas vu") == "Visto / no visto" and m.tr("titre inconnu") == "titre inconnu"
assert "Películas (" in m.gabarit() and "🌐 Français" in m.gabarit() and 'lang="es"' in m.gabarit()
assert m.nom_piste({"tags": {"language": "fre"}}) == "Francés" and m.nom_piste({}, "Piste") == "Pista"
m.LANGUE[0] = "fr"
assert m.tr("Vu / pas vu") == "Vu / pas vu" and "Films (" in m.gabarit()
# Garde-fou : traduire() ne doit jamais toucher au code des pages (noms de variables, classes, identifiants).
import re as _re
code = "".join((Path(mediacenter.WEB_DIR) / f).read_text("utf-8") for f in ("app.js", "nav.js", "page.html", "style.css"))
noms_code = set(_re.findall(r"[A-Za-zÀ-ÿ_][\wÀ-ÿ]*", _re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|>[^<]*<|//[^\n]*|/\*.*?\*/", " ", code, flags=_re.S)))
dangereuses = [k for k in mediacenter.ES if _re.fullmatch(r"[\wÀ-ÿ]+", k) and k in noms_code]
assert not dangereuses, dangereuses
m.LANGUE[0] = "es"
assert "'vu'" in mediacenter.traduire(code) and 'id="nonvus"' in mediacenter.traduire('<input type="checkbox" id="nonvus"> Non vus')
m.LANGUE[0] = "fr"
# Profils : suivi séparé ; un profil inconnu (cookie trafiqué) retombe sur « Principal »
m.PROFILS[:] = ["Ana"]
m.ACTUEL.profil = "Ana"
assert m.S() is not m.SUIVI and m.S() == {} and m.fichier_suivi("Ana") != m.SUIVI_F
m.S()["x.mkv"] = {"vu": True}
m.ACTUEL.profil = "Intrus"
assert m.S() is m.SUIVI
m.ACTUEL.profil = ""
assert "x.mkv" not in m.S()
assert m.valider_profil("  Lucía  ") == "Lucía"
for mauvais in ("", "Principal", "a/b", "x" * 31, "<script>"):
    try:
        m.valider_profil(mauvais)
        raise AssertionError(mauvais)
    except ValueError:
        pass
m.PROFILS[:] = []
c = mediacenter.commande_winget("ffmpeg")
assert c[1:5] == ["install", "-e", "--id", "Gyan.FFmpeg"] and "--accept-package-agreements" in c
assert mediacenter.commande_winget("vlc")[4] == "VideoLAN.VLC"
assert mediacenter.lire_release({"tag_name": "build-42", "html_url": "https://x/r", "assets": [
    {"name": "notes.txt", "browser_download_url": "a"}, {"name": "MediaCenter.exe", "browser_download_url": "https://x/e"}]}) == (42, "https://x/r", "https://x/e")
assert mediacenter.lire_release({}) == (0, "", None)
assert "1.ts?mc=abc" in mediacenter.playlist_hls(10, "?mc=abc")
assert mediacenter.ip_lan() == "" or mediacenter.ip_lan().count(".") == 3
# Diagnostic : ne plante jamais, même sans internet ni dossiers
m.CFG.clear()
d = m.diagnostic(complet=False)
assert any(x[1] == "Dossiers" and x[0] == "❌" for x in d) and any(x[1] == "ffmpeg" for x in d)
with tempfile.TemporaryDirectory() as dd:
    m.CFG.update(films=[dd, dd + "/absent"])
    d = m.diagnostic(complet=False)
    assert [x[0] for x in d if x[1] == "Dossier Films"] == ["✅", "❌"]
m.CFG.clear()
assert m.tester_url("http://127.0.0.1:9/") != "ok"
# Sauvegarde : export puis import (même dossier remis à zéro), noms piégés refusés
import io as _io, json as _json, zipfile as _zip
from pathlib import Path as _P
_avant = {k: getattr(m, k) for k in ("BASE", "CONFIG", "CACHE", "SUIVI_F", "FILE_F", "ENCOURS_F")}
with tempfile.TemporaryDirectory() as dd:
    b = _P(dd)
    m.BASE, m.CONFIG, m.CACHE, m.SUIVI_F = b, b / "mediacenter.json", b / "mediacenter_cache.json", b / "mediacenter_suivi.json"
    m.FILE_F, m.ENCOURS_F = b / "mediacenter_file.json", b / "mediacenter_encours.json"
    m.CONFIG.write_text(_json.dumps({"profils": ["Ana"]}))
    m.SUIVI_F.write_text(_json.dumps({"film.mkv": {"t": 10, "vu": True}}))
    (b / "mediacenter.log").write_text("x")
    z = m.exporter_sauvegarde()
    assert sorted(_zip.ZipFile(_io.BytesIO(z)).namelist()) == ["mediacenter.json", "mediacenter_suivi.json"]
    m.SUIVI_F.unlink(); m.CONFIG.write_text("{}"); m.charger_etat()
    assert m.PROFILS == [] and m.SUIVI == {}
    assert m.importer_sauvegarde(z) == 2 and m.PROFILS == ["Ana"] and m.SUIVI["film.mkv"]["vu"] and m.SUIVIS[""] is m.SUIVI
    for nom in ("../mediacenter.json", "autre.json"):
        t = _io.BytesIO()
        with _zip.ZipFile(t, "w") as zz:
            zz.writestr("mediacenter.json", "{}"); zz.writestr(nom, "{}")
        try:
            m.importer_sauvegarde(t.getvalue()); assert False
        except ValueError:
            pass
    assert not (b.parent / "mediacenter.json").exists() and _json.loads(m.CONFIG.read_text()) == {"profils": ["Ana"]}
for k, v in _avant.items():
    setattr(m, k, v)
m.PROFILS.clear(); m.SUIVI.clear()
# Listes de lecture : noms vérifiés
assert m.valider_nom_liste("  Fiesta ") == "Fiesta"
for mauvais in ("", " ", "x" * 51, "<b>", None, 3):
    try:
        m.valider_nom_liste(mauvais); assert False
    except ValueError:
        pass
# Contrôle parental : profil enfant filtré, code exigé pour changer les réglages
_lib = {k: list(v) for k, v in m.LIB.items()}
m.LIB["films"][:] = [("Nemo", "", "/x/nemo.mkv"), ("Alien", "", "/x/alien.mkv"), ("Inconnu", "", "/x/inconnu.mkv")]
m.META.update({"nemo.mkv": {"genres": ["Animation"]}, "alien.mkv": {"genres": ["Horreur"]}})
m.PROFILS[:] = ["Léo"]
try:
    m.regler_parental({"enfants": ["Léo"], "pin": ""}); assert False  # pas de code : refusé
except ValueError:
    pass
r = m.regler_parental({"enfants": ["Léo"], "pin": "4242"}); m.charger_parental(r)
assert m.ENFANTS == {"Léo"}
try:
    m.regler_parental({"enfants": [], "pin": "", "ancien": "0000"}); assert False
except PermissionError:
    pass
m.ACTUEL.profil = "Léo"
assert m.ordre("films") == [0] and not m.permis("films", 1) and m.permis("musique", 0)
m.ACTUEL.profil = ""
assert m.ordre("films") == [1, 2, 0]
m.charger_parental(m.regler_parental({"enfants": [], "pin": "", "ancien": "4242"}))
assert not m.ENFANTS
m.LIB.update(_lib); m.PROFILS.clear(); m.charger_parental({})
# Empreinte OpenSubtitles : comparée à un calcul indépendant (struct, mots de 64 bits)
import struct as _st
def _ref(f):
    d = open(f, "rb").read(); h = len(d)
    for b in (d[:65536], d[-65536:] if len(d) > 65536 else d):
        b += b"\0" * (-len(b) % 8); h += sum(_st.unpack("<%dQ" % (len(b) // 8), b))
    return "%016x" % (h & 0xFFFFFFFFFFFFFFFF)
with tempfile.TemporaryDirectory() as dd:
    for taille in (200_000, 1000):
        f = os.path.join(dd, "v.mkv"); open(f, "wb").write(os.urandom(taille))
        assert m.hash_osub(f) == _ref(f)
# Statistiques : heures (vu = durée entière, sinon position), films par année, artistes
_lib = {k: list(v) for k, v in m.LIB.items()}
m.LIB["films"][:] = [("A", "", "/x/a.mkv"), ("B", "", "/x/b.mkv")]
m.LIB["series"][:] = [("S01E01", "Lost", "/x/l1.mkv")]
m.META.update({"a.mkv": {"annee": "1999"}})
m.SUIVI.update({"a.mkv": {"vu": True, "d": 7200}, "b.mkv": {"t": 1800}, "l1.mkv": {"vu": True, "d": 1800}, "absent.mkv": {"vu": True, "d": 9e9}})
m.ECOUTES.update({"Queen/a.mp3": 3, "Queen/b.mp3": 2, "Abba/c.mp3": 4})
st = m.stats()
assert st["heures"] == 3.0 and st["films"] == 1 and st["episodes"] == 1 and st["par_annee"] == [("1999", 1)]
assert st["artistes"][0] == ("Queen", 5) and st["morceaux"][0] == ("c", 4) and st["ecoutes"] == 9
m.LIB.update(_lib); m.SUIVI.clear(); m.ECOUTES.clear()
# Dossiers ajoutés / retirés depuis la page : fichiers masqués et plus servis, config à jour
_conf = m.CONFIG
with tempfile.TemporaryDirectory() as dd:
    from pathlib import Path as _P
    m.CONFIG = _P(dd) / "mediacenter.json"
    a, b = _P(dd) / "A", _P(dd) / "B"
    a.mkdir(); b.mkdir(); (a / "Un.2020.mp4").write_bytes(b"x"); (b / "Deux.2021.mp4").write_bytes(b"x")
    _lib = list(m.LIB["films"]); m.LIB["films"].clear(); m.DOSSIERS.clear(); m.DOSSIERS.update(films=[str(a)], series=[], musique=[])
    m.scan(m.DOSSIERS)
    assert m.ajouter_dossier("films", str(b)) == str(b.resolve())
    for _ in range(50):
        if len(m.LIB["films"]) == 2: break
        time.sleep(0.05)
    assert len(m.ordre("films")) == 2 and _json.loads(m.CONFIG.read_text())["films"] == [str(a), str(b.resolve())]
    m.retirer_dossier("films", str(b.resolve()))
    assert [m.LIB["films"][i][0] for i in m.ordre("films")] == ["Un"]
    for mauvais in (("films", str(_P(dd) / "absent")), ("autre", str(a))):
        try:
            m.ajouter_dossier(*mauvais); assert False
        except ValueError:
            pass
    m.LIB["films"][:] = _lib; m.DOSSIERS.clear()
m.CONFIG = _conf
# Grille : les affiches ont une taille fixe (sinon elles s'affichent en taille réelle et cachent les titres)
import re as _re2
_css = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "style.css"), encoding="utf-8").read()
assert _re2.search(r"ul\.grid img[^{]*\{[^}]*width:100%[^}]*aspect-ratio:2/3", _css)
# Dossier de téléchargements rangé dans les films : les épisodes (S01E02) vont dans les séries, et restent visibles
with tempfile.TemporaryDirectory() as dd:
    from pathlib import Path as _P
    dl = _P(dd) / "Download"; (dl / "Friends.Sex.and.Games.S01.MULTi.1080p.WEB.H265-GL0P").mkdir(parents=True)
    for n in (1, 2):
        (dl / "Friends.Sex.and.Games.S01.MULTi.1080p.WEB.H265-GL0P" / f"Friends.Sex.and.Games.S01E0{n}.MULTi.1080p.WEB.H265-GL0P.mkv").write_bytes(b"x")
    (dl / "Inception.2010.1080p.mkv").write_bytes(b"x")
    _lib = {k: list(v) for k, v in m.LIB.items()}
    for k in m.LIB: m.LIB[k].clear()
    m.DOSSIERS.clear(); m.DOSSIERS.update(films=[str(dl)], series=[str(dl)], musique=[])  # même dossier dans les deux : pas de doublon
    assert m.scan(m.DOSSIERS) == 3 and m.scan(m.DOSSIERS) == 0
    assert [t for t, _, _ in m.LIB["films"]] == ["Inception"]
    assert [(d, t) for t, d, _ in m.LIB["series"]] == [("Friends Sex and Games", "S01E01"), ("Friends Sex and Games", "S01E02")]
    m.DOSSIERS["series"] = []
    assert len(m.ordre("series")) == 2  # visibles même sans dossier de séries
    m.LIB.update(_lib); m.DOSSIERS.clear()
# Disque entier en films + séries + musique, avec un sous-dossier aussi configuré : parcouru une fois, sans doublon,
# dossiers système sautés
with tempfile.TemporaryDirectory() as dd:
    from pathlib import Path as _P
    H = _P(dd) / "H"
    for f in ("Film Français/Amelie.2001.mkv", "Series/Lost/Lost.S01E01.mkv", "Musique/Queen/Bohemian.mp3",
              "$RECYCLE.BIN/Vieux.2000.mkv", "Windows/x.mp3", ".cache/y.mkv", "Divers.2019.mp4"):
        (H / f).parent.mkdir(parents=True, exist_ok=True); (H / f).write_bytes(b"x")
    _lib = {k: list(v) for k, v in m.LIB.items()}
    for k in m.LIB: m.LIB[k].clear()
    m.DOSSIERS.clear(); m.DOSSIERS.update(films=[str(H / "Film Français"), str(H)], series=[str(H)], musique=[str(H)])
    assert m.scan(m.DOSSIERS) == 4, m.LIB
    assert sorted(t for t, _, _ in m.LIB["films"]) == ["Amelie", "Divers"]
    assert [(d, t) for t, d, _ in m.LIB["series"]] == [("Lost", "S01E01")]
    assert [(t, d) for t, d, _ in m.LIB["musique"]] == [("Bohemian", os.path.join("Musique", "Queen"))]
    assert m.dans(str(H / "Film Français" / "a.mkv"), str(H)) and not m.dans(str(H) + "2/a.mkv", str(H))
    m.LIB.update(_lib); m.DOSSIERS.clear()
# Relance après mise à jour : pas de variables PyInstaller de l'ancien .exe (sinon « Failed to load Python DLL »)
os.environ.update(_PYI_APPLICATION_HOME_DIR="C:/x/_MEI123", _MEIPASS2="C:/x/_MEI123")
e = m.env_neuf()
assert not any(k.startswith(("_PYI", "_MEI")) for k in e) and e["PYINSTALLER_RESET_ENVIRONMENT"] == "1" and "PATH" in e
del os.environ["_PYI_APPLICATION_HOME_DIR"], os.environ["_MEIPASS2"]
# Windows : aucun programme lancé n'ouvre de fenêtre de terminal (ffmpeg toutes les 6 s pendant une conversion)
if os.name == "nt":
    import subprocess as _sp
    assert _sp.Popen.__name__ == "_PopenSansFenetre"
    assert _sp.run(["cmd", "/c", "exit 3"]).returncode == 3
# Autres vidéos : WhatsApp / téléphone / petites vidéos / dossier choisi / choix à la main ; les films restent films
for nom in ("VID-20231105-WA0012.mp4", "WhatsApp Video 2023-11-05 at 10.12.33.mp4", "PXL_20230101_101010.mp4",
            "IMG_1234.MOV", "VID_20240202_120000.mp4", "Grabación 2026-11-24 202632.mp4", "20230506_153012.mp4"):
    assert m.est_autre("/x/" + nom), nom
for nom in ("Inception.2010.1080p.mkv", "Amelie.mkv", "Le.Pacte.2015.mkv", "Video.Killed.the.Radio.Star.1999.mkv"):
    assert not m.est_autre("/x/" + nom), nom
m.TAILLE["/x/Formation.Excel.mp4"] = 50e6; assert m.est_autre("/x/Formation.Excel.mp4")
m.DOSSIERS["autres"] = [os.path.join(os.sep, "x", "Formations")]
assert m.est_autre(os.path.join(os.sep, "x", "Formations", "Module.1.mp4"))
m.AUTRES[os.path.join(os.sep, "x", "Formations", "Vrai.Film.mkv")] = False
assert not m.est_autre(os.path.join(os.sep, "x", "Formations", "Vrai.Film.mkv"))
m.AUTRES["/x/Inception.mkv"] = True; assert m.est_autre("/x/Inception.mkv")
m.AUTRES.clear(); m.TAILLE.clear(); m.DOSSIERS.clear()
print("OK")
