import os
import re
import io
import unicodedata
import asyncio
import discord
from typing import Optional
from discord.ext import commands
from datetime import datetime, timezone, timedelta

# ====== CONFIGURATION ======
VERIFY_CHANNEL_ID = 1402889712888447037
APPROVAL_CHANNEL_ID = 1402889786712395859
LOG_CHANNEL_ID = 1418941833819590699
ADMIN_NOTIFY_CHANNEL_ID = 1418941833819590699 

ROLE_ID_TO_GIVE = 1321268883088211981
ROLE_MALE = 1321268883025559689
ROLE_FEMALE = 1321268883025559688
ROLE_LGBT = 1321268883025559687
ROLE_GENDER_UNDISCLOSED = 1419046348023398421

# --- Age roles ---
ROLE_0_12   = 1402907371696558131
ROLE_13_15  = 1344232758129594379
ROLE_16_18  = 1344232891093090377
ROLE_19_21  = 1344232979647565924
ROLE_22_24  = 1344233048593403955
ROLE_25_29  = 1418703710137094357
ROLE_30_34  = 1418703702843457576
ROLE_35_39  = 1418703707100545075
ROLE_40_44  = 1418703944711929917
ROLE_45_49  = 1418703955176718396
ROLE_50_54  = 1418704062592843948
ROLE_55_59  = 1418704067194261615
ROLE_60_64  = 1418704072617496666
ROLE_65_UP  = 1418704076119736390
ROLE_AGE_UNDISCLOSED = 1419045340576747663

# ✅ ปิดการเติมวงเล็บชื่อเล่นอัตโนมัติ (เก็บไว้ใน ID Card อย่างเดียว)
APPEND_FORM_NAME_TO_NICK = False

# ====== AUTO REFRESH CONFIG (ตั้งเวลาเองได้) ======
AUTO_REFRESH_ENABLED = True
REFRESH_TZ = timezone(timedelta(hours=7))  # Asia/Bangkok
REFRESH_FREQUENCY = "YEARLY"               # "YEARLY" | "MONTHLY" | "WEEKLY" | "DAILY"
REFRESH_AT_HOUR = 6
REFRESH_AT_MINUTE = 0
REFRESH_AT_DAY = 1                         # ใช้กับ MONTHLY/YEARLY
REFRESH_AT_MONTH = 1                       # ใช้กับ YEARLY (1=มกราคม)
REFRESH_AT_WEEKDAY = 0                     # ใช้กับ WEEKLY (0=Mon .. 6=Sun)

# ====== Account risk (age only) ======
ACCOUNT_RISK_ENABLED = True
MIN_ACCOUNT_AGE_DAYS_HIGH = 3    # < 3 วัน = HIGH
MIN_ACCOUNT_AGE_DAYS_MED  = 7    # < 7 วัน = MED (และ >= 3)

# ====== BIRTHDAY NOTIFY CONFIG ======
BIRTHDAY_CHANNEL_ID = 1323069987845312554  # ช่องสำหรับอวยพร HBD
HBD_NOTIFY_ENABLED = True
HBD_NOTIFY_HOUR = 9     # แจ้งเตือนกี่โมง (เวลาไทย)
HBD_NOTIFY_MINUTE = 0

# ====== PRIVACY CONFIG ======
HIDE_BIRTHDAY_ON_IDCARD = True  # ซ่อนวันเกิดในบัตร ID Card
BIRTHDAY_HIDDEN_TEXT = "ไม่แสดง"

# ====== HBD MESSAGE ROTATION ======
HBD_MESSAGES = [
    "🎉🎂 สุขสันต์วันเกิด {mention}! ขอให้ปีนี้มีแต่สิ่งดี ๆ เข้ามา 🥳",
    "✨🎂 HBD {mention}! สุขภาพแข็งแรง สมหวังทุกเรื่องนะ!",
    "🥳🎉 Happy Birthday {mention}! ขอให้รอยยิ้มอยู่กับเธอทั้งปี",
    "🎈🎂 สุขสันต์วันเกิดนะ {mention}! งานปัง เงินปั๊วะ ความสุขล้น ๆ",
    "🍰🎉 HBD {mention}! ขอให้ทุกความพยายามสำเร็จสวยงาม",
    "🌟🎂 Happy Birthday {mention}! ให้วันนี้พิเศษกว่าทุกวัน",
    "🎁🎉 สุขสันต์วันเกิด {mention}! ขอให้สมหวังในสิ่งที่ตั้งใจ",
    "🧁🎈 HBD {mention}! พักผ่อนให้พอ มีแรงลุยต่อทั้งปีนะ",
    "🌈🎂 Happy Birthday {mention}! ขอให้โชคดีและมีแต่เรื่องดี ๆ",
    "💫🎉 สุขสันต์วันเกิด {mention}! ให้ทุกวันเต็มไปด้วยพลังบวก",
]

# ====== DISCORD BOT SETUP ======
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents)
pending_verifications = set()

INVALID_CHARS = set("=+*/@#$%^&*()<>?|{}[]\"'\\~`")

EMOJI_RE = re.compile(
    r"["
    r"\U0001F300-\U0001F5FF"
    r"\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F700-\U0001F77F"
    r"\U0001F780-\U0001F7FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FA6F"
    r"\U0001FA70-\U0001FAFF"
    r"\u2600-\u26FF"
    r"\u2700-\u27BF"
    r"]"
    r"|[\u200d\uFE0F]"
    r"|[\U0001F1E6-\U0001F1FF]{2}"
)
def contains_emoji(s: str) -> bool:
    return bool(EMOJI_RE.search(s or ""))

# ====== Admin notifications ======
async def notify_admin(guild: discord.Guild, text: str):
    try:
        ch = guild.get_channel(ADMIN_NOTIFY_CHANNEL_ID) or guild.get_channel(APPROVAL_CHANNEL_ID)
        if ch:
            await ch.send(f"🔔 **Admin Notice:** {text}")
    except Exception:
        pass

# ====== Nickname canonicalizer & same-name block ======
_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]")
_CONFUSABLES_MAP = str.maketrans({
    # Cyrillic -> Latin
    "А":"A","В":"B","Е":"E","К":"K","М":"M","Н":"H","О":"O","Р":"P","С":"S","Т":"T","У":"Y","Х":"X",
    "а":"a","в":"b","е":"e","к":"k","м":"m","н":"h","о":"o","р":"p","с":"c","т":"t","у":"y","х":"x",
    # Greek -> Latin
    "Α":"A","Β":"B","Ε":"E","Ζ":"Z","Η":"H","Ι":"I","Κ":"K","Μ":"M","Ν":"N","Ο":"O","Ρ":"P","Τ":"T","Υ":"Y","Χ":"X",
    "α":"a","β":"b","ε":"e","ι":"i","κ":"k","ν":"n","ο":"o","ρ":"p","τ":"t","υ":"y","χ":"x",
})
_LEET_MAP = str.maketrans({
    "0":"o","1":"l","3":"e","4":"a","5":"s","7":"t","8":"b","9":"g","2":"z","6":"g",
    "@":"a","$":"s","+":"t"
})
def _strip_combining(s: str) -> str:
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
def _letters_only(s: str) -> str:
    return "".join(ch for ch in s if unicodedata.category(ch).startswith("L"))
def _collapse_runs(s: str) -> str:
    if not s: return s
    out=[s[0]]
    for ch in s[1:]:
        if ch!=out[-1]: out.append(ch)
    return "".join(out)
