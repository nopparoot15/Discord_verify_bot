import os
import re
import io
import logging
import unicodedata
import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta

# ====== LOGGING ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("verify-bot")

# ====== CONFIGURATION ======
VERIFY_CHANNEL_ID = 1402889712888447037
APPROVAL_CHANNEL_ID = 1402889786712395859
LOG_CHANNEL_ID = 1418941833819590699

# ช่องแจ้งเตือนผู้ดูแล (ไม่ตั้ง = ใช้ LOG_CHANNEL_ID)
ADMIN_NOTIFY_CHANNEL_ID = LOG_CHANNEL_ID

ROLE_ID_TO_GIVE = 1321268883088211981  # role ผ่านยืนยัน
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

APPEND_FORM_NAME_TO_NICK = True

# ====== AUTO REFRESH CONFIG (ตั้งเวลาเองได้) ======
AUTO_REFRESH_ENABLED = True
REFRESH_TZ = timezone(timedelta(hours=7))  # Asia/Bangkok
REFRESH_FREQUENCY = "YEARLY"               # "YEARLY" | "MONTHLY" | "WEEKLY" | "DAILY"
REFRESH_AT_HOUR = 6
REFRESH_AT_MINUTE = 0
REFRESH_AT_DAY = 1                         # ใช้กับ MONTHLY/YEARLY
REFRESH_AT_MONTH = 1                       # ใช้กับ YEARLY (1=มกราคม)
REFRESH_AT_WEEKDAY = 0                     # ใช้กับ WEEKLY (0=Mon .. 6=Sun)

# ====== RE-VERIFICATION CONFIG ======
# เมื่อ reverify จะลบ role เพศ/อายุด้วยหรือไม่ (แนะนำ True เพื่อให้กลับมาจากศูนย์)
REVERIFY_CLEAR_GENDER_AND_AGE = True
# แจ้งผู้ใช้ในห้อง verify ด้วยหลังจาก DM (จะ @mention ผู้ใช้)
REVERIFY_PING_IN_VERIFY_CHANNEL = True

# ====== ACCOUNT DEEP CHECK CONFIG ======
ACCOUNT_CHECKS_ENABLED = True
MIN_ACCOUNT_AGE_DAYS = 3            # อายุน้อยกว่านี้ = เสี่ยง
MIN_SHARED_GUILDS = 1               # น้อยกว่าหรือเท่าค่านี้ = เสี่ยง
REQUIRE_MIN_ACCOUNT_AGE_TO_SUBMIT = False  # True = บล็อคการส่งฟอร์มเลย

SAFE_MENTIONS = discord.AllowedMentions(everyone=False, roles=False, users=True)

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
    "เพศทางเลือก", "สาวสอง", "สาวประเภทสอง", "ทอม", "ดี้", "ไบ",
    "非二元", "跨性别", "酷儿",
    "ノンバイナリー", "xジェンダー", "トランス", "クィア",
    "논바이너리", "트랜스", "퀴어",
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
    if t in GENDER_UNDISCLOSED_ALIASES:
        return ROLE_GENDER_UNDISCLOSED
    if t in LGBT_ALIASES:
        return ROLE_LGBT
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
async def build_avatar_attachment(user: discord.User):
    try:
        try:
            asset = user.display_avatar.with_format("webp").with_size(512)
            data = await asset.read()
            filename = f"avatar_{user.id}.webp"
        except Exception:
            asset = user.display_avatar.with_static_format("png").with_size(512)
            data = await asset.read()
            filename = f"avatar_{user.id}.png"
        f = discord.File(io.BytesIO(data), filename=filename)
        return f, filename
    except Exception:
        logger.exception("build_avatar_attachment failed for user=%s", user.id if user else None)
        return None, None

def copy_embed_fields(src: discord.Embed) -> discord.Embed:
    e = discord.Embed(
        title=src.title or discord.Embed.Empty,
        description=src.description or discord.Embed.Empty,
        color=src.color if src.color is not None else discord.Embed.Empty,
    )
    try:
        if src.author and (src.author.name or src.author.icon_url or src.author.url):
            e.set_author(name=getattr(src.author, "name", discord.Embed.Empty) or discord.Embed.Empty)
        if src.footer and (src.footer.text or src.footer.icon_url):
            e.set_footer(text=getattr(src.footer, "text", discord.Embed.Empty) or discord.Embed.Empty)
        if src.image and src.image.url:
            e.set_image(url=src.image.url)
        for f in src.fields:
            e.add_field(name=f.name, value=f.value, inline=f.inline)
    except Exception:
        logger.exception("copy_embed_fields failed")
    return e

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

async def _latest_verification_embed_for(member: discord.Member) -> discord.Embed | None:
    channel = member.guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        return None
    try:
        async for msg in channel.history(limit=500):
            if msg.author == bot.user and msg.embeds and member in msg.mentions:
                return msg.embeds[0]
    except Exception:
        logger.exception("history scan failed in _latest_verification_embed_for for member=%s", member.id)
    return None

