"""python test_mediacenter.py"""
from mediacenter import nettoyer, choisir, choisir_tmdb

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
print("OK")
