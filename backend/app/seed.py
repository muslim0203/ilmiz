from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Article, Journal
from .services.ingest import normalize_title


JOURNALS = [
    {
        "slug": "fardu-ilmiy-xabarlari",
        "name": "FarDU ilmiy xabarlari",
        "short_name": "FarDU IX",
        "publisher": "Farg‘ona davlat universiteti",
        "city": "Farg‘ona",
        "fields": ["Filologiya", "Pedagogika", "Tarix", "Biologiya"],
        "issn": "2010-8419",
        "eissn": "2181-1571",
        "languages": ["O‘zbek", "Rus", "Ingliz"],
        "oak_status": "active",
        "access": "open",
        "founded": 1995,
        "website": "https://journal.fdu.uz/",
        "description": "Ko‘p tarmoqli ilmiy jurnal. Tabiiy, ijtimoiy va gumanitar fanlar bo‘yicha tadqiqotlarni nashr etadi.",
    },
    {
        "slug": "acta-camu",
        "name": "Acta CAMU",
        "short_name": "ACTA CAMU",
        "publisher": "Central Asian Medical University",
        "city": "Farg‘ona",
        "fields": ["Tibbiyot"],
        "issn": "2992-9024",
        "languages": ["Ingliz", "Rus"],
        "oak_status": "active",
        "access": "open",
        "founded": 2022,
        "website": "https://www.camuf.uz/en",
        "description": "Klinik tibbiyot, profilaktika va zamonaviy tibbiy ta’lim yo‘nalishlaridagi tadqiqotlar jurnali.",
    },
    {
        "slug": "agro-ilm",
        "name": "Agro ILM",
        "short_name": "Agro ILM",
        "publisher": "O‘zbekiston qishloq xo‘jaligi jurnali ilmiy ilovasi",
        "city": "Toshkent",
        "fields": ["Qishloq xo‘jaligi", "Texnika"],
        "issn": "2091-5616",
        "languages": ["O‘zbek", "Rus"],
        "oak_status": "active",
        "access": "open",
        "founded": 2007,
        "website": "https://qxjurnal.uz/index.php/ai",
        "description": "Agronomiya, suv xo‘jaligi, agrotexnologiya va qishloq xo‘jaligi mexanizatsiyasi bo‘yicha ilmiy nashr.",
    },
    {
        "slug": "adabiy-meros",
        "name": "Adabiy meros",
        "short_name": "Adabiy meros",
        "publisher": "Alisher Navoiy nomidagi Davlat adabiyot muzeyi",
        "city": "Toshkent",
        "fields": ["Filologiya"],
        "issn": "2181-1320",
        "languages": ["O‘zbek", "Rus"],
        "oak_status": "active",
        "access": "mixed",
        "founded": 1968,
        "website": "https://navoimuseum.uz/uz/jurnallar",
        "description": "O‘zbek adabiyoti, matnshunoslik va adabiy manbashunoslik masalalariga bag‘ishlangan nashr.",
    },
    {
        "slug": "agro-inform",
        "name": "Agro Inform",
        "short_name": "Agro Inform",
        "publisher": "Toshkent davlat agrar universiteti",
        "city": "Toshkent",
        "fields": ["Qishloq xo‘jaligi"],
        "issn": "2181-8369",
        "languages": ["O‘zbek", "Ingliz", "Rus"],
        "oak_status": "active",
        "access": "open",
        "founded": 2020,
        "website": "https://agro-inform.uz/index.php/agro-inform",
        "description": "Qishloq xo‘jaligi, oziq-ovqat xavfsizligi va agrar iqtisodiyotga oid ochiq ilmiy jurnal.",
    },
    {
        "slug": "qardu-xabarlari",
        "name": "QarDU xabarlari",
        "short_name": "QarDU xabarlari",
        "publisher": "Qarshi davlat universiteti",
        "city": "Qarshi",
        "fields": ["Pedagogika", "Tarix", "Filologiya"],
        "issn": "2181-0958",
        "languages": ["O‘zbek", "Rus", "Ingliz"],
        "oak_status": "active",
        "access": "open",
        "founded": 2009,
        "website": "https://qarshidu.uz/",
        "description": "Ijtimoiy-gumanitar va tabiiy fanlar bo‘yicha universitet ilmiy axborotnomasi.",
    },
]

ARTICLES = [
    {
        "journal_slug": "fardu-ilmiy-xabarlari",
        "title": "Oliy ta’limda raqamli pedagogikaning yangi yondashuvlari",
        "authors": ["Dilnoza Karimova", "Jasur Ergashev"],
        "abstract": "Tadqiqot oliy ta’limda raqamli vositalardan foydalanish amaliyoti va uning ta’lim natijalariga ta’sirini tahlil qiladi.",
        "keywords": ["raqamli pedagogika", "oliy ta’lim", "ta’lim texnologiyalari"],
        "language": "O‘zbek",
        "fields": ["Pedagogika"],
        "publication_year": 2026,
        "volume": "7",
        "issue": "4",
        "pages": "44–52",
        "doi": "10.0000/demo.2026.041",
        "pdf_url": "demo://pdf",
    },
    {
        "journal_slug": "acta-camu",
        "title": "Clinical indicators in early cardiovascular risk assessment",
        "authors": ["M. Rakhimov", "S. Yuldasheva", "A. Kim"],
        "abstract": "This study evaluates accessible clinical indicators for early cardiovascular risk stratification.",
        "keywords": ["cardiovascular risk", "screening", "clinical indicators"],
        "language": "Ingliz",
        "fields": ["Tibbiyot"],
        "publication_year": 2026,
        "volume": "4",
        "issue": "2",
        "pages": "18–27",
        "doi": "10.0000/demo.2026.118",
        "pdf_url": "demo://pdf",
    },
]


def seed_database(db: Session) -> None:
    if db.scalar(select(Journal.id).limit(1)) is not None:
        return
    journal_by_slug: dict[str, Journal] = {}
    for payload in JOURNALS:
        journal = Journal(**payload)
        db.add(journal)
        journal_by_slug[journal.slug] = journal
    db.flush()
    for payload in ARTICLES:
        data = dict(payload)
        journal_slug = data.pop("journal_slug")
        title = str(data["title"])
        db.add(Article(journal=journal_by_slug[journal_slug], normalized_title=normalize_title(title), **data))
    db.commit()