async def _find_latest_approval_message(guild: discord.Guild, member: discord.Member):
    ch = guild.get_channel(APPROVAL_CHANNEL_ID)
    if not ch:
        return None
    try:
        async for m in ch.history(limit=1000):
            if m.author == bot.user and m.embeds and member in m.mentions:
                return m
    except Exception:
        logger.exception("history scan failed in _find_latest_approval_message for member=%s", member.id)
    return None

async def _build_latest_verification_index(guild: discord.Guild, limit: int = 2000):
    channel = guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        return {}
    index = {}
    try:
        async for msg in channel.history(limit=limit):
            if msg.author != bot.user or not msg.embeds or not msg.mentions:
                continue
            u = msg.mentions[0]
            if u is None:
                continue
            if u.id not in index:
                index[u.id] = (msg.embeds[0], msg.created_at)
    except Exception:
        logger.exception("history scan failed in _build_latest_verification_index")
    return index

async def _log_chunks(channel: discord.TextChannel, header: str, lines: list[str], chunk_size: int = 1900):
    try:
        if not lines:
            await channel.send(header, allowed_mentions=SAFE_MENTIONS)
            return
        buf = header + "\n"
        for line in lines:
            if len(buf) + len(line) + 1 > chunk_size:
                await channel.send(buf.rstrip(), allowed_mentions=SAFE_MENTIONS)
                buf = ""
            buf += line + "\n"
        if buf.strip():
            await channel.send(buf.rstrip(), allowed_mentions=SAFE_MENTIONS)
    except discord.Forbidden:
        logger.error("Cannot send logs to channel id=%s (Forbidden)", channel.id if channel else None)
    except discord.HTTPException:
        logger.exception("HTTP error while sending logs")

# ====== Admin notifications ======
def _get_admin_notify_channel(guild: discord.Guild):
    cid = ADMIN_NOTIFY_CHANNEL_ID or LOG_CHANNEL_ID
    return guild.get_channel(cid)

async def _notify_admins(guild: discord.Guild, text: str):
    try:
        ch = _get_admin_notify_channel(guild)
        if ch:
            await ch.send(f"🔔 **Admin Notification**: {text}", allowed_mentions=SAFE_MENTIONS)
        else:
            logger.warning("Admin notify channel not found: %s", ADMIN_NOTIFY_CHANNEL_ID)
    except Exception:
        logger.exception("notify admins failed")

# ====== Account deep check ======
def _count_shared_guilds(user: discord.abc.User):
    try:
        mg = getattr(user, "mutual_guilds", None)
        if mg is not None:
            return len(mg)
    except Exception:
        pass
    cnt = 0
    for g in bot.guilds:
        try:
            if g.get_member(user.id):
                cnt += 1
        except Exception:
            continue
    return cnt

def assess_account_risk(user: discord.abc.User):
    try:
        now = datetime.now(timezone.utc)
        created = getattr(user, "created_at", None)
        if not created:
            return {"age_days": None, "shared": _count_shared_guilds(user), "suspicious": False, "reasons": []}
        age_days = max((now - created).days, 0)
        shared = _count_shared_guilds(user)
        reasons = []
        if age_days < MIN_ACCOUNT_AGE_DAYS:
            reasons.append(f"Account age < {MIN_ACCOUNT_AGE_DAYS} days")
        if shared <= MIN_SHARED_GUILDS:
            reasons.append(f"Shared servers ≤ {MIN_SHARED_GUILDS}")
        suspicious = bool(reasons)
        return {"age_days": age_days, "shared": shared, "suspicious": suspicious, "reasons": reasons}
    except Exception:
        logger.exception("assess_account_risk failed")
        return {"age_days": None, "shared": 0, "suspicious": False, "reasons": []}

# ====== Full age refresh ======
async def _run_full_age_refresh(guild: discord.Guild):
    tz = timezone(timedelta(hours=7))
    now = datetime.now(tz)
    log_ch = guild.get_channel(LOG_CHANNEL_ID)
    if not log_ch:
        logger.warning("LOG_CHANNEL_ID not found in guild=%s", guild.id)
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
        try:
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
        except Exception:
            logger.exception("Unexpected error while refreshing member=%s", member.id)
            error_lines.append(f"❌ {member.mention}: Unexpected error (ดู log ของบอท)")

    tag = _refresh_period_tag(now, REFRESH_FREQUENCY)
    header = (
        f"{tag} • Guild: {guild.name}\n"
        f"Members found: {len(candidates)}\n"
        f"Changed/No-map: {len(changed_lines)} • Errors: {len(error_lines)}"
    )
    await _log_chunks(log_ch, header, changed_lines + (["— Errors —"] + error_lines if error_lines else []))

