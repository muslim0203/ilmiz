"""Maqolaning ilmiy sohasini maqolaning o'zidan aniqlash.

Ilgari harvest har maqolaga jurnalning barcha sohalarini ko'chirardi: besh
sohali jurnaldagi filologiya maqolasi "Biologiya, Filologiya, Kimyo,
Pedagogika, Tarix" bo'lib chiqardi. Endi:

- jurnalning sohasi bitta bo'lsa — o'sha (maqola boshqa sohada bo'lishi
  mumkin emas, chunki OAK jurnalni shu soha uchun ro'yxatga olgan);
- bir nechta bo'lsa — sarlavha, kalit so'zlar va annotatsiya shu sohalar
  lug'ati bilan solishtiriladi; aniq g'olib chiqmasa soha bo'sh qoladi
  (admin paneldan qo'lda qo'shiladi).

Lug'at o'zaklari istalgan yozuvda yoziladi (o'zbek lotin/kirill, rus,
ingliz) — `search_text.normalize` ularni matn bilan bir xil shaklga keltiradi.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from .search_text import normalize

_LEXICON: dict[str, str] = {
    "Pedagogika": """pedagog педагог talim таълим oqit ўқит oquvchi ўқувчи oqituvchi ўқитувчи tarbiya
        тарбия maktab мактаб dars дарс metodika методика metodik didakt kompetens malaka education teaching
        learning school обучен образован преподав урок учащ учител curricul oquv ўқув""",
    "Filologiya": """tilshunos тилшунос lingvist лингвист linguist leksik лексик lexic frazeolog фразеолог
        phraseolog grammat грамматик morfolog морфолог morpholog sintaks синтакс syntax semant семант fonet
        фонет phonet adabiyot адабиёт adabiy адабий literat литератур poet поэт sheriyat шеърият hikoya ҳикоя
        doston достон folklor фольклор badiiy бадиий translat tarjima таржима перевод dialekt диалект lahja
        шева terminolog терминолог nutq нутқ diskurs дискурс discourse lugat луғат yozuvchi ёзувчи shoir шоир
        филолог языкознан язык стилист stylist konsept концепт metafor метафор antroponim toponim топоним
        onomast ономаст ingliz_tili""",
    "Tarix": """tarix тарих history histor история istori arxeolog археолог archaeolog sulola сулола xonlig
        хонлиг amirlik амирлик imperiya империя empire mustamlaka мустамлака qadimgi қадимги ancient
        orta_asr ўрта_аср medieval sovet совет soviet manbashunos манбашунос etnograf этнограф ethnograph
        numizmat нумизмат epigraf эпиграф temuriy темурий shayboniy шайбоний jadid жадид khanate khan dynast caravan карван century
        colonial колониал revolution inqilob инқилоб революц chorizm чоризм tsaris царизм царск bosqin босқин""",
    "Iqtisodiyot": """iqtisod иқтисод ekonom эконом econom moliya молия financ финанс bank kredit кредит
        credit investits инвестиц invest soliq солиқ taxation biznes бизнес business tadbirkor тадбиркор
        entrepreneur marketing маркетинг menejment менежмент management buxgalter бухгалтер accounting audit
        аудит byudjet бюджет budget inflyats инфляц inflation eksport экспорт export savdo савдо trade bozor
        бозор market raqobat рақобат competit daromad даромад income xarajat харажат narx нарх price
        korxona корхона enterprise sugurta суғурта insur logist логист bandlik бандлик employment turizm
        туризм touris""",
    "Tibbiyot": """tibb тибб medic медиц kasallik касаллик disease bemor бемор patient davolash даволаш
        treatment лечен jarroh жарроҳ surg хирург terapiya терапия therap klinik клиник clinic diagnost
        диагност sindrom синдром syndrom infeksiya инфекц infect patolog патолог kardio кардио cardio onkolog
        онколог oncol pediatr педиатр stomatolog стоматолог dental homiladorlik ҳомиладорлик pregnan akusher
        акушер obstet ginekolog гинеколог gynec nevrolog невролог neurolog shifokor шифокор physician
        sogliq соғлиқ health здоров virus вирус covid gepatit гепатит hepat diabet диабет jigar жигар liver
        buyrak буйрак kidney anesteziya анестез anesth travma травма trauma ortoped ортопед oftalm офтальм
        ophthalm dermatolog дерматолог urolog уролог endokrin эндокрин immun иммун""",
    "Farmatsevtika": """farmats фармац pharmac dori дори drug preparat препарат tabletka таблетка ekstrakt
        экстракт extract farmakolog фармаколог pharmacol farmakognoz фармакогноз dorivor доривор""",
    "Veterinariya": """veterin ветерин chorva чорва livestock qoramol қорамол cattle parranda парранда poultry
        hayvon ҳайвон buzoq бузоқ sigir сигир zoovet gelmint гельминт helminth epizoot эпизоот parazit
        паразит""",
    "Qishloq xo‘jaligi": """qishloq_xojalig қишлоқ_хўжалиг agricult сельск agro агро dehqon деҳқон farmer
        fermer фермер hosil ҳосил yield urug уруғ seed tuproq тупроқ soil почв sugorish суғориш irrigat
        ирригац paxta пахта cotton хлопк хлопч bugdoy буғдой wheat пшениц goza ғўза ogit ўғит fertiliz
        удобрен zararkunanda зараркунанда pest bogdorchilik боғдорчилик uzumchilik узумчилик sabzavot
        сабзавот vegetable issiqxona иссиқхона greenhouse meliorats мелиорац ekin экин crop""",
    "Biologiya": """biolog биолог hujayra ҳужайра cell клетк genet генет genom геном ekolog эколог ecolog
        flora fauna фауна osimlik ўсимлик plant растен botanik ботаник botan zoolog зоолог mikrobiolog
        микробиолог microbi bakteriya бактерия bacteri hasharot ҳашарот insect populyats популяц biokim
        биохим biochem fiziolog физиолог physiolog oqsil оқсил protein белок ferment фермент enzym
        biotexnolog биотехнолог biotechn species""",
    "Kimyo": """kimyo кимё chemi хими ximi sintez синтез synthes reaksiya реакция katalizator катализ catal
        polimer полимер polymer birikma бирикма compound соединен kislota кислот acid spektr спектр spectr
        xromatograf хроматограф chromatog oksid оксид oxid metall металл alkaloid алкалоид flavonoid
        флавоноид adsorbs адсорбц sorbs kristall кристалл crystal titrlash noorganik inorganic organik
        органик molekul молекул""",
    "Fizika-matematika": """fizik физик physic matemat математ math algebra алгебра geometr геометр
        tenglama тенглама equation уравнен differensial дифференц differential integral интеграл matritsa
        матриц matrix teorema теорема theorem kvant квант quantum optik оптик optic lazer лазер laser
        yarimotkazgich яримўтказгич semiconduct zarracha заррача elektromagnit электромагнит termodinam
        термодинам ehtimollar эҳтимоллар probabilit topolog тополог astronom астроном astrophys""",
    "Geografiya": """geograf географ landshaft ландшафт landscape relyef рельеф iqlim иқлим climat климат
        kartograf картограф cartog rekreats рекреац recreat demograf демограф demograph urbaniz урбаниз
        gidrolog гидролог hydrolog daryo дарё river chol чўл desert aral orol орол ekoturizm экотуризм
        turizm туризм touris""",
    "Geologiya-mineralogiya": """geolog геолог mineral минерал qazilma қазилма ruda руда petrograf петрограф
        neft нефть petrol litolog литолог tektonik тектоник tecton seysmik сейсмик seism gidrogeolog
        гидрогеолог burgulash бурғулаш drilling tog_jins тоғ_жинс magmat магмат stratigraf стратиграф
        paleontolog палеонтолог geokim геохим geochem mining""",
    "Texnika": """muhandis муҳандис engineer инженер mashina машина machin dvigatel двигател engine elektr
        электр electric energetik энергетик energiya энергия avtomatlashtir автоматлаштир automat автомат
        robot робот dasturiy_taminot дастурий_таъминот software axborot_texnolog ахборот_технолог information
        techno kompyuter компьютер computer neyron нейрон neural suniy_intellekt сунъий_интеллект algoritm
        алгоритм algorithm transport транспорт avtomobil автомобил vehicle temir_yol темир_йўл railway beton
        бетон concrete payvand пайванд weld metallurg металлург tekstil текстил textile gidrotexnik
        гидротехник nasos насос pump turbina турбина turbin quyosh_energ қуёш_энерг solar radiotexn
        радиотехн telekommunik телекоммуник telecom sensor сенсор datchik датчик mikrokontroller korroziya
        коррозия corros ishonchlilik ишончлилик dizel дизел diesel traktor трактор kabel кабел transformator
        трансформатор""",
    "Arxitektura": """arxitektur архитектур architect shaharsozlik шаҳарсозлик urban градостр inshoot иншоот
        interyer интерьер interior restavrats реставрац restor obida обида monument memorchilik меъморчилик
        memoriy меъморий qurilish қурилиш construct konstruksiya конструкц fasad фасад facade""",
    "Falsafa": """falsaf фалсаф philosoph философ filosof ontolog онтолог epistemolog эпистемолог gnoseolog
        гносеолог dialektik диалектик axloq ахлоқ ethic этик estetik эстетик aesthet manaviyat маънавият
        manaviy маънавий mafkura мафкура ideolog идеолог dunyoqarash дунёқараш qadriyat қадрият metafizik
        метафизик mantiq мантиқ tafakkur тафаккур aksiolog аксиолог sinergetik синергетик""",
    "Islomshunoslik": """islom ислом islam ислам hadis ҳадис hadith хадис quron қуръон quran коран tasavvuf
        тасаввуф sufi fiqh фиқҳ aqida ақида imom имом imam kalom калом shariat шариат tafsir тафсир muhaddis
        муҳаддис diniy диний religio религи masjid масжид mosque madrasa мадраса naqshband нақшбанд
        moturidiy мотуридий maturidi buxoriy бухорий termiziy термизий""",
    "Sotsiologiya": """sotsiolog социолог sociolog jamiyat жамият societ обществ oila оила family gender
        гендер migrats миграц migrat yoshlar ёшлар youth молодеж fuqarolik_jamiyat фуқаролик_жамият mahalla
        маҳалла ijtimoiy_himoya ижтимоий_ҳимоя survey""",
    "Psixologiya": """psixolog психолог psycholog personality emotsional эмоционал emotion motivats мотивац
        motivat kognitiv когнитив cognit stress стресс xulq хулқ behavio поведен temperament темперамент
        ruhiy руҳий depress депресс tashvish ташвиш anxiet psixodiagnost психодиагност psixik психик idrok
        идрок perception iroda ирода frustrats фрустрац agress агресс""",
    "Siyosiy fanlar": """siyosat сиёсат siyosiy сиёсий politic политич demokrat демократ democr saylov сайлов
        election geosiyos геосиёс geopolit геополит diplomat дипломат xalqaro_munosabat халқаро_муносабат
        international_relations tashqi_siyosat ташқи_сиёсат foreign_policy parlament парламент suverenitet
        суверенитет sovereign terrorizm терроризм terror ekstremizm экстремизм extremis globallash глобаллаш
        globaliz davlat_boshqaruv давлат_бошқарув public_administr""",
    "Ijtimoiy-gumanitar": """gumanitar гуманитар humanit madaniyatshunos маданиятшунос kulturolog культуролог
        culturol jurnalistika журналистика journalism media медиа ommaviy_axborot оммавий_ахборот kutubxona
        кутубхона library muzey музей museum sport спорт jismoniy_tarbiya жисмоний_тарбия physical_education""",
    "San’atshunoslik": """sanat санъат iskusstv искусств musiqa мусиқа music музык teatr театр theat kino
        кино cinema film фильм tasviriy тасвирий haykal ҳайкал sculpt xoreograf хореограф choreog raqs рақс
        dance vokal вокал vocal maqom мақом baxshi бахши dizayn дизайн design ijrochilik ижрочилик dramaturg
        драматург rejissyor режиссёр hunarmand ҳунарманд kulolchilik кулолчилик ceram miniatyura миниатюра
        fotograf фотограф photograph""",
    "Yuridik": """huquq ҳуқуқ legal юрид yurid правов qonun қонун jinoyat жиноят crimin crime уголов sud
        суд court konstitutsiyaviy конституцияв constitution prokuratura прокуратура advokat адвокат attorney
        notarius нотариус shartnoma шартнома contract договор jazo жазо tergov тергов huquqbuzarlik
        ҳуқуқбузарлик offence offense kriminolog криминолог sudlov судлов arbitraj арбитраж arbitrat
        normativ-huquqiy норматив-ҳуқуқий intellectual_property intellektual_mulk""",
    "Harbiy fanlar": """harbiy ҳарбий military военн qurolli_kuch қуролли_куч armed_forces mudofaa мудофаа
        defence defense askar аскар soldier ofitser офицер officer jangovar жанговар combat milliy_gvardiya
        миллий_гвардия qurol қурол weapon""",
}

TITLE_WEIGHT = 3
KEYWORD_WEIGHT = 2
ABSTRACT_WEIGHT = 1
ABSTRACT_CAP = 5
# G'olib shu balldan past bo'lsa yoki ikkinchisidan ikki baravar ko'p
# bo'lmasa — soha aniqlanmagan hisoblanadi.
MIN_SCORE = 3
MARGIN = 2.0


def _stems(raw: str) -> list[str]:
    # Ko'p so'zli ibora pastki chiziq bilan yoziladi: "tashqi_siyosat".
    return [normalize(word.replace("_", " ")) for word in raw.split()]


@lru_cache(maxsize=None)
def _patterns() -> dict[str, re.Pattern[str]]:
    patterns: dict[str, re.Pattern[str]] = {}
    for field, raw in _LEXICON.items():
        alternatives = sorted({stem for stem in _stems(raw) if stem}, key=len, reverse=True)
        patterns[field] = re.compile(r"(?<![a-z0-9])(?:" + "|".join(map(re.escape, alternatives)) + ")")
    return patterns


def _hits(pattern: re.Pattern[str], text: str) -> int:
    return len(set(pattern.findall(text))) if text else 0


def scores(title: str | None, keywords: Iterable[str] | None, abstract: str | None, candidates: Iterable[str]) -> dict[str, int]:
    """Har bir nomzod soha uchun ball (faqat lug'ati bor sohalar)."""
    patterns = _patterns()
    title_text = normalize(title)
    keyword_text = normalize(" ; ".join(keywords or []))
    abstract_text = normalize(abstract)
    result: dict[str, int] = {}
    for field in candidates:
        pattern = patterns.get(field)
        if pattern is None:
            continue
        result[field] = (
            TITLE_WEIGHT * _hits(pattern, title_text)
            + KEYWORD_WEIGHT * _hits(pattern, keyword_text)
            + ABSTRACT_WEIGHT * min(_hits(pattern, abstract_text), ABSTRACT_CAP)
        )
    return result


def classify(
    title: str | None,
    keywords: Iterable[str] | None,
    abstract: str | None,
    journal_fields: Iterable[str] | None,
) -> list[str]:
    """Maqola sohasi: bitta soha yoki bo'sh ro'yxat."""
    candidates = list(dict.fromkeys(journal_fields or []))
    if len(candidates) <= 1:
        return candidates
    ranked = sorted(scores(title, keywords, abstract, candidates).items(), key=lambda item: -item[1])
    if not ranked:
        return []
    best_field, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if best >= MIN_SCORE and best >= MARGIN * second:
        return [best_field]
    return []
