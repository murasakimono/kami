"""Kami'yi konsolsuz baslatir; klasorden bagimsiz (Windows magnet: isleyicisi bunu cagirir).

    pythonw.exe kami_open.pyw --magnet "magnet:?xt=..."
Kami aciksa magnet calisan Kami'ye gider, degilse Kami acilir ve magneti alir.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from app.main import main  # noqa: E402

sys.exit(main())