# ====== Update latest approval embed ======
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
                                            gender: str | None = None) -> bool:
    msg = await _find_latest_approval_message(guild, member)
    if not msg:
        return False
    try:
        e = msg.embeds[0]
        if nickname is not None:
            _set_or_add_field(e, ("nickname", "ชื่อเล่น"), "Nickname / ชื่อเล่น", nickname or "ไม่ระบุ")
        if age is not None:
            _set_or_add_field(e, ("age", "อายุ"), "Age / อายุ", age or "ไม่ระบุ")
        if gender is not None:
            _set_or_add_field(e, ("gender", "เพศ"), "Gender / เพศ", gender or "ไม่ระบุ")
        await msg.edit(embed=e)
        return True
    except discord.HTTPException:
        logger.exception("HTTP error while editing approval embed for member=%s", member.id)
        return False
    except Exception:
        logger.exception("Unexpected error while editing approval embed for member=%s", member.id)
        return False

# =========== Modal / Views / Commands ===========
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    name = discord.ui.TextInput(
        label="Nickname / ชื่อเล่น (เว้นว่างได้)",
        placeholder="ชื่อเล่น • 2–32 ตัว (ปล่อยว่างถ้าไม่อยากระบุ)",
        style=discord.TextStyle.short,
        min_length=0, max_length=32, required=False
    )
    age = discord.ui.TextInput(
        label="Age / อายุ (ปล่อยว่าง = ไม่ระบุ)",
        placeholder='เช่น 21 หรือ "ไม่ระบุ" (ปล่อยว่างก็ได้)',
        style=discord.TextStyle.short,
        min_length=0, max_length=16, required=False
    )
    gender = discord.ui.TextInput(
        label="Gender / เพศ (ปล่อยว่าง = ไม่ระบุ)",
        placeholder='เช่น ชาย / หญิง / LGBT (ปล่อยว่างก็ได้)',
        style=discord.TextStyle.short,
        min_length=0, required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            if interaction.user.id in pending_verifications:
                await interaction.followup.send(
                    "❗ คุณได้ส่งคำขอไปแล้ว กรุณารอการอนุมัติจากแอดมิน",
                    ephemeral=True
                )
                return

            # --- Validate age ---
            age_raw = (self.age.value or "").strip()
            if not (age_raw == "" or re.fullmatch(r"\d{1,3}", age_raw) or is_age_undisclosed(age_raw)):
                await interaction.followup.send(
                    "❌ รูปแบบอายุไม่ถูกต้อง\n"
                    "• ใส่เป็นตัวเลข 1–3 หลัก เช่น 21\n"
                    "• หรือพิมพ์/ปล่อยว่าง เพื่อ “ไม่ระบุ”",
                    ephemeral=True
                )
                return

            # --- Validate nickname (เฉพาะเมื่อกรอกมา) ---
            nick = (self.name.value or "").strip()
            if nick:
                if len(nick) < 2 or len(nick) > 32 or any(ch.isdigit() for ch in nick) or any(c in INVALID_CHARS for c in nick) or contains_emoji(nick):
                    await interaction.followup.send(
                        "❌ Nickname invalid (letters only, 2–32; no digits/symbols/emoji).",
                        ephemeral=True
                    )
                    return
                if _canon_full(nick) in _discord_names_set(interaction.user):
                    await interaction.followup.send(
                        "❌ ชื่อเล่นต้องต่างจากชื่อในดิสคอร์ดของคุณจริง ๆ",
                        ephemeral=True
                    )
                    return

            # --- Validate gender ---
            gender_raw = (self.gender.value or "")
            if gender_raw.strip():
                if _norm_gender(gender_raw) not in GENDER_UNDISCLOSED_ALIASES:
                    if any(ch.isdigit() for ch in gender_raw) or any(c in INVALID_CHARS for c in gender_raw) or contains_emoji(gender_raw):
                        await interaction.followup.send("❌ Gender invalid. Text only.", ephemeral=True)
                        return

            # ===== Deep account check =====
            account_info = {"age_days": None, "shared": 0, "suspicious": False, "reasons": []}
            if ACCOUNT_CHECKS_ENABLED:
                account_info = assess_account_risk(interaction.user)
                if REQUIRE_MIN_ACCOUNT_AGE_TO_SUBMIT and account_info.get("suspicious"):
                    await interaction.followup.send(
                        "⛔ บัญชีของคุณเพิ่งถูกสร้างหรือมีความเสี่ยง โปรดลองใหม่อีกครั้งภายหลัง",
                        ephemeral=True
                    )
                    await _notify_admins(
                        interaction.guild,
                        f"บล็อคการยืนยันของ {interaction.user.mention} (ID:{interaction.user.id}) "
                        f"เนื่องจากเสี่ยง: {', '.join(account_info.get('reasons', []))}"
                    )
                    return

            # เตรียมค่าที่แสดงใน embed
            display_nick = (nick if nick else "ไม่ระบุ")
            display_age = (age_raw if age_raw else "ไม่ระบุ")
            display_gender = (gender_raw.strip() if gender_raw.strip() else "ไม่ระบุ")

            embed = discord.Embed(
                title="📋 Verification Request / คำขอยืนยันตัวตน",
                color=discord.Color.red() if account_info.get("suspicious") else discord.Color.orange()
            )
            try:
                thumb_url = interaction.user.display_avatar.with_static_format("png").with_size(128).url
                embed.set_thumbnail(url=thumb_url)
            except Exception:
                pass
            embed.add_field(name="Nickname / ชื่อเล่น", value=display_nick, inline=False)
            embed.add_field(name="Age / อายุ", value=display_age, inline=False)
            embed.add_field(name="Gender / เพศ", value=display_gender, inline=False)

            # ใส่ข้อมูลตรวจสอบบัญชี
            if ACCOUNT_CHECKS_ENABLED:
                age_days = account_info.get("age_days")
                shared = account_info.get("shared")
                risk = "HIGH ⚠️" if account_info.get("suspicious") else "LOW ✅"
                acct_txt = f"Account age: {age_days if age_days is not None else '?'} days • Shared servers: {shared} • Risk: {risk}"
                embed.add_field(name="🛡 Account Check", value=acct_txt, inline=False)

            now = datetime.now(timezone(timedelta(hours=7)))
            embed.add_field(name="📅 Sent at", value=now.strftime("%d/%m/%Y %H:%M"), inline=False)
            embed.set_footer(text=f"User ID: {interaction.user.id}")

            channel = interaction.guild.get_channel(APPROVAL_CHANNEL_ID)
            if not channel:
                await interaction.followup.send("❌ ไม่พบห้องอนุมัติ กรุณาเช็ค APPROVAL_CHANNEL_ID", ephemeral=True)
                await _notify_admins(interaction.guild, f"ไม่พบห้อง APPROVAL_CHANNEL_ID ({APPROVAL_CHANNEL_ID}) ตอนส่งคำขอของ {interaction.user.mention}")
                return

            view = ApproveRejectView(
                user=interaction.user,
                gender_text=gender_raw,
                age_text=age_raw if age_raw else "ไม่ระบุ",
                form_name=nick,
            )
            sent_msg = await channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=view,
                allowed_mentions=SAFE_MENTIONS,
            )

            # เพิ่มเข้าคิว หลังส่งข้อความสำเร็จ
            pending_verifications.add(interaction.user.id)

            # แจ้งแอดมินถ้าพบความเสี่ยง
            if ACCOUNT_CHECKS_ENABLED and account_info.get("suspicious"):
                await _notify_admins(
                    interaction.guild,
                    f"คำขอยืนยันของ {interaction.user.mention} (ID:{interaction.user.id}) มีความเสี่ยง: {', '.join(account_info.get('reasons', []))} • Jump: {sent_msg.jump_url}"
                )

            await interaction.followup.send(
                "✅ ส่งคำขอยืนยันตัวตนแล้ว กรุณารอการอนุมัติจากแอดมิน",
                ephemeral=True
            )
        except Exception:
            logger.exception("on_submit failed")
            pending_verifications.discard(interaction.user.id)
            try:
                await _notify_admins(interaction.guild, f"เกิดข้อผิดพลาดระหว่างส่งคำขอยืนยันของ {interaction.user.mention} (ID:{interaction.user.id})")
                await interaction.followup.send("❌ เกิดข้อผิดพลาดไม่คาดคิด โปรดลองใหม่ภายหลัง", ephemeral=True)
            except Exception:
                pass

