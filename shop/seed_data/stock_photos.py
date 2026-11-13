"""Свободные фото Unsplash (Unsplash License) — строго по типу товара."""

# Только кадры, где на фото сам товар (не «сцена офиса», не чип, не консоль).
STOCK_BY_CATEGORY = {
    'keyboards-mech': [
        'photo-1587829741301-dc798b83add3',
        'photo-1511467687858-23d96c32e4ae',
        'photo-1541140532154-b024d705b90a',
        'photo-1595225476474-87563907a212',
        'photo-1563191911-e65f8655ebf9',
        'photo-1618384887929-16ec2cab24a6',
        'photo-1558050032-160f36233a07',
        'photo-1635514569146-9a9607ecf303',
    ],
    'keyboards-membrane': [
        'photo-1587829741301-dc798b83add3',
        'photo-1563191911-e65f8655ebf9',
        'photo-1486312338219-ce68d2c6f44d',
        'photo-1516321318423-f06f85e504b3',
        'photo-1496181133206-80ce9b88a853',
    ],
    'mice-gaming': [
        'photo-1527814050087-3793815479db',
        'photo-1615663245857-ac93bb7c39e7',
        'photo-1629429408209-1f912961dbd8',
        'photo-1563297007-0386f4f0d8bc',
        'photo-1605773527852-c546a8584ea3',
        'photo-1586349906319-48d20e1b87be',
    ],
    'mice-office': [
        'photo-1527814050087-3793815479db',
        'photo-1615663245857-ac93bb7c39e7',
        'photo-1629429408209-1f912961dbd8',
        'photo-1605773527852-c546a8584ea3',
    ],
    'mousepads': [
        'photo-1616587894289-86480e533129',
        'photo-1542751371-adc38448a05e',
        'photo-1593640408182-31c70c8268f5',
        'photo-1511512578047-dfb367046420',
    ],
    'headsets': [
        'photo-1484704849700-f032a568e944',
        'photo-1546435770-a3e426bf472b',
        'photo-1618366712010-f4ae9c647dcb',
        'photo-1505740420928-5e560c06d30e',
        'photo-1572536147248-ac59a8abfa4b',
        'photo-1599669454699-248893623440',
        'photo-1613040809024-b4ef7ba99bc3',
        'photo-1487215078519-e21cc028cb29',
    ],
    'webcams': [
        'photo-1587826080692-f439cd0b70da',
        'photo-1593697821252-0c9137d9fc45',
        'photo-1614624532983-4ce03382d20d',
    ],
    'usb-hubs': [
        'photo-1625948515291-69613efd103f',
        'photo-1597872200969-2b65d56bd16b',
        'photo-1553062407-98eeb64c6a62',
    ],
    'cables': [
        'photo-1553062407-98eeb64c6a62',
        'photo-1625948515291-69613efd103f',
        'photo-1609081219090-a6d81d3085bf',
        'photo-1590658268037-6bf12165a8df',
    ],
    'laptop-stands': [
        'photo-1496181133206-80ce9b88a853',
        'photo-1517336714731-489689fd1ca8',
        'photo-1527443224154-c4a3942d3acf',
    ],
    'cable-organizers': [
        'photo-1553062407-98eeb64c6a62',
        'photo-1597872200969-2b65d56bd16b',
        'photo-1609081219090-a6d81d3085bf',
    ],
    'chairs': [
        'photo-1592078615290-033ee584e267',
        'photo-1580480055273-228ff5388ef8',
        'photo-1586023492125-27b2c045efd7',
        'photo-1505843490538-47334a1aaf01',
    ],
    'cooling': [
        'photo-1591799264318-7e6ef8ddb7ea',
        'photo-1587202372775-e229f172b9d7',
        'photo-1555617981-dac3880eac6e',
        'photo-1518770660439-4636190af475',
    ],
    'thermal-paste': [
        'photo-1555617981-dac3880eac6e',
        'photo-1591799264318-7e6ef8ddb7ea',
        'photo-1518770660439-4636190af475',
    ],
    # Не клинеры/уборщики — макро салфеток / жидкости для экрана
    'wipes': [
        'photo-1584305574647-0cc949a2bb9f',
        'photo-1607619056574-7b8d3ee536b2',
        'photo-1631549916768-4119b2e5f926',
    ],
    'antistatic': [
        'photo-1581091226825-a6a2a5aee158',
        'photo-1581092160562-40aa08e78837',
        'photo-1581092918056-0c4c3acd3789',
    ],
}

# Близкие категории — запасной пул того же типа, не «любой tech».
RELATED = {
    'keyboards-mech': ['keyboards-membrane'],
    'keyboards-membrane': ['keyboards-mech'],
    'mice-gaming': ['mice-office'],
    'mice-office': ['mice-gaming'],
    'usb-hubs': ['cables', 'cable-organizers'],
    'cables': ['usb-hubs', 'cable-organizers'],
    'cable-organizers': ['cables', 'usb-hubs'],
    'thermal-paste': ['cooling'],
    'cooling': ['thermal-paste'],
    'wipes': ['antistatic'],
    'antistatic': ['wipes'],
}

FALLBACK = [
    'photo-1587829741301-dc798b83add3',
    'photo-1527814050087-3793815479db',
    'photo-1484704849700-f032a568e944',
]


def unsplash_url(photo_id: str, w: int = 900, h: int = 675) -> str:
    return (
        f'https://images.unsplash.com/{photo_id}'
        f'?auto=format&fit=crop&w={w}&h={h}&q=85'
    )


def pool_for_category(slug: str) -> list[str]:
    """Кадры своей категории + родственные (того же типа товара)."""
    seen: set[str] = set()
    out: list[str] = []
    for key in [slug] + RELATED.get(slug, []):
        for pid in STOCK_BY_CATEGORY.get(key, []):
            if pid not in seen:
                seen.add(pid)
                out.append(pid)
    if not out:
        out = list(FALLBACK)
    return out