def _canon_full(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKC", s)
    s = _ZERO_WIDTH_RE.sub("", s)
    s = EMOJI_RE.sub("", s)
    s = s.translate(_CONFUSABLES_MAP)
    s = s.translate(_LEET_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = _strip_combining(s)
    s = _letters_only(s)
    s = s.casefold()
    s = _collapse_runs(s)
    return s
def _base_display_name(member: discord.Member | discord.User) -> str:
    base = (
        getattr(member, "nick", None)
        or getattr(member, "global_name", None)
        or getattr(member, "display_name", None)
        or getattr(member, "name", None)
        or ""
    ).strip()
    # ลบวงเล็บชื่อเล่นเดิม (ถ้ามี)
    return re.sub(r"\s*\(.*?\)\s*$", "", base).strip()
def _discord_names_set(member: discord.Member | discord.User) -> set[str]:
    names = filter(None, {
        getattr(member, "nick", ""),
        getattr(member, "global_name", ""),
        getattr(member, "display_name", ""),
        getattr(member, "name", ""),
        _base_display_name(member),
    })
    return {_canon_full(x) for x in names if x}

# ====== Gender Normalizer & Aliases ======
def _norm_gender(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r'[\s\.\-_\/\\]+', '', s)
    return s

_MALE_ALIASES_RAW = {
    "ช", "ชา", "ชาย", "ผู้ชาย", "เพศชาย", "ผช", "ชายแท้", "หนุ่ม",
    "male", "man", "boy", "m", "masculine", "he", "him",
    "男", "男性", "男生", "男人",
    "男", "男性", "おとこ", "だんせい",
    "남", "남자", "남성",
    "nam", "đàn ông", "dan ong", "con trai", "nam giới", "namgioi",
    "pria", "laki", "laki-laki", "lelaki", "cowok",
    "lalaki",
    "पुरुष", "aadmi", "ladka", "पुरूष", "mard", "आदमी", "مرد",
    "ذكر", "रجل", "صبي",
    "erkek", "bay",
    "мужчина", "парень", "мальчик", "чоловік", "хлопець",
    "hombre", "masculino", "chico", "varon", "varón",
    "homem", "rapaz",
    "homme", "masculin", "garçon",
    "mann", "männlich", "junge",
    "uomo", "maschio", "ragazzo",
    "mezczyzna", "mężczyzna", "chlopak", "chłopak",
    "muž", "chlapec",
    "andras", "άνδρας", "arseniko", "αρσενικό", "agori", "αγόρι",
    "ຜູ້ຊາຍ", "ប្រុស", "បុរស", "ယောက်ျား", "အမျိုးသား",
}
_FEMALE_ALIASES_RAW = {
    "ห", "หญ", "หญิ", "หญิง", "ผู้หญิง", "เพศหญิง", "ผญ", "สาว", "ญ",
    "female", "woman", "girl", "f", "feminine", "she", "her",
    "女", "女性", "女生", "女人",
    "女", "女性", "おんな", "じょせい",
    "여", "여자", "여성",
    "nữ", "phụ nữ", "con gái",
    "wanita", "perempuan", "cewek",
    "babae", "dalaga",
    "महिला", "औरत", "लड़की", "ladki", "aurat", "عورت", "ขатون",
    "أنثى", "امرأة", "بنت", "فتاة",
    "kadın", "bayan", "kız",
    "женщина", "девушка", "девочка", "жінка", "дівчина",
    "mujer", "femenino", "chica",
    "mulher", "feminina", "menina",
    "femme", "féminin", "fille",
    "frau", "weiblich", "mädchen",
    "donna", "femmina", "ragazza",
    "kobieta", "dziewczyna", "zenska", "żeńska",
    "žena", "dívka",
    "gynaika", "γυναίκα", "thyliko", "θηλυκό", "koritsi", "κορίτσι",
    "ຜູ້ຍິງ", "ស្រី", "នារី", "မိန်းမ", "အမျိုးသမီး",
}
_LGBT_ALIASES_RAW = {
    "lgbt", "lgbtq", "lgbtq+",
    "nonbinary", "non-binary", "nb", "enby",
    "trans", "transgender",
    "genderqueer", "bigender", "agender", "genderfluid",
    "queer", "other",
    "เกย์", "เกย", "เกย์ชาย", "เกย์หญิง",
    "เลส", "เลสเบี้ยน", "เลสเบียน",
    "ไบ", "ไบเซ็กชวล", "แพน", "แพนเซ็กชวล",
    "เพศทางเลือก", "สาวสอง", "สาวประเภทสอง", "ทอม", "ดี้",
    "非二元", "跨性别", "酷儿",
    "ノンバイナリー", "xジェンダー", "トランス", "クィア",
    "논바이너리", "트랜스", "퀴어",
    "gay", "lesbian", "bi", "bisexual", "pan", "pansexual",
}
_GENDER_UNDISCLOSED_ALIASES_RAW = {
    "ไม่ระบุ", "ไม่ระบุเพศ", "ไม่อยากเปิดเผย", "ไม่สะดวก", "ไม่สะดวกกรอก", "ไม่บอก",
    "prefer not to say", "prefer-not-to-say", "undisclosed", "unspecified", "unknown", "private", "secret",
    "n/a", "na", "none", "—", "-"
}

MALE_ALIASES   = {_norm_gender(x) for x in _MALE_ALIASES_RAW}
FEMALE_ALIASES = {_norm_gender(x) for x in _FEMALE_ALIASES_RAW}
LGBT_ALIASES   = {_norm_gender(x) for x in _LGBT_ALIASES_RAW}
GENDER_UNDISCLOSED_ALIASES = {_norm_gender(x) for x in _GENDER_UNDISCLOSED_ALIASES_RAW}

MALE_PREFIXES   = {_norm_gender(x) for x in ["ช", "ชา", "ชาย", "ผู้ช", "เพศช", "m", "ma", "masc", "man", "男", "おとこ", "だん", "남"]}
FEMALE_PREFIXES = {_norm_gender(x) for x in ["ห", "หญ", "หญิ", "หญิง", "ผู้ห", "เพศห", "f", "fe", "fem", "woman", "wo", "女", "おんな", "じょ", "여"]}

# ====== Age "ไม่ระบุ" ======
def _norm_simple(s: str) -> str:
    return re.sub(r'[\s\.\-_\/\\]+', '', (s or '').strip().lower())
_AGE_UNDISCLOSED_ALIASES_RAW = {
    "ไม่ระบุ","ไม่บอก","ไม่เปิดเผย","ไม่อยากเปิดเผย","ไม่สะดวกกรอก","ไม่สะดวก","ไม่ต้องการระบุ","ปกปิด",
    "prefer not to say","prefer-not-to-say","undisclosed","unspecified","unknown","private","secret",
    "n/a","na","none","x","-","—"
}
AGE_UNDISCLOSED_ALIASES = {_norm_simple(x) for x in _AGE_UNDISCLOSED_ALIASES_RAW}
def is_age_undisclosed(text: str) -> bool:
    t = _norm_simple(text)
    return (t == "") or (t in AGE_UNDISCLOSED_ALIASES)  # ว่าง = ไม่ระบุ

def resolve_gender_role_id(text: str) -> int:
    t = _norm_gender(text)
    if t in MALE_ALIASES or any(t.startswith(p) for p in MALE_PREFIXES):
        return ROLE_MALE
    if t in FEMALE_ALIASES or any(t.startswith(p) for p in FEMALE_PREFIXES):
        return ROLE_FEMALE
    if t in LGBT_ALIASES:
        return ROLE_LGBT
    if t in GENDER_UNDISCLOSED_ALIASES:
        return ROLE_GENDER_UNDISCLOSED
    return ROLE_GENDER_UNDISCLOSED

def resolve_age_role_id(age_text: str) -> int | None:
    if is_age_undisclosed(age_text):
        return ROLE_AGE_UNDISCLOSED
    try:
        age = int((age_text or "").strip())
    except ValueError:
        return None
    slots = [
        ((0, 12), ROLE_0_12),
        ((13, 15), ROLE_13_15),
        ((16, 18), ROLE_16_18),
        ((19, 21), ROLE_19_21),
        ((22, 24), ROLE_22_24),
        ((25, 29), ROLE_25_29),
        ((30, 34), ROLE_30_34),
        ((35, 39), ROLE_35_39),
        ((40, 44), ROLE_40_44),
        ((45, 49), ROLE_45_49),
        ((50, 54), ROLE_50_54),
        ((55, 59), ROLE_55_59),
        ((60, 64), ROLE_60_64),
        ((65, 200), ROLE_65_UP),
    ]
    for (lo, hi), rid in slots:
        if lo <= age <= hi and rid > 0:
            return rid
    return None

# ====== Helpers ======

async def _has_any_pending_embed_for_user(bot: commands.Bot, user_id: int) -> bool:
    try:
        for guild in bot.guilds:
            ch = guild.get_channel(APPROVAL_CHANNEL_ID)
            if not ch:
                continue
            member = guild.get_member(user_id)
            if not member:
                # ถ้าไม่ใช่สมาชิกกิลด์นี้ก็ข้าม
                continue
            # ใช้ฟังก์ชันเดิมเพื่อหาข้อความล่าสุดของคนนี้
            msg = await _find_latest_approval_message(guild, member)
            if msg:
                return True
        return False
    except Exception:
        # ถ้ามี error ใด ๆ อย่าทำให้ล้มทั้งฟังก์ชัน — ถือว่า “ไม่เจอ”
        return False

_USERID_RE = re.compile(r"User ID:\s*(\d{17,20})")

def _user_id_from_embed_footer(e: discord.Embed) -> int | None:
    try:
        ft = (e.footer.text or "")
        m = _USERID_RE.search(ft)
        return int(m.group(1)) if m else None
    except Exception:
        return None

def _message_belongs_to_member(message: discord.Message, member: discord.Member) -> bool:
    if message.mentions and member in message.mentions:
        return True
    try:
        e = message.embeds[0]
    except Exception:
        return False
    uid = _user_id_from_embed_footer(e)
    return uid == member.id if uid is not None else False

async def build_avatar_attachment(user: discord.User):
    try:
        asset = user.display_avatar
        if asset is None:
            return None, None
        try:
            data = await asset.with_format("webp").with_size(512).read()
            filename = f"avatar_{user.id}.webp"
        except Exception:
            data = await asset.with_static_format("png").with_size(512).read()
            filename = f"avatar_{user.id}.png"

        file = discord.File(io.BytesIO(data), filename=filename)
        return file, filename
    except Exception:
        return None, None


def copy_embed_fields(src: discord.Embed) -> discord.Embed:
    e = discord.Embed()
    if src.title:
        e.title = src.title
    if src.description:
        e.description = src.description
    if getattr(src, "color", None) is not None:
        e.color = src.color
    if getattr(src, "author", None):
        name = getattr(src.author, "name", None)
        icon = getattr(src.author, "icon_url", None)
        url = getattr(src.author, "url", None)
        if name or icon or url:
            e.set_author(name=name or None, icon_url=icon or None, url=url or None)
    if getattr(src, "footer", None):
        text = getattr(src.footer, "text", None)
        icon = getattr(src.footer, "icon_url", None)
        if text or icon:
            e.set_footer(text=text or None, icon_url=icon or None)
    if src.image and src.image.url:
        e.set_image(url=src.image.url)
    if src.thumbnail and src.thumbnail.url:
        e.set_thumbnail(url=src.thumbnail.url)
    for f in src.fields:
        e.add_field(name=f.name, value=f.value, inline=f.inline)
    return e

def mask_birthday_field_for_idcard(e: discord.Embed):
    """
    ปิดบังวันเกิดบน ID Card (ผู้ใช้เห็น) แต่ยังเก็บจริงไว้ใน embed ห้องอนุมัติ
    ถ้าจะลบช่องออก ให้ใช้ e.remove_field(i) แทน set_field_at
    """
    try:
        for i, f in enumerate(e.fields):
            nm = (f.name or "").lower()
            if ("birthday" in nm) or ("วันเกิด" in nm):
                if HIDE_BIRTHDAY_ON_IDCARD:
                    e.set_field_at(i, name=f.name, value=BIRTHDAY_HIDDEN_TEXT, inline=False)
                break
    except Exception:
        pass

def build_parenthesized_nick(member: discord.Member, form_name: str) -> str:
    base = (
        member.nick
        or getattr(member, "global_name", None)
        or member.display_name
        or member.name
        or ""
    ).strip()
    base = re.sub(r"\s*\(.*?\)\s*$", "", base).strip()
    real = (form_name or "").strip()
    candidate = f"{base} ({real})".strip()
    if len(candidate) <= 32:
        return candidate
    max_base = 32 - (len(real) + 3)
    if max_base > 1:
        candidate = f"{base[:max_base].rstrip()} ({real})"
        if len(candidate) <= 32:
            return candidate
    return real[:32]

# ---------- Role sets ----------
GENDER_ROLE_IDS_ALL = [ROLE_MALE, ROLE_FEMALE, ROLE_LGBT, ROLE_GENDER_UNDISCLOSED]
AGE_ROLE_IDS_ALL = [rid for rid in [
    ROLE_0_12, ROLE_13_15, ROLE_16_18, ROLE_19_21, ROLE_22_24,
    ROLE_25_29, ROLE_30_34, ROLE_35_39, ROLE_40_44, ROLE_45_49,
    ROLE_50_54, ROLE_55_59, ROLE_60_64, ROLE_65_UP, ROLE_AGE_UNDISCLOSED
] if rid and rid > 0]

# ---------- Utils for refresh ----------
def _find_embed_field(embed: discord.Embed, *keys: str) -> str | None:
    keys = [k.lower() for k in keys]
    for f in embed.fields:
        name = (f.name or "").lower()
        if any(k in name for k in keys):
            return f.value
    return None

def _parse_sent_at(s: str) -> datetime | None:
    try:
        dt = datetime.strptime(s.strip(), "%d/%m/%Y %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=7)))
    except Exception:
        return None

def _years_between(a: datetime, b: datetime) -> int:
    years = b.year - a.year
    if (b.month, b.day) < (a.month, a.day):
        years -= 1
    return max(years, 0)

# ====== Birthday helpers (optional) ======
_BDAY_RE = re.compile(r"^\s*(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})\s*$")

def parse_birthday(text: str) -> datetime | None:
    """
    รับรูปแบบ dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy
    คืนค่า datetime(tz=Asia/Bangkok) เวลา 00:00 ถ้าถูกต้อง
    """
    if not text:
        return None
    m = _BDAY_RE.match(text)
    if not m:
        return None
    d, mth, y = map(int, m.groups())
    try:
        dt = datetime(y, mth, d, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    except ValueError:
        return None
    # ห้ามอนาคต
    now = datetime.now(timezone(timedelta(hours=7)))
    if dt > now:
        return None
    # guard ปีสมเหตุสมผล
    if y < 1900 or y > now.year:
        return None
    return dt

def age_from_birthday(bday: datetime, now_local: datetime | None = None) -> int:
    now_local = now_local or datetime.now(timezone(timedelta(hours=7)))
    return _years_between(bday, now_local)

async def _latest_verification_embed_for(member: discord.Member) -> discord.Embed | None:
    channel = member.guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        return None
    async for msg in channel.history(limit=500):
        if msg.author == bot.user and msg.embeds and _message_belongs_to_member(msg, member):
            return msg.embeds[0]
    return None

async def _build_latest_verification_index(guild: discord.Guild, limit: int = 2000):
    channel = guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        return {}

    index: dict[int, tuple[discord.Embed, datetime]] = {}
    async for msg in channel.history(limit=limit):
        if msg.author != bot.user or not msg.embeds:
            continue

        e = msg.embeds[0]
        uid = _user_id_from_embed_footer(e)
        if uid is None and msg.mentions:
            uid = msg.mentions[0].id
        if uid is None:
            continue

        if uid not in index:
            index[uid] = (e, msg.created_at)

    return index

async def _log_chunks(channel: discord.TextChannel, header: str, lines: list[str], chunk_size: int = 1900):
    if not lines:
        await channel.send(header)
        return
    buf = header + "\n"
    for line in lines:
        if len(buf) + len(line) + 1 > chunk_size:
            await channel.send(buf.rstrip())
            buf = ""
        buf += line + "\n"
    if buf.strip():
        await channel.send(buf.rstrip())

async def _run_full_age_refresh(guild: discord.Guild):
    tz = timezone(timedelta(hours=7))
    now = datetime.now(tz)
    log_ch = guild.get_channel(LOG_CHANNEL_ID)
    if not log_ch:
        return

    index = await _build_latest_verification_index(guild)
    candidates = []
    for uid, (embed, _) in index.items():
        m = guild.get_member(uid)
        if m:
            candidates.append((m, embed))

    changed_lines = []
    error_lines = []

    for member, embed in candidates:
        # ✅ PRIORITY: birthday
        bday_text = _find_embed_field(embed, "birthday", "วันเกิด")
        if bday_text and str(bday_text).strip() not in {"", "ไม่ระบุ"}:
            bday_dt = parse_birthday(str(bday_text))
            if bday_dt:
                years = age_from_birthday(bday_dt, now)
                new_role_id = resolve_age_role_id(str(years))
                new_role = guild.get_role(new_role_id) if new_role_id else None
                to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and (new_role is None or r.id != new_role.id)]
                try:
                    if to_remove:
                        await member.remove_roles(*to_remove, reason=f"Age refresh (birthday) → now {years}")
                    if new_role and new_role not in member.roles:
                        await member.add_roles(new_role, reason=f"Age refresh (birthday) → now {years}")
                    old_names = ", ".join(r.name for r in to_remove) if to_remove else "—"
                    changed_lines.append(f"✅ {member.mention}: {years} ปี (จากวันเกิด) → {new_role.name if new_role else '—'} (removed: {old_names})")
        
                    await _update_approval_embed_for_member(guild, member, age=str(years))
                except discord.Forbidden:
                    error_lines.append(f"❌ {member.mention}: ปรับยศจากวันเกิดไม่สำเร็จ (สิทธิ์)")
                except discord.HTTPException:
                    error_lines.append(f"❌ {member.mention}: ปรับยศจากวันเกิดไม่สำเร็จ (HTTP)")
            continue

        age_text = _find_embed_field(embed, "age", "อายุ")
        sent_text = _find_embed_field(embed, "sent at")
        if not age_text or not sent_text:
            error_lines.append(f"❌ {member.mention}: Embed ขาด Age/Sent at")
            continue

        if is_age_undisclosed(str(age_text)):
            new_role = guild.get_role(ROLE_AGE_UNDISCLOSED)
            to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and (new_role is None or r.id != new_role.id)]
            try:
                if to_remove:
                    await member.remove_roles(*to_remove, reason="Age refresh → undisclosed")
                if new_role and new_role not in member.roles:
                    await member.add_roles(new_role, reason="Age refresh → undisclosed")
                changed_lines.append(f"✅ {member.mention}: อายุไม่ระบุ → {new_role.name if new_role else '—'}")
            except discord.Forbidden:
                error_lines.append(f"❌ {member.mention}: ปรับยศ 'ไม่ระบุอายุ' ไม่สำเร็จ (สิทธิ์)")
            except discord.HTTPException:
                error_lines.append(f"❌ {member.mention}: ปรับยศ 'ไม่ระบุอายุ' ไม่สำเร็จ (HTTP)")
            continue

        try:
            old_age = int(str(age_text).strip())
        except ValueError:
            error_lines.append(f"❌ {member.mention}: Age เดิมไม่ใช่ตัวเลข: {age_text!r}")
            continue

        sent_dt = _parse_sent_at(sent_text)
        if not sent_dt:
            error_lines.append(f"❌ {member.mention}: Sent at ไม่ถูกต้อง: {sent_text!r}")
            continue

        added_years = _years_between(sent_dt, now)
        new_age = max(old_age + added_years, 0)
        new_role_id = resolve_age_role_id(str(new_age))
        new_role = guild.get_role(new_role_id) if new_role_id else None

        to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and (new_role is None or r.id != new_role.id)]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason=f"Age refresh → now {new_age}")
        except discord.Forbidden:
            error_lines.append(f"❌ {member.mention}: ไม่มีสิทธิ์ถอดยศอายุเดิม")
            continue
        except discord.HTTPException:
            error_lines.append(f"❌ {member.mention}: ถอดยศอายุเดิมไม่สำเร็จ (HTTP)")
            continue

        if new_role:
            try:
                await member.add_roles(new_role, reason=f"Age refresh → now {new_age}")
                old_names = ", ".join(r.name for r in to_remove) if to_remove else "—"
                changed_lines.append(f"✅ {member.mention}: {new_age} ปี → {new_role.name} (removed: {old_names})")
            except discord.Forbidden:
                error_lines.append(f"❌ {member.mention}: เพิ่มยศใหม่ไม่สำเร็จ (สิทธิ์ไม่พอ)")
            except discord.HTTPException:
                error_lines.append(f"❌ {member.mention}: เพิ่มยศใหม่ไม่สำเร็จ (HTTP)")
        else:
            changed_lines.append(f"⚠️ {member.mention}: {new_age} ปี → ไม่มี role ที่แมปไว้")

    tag = _refresh_period_tag(now, REFRESH_FREQUENCY)
    header = (
        f"{tag} • Guild: {guild.name}\n"
        f"Members found: {len(candidates)}\n"
        f"Changed/No-map: {len(changed_lines)} • Errors: {len(error_lines)}"
    )
    await _log_chunks(log_ch, header, changed_lines + (["— Errors —"] + error_lines if error_lines else []))

