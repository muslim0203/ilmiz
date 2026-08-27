"""Soha va shahar taksonomiyasi.

OAK reestri 24 ta fan yo‘nalishini beradi, lekin ular tekis ro‘yxat. Bu modul
ularni guruhlarga ajratadi va shahar nomlarining kirill/lotin variantlarini
bitta kanonik nomga keltiradi.
"""
from __future__ import annotations

# Guruh -> OAK sohalari. Sohalar `journals.fields` dagi qiymatlar bilan aynan mos.
FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("Tabiiy fanlar", ["Fizika-matematika", "Kimyo", "Biologiya", "Geografiya", "Geologiya-mineralogiya"]),
    ("Muhandislik va texnologiya", ["Texnika", "Arxitektura"]),
    ("Tibbiyot va sog‘liqni saqlash", ["Tibbiyot", "Farmatsevtika", "Veterinariya"]),
    ("Qishloq xo‘jaligi", ["Qishloq xo‘jaligi"]),
    ("Ta’lim", ["Pedagogika"]),
    ("Gumanitar fanlar", ["Tarix", "Filologiya", "Falsafa", "Islomshunoslik"]),
    ("Ijtimoiy fanlar", ["Sotsiologiya", "Psixologiya", "Siyosiy fanlar", "Ijtimoiy-gumanitar"]),
    ("San’at", ["San’atshunoslik"]),
    ("Iqtisodiyot va boshqaruv", ["Iqtisodiyot"]),
    ("Huquq va xavfsizlik", ["Yuridik", "Harbiy fanlar"]),
]

FIELD_TO_GROUP: dict[str, str] = {
    field: group for group, fields in FIELD_GROUPS for field in fields
}

OTHER_GROUP = "Boshqa"


def field_group(field: str) -> str:
    """Guruhda ko‘rsatilmagan yangi soha ham yo‘qolmasligi kerak."""
    return FIELD_TO_GROUP.get(field, OTHER_GROUP)


# Bir shahar kirill va lotin yozuvida alohida yozuv sifatida kelgan. Homoglifli
# variantlar ham bor ("Urgаnсh" ichida kirill "а" va "с").
CITY_CANONICAL: dict[str, str] = {
    "Тошкент": "Toshkent",
    "Toshkent": "Toshkent",
    "Самарқанд": "Samarqand",
    "Бухоро": "Buxoro",
    "Нукус": "Nukus",
    "Наманган": "Namangan",
    "Андижон": "Andijon",
    "Термиз": "Termiz",
    "Урганч": "Urganch",
    "Urgаnсh": "Urganch",
    "Фарғона": "Farg‘ona",
    "Farg‘ona": "Farg‘ona",
    "Қарши": "Qarshi",
    "Qarshi": "Qarshi",
    "Жиззах": "Jizzax",
    "Чирчиқ": "Chirchiq",
    "Гулистон": "Guliston",
    "Навоий": "Navoiy",
    "Қўқон": "Qo‘qon",
    "Xorazm": "Xorazm",
    "Қорақалпоғистон Республикаси": "Qoraqalpog‘iston Respublikasi",
    "Минск": "Minsk",
    "Москва": "Moskva",
    "Санкт-Петербург": "Sankt-Peterburg",
}


def canonical_city(city: str | None) -> str:
    if not city:
        return ""
    return CITY_CANONICAL.get(city.strip(), city.strip())


def city_variants(canonical: str) -> list[str]:
    """Kanonik nomdan bazadagi barcha xom variantlarni qaytaradi.

    Filtrlashda kerak: foydalanuvchi "Toshkent" ni tanlaydi, bazada esa
    "Тошкент" va "Toshkent" ikkalasi ham bor.
    """
    variants = [raw for raw, name in CITY_CANONICAL.items() if name == canonical]
    return variants or [canonical]
