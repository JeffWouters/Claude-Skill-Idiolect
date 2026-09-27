#!/usr/bin/env python3
"""Build the native-prose fixtures for the language-flavour false-alarm test.

Fetches public-domain essays, articles, feuilletons, letters and narrative prose in German, French,
Spanish, Italian, Portuguese, Polish, Russian, Ukrainian, Turkish, Swedish, Norwegian (Bokmål/Riksmål,
code nb, from no.wikisource.org) and Danish from Wikisource and writes one Markdown file per piece to
evals/fixtures/native-<lang>/.

Every text in SOURCES is by an author who died before 1956 and was first published before 1929,
so it is in the public domain in the US and the EU.

Usage:
    python3 tools/build_native_fixtures.py                 # fetch (cached) and write all fixtures
    python3 tools/build_native_fixtures.py --lang de       # one language only
    python3 tools/build_native_fixtures.py --probe TITLE --lang fr   # print the cleaned text of a page
    python3 tools/build_native_fixtures.py --links TITLE --lang es   # list the main-namespace links of a page

Wikimedia rate-limits clients: every request sends a User-Agent, pauses one second, and on HTTP 429
waits the Retry-After seconds. Pages are rendered in batches (one parse call transcludes several
pages), and responses are cached (default: ~/.cache/idiolect-native-fixtures) so reruns are cheap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "fixtures"
UA = "IdiolectFixtureBuilder/1.0 (https://github.com/JeffWouters/Claude-Skill-Idiolect)"
LICENCE = "public domain (US and EU)"
LANGS = ["de", "fr", "es", "it", "pt", "pl", "ru", "uk", "tr", "sv", "nb", "da"]
# fixture language code -> Wikisource subdomain, where they differ
HOST = {"nb": "no"}
# languages whose fixtures were built and reviewed before the cleaning rules below were added;
# paragraphs() keeps their original behaviour so that a rebuild gives the same files
LEGACY = {"de", "fr", "es"}

# (lang, page title, author, died, book, first published, display title or None)
# The display title defaults to the last part of the page title without a disambiguator.
SOURCES: list[tuple[str, str, str, int, str, int, str | None]] = [
    # ---------------------------------------------------------------- German
    ("de", "Traktat über den Hund", "Kurt Tucholsky", 1935, "Die Weltbühne", 1927, None),
    ("de", "Traktat über Lerm und Geräusch", "Kurt Tucholsky", 1935, "Die Weltbühne", 1927, None),
    ("de", "Was darf die Satire? (Tucholsky)", "Kurt Tucholsky", 1935, "Berliner Tageblatt", 1919, None),
    ("de", "Die Flecke", "Kurt Tucholsky", 1935, "Berliner Volkszeitung", 1919, None),
    ("de", "Der Obermieter", "Kurt Tucholsky", 1935, "Prager Tagblatt", 1922, None),
    ("de", "Der berühmteste Mann der Welt", "Kurt Tucholsky", 1935, "Prager Tagblatt", 1922, None),
    ("de", "Ein deutsches Volkslied", "Kurt Tucholsky", 1935, "Prager Tagblatt", 1922, None),
    ("de", "Vormärz", "Kurt Tucholsky", 1935, "Die Schaubühne", 1914, None),
    ("de", "Wir Negativen (Tucholsky)", "Kurt Tucholsky", 1935, "Die Weltbühne", 1919, None),
    ("de", "Fütterung der Raubtiere", "Kurt Tucholsky", 1935, "Die Weltbühne", 1920, None),
    ("de", "Die Dicken", "Kurt Tucholsky", 1935, "Die Weltbühne", 1921, None),
    ("de", "Der Hund als Untergebener", "Kurt Tucholsky", 1935, "Die Weltbühne", 1922, None),
    ("de", "Zehn Minuten (Tucholsky)", "Kurt Tucholsky", 1935, "Die Weltbühne", 1922, None),
    ("de", "Der Linksdenker", "Kurt Tucholsky", 1935, "Die Weltbühne", 1924, None),
    ("de", "Außenseiter der Gesellschaft (Weltbühne)", "Kurt Tucholsky", 1935, "Die Weltbühne", 1925, None),
    ("de", "Der Namensfimmel", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Berliner auf Reisen", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Alte Filme", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Der politische Rundfunk", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Der Hund und der Blinde", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Herr Schwejk", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Typographisches", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Ein Indianerbuch der Technik", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Siegfried Jacobsohn †", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Katzenmutter in Paris", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1926, None),
    ("de", "Der Brötchentanz", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1925, None),
    ("de", "Der sinnlose Film", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1928, None),
    ("de", "Der Katzentrust", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1928, None),
    ("de", "... à la Bratianu", "Carl von Ossietzky", 1938, "Die Weltbühne", 1926, "… à la Bratianu"),
    ("de", "Sexual-Kochbücher (Ossietzky)", "Carl von Ossietzky", 1938, "Die Weltbühne", 1927, None),
    ("de", "Klabund (Ossietzky)", "Carl von Ossietzky", 1938, "Die Weltbühne", 1928, None),
    ("de", "Die Chinesische Mauer", "Karl Kraus", 1936, "Die Fackel", 1909, None),
    ("de", "Peter Altenberg (Grabrede von Karl Kraus)", "Karl Kraus", 1936, "Die Fackel", 1919, "Peter Altenberg"),
    ("de", "Die Straße des Ruhms", "Ludwig Bauer", 1935, "Die Schaubühne", 1905, None),
    # ---------------------------------------------------------------- French
    ("fr", "Propos sur le Bonheur/Bucéphale", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Agir", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Amitié", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Attitudes", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Bonne humeur", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/De l’irrésolution", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Des passions", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Devoir d’être heureux", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Diogène", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Espérance", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Gymnastique", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Faire plaisir", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Hercule", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Dénouer", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Drames", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Du désespoir", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Consolation", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Connais-toi", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Accidents", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Bienveillance", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Promenades Littéraires (Gourmont)/De la fécondité littéraire", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Les Contes de fées", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/La Femme naturelle", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Renan et l’idée scientifique", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Un homme qui pense", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Il pleut, il pleut, bergère", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/La beauté de la mer", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "Promenades Littéraires (Gourmont)/L’architecture", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "Promenades Littéraires (Gourmont)/L’adoucissement des mœurs", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "Promenades Littéraires (Gourmont)/Les parchemins du féminisme", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "La Rentrée (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1898, None),
    ("fr", "Défaite en échelons", "Charles Péguy", 1914, "La Revue blanche", 1898, None),
    ("fr", "Règlement de juges", "Charles Péguy", 1914, "La Revue blanche", 1898, None),
    ("fr", "Service militaire (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1899, None),
    ("fr", "L’Opinion publique (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1899, None),
    ("fr", "Associations (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1899, None),
    ("fr", "Idées générales", "Octave Mirbeau", 1917, "La Vache tachetée", 1886, None),
    ("fr", "Vers le bonheur", "Octave Mirbeau", 1917, "La Vache tachetée", 1887, None),
    ("fr", "Mon jardinier", "Octave Mirbeau", 1917, "La Vache tachetée", 1893, None),
    ("fr", "Le Concombre fugitif", "Octave Mirbeau", 1917, "La Vache tachetée", 1894, None),
    ("fr", "Explosif et baladeur", "Octave Mirbeau", 1917, "La Vache tachetée", 1894, None),
    ("fr", "En attendant l’omnibus", "Octave Mirbeau", 1917, "La Vache tachetée", 1896, None),
    # ---------------------------------------------------------------- Spanish
    ("es", "Mi religión", "Miguel de Unamuno", 1936, "Mi religión y otros ensayos breves", 1907, None),
    ("es", "Verdad y vida", "Miguel de Unamuno", 1936, "Mi religión y otros ensayos breves", 1908, None),
    ("es", "¡Adentro!", "Miguel de Unamuno", 1936, "Tres ensayos", 1900, None),
    ("es", "La crisis actual del patriotismo español", "Miguel de Unamuno", 1936, "Nuestro Tiempo", 1905, None),
    ("es", "Sobre la tumba de Costa", "Miguel de Unamuno", 1936, "Sobre la tumba de Costa", 1911, None),
    ("es", "Con Don Quijote en Sigüenza", "Miguel de Unamuno", 1936, "El Imparcial", 1916, None),
    ("es", "La Kultura y la cultura", "Miguel de Unamuno", 1936, "La Kultura y la cultura", 1913, None),
    ("es", "El anti-maquetismo", "Miguel de Unamuno", 1936, "Heraldo de Madrid", 1898, None),
    ("es", "Méjico y no México", "Miguel de Unamuno", 1936, "Méjico y no México", 1898, None),
    ("es", "España protegida", "Miguel de Unamuno", 1936, "España protegida", 1918, None),
    ("es", "Confesión de culpa", "Miguel de Unamuno", 1936, "El Día", 1917, None),
    ("es", "De las luchas de nuestros días. La res humana", "Miguel de Unamuno", 1936, "De las luchas de nuestros días", 1920, None),
    ("es", "Nuestra América", "José Martí", 1895, "La Revista Ilustrada de Nueva York", 1891, None),
    ("es", "Vindicación de Cuba", "José Martí", 1895, "Vindicación de Cuba", 1889, None),
    ("es", "La verdad sobre los Estados Unidos", "José Martí", 1895, "Patria", 1894, None),
    ("es", "Karl Marx (José Martí)", "José Martí", 1895, "La Nación", 1883, None),
    ("es", "Maestros ambulantes", "José Martí", 1895, "La América", 1884, None),
    ("es", "Educación científica", "José Martí", 1895, "La América", 1883, None),
    ("es", "Mi raza", "José Martí", 1895, "Patria", 1893, None),
    ("es", "La futura esclavitud", "José Martí", 1895, "La América", 1884, None),
    ("es", "A aprender en las haciendas", "José Martí", 1895, "La América", 1883, None),
    ("es", "El tercer año del partido revolucionario cubano", "José Martí", 1895, "Patria", 1894, None),
    ("es", "Prólogo al Poema del Niágara", "José Martí", 1895, "Poema del Niágara", 1882, None),
    ("es", "Carta a Manuel Mercado", "José Martí", 1895, "Cartas", 1895, None),
    ("es", "Granada la bella/01", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Puntos de vista"),
    ("es", "Granada la bella/02", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Lo viejo y lo nuevo"),
    ("es", "Granada la bella/03", "Ángel Ganivet", 1898, "Granada la bella", 1896, "¡Agua!"),
    ("es", "Granada la bella/04", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Luz y sombra"),
    ("es", "Granada la bella/05", "Ángel Ganivet", 1898, "Granada la bella", 1896, "No hay que ensancharse"),
    ("es", "Granada la bella/06", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Nuestro carácter"),
    ("es", "Granada la bella/07", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Nuestro arte"),
    ("es", "Granada la bella/08", "Ángel Ganivet", 1898, "Granada la bella", 1896, "¿Qué somos?"),
    ("es", "Granada la bella/09", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Parrafada filosófica ante una estación de ferrocarril"),
    ("es", "Granada la bella/10", "Ángel Ganivet", 1898, "Granada la bella", 1896, "El constructor espiritual"),
    ("es", "Granada la bella/11", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Monumentos"),
    ("es", "Granada la bella/12", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Lo eterno femenino"),
    ("es", "Cuadros de viaje", "José Ortega y Gasset", 1955, "Artículos (1915)", 1915, None),
    ("es", "La guerra, los pueblos y los dioses", "José Ortega y Gasset", 1955, "Artículos (1915)", 1915, None),
    ("es", "La voluntad del barroco", "José Ortega y Gasset", 1955, "Artículos (1915)", 1915, None),
    ("es", "París nocturno", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Mi domingo de Ramos", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Hombres y pájaros", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Visiones pasadas", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Primavera apolínea", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Curiosidades literarias", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    # ---------------------------------------------------------------- Italian
    ("it", "Novelle rusticane/La roba", "Giovanni Verga", 1922, "Novelle rusticane", 1880, None),
    ("it", "Novelle rusticane/Malaria", "Giovanni Verga", 1922, "Novelle rusticane", 1883, None),
    ("it", "Novelle rusticane/Libertà", "Giovanni Verga", 1922, "Novelle rusticane", 1882, None),
    ("it", "Novelle rusticane/Il Reverendo", "Giovanni Verga", 1922, "Novelle rusticane", 1883, None),
    ("it", "La giara (Novella, 1928)", "Luigi Pirandello", 1936, "Novelle per un anno", 1909, None),
    ("it", "La paura del sonno", "Luigi Pirandello", 1936, "Novelle per un anno", 1900, None),
    ("it", "Pensaci, Giacomino! (Novella, 1928)", "Luigi Pirandello", 1936, "Novelle per un anno", 1910, None),
    ("it", "Non è una cosa seria", "Luigi Pirandello", 1936, "Novelle per un anno", 1910, None),
    ("it", "La lega disciolta", "Luigi Pirandello", 1936, "Novelle per un anno", 1910, None),
    ("it", "La novella del buon vecchio e della bella fanciulla ed altri scritti/Vino generoso", "Italo Svevo", 1928,
     "La novella del buon vecchio e della bella fanciulla ed altri scritti", 1927, None),
    # ---------------------------------------------------------------- Portuguese
    ("pt", "A Cartomante", "Machado de Assis", 1908, "Várias histórias", 1884, None),
    ("pt", "Uns Braços", "Machado de Assis", 1908, "Várias histórias", 1885, None),
    ("pt", "Um homem célebre", "Machado de Assis", 1908, "Várias histórias", 1888, None),
    ("pt", "Conto de Escola", "Machado de Assis", 1908, "Várias histórias", 1884, None),
    ("pt", "O Enfermeiro", "Machado de Assis", 1908, "Várias histórias", 1884, None),
    ("pt", "A causa secreta", "Machado de Assis", 1908, "Várias histórias", 1885, None),
    ("pt", "Missa do galo", "Machado de Assis", 1908, "Páginas recolhidas", 1894, None),
    ("pt", "Os Bruzundangas/I", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "Um grande financeiro"),
    ("pt", "Os Bruzundangas/II", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "A nobreza da Bruzundanga"),
    ("pt", "Os Bruzundangas/III", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "A outra nobreza da Bruzundanga"),
    ("pt", "Os Bruzundangas/IV", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "A política e os políticos da Bruzundanga"),
    ("pt", "Os Bruzundangas/VII", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "A diplomacia da Bruzundanga"),
    ("pt", "Os Bruzundangas/VIII", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "A Constituição"),
    ("pt", "Os Bruzundangas/IX", "Lima Barreto", 1922, "Os Bruzundangas", 1923, "Um mandachuva"),
    # ---------------------------------------------------------------- Polish (pre-1936 spelling: -ja, -ji)
    ("pl", "Kamizelka", "Bolesław Prus", 1912, "Szkice i obrazki", 1882, None),
    ("pl", "Katarynka", "Bolesław Prus", 1912, "Szkice i obrazki", 1880, None),
    ("pl", "Cienie (Prus)", "Bolesław Prus", 1912, "Szkice i obrazki", 1885, None),
    ("pl", "Z legend dawnego Egiptu", "Bolesław Prus", 1912, "Opowiadania wieczorne", 1888, None),
    ("pl", "Siłaczka (Żeromski, 1945)", "Stefan Żeromski", 1925, "Opowiadania", 1891, None),
    ("pl", "Zmierzch (Żeromski, 1945)", "Stefan Żeromski", 1925, "Opowiadania", 1892, None),
    ("pl", "Rozdziobią nas kruki, wrony (1927)", "Stefan Żeromski", 1925, "Opowiadania", 1895, None),
    ("pl", "Sachem (1928)", "Henryk Sienkiewicz", 1916, "Orso. Sachem", 1889, None),
    # ---------------------------------------------------------------- Russian (modern orthography)
    ("ru", "Студент (Чехов)", "Антон Чехов", 1904, "Русские ведомости", 1894, None),
    ("ru", "Тоска (Чехов)", "Антон Чехов", 1904, "Петербургская газета", 1886, None),
    ("ru", "Спать хочется (Чехов)", "Антон Чехов", 1904, "Петербургская газета", 1888, None),
    ("ru", "Смерть чиновника (Чехов)", "Антон Чехов", 1904, "Осколки", 1883, None),
    ("ru", "Злоумышленник (Чехов)", "Антон Чехов", 1904, "Петербургская газета", 1885, None),
    ("ru", "Крыжовник (Чехов)", "Антон Чехов", 1904, "Русская мысль", 1898, None),
    ("ru", "Человек в футляре (Чехов)", "Антон Чехов", 1904, "Русская мысль", 1898, None),
    ("ru", "Душечка (Чехов)", "Антон Чехов", 1904, "Семья", 1899, None),
    ("ru", "Четыре дня (Гаршин)", "Всеволод Гаршин", 1888, "Отечественные записки", 1877, None),
    ("ru", "Сигнал (Гаршин)", "Всеволод Гаршин", 1888, "Северный вестник", 1887, None),
    ("ru", "Красный цветок (Гаршин)", "Всеволод Гаршин", 1888, "Отечественные записки", 1883, None),
    ("ru", "Лёгкое дыхание (Бунин)", "Иван Бунин", 1953, "Русское слово", 1916, None),
    # ---------------------------------------------------------------- Ukrainian (1955-62 editions, modern orthography)
    ("uk", "Твори (Коцюбинський, 1955)/2/Intermezzo", "Михайло Коцюбинський", 1913, "Літературно-науковий вістник", 1909, None),
    ("uk", "Твори (Коцюбинський, 1955)/2/Сміх", "Михайло Коцюбинський", 1913, "Твори (1955)", 1906, None),
    ("uk", "Твори (Коцюбинський, 1955)/2/Він іде", "Михайло Коцюбинський", 1913, "Твори (1955)", 1906, None),
    ("uk", "Твори (Коцюбинський, 1955)/1/Цвіт яблуні", "Михайло Коцюбинський", 1913, "Твори (1955)", 1902, None),
    ("uk", "Твори (Коцюбинський, 1955)/1/На камені", "Михайло Коцюбинський", 1913, "Твори (1955)", 1902, None),
    ("uk", "Твори (Коцюбинський, 1955)/2/Невідомий", "Михайло Коцюбинський", 1913, "Твори (1955)", 1907, None),
    ("uk", "Твори (Франко, 1956–1962)/2/Грицева шкільна наука", "Іван Франко", 1916, "Діло", 1883, None),
    ("uk", "Твори (Франко, 1956–1962)/2/Олівець", "Іван Франко", 1916, "Правда", 1879, None),
    ("uk", "Твори (Франко, 1956–1962)/2/Малий Мирон", "Іван Франко", 1916, "Галицькі образки", 1885, None),
    ("uk", "Твори (Франко, 1956–1962)/2/Під оборогом", "Іван Франко", 1916, "На лоні природи", 1905, None),
    ("uk", "Твори (Франко, 1956–1962)/2/Моя стріча з Олексою", "Іван Франко", 1916, "Дзвін", 1878, None),
    # ---------------------------------------------------------------- Turkish (Latin-script transcriptions)
    ("tr", "Pembe İncili Kaftan", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1917, None),
    ("tr", "Başını Vermeyen Şehit", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1917, None),
    ("tr", "Kütük", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1917, None),
    ("tr", "Topuz", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1917, None),
    ("tr", "Teke Tek", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1917, None),
    ("tr", "Vire", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1917, None),
    ("tr", "Diyet", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1918, None),
    ("tr", "Bahar ve Kelebekler", "Ömer Seyfettin", 1920, "Genç Kalemler", 1911, None),
    ("tr", "Forsa", "Ömer Seyfettin", 1920, "Büyük Mecmua", 1919, None),
    ("tr", "Nâdan", "Ömer Seyfettin", 1920, "Vakit", 1918, None),
    ("tr", "Yuf Borusu Seni Bekliyor", "Ömer Seyfettin", 1920, "İfham", 1919, None),
    ("tr", "Kesik Bıyık", "Ömer Seyfettin", 1920, "Diken", 1918, None),
    ("tr", "Yalnız Efe", "Ömer Seyfettin", 1920, "Yeni Mecmua", 1919, None),
    # ---------------------------------------------------------------- Swedish (post-1906 spelling)
    ("sv", "Samtidsnoveller/Det blå ankaret", "Hjalmar Söderberg", 1941, "Främlingarna", 1902, None),
    ("sv", "Samtidsnoveller/Kyrkoherdens kor", "Hjalmar Söderberg", 1941, "Främlingarna", 1901, None),
    ("sv", "Samtidsnoveller/Generalkonsulns middagar/I", "Hjalmar Söderberg", 1941, "Främlingarna", 1901,
     "Generalkonsulns middagar I"),
    ("sv", "Samtidsnoveller/Generalkonsulns middagar/II", "Hjalmar Söderberg", 1941, "Främlingarna", 1903,
     "Generalkonsulns middagar II"),
    ("sv", "Samtidsnoveller/Generalkonsulns middagar/III", "Hjalmar Söderberg", 1941, "Främlingarna", 1903,
     "Generalkonsulns middagar III"),
    ("sv", "Samtidsnoveller/Generalkonsulns middagar/IV", "Hjalmar Söderberg", 1941, "Främlingarna", 1900,
     "Generalkonsulns middagar IV"),
    ("sv", "Samtidsnoveller/Skalder och folk", "Hjalmar Söderberg", 1941, "Det mörknar över vägen", 1906, None),
    ("sv", "Samtidsnoveller/Det mörknar över vägen", "Hjalmar Söderberg", 1941, "Det mörknar över vägen", 1907, None),
    ("sv", "Samtidsnoveller/Sibyllans grotta", "Hjalmar Söderberg", 1941, "Det mörknar över vägen", 1907, None),
    ("sv", "Kejsarn av Portugallien/Kapitel 01", "Selma Lagerlöf", 1940, "Kejsarn av Portugallien", 1914, "Kejsarn av Portugallien, kapitel 1"),
    ("sv", "Kejsarn av Portugallien/Kapitel 02", "Selma Lagerlöf", 1940, "Kejsarn av Portugallien", 1914, "Kejsarn av Portugallien, kapitel 2"),
    ("sv", "Kejsarn av Portugallien/Kapitel 03", "Selma Lagerlöf", 1940, "Kejsarn av Portugallien", 1914, "Kejsarn av Portugallien, kapitel 3"),
    ("sv", "Kejsarn av Portugallien/Kapitel 04", "Selma Lagerlöf", 1940, "Kejsarn av Portugallien", 1914, "Kejsarn av Portugallien, kapitel 4"),
    ("sv", "Kejsarn av Portugallien/Kapitel 05", "Selma Lagerlöf", 1940, "Kejsarn av Portugallien", 1914, "Kejsarn av Portugallien, kapitel 5"),
    ("sv", "Kejsarn av Portugallien/Kapitel 06", "Selma Lagerlöf", 1940, "Kejsarn av Portugallien", 1914, "Kejsarn av Portugallien, kapitel 6"),
    # ---------------------------------------------------------------- Norwegian, Riksmål (from no.wikisource)
    ("nb", "Byens sjæl", "Hans E. Kinck", 1926, "Steder og folk", 1919, None),
    ("nb", "Strandebarm kirke", "Hans E. Kinck", 1926, "Steder og folk", 1921, None),
    ("nb", "Rundt om Vestlandshus", "Hans E. Kinck", 1926, "Steder og folk", 1921, None),
    ("nb", "Hardanger", "Hans E. Kinck", 1926, "Steder og folk", 1923, None),
    ("nb", "Litt om stil", "Hans E. Kinck", 1926, "Mange slags kunst", 1919, None),
    ("nb", "Mit reisefølge", "Hans E. Kinck", 1926, "Italienere", 1901, None),
    ("nb", "Sydover sletten fra Milano", "Hans E. Kinck", 1926, "Italienere", 1901, None),
    ("nb", "Smaa Epistler/02", "Nils Kjær", 1924, "Smaa Epistler", 1908, "Smaa Epistler II"),
    ("nb", "Smaa Epistler/04", "Nils Kjær", 1924, "Smaa Epistler", 1908, "Smaa Epistler IV"),
    ("nb", "Smaa Epistler/06", "Nils Kjær", 1924, "Smaa Epistler", 1908, "Smaa Epistler VI"),
    # ---------------------------------------------------------------- Danish (pre-1948 spelling: capital nouns, aa)
    ("da", "Pesten i Bergamo", "J.P. Jacobsen", 1885, "Mogens og andre Noveller", 1881, None),
    ("da", "Fru Fønss", "J.P. Jacobsen", 1885, "Mogens og andre Noveller", 1882, None),
    ("da", "Der burde have været Roser", "J.P. Jacobsen", 1885, "Mogens og andre Noveller", 1882, None),
    ("da", "En Fortælling om dem der skal dø", "Herman Bang", 1912, "Liv og Død", 1899, None),
    ("da", "Ane-Mette", "Henrik Pontoppidan", 1943, "Fra Hytterne", 1887, None),
    ("da", "Et Grundskud", "Henrik Pontoppidan", 1943, "Fra Hytterne", 1887, None),
    ("da", "Naadsensbrød", "Henrik Pontoppidan", 1943, "Fra Hytterne", 1887, None),
    ("da", "Knokkelmanden", "Henrik Pontoppidan", 1943, "Fra Hytterne", 1887, None),
    ("da", "Vandreren", "Henrik Pontoppidan", 1943, "Fra Hytterne", 1887, None),
]


# ------------------------------------------------------------------------------------ fetching

class Wiki:
    def __init__(self, cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)

    def api(self, lang: str, params: dict, post: bool = False) -> dict:
        params = dict(params, format="json", formatversion="2")
        url = f"https://{HOST.get(lang, lang)}.wikisource.org/w/api.php"
        body = urllib.parse.urlencode(params)
        key = hashlib.sha256((url + "?" + body).encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        while True:
            if post:
                req = urllib.request.Request(url, data=body.encode(), headers={"User-Agent": UA})
            else:
                req = urllib.request.Request(url + "?" + body, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.load(resp)
                break
            except urllib.error.HTTPError as err:
                if err.code == 429:
                    wait = int(err.headers.get("Retry-After") or 30)
                    print(f"  429, waiting {wait}s", file=sys.stderr)
                    time.sleep(wait + 1)
                    continue
                raise
        time.sleep(1)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def links(self, lang: str, title: str) -> list[str]:
        data = self.api(lang, {"action": "parse", "page": title, "prop": "links"})
        return [l["title"] for l in data.get("parse", {}).get("links", []) if l["ns"] == 0 and l.get("exists")]

    def render(self, lang: str, titles: list[str], batch: int = 6) -> dict[str, str]:
        """Render pages to HTML, several per parse call, by transcluding them into one text."""
        out: dict[str, str] = {}
        for i in range(0, len(titles), batch):
            group = titles[i:i + batch]
            # a marker paragraph after each page; splitting the HTML string on it (rather than
            # wrapping pages in divs) survives pages that leave a <div> unclosed
            text = "\n\n".join(f"{{{{:{t}}}}}\n\n@@IDIOLECT-SPLIT-{n}@@" for n, t in enumerate(group))
            data = self.api(lang, {"action": "parse", "text": text, "title": "Idiolect fixture",
                                   "contentmodel": "wikitext", "prop": "text", "disablelimitreport": 1,
                                   "disableeditsection": 1}, post=True)
            parts = re.split(r"@@IDIOLECT-SPLIT-(\d+)@@", data["parse"]["text"])
            for k in range(1, len(parts), 2):
                out[group[int(parts[k])]] = parts[k - 1]
        return out


# ------------------------------------------------------------------------------------ cleaning

DROP_SELECTORS = [
    "style", "script", "#textdaten", ".ws-noexport", ".noprint", ".hiddenStructure",
    ".PageNumber", ".pagenum", ".ws-pagenum", "span[class*=pagenum]", ".mw-references-wrap",
    "ol.references", ".references", "sup.reference", ".reference", ".mw-cite-backlink", ".footnote",
    ".footnotes", ".ws-header", ".headertemplate", "#headertemplate", ".ws-summary", ".mw-heading",
    "h1", "h2", "h3", "h4", "h5", "h6", ".poem", ".mw-editsection", ".navigation", ".ws-navigation",
    ".sisitem", ".licenseContainer", ".licence", ".license", "div.center", ".prp-page-qualityheader",
    ".error", ".Z3988", "[style*='display:none']", "[style*='display: none']", ".interProject",
    ".ws-page-nav", ".mw-empty-elt", ".tablenum", ".annotation",
]
CENTER_RE = re.compile(r"text-align:\s*(center|right)", re.I)
# transcription slips in the sources, corrected so that the fixtures read as the author wrote
FIXES = {
    "Earlos Marx": "Carlos Marx",  # drop initial image with the wrong alt text
    "decir ]a verdad": "decir la verdad",
    "die Erscheinungfremd": "die Erscheinung fremd",
    "заважаютъ": "заважають",
}
PARA_END = (".", "!", "?", "…", ":", ";", "“", "”", "»", "«", '"', "—", "–", ")", "’", "'", ",")
SENT_END = (".", "!", "?", "…", ":", "“", "”", "»", "«")
MARKER_RES = [
    re.compile(r"\[(?:…|\.\.\.)\]"),         # editorial [...] for a gap in the source
    re.compile(r"WS: Dieses Bild kann aus urheberrechtlichen Gründen nicht dargestellt werden\.?"),
    re.compile(r"\[\s*\d+\s*\]"),               # [1]
    re.compile(r"\[\s*(?:p\.|S\.|Seite|pág\.)\s*\d+\s*\]", re.I),  # [p. 12]
    re.compile(r"\(\s*\d{1,2}\s*\)(?=[\s.,;:])"),  # (1) after a word
    re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+"),
]

# paragraphs that are apparatus, not prose (applied outside LEGACY)
DROP_PARA_RES = [
    re.compile(r"Kaynakça\s*:"),  # tr.wikisource source line under the text
]


def paragraph_text(raw: str) -> str:
    """One paragraph of source text (lines separated by U+2028) as clean prose, or "" to drop it."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in raw.split("\u2028")]
    lines = [l for l in lines if l]
    if not lines:
        return ""
    if len(lines) >= 3 and max(len(l.split()) for l in lines) < 20:
        return ""  # verse, address blocks and lists of lines
    # a title or byline set on its own line(s) above the prose in the same paragraph
    while len(lines) > 1 and len(lines[0].split()) <= 8 and not lines[0].endswith(SENT_END):
        lines.pop(0)
    text = " ".join(lines)
    for rx in MARKER_RES:
        text = rx.sub("", text)
    for bad, good in FIXES.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r" ([,.)])", r"\1", text)
    text = re.sub(r"([(„¿¡]) ", r"\1", text)
    if not text or not re.search(r"\w{2,}", text):
        return ""
    if re.fullmatch(r"[\W\d_]*", text):
        return ""
    return text