# ====== Update latest approval embed (helpers) ======
async def _find_latest_approval_message(guild: discord.Guild, member: discord.Member):
    ch = guild.get_channel(APPROVAL_CHANNEL_ID)
    if not ch:
        return None
    async for m in ch.history(limit=1000):
        if m.author == bot.user and m.embeds and _message_belongs_to_member(m, member):
            return m
    return None

def _set_or_add_field(embed: discord.Embed, name_keys: tuple[str, ...], display_name: str, value: str):
    name_keys_low = tuple(k.lower() for k in name_keys)
    for i, f in enumerate(embed.fields):
        nm = (f.name or "").lower()
        if any(k in nm for k in name_keys_low):
            embed.set_field_at(i, name=display_name, value=value, inline=False)
            return
    embed.add_field(name=display_name, value=value, inline=False)

async def _update_approval_embed_for_member(guild: discord.Guild, member: discord.Member, *,
                                            nickname: str | None = None,
                                            age: str | None = None,
                                            gender: str | None = None,
                                            birthday: str | None = None) -> bool:
    msg = await _find_latest_approval_message(guild, member)
    if not msg:
        return False
    e = msg.embeds[0]
    if nickname is not None:
        _set_or_add_field(e, ("nickname", "ชื่อเล่น"), "Nickname / ชื่อเล่น", nickname or "ไม่ระบุ")
    if age is not None:
        _set_or_add_field(e, ("age", "อายุ"), "Age / อายุ", age or "ไม่ระบุ")
    if gender is not None:
        _set_or_add_field(e, ("gender", "เพศ"), "Gender / เพศ", gender or "ไม่ระบุ")
    if birthday is not None:
        _set_or_add_field(e, ("birthday", "วันเกิด"), "Birthday / วันเกิด", birthday or "ไม่ระบุ")
    try:
        await msg.edit(embed=e)
        return True
    except discord.HTTPException:
        return False