class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Identity / ยืนยันตัวตน", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(VerificationForm())
        except Exception:
            logger.exception("open VerificationForm failed")
            try:
                await interaction.response.send_message("❌ เปิดแบบฟอร์มไม่สำเร็จ โปรดลองใหม่", ephemeral=True)
            except Exception:
                pass

class ApproveRejectView(discord.ui.View):
    def __init__(self, user: discord.User, gender_text: str, age_text: str, form_name: str):
        super().__init__(timeout=None)
        self.user = user
        self.gender_text = (gender_text or "").strip()
        self.age_text = (age_text or "").strip()
        self.form_name = (form_name or "").strip()

    @discord.ui.button(label="✅ Approve / อนุมัติ", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()

            member = interaction.guild.get_member(self.user.id)
            if not member:
                try:
                    member = await interaction.guild.fetch_member(self.user.id)
                except Exception:
                    await interaction.followup.send("❌ Member not found in guild.", ephemeral=True)
                    return

            general_role = interaction.guild.get_role(ROLE_ID_TO_GIVE)
            gender_role = interaction.guild.get_role(resolve_gender_role_id(self.gender_text))
            age_role_id = resolve_age_role_id(self.age_text)
            age_role = interaction.guild.get_role(age_role_id) if age_role_id else None

            if member and general_role and gender_role:
                try:
                    # enforce one gender role
                    to_remove_gender = [r for r in member.roles if r.id in GENDER_ROLE_IDS_ALL and (gender_role is None or r.id != gender_role.id)]
                    if to_remove_gender:
                        await member.remove_roles(*to_remove_gender, reason="Verification: enforce single gender role")
                except discord.Forbidden:
                    await _notify_admins(interaction.guild, f"บอทไม่มีสิทธิ์ถอดยศเพศของ {member.mention}")
                    await interaction.followup.send("❌ ไม่มีสิทธิ์ถอดยศเพศเดิม", ephemeral=True)
                    return

                if age_role:
                    try:
                        to_remove_age = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and r.id != age_role.id]
                        if to_remove_age:
                            await member.remove_roles(*to_remove_age, reason="Verification: enforce single age role")
                    except discord.Forbidden:
                        await _notify_admins(interaction.guild, f"บอทไม่มีสิทธิ์ถอดยศอายุของ {member.mention}")
                        await interaction.followup.send("❌ ไม่มีสิทธิ์ถอดยศอายุเดิม", ephemeral=True)
                        return

                roles_to_add = []
                if general_role and general_role not in member.roles: roles_to_add.append(general_role)
                if gender_role and gender_role not in member.roles: roles_to_add.append(gender_role)
                if age_role and age_role not in member.roles: roles_to_add.append(age_role)

                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="Verified")
                    except discord.Forbidden:
                        await _notify_admins(interaction.guild, f"บอทไม่มีสิทธิ์เพิ่มยศให้ {member.mention}")
                        await interaction.followup.send("❌ Missing permissions to add roles.", ephemeral=True)
                        return

                # set nickname suffix
                if APPEND_FORM_NAME_TO_NICK and self.form_name:
                    try:
                        bot_me = interaction.guild.me or await interaction.guild.fetch_member(bot.user.id)
                        if bot_me and bot_me.guild_permissions.manage_nicknames and bot_me.top_role > member.top_role and member.guild.owner_id != member.id:
                            new_nick = build_parenthesized_nick(member, self.form_name)
                            current_nick = member.nick or ""
                            if new_nick and new_nick != current_nick:
                                await member.edit(nick=new_nick, reason="Verification: append form nickname")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    except Exception:
                        logger.exception("edit nick failed during approve for member=%s", member.id)

                pending_verifications.discard(self.user.id)
            else:
                await interaction.followup.send("❌ Member or role not found.", ephemeral=True)

            # ปรับปุ่ม & footer
            for child in self.children:
                if getattr(child, "custom_id", None) == "approve_button":
                    child.label = "✅ Approved / อนุมัติแล้ว"
                    child.style = discord.ButtonStyle.success
                elif getattr(child, "custom_id", None) == "reject_button":
                    child.style = discord.ButtonStyle.secondary
                child.disabled = True

            try:
                msg = interaction.message
                if msg and msg.embeds:
                    e = msg.embeds[0]
                    actor = getattr(interaction.user, "display_name", None) or interaction.user.name
                    stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
                    orig = e.footer.text or ""
                    footer = f"{orig} • Approved by {actor} • {stamp}" if orig else f"Approved by {actor} • {stamp}"
                    e.set_footer(text=footer)
                    await msg.edit(embed=e, view=self)
                else:
                    await interaction.message.edit(view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.exception("edit approval message failed (approve)")
        except Exception:
            logger.exception("Approve handler crashed")
            await _notify_admins(interaction.guild, f"เกิดข้อผิดพลาดระหว่างอนุมัติให้ {self.user.mention}")
            try:
                await interaction.followup.send("❌ เกิดข้อผิดพลาดระหว่างอนุมัติ", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="❌ Reject / ปฏิเสธ", style=discord.ButtonStyle.danger, custom_id="reject_button")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()

            pending_verifications.discard(self.user.id)
            try:
                await self.user.send(
                    "❌ การยืนยันตัวตนของคุณไม่ผ่าน กรุณาติดต่อแอดมิน หรือกดยืนยันใหม่ได้ที่ห้อง Verify"
                )
            except Exception:
                await interaction.followup.send("⚠️ ไม่สามารถส่ง DM แจ้งผู้ใช้ได้", ephemeral=True)

            for child in self.children:
                if getattr(child, "custom_id", None) == "reject_button":
                    child.label = "❌ Rejected / ปฏิเสธแล้ว"
                    child.style = discord.ButtonStyle.danger
                elif getattr(child, "custom_id", None) == "approve_button":
                    child.style = discord.ButtonStyle.secondary
                child.disabled = True

            try:
                msg = interaction.message
                if msg and msg.embeds:
                    e = msg.embeds[0]
                    actor = getattr(interaction.user, "display_name", None) or interaction.user.name
                    stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
                    orig = e.footer.text or ""
                    footer = f"{orig} • Rejected by {actor} • {stamp}" if orig else f"Rejected by {actor} • {stamp}"
                    e.set_footer(text=footer)
                    await msg.edit(embed=e, view=self)
                else:
                    await interaction.message.edit(view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.exception("edit approval message failed (reject)")
        except Exception:
            logger.exception("Reject handler crashed")
            await _notify_admins(interaction.guild, f"เกิดข้อผิดพลาดระหว่างปฏิเสธของ {self.user.mention}")
            try:
                await interaction.followup.send("❌ เกิดข้อผิดพลาดระหว่างปฏิเสธ", ephemeral=True)
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
        embed.set_footer(text="Verification System / ระบบยืนยันตัวตนโดย Bot")
        await channel.send(embed=embed, view=VerificationView(), allowed_mentions=SAFE_MENTIONS)
        await ctx.send(f"✅ Verification embed sent to {channel.mention}")
    except discord.Forbidden:
        await ctx.send("❌ บอทไม่มีสิทธิ์ส่งข้อความไปยังห้องเป้าหมาย")
    except discord.HTTPException:
        logger.exception("verify_embed HTTP error")
        await ctx.send("❌ ส่ง embed ไม่สำเร็จ (HTTP)")

@bot.command(name="userinfo")
@commands.has_permissions(administrator=True)
async def userinfo(ctx, member: discord.Member):
    try:
        channel = ctx.guild.get_channel(APPROVAL_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ APPROVAL_CHANNEL_ID not found.")
            return

        async for message in channel.history(limit=200):
            if message.author == bot.user and message.embeds and message.mentions:
                if member in message.mentions:
                    embed0 = message.embeds[0]
                    new_embed = copy_embed_fields(embed0)

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
                            logger.exception("Reading attachment failed in userinfo")

                    await ctx.send(embed=new_embed)
                    return

        await ctx.send("❌ No verification info found for this user.")
    except discord.Forbidden:
        await ctx.send("❌ บอทไม่มีสิทธิ์อ่านประวัติข้อความในห้องอนุมัติ")
    except discord.HTTPException:
        logger.exception("userinfo HTTP error")
        await ctx.send("❌ ดึงข้อมูลไม่สำเร็จ (HTTP)")
    except Exception:
        logger.exception("userinfo crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

# ---------- Single user refresh ----------
@bot.command(name="refresh_age")
@commands.has_permissions(administrator=True)
async def refresh_age(ctx, member: discord.Member):
    try:
        embed = await _latest_verification_embed_for(member)
        if not embed:
            await ctx.send("❌ ไม่พบข้อมูลคำขอยืนยันล่าสุดของผู้ใช้นี้ในห้องอนุมัติ")
            return

        age_text = _find_embed_field(embed, "age", "อายุ")
        sent_text = _find_embed_field(embed, "sent at")
        if not age_text or not sent_text:
            await ctx.send("❌ ข้อมูลใน embed ไม่ครบ (Age หรือ Sent at หาย)")
            return

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
    except discord.HTTPException:
        logger.exception("refresh_age HTTP error")
        await ctx.send("❌ เกิดข้อผิดพลาด HTTP")
    except Exception:
        logger.exception("refresh_age crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

# ---------- All users refresh ----------
@bot.command(name="refresh_age_all")
@commands.has_permissions(administrator=True)
async def refresh_age_all(ctx):
    try:
        await ctx.send("⏳ กำลังรีเฟรชอายุทั้งเซิร์ฟเวอร์และบันทึก log ...")
        await _run_full_age_refresh(ctx.guild)
        await ctx.send("✅ เสร็จสิ้น (ดูรายละเอียดในห้อง log)")
    except discord.HTTPException:
        logger.exception("refresh_age_all HTTP error")
        await ctx.send("❌ เกิดข้อผิดพลาด HTTP")
    except Exception:
        logger.exception("refresh_age_all crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

# ====== Admin adjust commands ======
CLEAR_ALIASES = {"clear", "reset", "remove", "none", "no", "x", "-", "—", "ลบ", "เอาออก", "ไม่ใช้", "ไม่ใส่", "ไม่ต้อง"}

def _bot_can_edit_member_and_role(ctx: commands.Context, member: discord.Member, role: discord.Role | None = None) -> tuple[bool, str]:
    bot_me = ctx.guild.me
    if not bot_me:
        return False, "❌ ไม่พบสถานะของบอทในกิลด์"
    if bot_me.top_role <= member.top_role or member.id == ctx.guild.owner_id:
        return False, "❌ บอทไม่มีลำดับยศสูงพอที่จะจัดการสมาชิกคนนี้"
    if role and bot_me.top_role <= role:
        return False, f"❌ บอทไม่มีลำดับยศสูงพอที่จะจัดการยศ: {role.name}"
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

        if len(nickname) < 2 or len(nickname) > 32 or any(ch.isdigit() for ch in nickname) \
           or any(c in INVALID_CHARS for c in nickname) or contains_emoji(nickname):
            await ctx.send("❌ ชื่อเล่นไม่ถูกต้อง (ต้องเป็นตัวอักษร 2–32 ตัว, ห้ามตัวเลข/สัญลักษณ์/อีโมจิ)")
            return
        if _canon_full(nickname) in _discord_names_set(member):
            await ctx.send("❌ ชื่อเล่นต้องต่างจากชื่อในดิสคอร์ดของเป้าหมายจริง ๆ")
            return

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
    except Exception:
        logger.exception("setnick crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

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
    except Exception:
        logger.exception("setgender crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

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
        if role.id == ROLE_AGE_UNDISCLOSED:
            disp_age = "ไม่ระบุ"
        else:
            m = re.search(r"\d{1,3}", age_text)
            disp_age = m.group(0) if m else age_text.strip()
        updated = await _update_approval_embed_for_member(ctx.guild, member, age=disp_age)
        if not updated:
            await ctx.send("ℹ️ ไม่พบ embed ในห้องอนุมัติสำหรับผู้ใช้นี้ จึงไม่ได้อัปเดตข้อความ")
    except Exception:
        logger.exception("setage crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

# ====== Re-verification command ======
@bot.command(name="reverify", aliases=["บังคับยืนยัน", "รีเวอริฟาย"])
@commands.has_permissions(administrator=True)
async def reverify(ctx: commands.Context, member: discord.Member):
    """
    บังคับให้สมาชิกกลับไปยืนยันตัวตนใหม่:
    - ลบ role ยืนยัน (และตาม config อาจลบ role เพศ/อายุ)
    - ลบ embed ของผู้ใช้ในห้องอนุมัติ
    - ส่ง DM ให้สมาชิก พร้อม ping ในห้อง verify (ตาม config)
    """
    try:
        general_role = ctx.guild.get_role(ROLE_ID_TO_GIVE)
        roles_to_remove = []
        if general_role and general_role in member.roles:
            roles_to_remove.append(general_role)

        if REVERIFY_CLEAR_GENDER_AND_AGE:
            roles_to_remove.extend([r for r in member.roles if (r.id in GENDER_ROLE_IDS_ALL or r.id in AGE_ROLE_IDS_ALL)])

        if roles_to_remove:
            try:
                await member.remove_roles(*set(roles_to_remove), reason="Admin: force re-verification")
            except discord.Forbidden:
                await ctx.send("❌ บอทไม่มีสิทธิ์ถอดยศของสมาชิกคนนี้")
                return

        # ลบ embed ของผู้ใช้ในห้องอนุมัติ (ถ้ามี)
        deleted_embed = False
        try:
            msg = await _find_latest_approval_message(ctx.guild, member)
            if msg:
                await msg.delete()
                deleted_embed = True
        except discord.Forbidden:
            await ctx.send("⚠️ ลบ embed ในห้องอนุมัติไม่สำเร็จ (สิทธิ์ไม่พอ)")
        except discord.HTTPException:
            await ctx.send("⚠️ ลบ embed ในห้องอนุมัติไม่สำเร็จ (HTTP)")

        # แจ้งผู้ใช้ให้กลับไปยืนยัน
        try:
            verify_ch = ctx.guild.get_channel(VERIFY_CHANNEL_ID)
            vtxt = f"กรุณากลับไปยืนยันตัวตนใหม่ที่ห้อง {verify_ch.mention}" if verify_ch else "กรุณากลับไปยืนยันตัวตนใหม่ที่ห้องยืนยัน"
            await member.send(
                "ℹ️ ผู้ดูแลได้ขอให้คุณยืนยันตัวตนใหม่อีกครั้ง\n" + vtxt
            )
        except Exception:
            await ctx.send("⚠️ ไม่สามารถส่ง DM ถึงผู้ใช้งานได้ (ปิด DM หรือบล็อค)")

        # Ping ในห้อง verify
        if REVERIFY_PING_IN_VERIFY_CHANNEL:
            try:
                verify_ch = ctx.guild.get_channel(VERIFY_CHANNEL_ID)
                if verify_ch:
                    await verify_ch.send(
                        content=f"{member.mention} กรุณากดยืนยันตัวตนอีกครั้งได้ที่ปุ่มด้านบนนะครับ/ค่ะ",
                        allowed_mentions=SAFE_MENTIONS
                    )
            except Exception:
                logger.exception("ping verify channel failed")

        await ctx.send(f"✅ สั่งให้ {member.mention} ทำการยืนยันตัวตนใหม่แล้ว {'(ลบ embed แล้ว)' if deleted_embed else ''}")
        await _notify_admins(ctx.guild, f"{ctx.author.mention} สั่ง re-verify สำหรับ {member.mention} แล้ว")
    except Exception:
        logger.exception("reverify crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิดขณะ re-verify")

# ====== Help command (list & details) ======
try:
    bot.remove_command("help")
except Exception:
    pass

_SHORT_DESC = {
    "help": "แสดงรายการคำสั่งทั้งหมด หรือรายละเอียดของคำสั่งที่ระบุ",
    "verify_embed": "ส่ง Embed ปุ่มยืนยันตัวตนไปยังห้อง VERIFY_CHANNEL_ID",
    "userinfo": "แสดงข้อมูลยืนยันล่าสุดของสมาชิกจากห้องอนุมัติ",
    "refresh_age": "อัปเดตยศอายุตามเวลาที่ผ่านไป (รายบุคคล)",
    "refresh_age_all": "อัปเดตยศอายุทั้งเซิร์ฟเวอร์ตาม logs",
    "setnick": "ตั้ง/ลบ วงเล็บชื่อเล่น ต่อท้ายชื่อดิสของสมาชิก",
    "setgender": "ตั้งยศเพศ (ชาย/หญิง/LGBT/ไม่ระบุ)",
    "setage": "ตั้งยศอายุ (กรอกตัวเลขหรือ 'ไม่ระบุ')",
    "reverify": "ลบยศยืนยัน (และเพศ/อายุถ้าตั้งไว้) ลบ embed แล้วสั่งให้ยืนยันใหม่",
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
    "userinfo": {
        "usage": "$userinfo @สมาชิก",
        "example": "$userinfo @Alice",
        "note": "ดึง embed คำขอยืนยันล่าสุดจากห้องอนุมัติ",
    },
    "refresh_age": {
        "usage": "$refresh_age @สมาชิก",
        "example": "$refresh_age @Alice",
        "note": "คำนวณอัตโนมัติจากเวลาในฟิลด์ 'Sent at' ของ embed",
    },
    "refresh_age_all": {
        "usage": "$refresh_age_all",
        "example": "$refresh_age_all",
        "note": "รันทั้งเซิร์ฟเวอร์และส่งผลลัพธ์ไปห้อง log",
    },
    "setnick": {
        "usage": "$setnick @สมาชิก <ชื่อเล่น|clear>",
        "example": "$setnick @Alice มินนี่\n$setnick @Alice clear",
        "note": "ต้อง Manage Nicknames; ใช้ clear/reset/remove/ลบ เพื่อลบวงเล็บ",
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
    "reverify": {
        "usage": "$reverify @สมาชิก",
        "example": "$reverify @Alice",
        "note": "ต้องมีสิทธิ์ Administrator • ลบยศยืนยัน (+เพศ/อายุ ตาม config) • ลบ embed • DM ให้ยืนยันใหม่",
    },
}

_ADMIN_COMMANDS = {"verify_embed", "userinfo", "refresh_age", "refresh_age_all", "setnick", "setgender", "setage", "reverify"}

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
    except Exception:
        logger.exception("help_command crashed")
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิด")

# ====== AUTO REFRESH DAEMON (configurable) ======
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
        logger.exception("history read failed in _already_ran_this_period")
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
        try:
            now_utc = datetime.now(timezone.utc)
            now_local = now_utc.astimezone(tz)
            target_local = _compute_next_run_local(now_local)
            target_utc = target_local.astimezone(timezone.utc)
            sleep_sec = max(1, int((target_utc - now_utc).total_seconds()))
            await asyncio.sleep(sleep_sec)

            for guild in bot.guilds:
                try:
                    log_ch = guild.get_channel(LOG_CHANNEL_ID)
                    if not log_ch:
                        continue
                    if await _already_ran_this_period(log_ch, tz, REFRESH_FREQUENCY):
                        continue
                    await _run_full_age_refresh(guild)
                    await log_ch.send(_refresh_period_tag(datetime.now(tz), REFRESH_FREQUENCY) + " ✅ DONE", allowed_mentions=SAFE_MENTIONS)
                except Exception:
                    logger.exception("auto refresh failed for guild=%s", getattr(guild, "id", None))
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("auto refresh loop crashed (will continue)")

# ====== Global error handlers ======
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    try:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ คำสั่งไม่ครบอาร์กิวเมนต์: `{error.param.name}`"); return
        if isinstance(error, commands.BadArgument):
            await ctx.send("❌ อาร์กิวเมนต์ไม่ถูกต้อง (รูปแบบไม่ตรง)"); return
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ ไม่พบสมาชิกที่ระบุ"); return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้"); return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ บอทไม่มีสิทธิ์เพียงพอสำหรับคำสั่งนี้"); return
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ ไม่ผ่านเงื่อนไขการใช้งานคำสั่งนี้"); return
        await ctx.send("❌ เกิดข้อผิดพลาดไม่คาดคิดระหว่างรันคำสั่ง")
        logger.exception("on_command_error: %r", error)
        try:
            await _notify_admins(ctx.guild, f"Command error โดย {ctx.author.mention}: {error!r}")
        except Exception:
            pass
    except Exception:
        logger.exception("on_command_error handler crashed")

@bot.event
async def on_error(event_method: str, *args, **kwargs):
    logger.exception("on_error in event=%s", event_method)

# ====== Persistent View Loader ======
@bot.event
async def on_ready():
    try:
        logger.info("Logged in as %s", bot.user)
        bot.add_view(VerificationView())
        if AUTO_REFRESH_ENABLED and not getattr(bot, "_age_refresh_daemon_started", False):
            bot.loop.create_task(_auto_refresh_daemon())
            bot._age_refresh_daemon_started = True
    except Exception:
        logger.exception("on_ready failed")

# ====== Run bot ======
if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN ENV NOT SET")
    bot.run(token)