def paragraphs(html: str, title: str = "", lang: str = "") -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for sel in DROP_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    # tables: drop info boxes and navigation, keep layout tables that hold the prose
    for tab in soup.find_all("table"):
        if tab.decomposed:
            continue
        if not any(len(p.get_text().split()) >= 30 for p in tab.find_all("p")):
            tab.decompose()
    for el in soup.find_all(style=CENTER_RE):
        el.decompose()
    for el in soup.find_all(["p", "div"], attrs={"align": re.compile("center|right", re.I)}):
        el.decompose()
    # drop initials set as images: keep the letter from the alt text
    for el in soup.select(".dropinitial"):
        img = el.find("img")
        el.replace_with(img.get("alt", "") if img else el.get_text(""))
    # footnote anchors: superscripts that only hold a link to a note
    for sup in soup.find_all("sup"):
        if sup.find("a") or re.fullmatch(r"\W*\d+\W*", sup.get_text()):
            sup.decompose()
    if lang not in LEGACY:
        # pl.wikisource sets several paragraphs in one <p>, each opened by an indent span
        for el in soup.select("span._tb"):
            el.replace_with("\u2029")
        # dialogue set as indented lines (":— ...") renders as <dd>
        for dd in soup.find_all("dd"):
            dd.name = "p"
    paras: list[str] = []
    for p in soup.find_all("p"):
        for br in p.find_all("br"):
            br.replace_with("\u2028")
        for seg in p.get_text("").split("\u2029"):
            text = paragraph_text(seg if lang in LEGACY else seg.replace("\u00ad", ""))
            if text and lang not in LEGACY and any(rx.match(text) for rx in DROP_PARA_RES):
                continue
            if text:
                paras.append(text)

    def trim_head(paras: list[str]) -> list[str]:
        while paras and ((len(paras[0].split()) <= 6
                          and (not paras[0].endswith(SENT_END) or re.search(r"\d", paras[0])))
                         or (len(paras[0].split()) <= 10 and not paras[0].endswith(SENT_END))
                         or (len(paras[0].split()) <= 14 and title and title.lower() in paras[0].lower())):
            paras.pop(0)
        return paras

    paras = trim_head(paras)
    # a paragraph cut by a page break in the scan continues in the next one
    joined: list[str] = []
    for text in paras:
        if joined and not joined[-1].endswith(PARA_END):
            prev = joined.pop()
            if re.search(r"\w-$", prev) and text[:1].islower():
                text = prev[:-1] + text  # word hyphenated across the break
            else:
                text = prev + " " + text
        joined.append(text)
    paras = joined
    # signatures, dates and places at the end; title, byline and date lines at the start
    while paras and (len(paras[-1].split()) <= 4
                     or (len(paras[-1].split()) <= 12 and re.search(r"\b1[89]\d\d\b", paras[-1]))):
        paras.pop()
    paras = trim_head(paras)
    if lang not in LEGACY:
        # a list of characters or places set as one short line each before the prose
        k = 0
        while k < len(paras) and len(paras[k].split()) <= 4:
            k += 1
        if k >= 3:
            paras = paras[k:]
    return paras