# ====== Account risk helpers (age-only) ======
from datetime import timezone as _dt_timezone, timedelta as _dt_timedelta
def assess_account_risk_age_only(user: discord.User) -> tuple[int | None, str, list[str]]:
    try:
        created_at = user.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=_dt_timezone.utc)
        now = datetime.now(_dt_timezone.utc)
        delta = now - created_at
        age_days_float = delta.total_seconds() / 86400.0
        age_days_int = int(delta.total_seconds() // 86400)
    except Exception:
        return None, "UNKNOWN", ["cannot compute account age"]

    reasons = []
    if age_days_float < float(MIN_ACCOUNT_AGE_DAYS_HIGH):
        reasons.append(f"age<{MIN_ACCOUNT_AGE_DAYS_HIGH}d")
        return age_days_int, "HIGH", reasons
    if age_days_float < float(MIN_ACCOUNT_AGE_DAYS_MED):
        reasons.append(f"age<{MIN_ACCOUNT_AGE_DAYS_MED}d")
        return age_days_int, "MED", reasons
    return age_days_int, "LOW", reasons

def build_account_check_field(user: discord.User) -> tuple[str, str, str, int | None]:
    age_days, risk, reasons = assess_account_risk_age_only(user)
    icon = "⚠️" if risk == "HIGH" else ("🟧" if risk == "MED" else ("🟩" if risk == "LOW" else "❔"))
    age_txt = "—" if age_days is None else f"{age_days} days"
    reason_txt = f" • Reasons: {', '.join(reasons)}" if reasons else ""
    name = "🛡️ Account Check"
    value = f"Account age: {age_txt} • Risk: {risk} {icon}{reason_txt}"
    return name, value, risk, age_days

# =========== Modal / Views / Commands ===========
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    name = discord.ui.TextInput(
        label="Nickname / ชื่อเล่น (จำเป็นต้องกรอก)", 
        placeholder="ตัวอักษร 2–16",
        style=discord.TextStyle.short,
        min_length=2, max_length=16,
        required=True
    )
    gender = discord.ui.TextInput(
        label="Gender / เพศ (ไม่บังคับ)",
        placeholder="เช่น ชาย / หญิง / LGBT",
        style=discord.TextStyle.short,
        required=False
    )
    age = discord.ui.TextInput(
        label="Age / อายุ (ไม่บังคับ)",
        placeholder="เช่น 21",
        style=discord.TextStyle.short,
        required=False
    )
    birthday = discord.ui.TextInput(
        label="Birthday / วันเกิด dd/mm/yyyy (กรอกหากต้องการระบบ HBD)",
        placeholder="เช่น 12/09/2003",
        style=discord.TextStyle.short,
        required=False
    )



    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
            if member and any(r.id == ROLE_ID_TO_GIVE for r in member.roles):
                await interaction.followup.send(
                    "✅ ระบบพบว่าคุณได้รับการยืนยันตัวตนแล้ว จึงไม่สามารถส่งคำขอซ้ำได้\n"
                    "If you think this is a mistake, please contact an admin.",
                    ephemeral=True
                )
                return

            # PATCH: กันกดซ้ำ แต่ตรวจ 'ของจริง' ในห้องก่อน
            if interaction.user.id in pending_verifications:
                still_has = await _has_any_pending_embed_for_user(interaction.client, interaction.user.id)
                if still_has:
                    await interaction.followup.send(
                        "❗ You already submitted a verification request. Please wait for admin review.\n"
                        "❗ คุณได้ส่งคำขอไปแล้ว กรุณารอการอนุมัติจากแอดมิน",
                        ephemeral=True
                    )
                    return
                else:
                    # PATCH: เคยค้างแต่ embed ถูกลบไปแล้ว → ล้างสถานะ เพื่อให้ส่งใหม่ได้
                    pending_verifications.discard(interaction.user.id)

            # -------- validation --------
            age_raw = (self.age.value or "").strip()
            if not (age_raw == "" or re.fullmatch(r"\d{1,3}", age_raw) or is_age_undisclosed(age_raw)):
                await interaction.followup.send(
                    "❌ รูปแบบอายุไม่ถูกต้อง\n"
                    "• ใส่เป็นตัวเลข 1–3 หลัก เช่น 21\n"
                    "• หรือพิมพ์/ปล่อยว่าง เพื่อ “ไม่ระบุ”",
                    ephemeral=True
                )
                return

            nick = (self.name.value or "").strip()
            if nick:  # ตรวจเมื่อไม่ว่างเท่านั้น
                if (
                    len(nick) < 2 or len(nick) > 16
                    or any(ch.isdigit() for ch in nick)
                    or any(c in INVALID_CHARS for c in nick)
                    or contains_emoji(nick)
                ):
                    await interaction.followup.send(
                        "❌ Nickname invalid (ต้องเป็นตัวอักษร 2–16 ตัว และห้ามตัวเลข/สัญลักษณ์/อีโมจิ)\n"
                        "If you don't want a nickname, you can leave it blank.",
                        ephemeral=True
                    )
                    return
                if _canon_full(nick) in _discord_names_set(interaction.user):
                    await interaction.followup.send(
                        "❌ ชื่อเล่นต้องต่างจากชื่อในดิสคอร์ดของคุณจริง ๆ\n"
                        "If you don't want a nickname, you can leave it blank.",
                        ephemeral=True
                    )
                    return

            gender_raw = (self.gender.value or "")
            if gender_raw.strip():
                if _norm_gender(gender_raw) not in GENDER_UNDISCLOSED_ALIASES:
                    if any(ch.isdigit() for ch in gender_raw) or any(c in INVALID_CHARS for c in gender_raw) or contains_emoji(gender_raw):
                        await interaction.followup.send("❌ Gender invalid. Text only.", ephemeral=True)
                        return

            birthday_raw = (self.birthday.value or "").strip()
            if birthday_raw:
                if not parse_birthday(birthday_raw):
                    await interaction.followup.send(
                        "❌ รูปแบบวันเกิดไม่ถูกต้อง (ใช้ dd/mm/yyyy เช่น 05/11/2004)\n"
                        "• อนุญาตตัวคั่น / หรือ - หรือ .",
                        ephemeral=True
                    )
                    return

            # PATCH: ถ้าไม่ได้กรอกอายุ แต่กรอกวันเกิด → คำนวณให้อัตโนมัติ
            if not age_raw and birthday_raw:
                bdate = parse_birthday(birthday_raw)
                if bdate:
                    today = datetime.now(timezone(timedelta(hours=7))).date()
                    age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
                    # ป้องกันค่าผิดปกติ เช่นอายุเกิน 120 ปี
                    if 0 <= age <= 120:
                        age_raw = str(age)

            # PATCH: mark pending (จะถูกล้างตอน Approve/Reject)
            pending_verifications.add(interaction.user.id)

            # -------- build embed --------
            display_nick = nick if nick else "ไม่ระบุ"
            display_age = (age_raw if age_raw else "ไม่ระบุ")
            display_gender = (gender_raw.strip() if gender_raw.strip() else "ไม่ระบุ")
            display_birthday = birthday_raw if birthday_raw else "ไม่ระบุ"

            embed = discord.Embed(
                title="📋 Verification Request / คำขอยืนยันตัวตน",
                color=discord.Color.orange()
            )

            # PATCH: ใช้ URL แทนไฟล์แนบเสมอ เพื่อให้ได้ thumbnail เล็กตลอด
            thumb_url = interaction.user.display_avatar.with_static_format("png").with_size(128).url
            embed.set_thumbnail(url=thumb_url)

            embed.add_field(name="Nickname / ชื่อเล่น", value=display_nick, inline=False)
            embed.add_field(name="Gender / เพศ", value=display_gender, inline=False)
            embed.add_field(name="Age / อายุ", value=display_age, inline=False)
            embed.add_field(name="Birthday / วันเกิด", value=display_birthday, inline=False)

            if ACCOUNT_RISK_ENABLED:
                name, value, risk, age_days = build_account_check_field(interaction.user)
                embed.add_field(name=name, value=value, inline=False)
                if risk == "HIGH":
                    await notify_admin(interaction.guild, f"{interaction.user.mention} มีความเสี่ยงสูงจากอายุบัญชี ({age_days} วัน)")

            now = datetime.now(timezone(timedelta(hours=7)))
            embed.add_field(name="📅 Sent at", value=now.strftime("%d/%m/%Y %H:%M"), inline=False)
            embed.set_footer(text=f"User ID: {interaction.user.id}")

            # -------- send to approval channel with persistent view --------
            channel = interaction.guild.get_channel(APPROVAL_CHANNEL_ID)
            if not channel:
                await notify_admin(interaction.guild, "ไม่พบห้อง APPROVAL_CHANNEL_ID")
                await interaction.followup.send("⚠️ ระบบขัดข้อง: ไม่พบห้องอนุมัติ แจ้งแอดมินเรียบร้อย", ephemeral=True)
                return

            view = GlobalApproveRejectView()

            await channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False)
                # PATCH: ไม่แนบไฟล์ เพื่อไม่ให้เกิดรูปใหญ่
            )

            await interaction.followup.send(
                "✅ Verification request submitted. Please wait for admin approval.\n"
                "✅ ส่งคำขอยืนยันตัวตนแล้ว กรุณารอการอนุมัติจากแอดมิน",
                ephemeral=True
            )

        except Exception as e:
            pending_verifications.discard(interaction.user.id)
            await notify_admin(interaction.guild, f"เกิดข้อผิดพลาดตอนส่งแบบฟอร์มของ {interaction.user.mention}: {e!r}")
            try:
                await interaction.followup.send("❌ ระบบขัดข้อง กรุณาลองใหม่ภายหลัง", ephemeral=True)
            except Exception:
                pass


class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Identity / ยืนยันตัวตน", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 🔒 ถ้าสมาชิกมียศยืนยันแล้ว → ไม่ให้เปิดฟอร์ม
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
        if member and any(r.id == ROLE_ID_TO_GIVE for r in member.roles):
            await interaction.response.send_message(
                "✅ คุณได้รับการยืนยันตัวตนแล้ว จึงไม่ต้องกดอีกครั้ง\n"
                "If you think this is a mistake, please contact an admin.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(VerificationForm())

class GlobalApproveRejectView(discord.ui.View):
    def __init__(self, *, disabled: bool = False, approved: bool = False, rejected: bool = False):
        # persistent view
        super().__init__(timeout=None)
        # ใช้พารามิเตอร์เฉพาะตอน render ใหม่หลังตัดสิน เพื่อ disable ปุ่มในข้อความนั้น ๆ
        if disabled:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.custom_id == "approve_button":
                        child.disabled = True
                        child.style = discord.ButtonStyle.success
                        child.label = "✅ Approved / อนุมัติแล้ว" if approved else child.label
                    elif child.custom_id == "reject_button":
                        child.disabled = True
                        child.style = discord.ButtonStyle.danger
                        child.label = "❌ Rejected / ปฏิเสธแล้ว" if rejected else child.label

    # ✅ APPROVE
    @discord.ui.button(label="✅ Approve / อนุมัติ", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        e: discord.Embed | None = None
        uid: int | None = None
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            msg = interaction.message
            if not (msg and msg.embeds):
                await interaction.followup.send("❌ ไม่พบข้อมูลในข้อความนี้", ephemeral=True)
                return
            e = msg.embeds[0]

            # หา target user จาก footer → fallback mentions
            uid = _user_id_from_embed_footer(e)
            if uid is None and msg.mentions:
                uid = msg.mentions[0].id
            if uid is None:
                await interaction.followup.send("❌ ไม่พบผู้ใช้จากข้อความนี้", ephemeral=True)
                return

            guild = interaction.guild
            member = guild.get_member(uid) or await guild.fetch_member(uid)

            # เตรียม role
            general_role = guild.get_role(ROLE_ID_TO_GIVE)
            gender_text = (_find_embed_field(e, "gender", "เพศ") or "").strip()
            gender_role = guild.get_role(resolve_gender_role_id(gender_text))

            # age priority: วันเกิด > อายุ
            resolved_years = None
            age_role = None
            btxt = _find_embed_field(e, "birthday", "วันเกิด")
            if btxt:
                bdt = parse_birthday(str(btxt))
                if bdt:
                    resolved_years = age_from_birthday(bdt)
                    rid = resolve_age_role_id(str(resolved_years))
                    age_role = guild.get_role(rid) if rid else None
            if age_role is None:
                atxt = _find_embed_field(e, "age", "อายุ") or "ไม่ระบุ"
                rid = resolve_age_role_id(atxt)
                age_role = guild.get_role(rid) if rid else None

            if not (member and general_role and gender_role):
                await interaction.followup.send("❌ Member หรือ role ไม่ครบ", ephemeral=True)
                await notify_admin(guild, "อนุมัติไม่สำเร็จ: ไม่พบ member/role")
                return

            # enforce single-role (gender / age)
            try:
                to_remove_gender = [r for r in member.roles if r.id in GENDER_ROLE_IDS_ALL and r.id != gender_role.id]
                if to_remove_gender:
                    await member.remove_roles(*to_remove_gender, reason="Verification: enforce single gender role")
            except discord.Forbidden:
                await interaction.followup.send("❌ ไม่มีสิทธิ์ถอดยศเพศเดิม", ephemeral=True)
                return

            if age_role:
                try:
                    to_remove_age = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and r.id != age_role.id]
                    if to_remove_age:
                        await member.remove_roles(*to_remove_age, reason="Verification: enforce single age role")
                except discord.Forbidden:
                    await interaction.followup.send("❌ ไม่มีสิทธิ์ถอดยศอายุเดิม", ephemeral=True)
                    return

            roles_to_add = []
            if general_role not in member.roles:
                roles_to_add.append(general_role)
            if gender_role and gender_role not in member.roles:
                roles_to_add.append(gender_role)
            if age_role and age_role not in member.roles:
                roles_to_add.append(age_role)

            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason="Verified")
                except discord.Forbidden:
                    await interaction.followup.send("❌ Missing permissions to add roles.", ephemeral=True)
                    await notify_admin(guild, f"บอทให้ยศไม่สำเร็จที่ {member.mention}")
                    return

            # อัปเดต embed ให้ตรงค่าที่อนุมัติจริง
            disp_gender = gender_role.name if gender_role else "ไม่ระบุ"
            if resolved_years is not None:
                disp_age = str(resolved_years)
            else:
                atxt = _find_embed_field(e, "age", "อายุ") or "ไม่ระบุ"
                disp_age = atxt if not is_age_undisclosed(atxt) else "ไม่ระบุ"

            await _update_approval_embed_for_member(guild, member, gender=disp_gender, age=disp_age)

            # ✅ mark footer + ปิดปุ่ม (ใช้ชื่อจริงล่าสุด)
            try:
                approver = await guild.fetch_member(interaction.user.id)
                actor_name = (
                    approver.display_name
                    or approver.nick
                    or approver.global_name
                    or approver.name
                )
            except Exception:
                actor_name = interaction.user.display_name or interaction.user.name

            stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
            orig = (e.footer.text or "").strip()
            e.set_footer(
                text=(f"{orig} • Approved by {actor_name} • {stamp}" if orig else f"Approved by {actor_name} • {stamp}")
            )
            await interaction.message.edit(embed=e, view=GlobalApproveRejectView(disabled=True, approved=True))

        except Exception as ex:
            await notify_admin(interaction.guild, f"Approve error: {ex!r}")
        finally:
            try:
                if uid is not None:
                    pending_verifications.discard(uid)
            except Exception:
                pass

    # ❌ REJECT
    @discord.ui.button(label="❌ Reject / ปฏิเสธ", style=discord.ButtonStyle.danger, custom_id="reject_button")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        e: discord.Embed | None = None
        uid: int | None = None
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            msg = interaction.message
            if not (msg and msg.embeds):
                await interaction.followup.send("❌ ไม่พบข้อมูลในข้อความนี้", ephemeral=True)
                return
            e = msg.embeds[0]

            uid = _user_id_from_embed_footer(e)
            if uid is None and msg.mentions:
                uid = msg.mentions[0].id

            # แจ้งผู้ใช้ทาง DM (ถ้าส่งได้)
            if uid is not None:
                try:
                    user = await interaction.client.fetch_user(uid)
                    await user.send(
                        "❌ Your verification was rejected. Please contact admin.\n"
                        "❌ การยืนยันตัวตนของคุณไม่ผ่าน กรุณาติดต่อแอดมิน"
                    )
                except Exception:
                    await interaction.followup.send("⚠️ ไม่สามารถส่ง DM แจ้งผู้ใช้ได้", ephemeral=True)

            # ✅ mark footer + ปิดปุ่ม (ใช้ชื่อจริงล่าสุด)
            try:
                approver = await interaction.guild.fetch_member(interaction.user.id)
                actor_name = (
                    approver.display_name
                    or approver.nick
                    or approver.global_name
                    or approver.name
                )
            except Exception:
                actor_name = interaction.user.display_name or interaction.user.name

            stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
            orig = (e.footer.text or "").strip()
            e.set_footer(
                text=(f"{orig} • Rejected by {actor_name} • {stamp}" if orig else f"Rejected by {actor_name} • {stamp}")
            )
            await interaction.message.edit(embed=e, view=GlobalApproveRejectView(disabled=True, rejected=True))

        except Exception as ex:
            await notify_admin(interaction.guild, f"Reject error: {ex!r}")
        finally:
            try:
                if uid is not None:
                    pending_verifications.discard(uid)
            except Exception:
                pass


