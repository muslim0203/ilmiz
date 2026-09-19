"""GoAccess hisobotidagi yorliqlarni o'zbekchaga o'giradi.

GoAccess tarjimasi gettext locale'ga tayanadi (serverda `uz` locale ham,
`gettext` vositalari ham yo'q) va HTML hisobotni o'girishi kafolatlanmagan.
Yorliqlar esa hisobot ichidagi JSON sozlamasida turadi — `"head"` (panel
sarlavhasi), `"desc"` (izoh), `"label"` (ustun nomi). Shuning uchun hisobot
yasalgandan keyin faqat shu qiymatlar almashtiriladi: lug'atda yo'q matn
inglizcha qoladi, ya'ni GoAccess yangilanganda hisobot buzilmaydi.

Fayl baytlar sifatida o'qiladi: loglarda UTF-8 bo'lmagan baytlar uchraydi
(skanerlarning buzuq so'rovlari) va ular hisobotga o'zgarishsiz ko'chadi.

    python deploy/translate_stats.py /var/lib/ilmiz/stats/index.html
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HEADS = {
    "Overall Analyzed Requests": "Umumiy ko'rsatkichlar",
    "Unique visitors per day": "Kunlik tashrifchilar",
    "Requested Files (URLs)": "So'ralgan sahifalar",
    "Static Requests": "Statik fayllar",
    "Not Found URLs (404s)": "Topilmagan manzillar (404)",
    "Visitor Hostnames and IPs": "Tashrifchilar IP manzillari",
    "Operating Systems": "Operatsion tizimlar",
    "Browsers": "Brauzerlar",
    "Time Distribution": "Soatlar bo'yicha taqsimot",
    "Referring Sites": "Qaysi saytdan kelgan",
    "HTTP Status Codes": "HTTP javob kodlari",
}

DESCS = {
    "Hits having the same IP, date and agent are a unique visit.":
        "Bir xil IP, sana va brauzerdan kelgan so'rovlar bitta tashrif deb hisoblanadi.",
    "Top requests sorted by hits [, avgts, cumts, maxts, mthd, proto]":
        "Eng ko'p so'ralgan sahifalar",
    "Top static requests sorted by hits [, avgts, cumts, maxts, mthd, proto]":
        "Eng ko'p so'ralgan statik fayllar (rasm, css, js)",
    "Top not found URLs sorted by hits [, avgts, cumts, maxts, mthd, proto]":
        "Eng ko'p so'ralgan, lekin mavjud bo'lmagan manzillar",
    "Top visitor hosts sorted by hits [, avgts, cumts, maxts]":
        "Eng ko'p so'rov yuborgan IP manzillar",
    "Top Operating Systems sorted by hits [, avgts, cumts, maxts]":
        "Operatsion tizimlar, so'rovlar soni bo'yicha",
    "Top Browsers sorted by hits [, avgts, cumts, maxts]":
        "Brauzerlar, so'rovlar soni bo'yicha",
    "Data sorted by hour [, avgts, cumts, maxts]":
        "Sutka davomida so'rovlarning soatlar bo'yicha taqsimoti",
    "Top Referring Sites sorted by hits [, avgts, cumts, maxts]":
        "Havola bergan saytlar, so'rovlar soni bo'yicha",
    "Top HTTP Status Codes sorted by hits [, avgts, cumts, maxts]":
        "Server javob kodlari, so'rovlar soni bo'yicha",
}

LABELS = {
    "Hits": "So'rovlar",
    "Visitors": "Tashrifchilar",
    "Unique Visitors": "Noyob tashrifchilar",
    "Hits/Visitors": "So'rov/Tashrifchi",
    "Tx. Amount": "Uzatilgan hajm",
    "Data": "Ma'lumot",
    "Method": "Usul",
    "Protocol": "Protokol",
    "Total Requests": "Jami so'rovlar",
    "Valid Requests": "To'g'ri so'rovlar",
    "Failed Requests": "Xato so'rovlar",
    "Requested Files": "So'ralgan sahifalar",
    "Static Files": "Statik fayllar",
    "Not Found": "Topilmagan (404)",
    "Referrers": "Havola bergan saytlar",
    "Excl. IP Hits": "Hisobga olinmagan IP so'rovlari",
    "Log Size": "Log hajmi",
    "Log Parsing Time": "Tahlil vaqti",
}

TRANSLATIONS = {"head": HEADS, "desc": DESCS, "label": LABELS}
# Qiymat ichida ekranlangan qo'shtirnoq ham bo'lishi mumkin.
FIELD = re.compile(r'"(head|desc|label)":\s*"((?:[^"\\]|\\.)*)"')


def translate(report: str) -> str:
    """Tanish yorliqlarni o'zbekchaga almashtiradi, qolganiga tegmaydi."""

    def swap(match: re.Match[str]) -> str:
        key, value = match.group(1), match.group(2)
        try:
            decoded = json.loads('"' + value + '"')
        except json.JSONDecodeError:
            return match.group(0)
        replacement = TRANSLATIONS[key].get(decoded)
        if replacement is None:
            return match.group(0)
        return '"' + key + '": ' + json.dumps(replacement, ensure_ascii=False)

    return FIELD.sub(swap, report)


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__)
        return 1
    for name in paths:
        path = Path(name)
        report = path.read_bytes().decode("utf-8", errors="replace")
        path.write_text(translate(report), encoding="utf-8")
        print("Tarjima qilindi: " + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