# ------------------------------------------------------------------------------------ output

def display_title(page: str) -> str:
    t = page.rsplit("/", 1)[-1]
    return re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()


CYRILLIC = dict(zip(
    "абвгґдеєжзиіїйклмнопрстуфхцчшщъыьэюяё",
    ["a", "b", "v", "g", "g", "d", "e", "ie", "zh", "z", "i", "i", "i", "i", "k", "l", "m", "n", "o", "p",
     "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "iu", "ia", "e"],
))


def slugify(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ß", "ss").replace("œ", "oe").replace("æ", "ae")
    t = t.replace("ł", "l").replace("ø", "o").replace("ı", "i").replace("đ", "d")
    t = "".join(CYRILLIC.get(c, c) for c in t)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:48].rstrip("-") or "text"


def page_url(lang: str, title: str) -> str:
    return f"https://{HOST.get(lang, lang)}.wikisource.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="/_(),:!'’")


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(wiki: Wiki, lang: str, min_words: int = 150) -> None:
    items = [s for s in SOURCES if s[0] == lang]
    html = wiki.render(lang, [s[1] for s in items])
    outdir = OUT / f"native-{lang}"
    outdir.mkdir(parents=True, exist_ok=True)
    retired = None
    for old in sorted(outdir.glob("[0-9][0-9]-*.md")):
        # generated output of an earlier run (recognised by its front matter) is moved aside, never deleted
        if f"\nlang: {lang}\n---\n" in old.read_text(encoding="utf-8") and LICENCE in old.read_text(encoding="utf-8"):
            if retired is None:
                import datetime
                stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                retired = OUT.parent / "_to_delete" / f"native-{lang}-{stamp}"
                retired.mkdir(parents=True, exist_ok=True)
            old.rename(retired / old.name)
    written: set[str] = set()
    n = 0
    total = 0
    for _, page, author, died, book, year, title in items:
        title = title or display_title(page)
        paras = paragraphs(html.get(page, ""), title, lang)
        body = "\n\n".join(paras)
        words = len(body.split())
        if words < min_words:
            print(f"  skip {page!r}: {words} words", file=sys.stderr)
            continue
        n += 1
        name = f"{n:02d}-{slugify(title)}.md"
        front = "\n".join([
            "---",
            f"author: {author}",
            f"author_died: {died}",
            f"book: {yaml_str(book)}",
            f"first_published: {year}",
            f"title: {yaml_str(title)}",
            f"source: {page_url(lang, page)}",
            f"licence: {LICENCE}",
            f"words: {words}",
            f"lang: {lang}",
            "---",
        ])
        (outdir / name).write_text(front + "\n\n" + body + "\n", encoding="utf-8")
        written.add(name)
        total += words
        print(f"  {name}: {words}")
    for stale in sorted(outdir.glob("[0-9][0-9]-*.md")):
        if stale.name not in written:
            print(f"  warning: {stale.name} is not from this run; retire it by hand", file=sys.stderr)
    print(f"{lang}: {n} files, {total} words")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", choices=LANGS, action="append")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/idiolect-native-fixtures"))
    ap.add_argument("--probe", metavar="TITLE", help="print the cleaned text of one page")
    ap.add_argument("--links", metavar="TITLE", help="list the existing main-namespace links of one page")
    args = ap.parse_args()
    wiki = Wiki(Path(args.cache))
    langs = args.lang or LANGS
    if args.links:
        print("\n".join(wiki.links(langs[0], args.links)))
        return
    if args.probe:
        paras = paragraphs(wiki.render(langs[0], [args.probe])[args.probe], display_title(args.probe), langs[0])
        print("\n\n".join(paras))
        print(f"\n[{sum(len(p.split()) for p in paras)} words]", file=sys.stderr)
        return
    for lang in langs:
        build(wiki, lang)


if __name__ == "__main__":
    main()