# ====== Commands ======
@bot.command(name="verify_embed")
@commands.has_permissions(administrator=True)
async def verify_embed(ctx):
    try:
        channel = ctx.guild.get_channel(VERIFY_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ VERIFY_CHANNEL_ID not found.")
            return
        embed = discord.Embed(
            title="📌 Welcome / ยินดีต้อนรับ",
            description="Click the button below to verify your identity.\nกดปุ่มด้านล่างเพื่อยืนยันตัวตนของคุณ",
            color=discord.Color.blue()
        )
        embed.set_image(url="https://i.pinimg.com/originals/da/79/68/da7968c54b12ba7ebf7dfd70dd1faaf2.gif")
        embed.set_footer(text="Verification System / ระบบยืนยันตัวตนโดย Bot")
        await channel.send(embed=embed, view=VerificationView())
        await ctx.send(f"✅ Verification embed sent to {channel.mention}")
    except Exception as e:
        await notify_admin(ctx.guild, f"verify_embed error: {e!r}")
        await ctx.send("❌ ส่ง embed ไม่สำเร็จ")

@bot.command(name="idcard", aliases=["userinfo"])
async def userinfo(ctx, *, who: str = None):
    """
    $idcard                → ดู ID Card ของตัวเอง (ทุกคนใช้ได้)
    $idcard @someone       → ดู ID Card ของคนอื่น (แอดมินเท่านั้น)
    $idcard 12345678901234 → ดู ID Card ของคนอื่นจาก ID (แอดมินเท่านั้น)
    """
    try:
        # ---------- หา member ----------
        member = None
        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        elif who:
            try:
                member = await commands.MemberConverter().convert(ctx, who)
            except commands.BadArgument:
                member = None
        if member is None:
            member = ctx.author

        # ---------- ถ้าไม่ใช่ตัวเอง ต้องเป็นแอดมิน ----------
        if member.id != ctx.author.id and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ คุณสามารถดูบัตรของ **ตัวเอง** ได้เท่านั้น")
            return

        # ---------- หา approval channel ----------
        channel = ctx.guild.get_channel(APPROVAL_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ APPROVAL_CHANNEL_ID not found.")
            return

        # ---------- loop ประวัติ (เพิ่ม limit เป็น 1000) ----------
        try:
            async for message in channel.history(limit=1000):
                if (
                    message.author == bot.user
                    and message.embeds
                    and _message_belongs_to_member(message, member)
                ):
                    embed0 = message.embeds[0]
                    new_embed = copy_embed_fields(embed0)
                    new_embed.title = "🪪 ID Card / บัตรยืนยันตัวตน"

                    # ✅ ซ่อนวันเกิดบน ID Card
                    mask_birthday_field_for_idcard(new_embed)

                    # ✅ ถ้ามีไฟล์รูปจากตอนอนุมัติ → ใช้ไฟล์นั้นก่อน
                    if message.attachments:
                        try:
                            att = message.attachments[0]
                            data = await att.read()
                            fname = att.filename or f"avatar_{member.id}.png"
                            file = discord.File(io.BytesIO(data), filename=fname)
                            new_embed.set_thumbnail(url=f"attachment://{fname}")
                            await ctx.send(file=file, embed=new_embed)
                            return
                        except Exception:
                            # ถ้าอ่านไฟล์แนบล้มเหลว → จะไป fallback ข้างล่าง
                            pass

                    # ✅ Fallback: แนบ avatar ปัจจุบันของสมาชิกเป็นไฟล์ แล้วตั้ง thumbnail จากไฟล์
                    file, fname = await build_avatar_attachment(member)
                    if file and fname:
                        new_embed.set_thumbnail(url=f"attachment://{fname}")
                        await ctx.send(file=file, embed=new_embed)
                    else:
                        # ถ้าดึงไฟล์ไม่ได้จริง ๆ → ใช้ URL ปัจจุบันแทน
                        new_embed.set_thumbnail(url=member.display_avatar.with_static_format("png").with_size(128).url)
                        await ctx.send(embed=new_embed)
                    return

        except discord.Forbidden:
            await ctx.send(
                "❌ บอทไม่มีสิทธิ์อ่านห้องอนุมัติ\n"
                "→ ต้องเปิดสิทธิ์ View Channel + Read Message History"
            )
            return
        except discord.HTTPException as e:
            await ctx.send(f"❌ อ่านประวัติห้องอนุมัติไม่สำเร็จ: {e}")
            return

        await ctx.send("❌ No verification info found for this user.")

    except Exception as e:
        await notify_admin(ctx.guild, f"idcard error: {e!r}")
        await ctx.send(f"❌ คำสั่งล้มเหลว: {e!r}")


# ---------- Single user refresh ----------
@bot.command(name="refresh_age")
@commands.has_permissions(administrator=True)
async def refresh_age(ctx, member: discord.Member):
    try:
        embed = await _latest_verification_embed_for(member)
        if not embed:
            await ctx.send("❌ ไม่พบข้อมูลคำขอยืนยันล่าสุดของผู้ใช้นี้ในห้องอนุมัติ")
            return

        # ✅ PRIORITY: birthday
        bday_text = _find_embed_field(embed, "birthday", "วันเกิด")
        if bday_text:
            bday_dt = parse_birthday(str(bday_text))
            if bday_dt:
                years = age_from_birthday(bday_dt)
                new_age_role_id = resolve_age_role_id(str(years))
                new_age_role = ctx.guild.get_role(new_age_role_id) if new_age_role_id else None
                to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and (new_age_role is None or r.id != new_age_role.id)]
                if to_remove:
                    try:
                        await member.remove_roles(*to_remove, reason=f"Refresh age (birthday) → now {years}")
                    except discord.Forbidden:
                        await ctx.send("❌ ไม่มีสิทธิ์ถอดยศอายุของสมาชิกคนนี้")
                        return
                if new_age_role and new_age_role not in member.roles:
                    try:
                        await member.add_roles(new_age_role, reason=f"Refresh age (birthday) → now {years}")
                    except discord.Forbidden:
                        await ctx.send(f"⚠️ ถอดยศเดิมแล้ว แต่เพิ่มยศใหม่ไม่สำเร็จ: {new_age_role.name}")
                        return
                got = new_age_role.name if new_age_role else "— (ไม่มี role สำหรับช่วงนี้)"
                await ctx.send(f"✅ (วันเกิด) อัปเดตอายุเป็น **{years}** ปี และตั้งยศอายุเป็น **{got}** ให้กับ {member.mention} แล้ว")
                return

        age_text = _find_embed_field(embed, "age", "อายุ")
        sent_text = _find_embed_field(embed, "sent at")
        if not age_text or not sent_text:
            await ctx.send("❌ ข้อมูลใน embed ไม่ครบ (Age หรือ Sent at หาย)")
            return

        # ไม่ระบุอายุ
        if is_age_undisclosed(str(age_text)):
            new_age_role = ctx.guild.get_role(ROLE_AGE_UNDISCLOSED)
            to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and (new_age_role is None or r.id != new_age_role.id)]
            if to_remove:
                try:
                    await member.remove_roles(*to_remove, reason="Refresh age → undisclosed")
                except discord.Forbidden:
                    await ctx.send("❌ ไม่มีสิทธิ์ถอดยศอายุของสมาชิกคนนี้")
                    return
            if new_age_role and new_age_role not in member.roles:
                try:
                    await member.add_roles(new_age_role, reason="Refresh age → undisclosed")
                except discord.Forbidden:
                    await ctx.send("⚠️ ถอดยศเดิมแล้ว แต่เพิ่มยศใหม่ไม่สำเร็จ: ไม่ระบุอายุ")
                    return
            got = new_age_role.name if new_age_role else "— (ไม่มี role สำหรับช่วงนี้)"
            await ctx.send(f"✅ ตั้งยศอายุเป็น **{got}** ให้กับ {member.mention} แล้ว (ผู้ใช้เลือกไม่ระบุอายุ)")
            return

        # เดิม: คำนวณอายุจากตัวเลข
        try:
            old_age = int(str(age_text).strip())
        except ValueError:
            await ctx.send("❌ รูปแบบอายุเดิมใน embed ไม่ใช่ตัวเลข")
            return

        sent_dt = _parse_sent_at(sent_text)
        if not sent_dt:
            await ctx.send("❌ รูปแบบเวลา 'Sent at' ไม่ถูกต้อง (ต้องเป็น dd/mm/YYYY HH:MM)")
            return

        now = datetime.now(timezone(timedelta(hours=7)))
        added_years = _years_between(sent_dt, now)
        new_age = max(old_age + added_years, 0)

        new_age_role_id = resolve_age_role_id(str(new_age))
        new_age_role = ctx.guild.get_role(new_age_role_id) if new_age_role_id else None

        to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and (new_age_role is None or r.id != new_age_role.id)]
        if to_remove:
            try:
                await member.remove_roles(*to_remove, reason=f"Refresh age → now {new_age}")
            except discord.Forbidden:
                await ctx.send("❌ ไม่มีสิทธิ์ถอดยศอายุของสมาชิกคนนี้")
                return

        if new_age_role:
            try:
                await member.add_roles(new_age_role, reason=f"Refresh age → now {new_age}")
            except discord.Forbidden:
                await ctx.send(f"⚠️ ถอดยศเดิมแล้ว แต่เพิ่มยศใหม่ไม่สำเร็จ: {new_age_role.name}")
                return

        got = new_age_role.name if new_age_role else "— (ไม่มี role สำหรับช่วงนี้)"
        await ctx.send(f"✅ อัปเดตอายุเป็น **{new_age}** ปี และตั้งยศอายุเป็น **{got}** ให้กับ {member.mention} แล้ว")
    except Exception as e:
        await notify_admin(ctx.guild, f"refresh_age error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

# ---------- All users refresh ----------
@bot.command(name="refresh_age_all")
@commands.has_permissions(administrator=True)
async def refresh_age_all(ctx):
    try:
        await ctx.send("⏳ กำลังรีเฟรชอายุทั้งเซิร์ฟเวอร์และบันทึก log ...")
        await _run_full_age_refresh(ctx.guild)
        await ctx.send("✅ เสร็จสิ้น (ดูรายละเอียดในห้อง log)")
    except Exception as e:
        await notify_admin(ctx.guild, f"refresh_age_all error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

# ====== Admin adjust commands ======
CLEAR_ALIASES = {"clear", "reset", "remove", "none", "no", "x", "-", "—", "ลบ", "เอาออก", "ไม่ใช้", "ไม่ใส่", "ไม่ต้อง"}

def _bot_can_edit_member_and_role(ctx: commands.Context, member: discord.Member, role: discord.Role | None = None) -> tuple[bool, str]:
    bot_me = ctx.guild.me
    if not bot_me:
        return False, "❌ ไม่พบสถานะของบอทในกิลด์"
    if bot_me.top_role <= member.top_role or member.id == ctx.guild.owner_id:
        return False, "❌ บอทไม่มีลำดับยศสูงพอที่จะจัดการสมาชิกคนนี้ (ลาก role ของบอทให้อยู่เหนือยศเป้าหมาย)"
    if role and bot_me.top_role <= role:
        return False, f"❌ บอทไม่มีลำดับยศสูงพอที่จะจัดการยศ: {role.name} (ลาก role ของบอทให้อยู่เหนือยศนี้)"
    return True, ""

@bot.command(name="setnick", aliases=["nick", "ชื่อเล่น", "ปรับชื่อเล่น"])
@commands.has_permissions(manage_nicknames=True)
async def setnick(ctx: commands.Context, member: discord.Member, *, nickname: str):
    try:
        ok, msg = _bot_can_edit_member_and_role(ctx, member, None)
        if not ok:
            await ctx.send(msg)
            return

        want_clear = (_norm_simple(nickname) in CLEAR_ALIASES) or (nickname.strip() == "")
        if want_clear:
            base = _base_display_name(member)
            try:
                await member.edit(nick=base, reason="Admin: clear form nickname")
                await ctx.send(f"✅ เอาวงเล็บชื่อเล่นออกแล้ว → `{base}` (เป้าหมาย: {member.mention})")
            except discord.Forbidden:
                await ctx.send("❌ บอทไม่มีสิทธิ์พอในการแก้ชื่อคนนี้"); return
            except discord.HTTPException:
                await ctx.send("❌ เกิดข้อผิดพลาด HTTP ตอนแก้ชื่อ"); return

            updated = await _update_approval_embed_for_member(ctx.guild, member, nickname="ไม่ระบุ")
            if not updated:
                await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ")
            return

        # validate ชื่อเล่น
        if len(nickname) < 2 or len(nickname) > 10 or any(ch.isdigit() for ch in nickname) \
           or any(c in INVALID_CHARS for c in nickname) or contains_emoji(nickname):
            await ctx.send("❌ ชื่อเล่นไม่ถูกต้อง (ต้องเป็นตัวอักษร 2–10 ตัว, ห้ามตัวเลข/สัญลักษณ์/อีโมจิ)")
            return
        if _canon_full(nickname) in _discord_names_set(member):
            await ctx.send("❌ ชื่อเล่นต้องต่างจากชื่อในดิสคอร์ดของเป้าหมายจริง ๆ")
            return

        # NOTE: นโยบายปัจจุบันปิด auto-append วงเล็บ แต่คำสั่งนี้ยังอนุญาตแอดมินจะใส่วงเล็บได้เอง
        new_nick = build_parenthesized_nick(member, nickname)
        try:
            await member.edit(nick=new_nick, reason=f"Admin: set form nickname → {nickname}")
            await ctx.send(f"✅ ตั้งชื่อเป็น `{new_nick}` ให้ {member.mention}")
        except discord.Forbidden:
            await ctx.send("❌ บอทไม่มีสิทธิ์พอในการแก้ชื่อคนนี้"); return
        except discord.HTTPException:
            await ctx.send("❌ เกิดข้อผิดพลาด HTTP ตอนแก้ชื่อ"); return

        updated = await _update_approval_embed_for_member(ctx.guild, member, nickname=nickname)
        if not updated:
            await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ")
    except Exception as e:
        await notify_admin(ctx.guild, f"setnick error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

@bot.command(name="setgender", aliases=["gender", "เพศ", "ปรับเพศ"])
@commands.has_permissions(manage_roles=True)
async def setgender(ctx: commands.Context, member: discord.Member, *, gender_text: str = ""):
    try:
        role_id = resolve_gender_role_id(gender_text)
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("❌ ไม่พบ role เพศที่แมปไว้ในกิลด์นี้")
            return

        ok, msg = _bot_can_edit_member_and_role(ctx, member, role)
        if not ok:
            await ctx.send(msg)
            return
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ บอทไม่มีสิทธิ์ Manage Roles")
            return

        to_remove = [r for r in member.roles if r.id in GENDER_ROLE_IDS_ALL and r.id != role.id]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Admin: set gender (enforce single gender role)")
            if role not in member.roles:
                await member.add_roles(role, reason="Admin: set gender")
        except discord.Forbidden:
            await ctx.send("❌ บอทไม่มีสิทธิ์ปรับยศเพศให้สมาชิกคนนี้"); return
        except discord.HTTPException:
            await ctx.send("❌ เกิดข้อผิดพลาด HTTP ตอนปรับยศเพศ"); return

        removed_txt = ", ".join(r.name for r in to_remove) if to_remove else "—"
        await ctx.send(f"✅ ตั้งเพศของ {member.mention} เป็น **{role.name}** (removed: {removed_txt})")

        updated = await _update_approval_embed_for_member(ctx.guild, member, gender=role.name)
        if not updated:
            await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ")
    except Exception as e:
        await notify_admin(ctx.guild, f"setgender error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

@bot.command(name="setage", aliases=["age", "อายุ", "ปรับอายุ"])
@commands.has_permissions(manage_roles=True)
async def setage(ctx: commands.Context, member: discord.Member, *, age_text: str):
    try:
        if _norm_simple(age_text) in CLEAR_ALIASES or not age_text.strip():
            age_text = "ไม่ระบุ"

        role_id = resolve_age_role_id(age_text)
        if not role_id:
            await ctx.send("❌ อายุไม่ถูกต้อง (ใส่เป็นตัวเลข 0–200 หรือ 'ไม่ระบุ')")
            return
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("❌ ไม่พบ role อายุที่แมปไว้ในกิลด์นี้")
            return

        ok, msg = _bot_can_edit_member_and_role(ctx, member, role)
        if not ok:
            await ctx.send(msg)
            return
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ บอทไม่มีสิทธิ์ Manage Roles")
            return

        to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and r.id != role.id]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Admin: set age (enforce single age role)")
            if role not in member.roles:
                await member.add_roles(role, reason="Admin: set age")
        except discord.Forbidden:
            await ctx.send("❌ บอทไม่มีสิทธิ์ปรับยศอายุให้สมาชิกคนนี้"); return
        except discord.HTTPException:
            await ctx.send("❌ เกิดข้อผิดพลาด HTTP ตอนปรับยศอายุ"); return

        removed_txt = ", ".join(r.name for r in to_remove) if to_remove else "—"
        await ctx.send(f"✅ ตั้งอายุของ {member.mention} เป็น **{role.name}** (removed: {removed_txt})")

        # อัปเดต embed
        disp_age = "ไม่ระบุ" if role.id == ROLE_AGE_UNDISCLOSED else (re.search(r"\d{1,3}", age_text).group(0) if re.search(r"\d{1,3}", age_text) else age_text.strip())
        updated = await _update_approval_embed_for_member(ctx.guild, member, age=disp_age)
        if not updated:
            await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ")
    except Exception as e:
        await notify_admin(ctx.guild, f"setage error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

@bot.command(name="setbirthday", aliases=["birthday", "วันเกิด", "ปรับวันเกิด"])
@commands.has_permissions(manage_roles=True)
async def setbirthday(ctx: commands.Context, member: discord.Member, *, birthday_text: str = ""):
    """
    ตั้ง/ลบ วันเกิด ของสมาชิกใน embed อนุมัติ และอัปเดตยศอายุตามวันเกิดทันที
    ใช้รูปแบบ dd/mm/yyyy หรือ clear/reset/remove เพื่อลบ
    """
    try:
        want_clear = (_norm_simple(birthday_text) in CLEAR_ALIASES) or (birthday_text.strip() == "")
        if want_clear:
            ok = await _update_approval_embed_for_member(ctx.guild, member, birthday="ไม่ระบุ")
            if not ok:
                await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ")
                return
            await ctx.send(f"✅ ลบวันเกิดของ {member.mention} แล้ว (ตั้งค่าเป็น 'ไม่ระบุ')")
            return

        bday_dt = parse_birthday(birthday_text)
        if not bday_dt:
            await ctx.send("❌ รูปแบบวันเกิดไม่ถูกต้อง (dd/mm/yyyy เช่น 05/11/2004)")
            return

        # ✅ คำนวณอายุก่อน แล้วอัปเดตทั้ง embed และ role
        years = age_from_birthday(bday_dt)

        # อัปเดต embed: birthday + age ที่คำนวณจริง
        ok = await _update_approval_embed_for_member(ctx.guild, member, birthday=birthday_text, age=str(years))
        if not ok:
            await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ (แต่ยังอัปเดตยศได้)")

        # จัดยศอายุจากวันเกิดทันที
        role_id = resolve_age_role_id(str(years))
        role = ctx.guild.get_role(role_id) if role_id else None
        if not role:
            await ctx.send(f"⚠️ อายุ {years} ปี ไม่มี role ที่แมปไว้")
            return

        ok2, msg = _bot_can_edit_member_and_role(ctx, member, role)
        if not ok2:
            await ctx.send(msg); return
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ บอทไม่มีสิทธิ์ Manage Roles"); return

        to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and r.id != role.id]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Admin: set birthday (enforce single age role by birthday)")
            if role not in member.roles:
                await member.add_roles(role, reason="Admin: set birthday (age calculated)")
        except discord.Forbidden:
            await ctx.send("❌ บอทไม่มีสิทธิ์ปรับยศอายุให้สมาชิกคนนี้"); return
        except discord.HTTPException:
            await ctx.send("❌ เกิดข้อผิดพลาด HTTP ตอนปรับยศอายุ"); return

        removed_txt = ", ".join(r.name for r in to_remove) if to_remove else "—"
        await ctx.send(
            f"✅ ตั้งวันเกิด **{birthday_text}** → อายุ **{years}** ปี และตั้งยศเป็น **{role.name}** ให้ {member.mention} (removed: {removed_txt})"
        )
    except Exception as e:
        await notify_admin(ctx.guild, f"setbirthday error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")


# ---------- Force re-verification ----------
@bot.command(name="reverify", aliases=["บังคับยืนยันใหม่", "forceverify"])
@commands.has_permissions(manage_roles=True)
async def reverify(ctx: commands.Context, member: discord.Member):
    """ลบยศยืนยัน/ยศเพศ/ยศอายุ + ลบ embed ในห้องอนุมัติ + ส่ง DM ให้กลับไปยืนยันใหม่"""
    try:
        ok, msg = _bot_can_edit_member_and_role(ctx, member)
        if not ok:
            await ctx.send(msg); return

        # remove roles (general + gender + age)
        to_remove = [r for r in member.roles if r.id in {ROLE_ID_TO_GIVE, *GENDER_ROLE_IDS_ALL, *AGE_ROLE_IDS_ALL}]
        if to_remove:
            try:
                await member.remove_roles(*to_remove, reason="Force re-verification")
            except discord.Forbidden:
                await ctx.send("❌ ไม่มีสิทธิ์ถอดยศของสมาชิกคนนี้"); return

        # reset nickname to base (ตัดวงเล็บออก)
        try:
            base = _base_display_name(member)
            await member.edit(nick=base, reason="Force re-verification (reset nickname)")
        except Exception:
            pass

        # delete latest approval embed
        msg_obj = await _find_latest_approval_message(ctx.guild, member)
        if msg_obj:
            try:
                await msg_obj.delete()
            except Exception:
                pass

        # DM instructions
        try:
            await member.send(
                f"ℹ️ คุณถูกขอให้ยืนยันตัวตนใหม่ในเซิร์ฟเวอร์ **{ctx.guild.name}**\n"
                f"กรุณาไปที่ห้อง <#{VERIFY_CHANNEL_ID}> แล้วกดปุ่ม **Verify Identity** เพื่อเริ่มต้นอีกครั้ง"
            )
        except Exception:
            await ctx.send("⚠️ ส่ง DM แจ้งผู้ใช้ไม่ได้")

        await ctx.send(f"✅ สั่งให้ {member.mention} ยืนยันตัวตนใหม่แล้ว (roles cleared + embed removed)")
        await notify_admin(ctx.guild, f"{member.mention} ถูกสั่งให้ยืนยันตัวตนใหม่โดย {ctx.author.mention}")
    except Exception as e:
        await notify_admin(ctx.guild, f"reverify error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

# ====== Help command (list & details) ======
try:
    bot.remove_command("help")
except Exception:
    pass

_SHORT_DESC = {
    "help": "แสดงรายการคำสั่งทั้งหมด หรือรายละเอียดของคำสั่งที่ระบุ",
    "verify_embed": "ส่ง Embed ปุ่มยืนยันตัวตนไปยังห้อง VERIFY_CHANNEL_ID",
    "idcard": "ดู ID Card ของตัวเอง; ดูของคนอื่นได้เฉพาะแอดมิน",
    "refresh_age": "อัปเดตยศอายุตามเวลาที่ผ่านไป (รายบุคคล)",
    "refresh_age_all": "อัปเดตยศอายุทั้งเซิร์ฟเวอร์ตาม logs",
    "setnick": "ตั้ง/ลบวงเล็บชื่อเล่นต่อท้าย (ระบบไม่ใส่อัตโนมัติแล้ว; ใช้เมื่อแอดมินอยากแก้เองเท่านั้น)",
    "setgender": "ตั้งยศเพศ (ชาย/หญิง/LGBT/ไม่ระบุ)",
    "setage": "ตั้งยศอายุ (กรอกตัวเลขหรือ 'ไม่ระบุ')",
    "setbirthday": "ตั้ง/ลบ วันเกิด (คำนวณอายุอัตโนมัติจาก dd/mm/yyyy)",
    "reverify": "บังคับให้สมาชิกยืนยันตัวตนใหม่ (ลบ roles + ลบ embed + DM)",
    "hbd_test": "ทดสอบส่ง HBD สำหรับคนที่เกิด 'วันนี้' ที่บอทรู้จัก",
}

_HELP_DETAILS = {
    "help": {
        "usage": "$help [ชื่อคำสั่ง]",
        "example": "$help setage",
        "note": "ไม่ใส่อาร์กิวเมนต์จะโชว์รายการคำสั่งทั้งหมด",
    },
    "verify_embed": {
        "usage": "$verify_embed",
        "example": "$verify_embed",
        "note": "ต้องมีสิทธิ์ Administrator",
    },
    "idcard": {
        "usage": "$idcard\n$idcard @สมาชิก\n$idcard <user_id>",
        "example": "$idcard\n$idcard @Alice\n$idcard 123456789012345678",
        "note": "ทุกคนดูบัตรของตัวเองได้ด้วย `$idcard`; การดูบัตรของคนอื่น (ระบุ @สมาชิก หรือ ID) ทำได้เฉพาะแอดมิน • ดึงข้อมูลจากห้องอนุมัติ • วันเกิดถูกซ่อนบน ID Card ตามนโยบายความเป็นส่วนตัว",
    },
    "refresh_age": {
        "usage": "$refresh_age @สมาชิก",
        "example": "$refresh_age @Alice",
        "note": "คำนวณอัตโนมัติจาก 'วันเกิด' ถ้ามี; ถ้าไม่มีใช้ 'Age + Sent at'",
    },
    "refresh_age_all": {
        "usage": "$refresh_age_all",
        "example": "$refresh_age_all",
        "note": "รันทั้งเซิร์ฟเวอร์และส่งผลลัพธ์ไปห้อง log (ให้ความสำคัญวันเกิดก่อน)",
    },
    "setnick": {
        "usage": "$setnick @สมาชิก <ชื่อเล่น|clear>",
        "example": "$setnick @Alice มินนี่\n$setnick @Alice clear",
        "note": "ระบบไม่เติมวงเล็บชื่อเล่นอัตโนมัติอีกแล้ว — ชื่อเล่นถูกเก็บใน ID Card เท่านั้น; ใช้คำสั่งนี้เฉพาะกรณีต้องแก้ชื่อด้วยมือ",
    },
    "setgender": {
        "usage": "$setgender @สมาชิก [เพศ]",
        "example": "$setgender @Alice หญิง\n$setgender @Bob ไม่ระบุ",
        "note": "ต้อง Manage Roles; เว้นว่าง = ไม่ระบุ",
    },
    "setage": {
        "usage": "$setage @สมาชิก <อายุ|ไม่ระบุ|clear>",
        "example": "$setage @Alice 21\n$setage @Bob ไม่ระบุ\n$setage @Bob clear",
        "note": "ต้อง Manage Roles; ตัวเลขจัดเข้าช่วงอายุอัตโนมัติ",
    },
    "setbirthday": {
        "usage": "$setbirthday @สมาชิก <dd/mm/yyyy|clear>",
        "example": "$setbirthday @Alice 05/11/2004\n$setbirthday @Alice clear",
        "note": "ต้อง Manage Roles; จะอัปเดตยศอายุจากวันเกิดให้อัตโนมัติ และใช้แจ้ง HBD",
    },
    "reverify": {
        "usage": "$reverify @สมาชิก",
        "example": "$reverify @Alice",
        "note": "ลบยศยืนยัน/อายุ/เพศ + ลบ embed ในห้องอนุมัติ + ส่ง DM ให้เริ่มใหม่",
    },
    "hbd_test": {
        "usage": "$hbd_test",
        "example": "$hbd_test",
        "note": "ทดสอบโพสต์ HBD วันนี้ในช่องที่ตั้งค่าไว้",
    },
}

_ADMIN_COMMANDS = {"verify_embed", "refresh_age", "refresh_age_all", "setnick", "setgender", "setage", "setbirthday", "reverify", "hbd_test"}

def _fmt_cmd_list(prefix: str, names: list[str]) -> str:
    lines = []
    for n in names:
        desc = _SHORT_DESC.get(n, "-")
        lines.append(f"• **{prefix}{n}** — {desc}")
    return "\n".join(lines) if lines else "—"

@bot.command(name="help", aliases=["commands", "คำสั่ง", "วิธีใช้"])
async def help_command(ctx: commands.Context, *, command_name: str = None):
    try:
        prefix = ctx.prefix or "$"

        if command_name:
            cmd = bot.get_command(command_name.lower())
            if not cmd:
                await ctx.send(f"❌ ไม่พบคำสั่งชื่อ `{command_name}`")
                return

            name = cmd.name
            desc_short = _SHORT_DESC.get(name, cmd.help or "-")
            detail = _HELP_DETAILS.get(name, {})
            usage = detail.get("usage", f"{prefix}{name} …")
            example = detail.get("example", "-")
            note = detail.get("note", None)

            aliases = ", ".join(cmd.aliases) if getattr(cmd, "aliases", None) else "—"
            is_admin = "✅ ผู้ใช้ทั่วไป" if name not in _ADMIN_COMMANDS else "🛡️ ผู้ดูแล (ต้องมีสิทธิ์ที่เกี่ยวข้อง)"

            embed = discord.Embed(
                title=f"ℹ️ วิธีใช้คำสั่ง: {prefix}{name}",
                description=desc_short,
                color=discord.Color.blurple()
            )
            embed.add_field(name="การใช้งาน", value=f"`{usage}`", inline=False)
            embed.add_field(name="ตัวอย่าง", value=f"```\n{example}\n```", inline=False)
            embed.add_field(name="Aliases", value=aliases, inline=True)
            embed.add_field(name="สิทธิ์ที่ต้องใช้", value=is_admin, inline=True)
            if note:
                embed.add_field(name="หมายเหตุ", value=note, inline=False)

            await ctx.send(embed=embed)
            return

        all_cmds = {c.name for c in bot.commands if not c.hidden}
        general = sorted(all_cmds - _ADMIN_COMMANDS | {"help"})
        admin = sorted(all_cmds & _ADMIN_COMMANDS)

        embed = discord.Embed(
            title="📜 รายการคำสั่งทั้งหมด",
            description=f"พิมพ์ `{prefix}help <คำสั่ง>` เพื่อดูวิธีใช้แบบละเอียด",
            color=discord.Color.green()
        )
        embed.add_field(name="ทั่วไป", value=_fmt_cmd_list(prefix, general), inline=False)
        embed.add_field(name="สำหรับผู้ดูแล", value=_fmt_cmd_list(prefix, admin), inline=False)

        await ctx.send(embed=embed)
    except Exception as e:
        await notify_admin(ctx.guild, f"help error: {e!r}")
        await ctx.send("❌ คำสั่งล้มเหลว")

# ====== AUTO REFRESH DAEMON (configurable) ======

PENDING_CLEANUP_INTERVAL_MIN = 10

async def _pending_cleanup_daemon():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            # ทำสำเนาเพื่อ iterate ได้ปลอดภัย
            stale_ids = []
            for uid in list(pending_verifications):
                has_msg = await _has_any_pending_embed_for_user(bot, uid)
                if not has_msg:
                    stale_ids.append(uid)
            # ลบตัวที่ค้างจากเซ็ต
            for uid in stale_ids:
                pending_verifications.discard(uid)
        except Exception:
            # กัน daemon ล้ม
            pass

        try:
            await asyncio.sleep(PENDING_CLEANUP_INTERVAL_MIN * 60)
        except asyncio.CancelledError:
            return

def _refresh_period_tag(now_local: datetime, freq: str) -> str:
    if freq == "YEARLY":
        return f"[AGE-REFRESH] {now_local.year}"
    if freq == "MONTHLY":
        return f"[AGE-REFRESH] {now_local.year}-{now_local.month:02d}"
    if freq == "WEEKLY":
        iso = now_local.isocalendar()
        return f"[AGE-REFRESH] {iso.year}-W{iso.week:02d}"
    if freq == "DAILY":
        return f"[AGE-REFRESH] {now_local.date().isoformat()}"
    return f"[AGE-REFRESH] {now_local.year}-{now_local.month:02d}"

async def _already_ran_this_period(log_ch: discord.TextChannel, tz: timezone, freq: str) -> bool:
    now = datetime.now(tz)
    tag = _refresh_period_tag(now, freq)
    try:
        async for m in log_ch.history(limit=200):
            if m.author == bot.user and m.content and tag in m.content:
                return True
    except Exception:
        pass
    return False

def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        n = datetime(year+1, 1, 1)
    else:
        n = datetime(year, month+1, 1)
    return (n - timedelta(days=1)).day

def _compute_next_run_local(now_local: datetime) -> datetime:
    freq = REFRESH_FREQUENCY.upper()
    h, mi = REFRESH_AT_HOUR, REFRESH_AT_MINUTE

    if freq == "YEARLY":
        y = now_local.year
        m = max(1, min(12, REFRESH_AT_MONTH))
        dmax = _last_day_of_month(y, m)
        d = max(1, min(dmax, REFRESH_AT_DAY))
        target = datetime(y, m, d, h, mi, 0, tzinfo=REFRESH_TZ)
        if now_local >= target:
            y += 1
            dmax = _last_day_of_month(y, m)
            d = max(1, min(dmax, REFRESH_AT_DAY))
            target = datetime(y, m, d, h, mi, 0, tzinfo=REFRESH_TZ)
        return target

    if freq == "MONTHLY":
        y, m = now_local.year, now_local.month
        dmax = _last_day_of_month(y, m)
        d = max(1, min(dmax, REFRESH_AT_DAY))
        target = datetime(y, m, d, h, mi, 0, tzinfo=REFRESH_TZ)
        if now_local >= target:
            if m == 12:
                y += 1; m = 1
            else:
                m += 1
            dmax = _last_day_of_month(y, m)
            d = max(1, min(dmax, REFRESH_AT_DAY))
            target = datetime(y, m, d, h, mi, 0, tzinfo=REFRESH_TZ)
        return target

    if freq == "WEEKLY":
        weekday = max(0, min(6, REFRESH_AT_WEEKDAY))
        days_ahead = (weekday - now_local.weekday()) % 7
        target = (now_local + timedelta(days=days_ahead)).replace(hour=h, minute=mi, second=0, microsecond=0)
        if now_local >= target:
            target = target + timedelta(days=7)
        return target

    # DAILY
    target = now_local.replace(hour=h, minute=mi, second=0, microsecond=0)
    if now_local >= target:
        target = target + timedelta(days=1)
    return target

async def _auto_refresh_daemon():
    if not AUTO_REFRESH_ENABLED:
        return
    tz = REFRESH_TZ
    await bot.wait_until_ready()
    while not bot.is_closed():
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)
        target_local = _compute_next_run_local(now_local)
        target_utc = target_local.astimezone(timezone.utc)
        sleep_sec = max(1, int((target_utc - now_utc).total_seconds()))
        try:
            await asyncio.sleep(sleep_sec)
        except asyncio.CancelledError:
            return

        try:
            for guild in bot.guilds:
                log_ch = guild.get_channel(LOG_CHANNEL_ID)
                if not log_ch:
                    continue
                if await _already_ran_this_period(log_ch, tz, REFRESH_FREQUENCY):
                    continue
                await _run_full_age_refresh(guild)
                await log_ch.send(_refresh_period_tag(datetime.now(tz), REFRESH_FREQUENCY) + " ✅ DONE")
        except Exception:
            # กัน daemon ล้ม
            pass

# ====== Birthday (HBD) helpers & daemon ======
def _local_today(tz: timezone) -> datetime:
    now = datetime.now(tz)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)

async def _already_sent_hbd_today(log_ch: discord.TextChannel, date_local: datetime, user_id: int) -> bool:
    tag = f"[HBD {date_local.date().isoformat()}] {user_id}"
    try:
        async for m in log_ch.history(limit=200):
            if m.author == bot.user and m.content and tag in m.content:
                return True
    except Exception:
        pass
    return False

async def _mark_hbd_sent(log_ch: discord.TextChannel, date_local: datetime, user_id: int, member_mention: str):
    try:
        await log_ch.send(f"[HBD {date_local.date().isoformat()}] {user_id} • sent for {member_mention}")
    except Exception:
        pass

async def _latest_birthday_index(guild: discord.Guild, limit: int = 2000) -> dict[int, datetime]:
    ch = guild.get_channel(APPROVAL_CHANNEL_ID)
    out: dict[int, datetime] = {}
    if not ch:
        return out

    async for msg in ch.history(limit=limit):
        if msg.author != bot.user or not msg.embeds:
            continue

        e = msg.embeds[0]
        uid = _user_id_from_embed_footer(e)
        if uid is None and msg.mentions:
            uid = msg.mentions[0].id
        if uid is None or uid in out:
            continue

        btxt = _find_embed_field(e, "birthday", "วันเกิด")
        if not btxt:
            continue

        dt = parse_birthday(str(btxt))
        if dt:
            out[uid] = dt

    return out


async def _sync_age_role_from_birthday(guild: discord.Guild, member: discord.Member, bday_dt: datetime):
    years = age_from_birthday(bday_dt)
    role_id = resolve_age_role_id(str(years))
    new_role = guild.get_role(role_id) if role_id else None
    if not new_role:
        return False, f"no mapped role for {years}"

    to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and r.id != new_role.id]
    try:
        if to_remove:
            await member.remove_roles(*to_remove, reason=f"Birthday update → now {years}")
        if new_role not in member.roles:
            await member.add_roles(new_role, reason=f"Birthday update → now {years}")
        return True, new_role.name
    except discord.Forbidden:
        return False, "forbidden"
    except discord.HTTPException:
        return False, "http"

async def _send_hbd_today(guild: discord.Guild):
    tz = REFRESH_TZ
    today0 = _local_today(tz)
    today_md = (today0.month, today0.day)

    hbd_ch = guild.get_channel(BIRTHDAY_CHANNEL_ID)
    log_ch = guild.get_channel(LOG_CHANNEL_ID)
    if not hbd_ch or not log_ch:
        return

    bday_index = await _latest_birthday_index(guild)

    for uid, bday_dt in bday_index.items():
        if (bday_dt.month, bday_dt.day) != today_md:
            continue
        member = guild.get_member(uid)
        if not member:
            continue

        ok_role, info = await _sync_age_role_from_birthday(guild, member, bday_dt)
        if not ok_role:
            await log_ch.send(f"⚠️ HBD: sync age role for {member.mention} failed ({info})")

        if await _already_sent_hbd_today(log_ch, today0, uid):
            continue

        msg = _pick_hbd_message(member, today0)

        try:
            await hbd_ch.send(msg)
            await _mark_hbd_sent(log_ch, today0, uid, member.mention)
        except discord.Forbidden:
            await log_ch.send(f"❌ HBD: ไม่มีสิทธิ์โพสต์ที่ <#{BIRTHDAY_CHANNEL_ID}>")
            continue
        except Exception as e:
            await log_ch.send(f"❌ HBD ส่งไม่สำเร็จสำหรับ {member.mention}: {e!r}")
            continue

def _pick_hbd_message(member: discord.Member, when_local: datetime) -> str:
    """
    เลือกข้อความแบบหมุนเวียน: ใช้ (user_id + ปีปัจจุบัน) % จำนวนข้อความ
    → คนเดิมแต่ละปีจะได้ข้อความที่ต่างออกไป
    """
    idx = ((member.id or 0) + when_local.year) % len(HBD_MESSAGES)
    template = HBD_MESSAGES[idx]
    return template.format(mention=member.mention)

def _compute_next_hbd_run_local(now_local: datetime) -> datetime:
    target = now_local.replace(hour=HBD_NOTIFY_HOUR, minute=HBD_NOTIFY_MINUTE, second=0, microsecond=0)
    if now_local >= target:
        target = target + timedelta(days=1)
    return target

async def _birthday_daemon():
    if not HBD_NOTIFY_ENABLED:
        return
    tz = REFRESH_TZ
    await bot.wait_until_ready()
    while not bot.is_closed():
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)
        target_local = _compute_next_hbd_run_local(now_local)
        target_utc = target_local.astimezone(timezone.utc)
        sleep_sec = max(1, int((target_utc - now_utc).total_seconds()))
        try:
            await asyncio.sleep(sleep_sec)
        except asyncio.CancelledError:
            return

        try:
            for guild in bot.guilds:
                await _send_hbd_today(guild)
        except Exception:
            # กัน daemon ล้ม
            pass

@bot.command(name="hbd_test")
@commands.has_permissions(administrator=True)
async def hbd_test(ctx):
    await _send_hbd_today(ctx.guild)
    await ctx.send("✅ ลองส่ง HBD สำหรับวันและสมาชิกที่ตรงวันนี้แล้ว (ดูที่ช่อง HBD/Log)")

# ====== Persistent View Loader ======
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not getattr(bot, "_persistent_views_registered", False):
        bot.add_view(VerificationView())
        bot.add_view(GlobalApproveRejectView())
        bot._persistent_views_registered = True

    if AUTO_REFRESH_ENABLED and not getattr(bot, "_age_refresh_daemon_started", False):
        asyncio.create_task(_auto_refresh_daemon())
        bot._age_refresh_daemon_started = True
    if HBD_NOTIFY_ENABLED and not getattr(bot, "_birthday_daemon_started", False):
        asyncio.create_task(_birthday_daemon())
        bot._birthday_daemon_started = True

    # PATCH: start pending cleanup daemon
    if not getattr(bot, "_pending_cleanup_started", False):
        asyncio.create_task(_pending_cleanup_daemon())
        bot._pending_cleanup_started = True


# ====== Run bot ======
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

