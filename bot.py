import os
import re
import io
import unicodedata
import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta

# ====== CONFIGURATION ======
VERIFY_CHANNEL_ID = 1402889712888447037
APPROVAL_CHANNEL_ID = 1402889786712395859
LOG_CHANNEL_ID = 1418941833819590699  # ห้องเก็บ logs ของการรีเฟรชอายุ (ใหม่)

ROLE_ID_TO_GIVE = 1321268883088211981
ROLE_MALE = 1321268883025559689
ROLE_FEMALE = 1321268883025559688
ROLE_LGBT = 1321268883025559687
ROLE_GENDER_UNDISCLOSED = 1419046348023398421  # << ใหม่: เพศไม่ระบุ/ไม่อยากเปิดเผย

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
ROLE_AGE_UNDISCLOSED = 1419045340576747663  # ไม่สะดวกกรอก/ไม่อยากเปิดเผยอายุ

APPEND_FORM_NAME_TO_NICK = True

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

# ====== Nickname canonicalizer (เข้ม) & same-name block ======
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
    "महिला", "औरत", "लड़की", "ladki", "aurat", "عورت", "خاتون",
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
# LGBT (เพศทางเลือก/อัตลักษณ์ทางเพศที่ไม่ใช่ชาย/หญิงแบบไบนารี)
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
# ใหม่: เพศไม่ระบุ/ไม่อยากเปิดเผย
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
    # ค่าไม่รู้จัก → ปลอดภัยสุดให้ "ไม่ระบุเพศ"
    return ROLE_GENDER_UNDISCLOSED

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
    return _norm_simple(text) in AGE_UNDISCLOSED_ALIASES

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
        return None, None

def copy_embed_fields(src: discord.Embed) -> discord.Embed:
    e = discord.Embed(
        title=src.title or discord.Embed.Empty,
        description=src.description or discord.Embed.Empty,
        color=src.color if src.color is not None else discord.Embed.Empty,
    )
    if src.author and (src.author.name or src.author.icon_url or src.author.url):
        e.set_author(name=getattr(src.author, "name", discord.Embed.Empty) or discord.Embed.Empty)
    if src.footer and (src.footer.text or src.footer.icon_url):
        e.set_footer(text=getattr(src.footer, "text", discord.Embed.Empty) or discord.Embed.Empty)
    if src.image and src.image.url:
        e.set_image(url=src.image.url)
    for f in src.fields:
        e.add_field(name=f.name, value=f.value, inline=f.inline)
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
GENDER_ROLE_IDS_ALL = [ROLE_MALE, ROLE_FEMALE, ROLE_LGBT, ROLE_GENDER_UNDISCLOSED]  # << เพิ่ม
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
    async for msg in channel.history(limit=500):
        if msg.author == bot.user and msg.embeds and member in msg.mentions:
            return msg.embeds[0]
    return None

async def _build_latest_verification_index(guild: discord.Guild, limit: int = 2000):
    channel = guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        return {}
    index = {}
    async for msg in channel.history(limit=limit):
        if msg.author != bot.user or not msg.embeds or not msg.mentions:
            continue
        u = msg.mentions[0]
        if u is None:
            continue
        if u.id not in index:
            index[u.id] = (msg.embeds[0], msg.created_at)
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
                    await member.remove_roles(*to_remove, reason="Monthly age refresh → undisclosed")
                if new_role and new_role not in member.roles:
                    await member.add_roles(new_role, reason="Monthly age refresh → undisclosed")
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
                await member.remove_roles(*to_remove, reason=f"Monthly age refresh → now {new_age}")
        except discord.Forbidden:
            error_lines.append(f"❌ {member.mention}: ไม่มีสิทธิ์ถอดยศอายุเดิม")
            continue
        except discord.HTTPException:
            error_lines.append(f"❌ {member.mention}: ถอดยศอายุเดิมไม่สำเร็จ (HTTP)")
            continue

        if new_role:
            try:
                await member.add_roles(new_role, reason=f"Monthly age refresh → now {new_age}")
                old_names = ", ".join(r.name for r in to_remove) if to_remove else "—"
                changed_lines.append(f"✅ {member.mention}: {new_age} ปี → {new_role.name} (removed: {old_names})")
            except discord.Forbidden:
                error_lines.append(f"❌ {member.mention}: เพิ่มยศใหม่ไม่สำเร็จ (สิทธิ์ไม่พอ)")
            except discord.HTTPException:
                error_lines.append(f"❌ {member.mention}: เพิ่มยศใหม่ไม่สำเร็จ (HTTP)")
        else:
            changed_lines.append(f"⚠️ {member.mention}: {new_age} ปี → ไม่มี role ที่แมปไว้")

    header = (
        f"[AGE-REFRESH] {now.year}-{now.month:02d} • Guild: {guild.name}\n"
        f"Members found: {len(candidates)}\n"
        f"Changed/No-map: {len(changed_lines)} • Errors: {len(error_lines)}"
    )
    await _log_chunks(log_ch, header, changed_lines + (["— Errors —"] + error_lines if error_lines else []))

# =========== Modal / Views / Commands ===========
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    name = discord.ui.TextInput(
        label="Nickname / ชื่อเล่น",
        placeholder="ชื่อเล่น 2–32 ตัว",
        style=discord.TextStyle.short,
        min_length=2, max_length=32, required=True
    )
    age = discord.ui.TextInput(
        label="Age / อายุ (ใส่ตัวเลข หรือพิมพ์ 'ไม่ระบุ')",
        placeholder='เช่น 21 หรือ "ไม่ระบุ"',
        style=discord.TextStyle.short,
        min_length=1, max_length=16, required=True
    )
    gender = discord.ui.TextInput(
        label="Gender / เพศ (ชาย/หญิง/LGBT หรือ 'ไม่ระบุ')",
        placeholder="ชาย / หญิง / LGBT / ไม่ระบุ",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if interaction.user.id in pending_verifications:
            await interaction.followup.send(
                "❗ You already submitted a verification request. Please wait for admin review.\n"
                "❗ คุณได้ส่งคำขอไปแล้ว กรุณารอการอนุมัติจากแอดมิน",
                ephemeral=True
            )
            return

        age_str = (self.age.value or "").strip()
        if not (re.fullmatch(r"\d{1,3}", age_str) or is_age_undisclosed(age_str)):
            await interaction.followup.send(
                "❌ รูปแบบอายุไม่ถูกต้อง\n"
                "• ใส่เป็นตัวเลข 1–3 หลัก เช่น 21\n"
                "• หรือพิมพ์ว่า “ไม่ระบุ / ไม่อยากเปิดเผย / prefer not to say”",
                ephemeral=True
            )
            return

        nick = (self.name.value or "").strip()
        if len(nick) < 2 or len(nick) > 32 or any(ch.isdigit() for ch in nick) or any(c in INVALID_CHARS for c in nick) or contains_emoji(nick):
            await interaction.followup.send(
                "❌ Nickname invalid (letters only, 2–32; no digits/symbols/emoji).",
                ephemeral=True
            )
            return

        # บล็อกกรณีชื่อเล่น == ชื่อดิสคอร์ด (หลัง normalize แบบเข้ม)
        if _canon_full(nick) in _discord_names_set(interaction.user):
            await interaction.followup.send(
                "❌ ชื่อเล่นต้องต่างจากชื่อในดิสคอร์ดของคุณจริง ๆ\n"
                "   (การเปลี่ยนพิมพ์เล็ก-ใหญ่ ใส่อักษรพิเศษ/อีโมจิ เลขแทนอักษร หรือใช้อักษรหน้าตาคล้าย จะไม่ถือว่าต่าง)\n"
                "❌ Nickname must be different from your current Discord name.",
                ephemeral=True
            )
            return

        # เพศ: อนุญาตข้อความธรรมดา/ไม่ระบุ (ตัวเลข/อีโมจิ/สัญลักษณ์แปลกยังไม่ให้)
        if any(ch.isdigit() for ch in self.gender.value) or any(c in INVALID_CHARS for c in self.gender.value) or contains_emoji(self.gender.value):
            await interaction.followup.send("❌ Gender invalid. Text only.", ephemeral=True)
            return

        pending_verifications.add(interaction.user.id)

        embed = discord.Embed(title="📋 Verification Request / คำขอยืนยันตัวตน", color=discord.Color.orange())
        thumb_url = interaction.user.display_avatar.with_static_format("png").with_size(128).url
        embed.set_thumbnail(url=thumb_url)
        embed.add_field(name="Nickname / ชื่อเล่น", value=self.name.value, inline=False)
        embed.add_field(name="Age / อายุ", value=self.age.value, inline=False)
        embed.add_field(name="Gender / เพศ", value=self.gender.value, inline=False)

        now = datetime.now(timezone(timedelta(hours=7)))
        embed.add_field(name="📅 Sent at", value=now.strftime("%d/%m/%Y %H:%M"), inline=False)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        channel = interaction.guild.get_channel(APPROVAL_CHANNEL_ID)
        if channel:
            view = ApproveRejectView(
                user=interaction.user,
                gender_text=self.gender.value,
                age_text=self.age.value,
                form_name=self.name.value,
            )
            await channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            )

        await interaction.followup.send(
            "✅ Verification request submitted. Please wait for admin approval.\n"
            "✅ ส่งคำขอยืนยันตัวตนแล้ว กรุณารอการอนุมัติจากแอดมิน",
            ephemeral=True
        )

class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Identity / ยืนยันตัวตน", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerificationForm())

class ApproveRejectView(discord.ui.View):
    def __init__(self, user: discord.User, gender_text: str, age_text: str, form_name: str):
        super().__init__(timeout=None)
        self.user = user
        self.gender_text = (gender_text or "").strip()
        self.age_text = (age_text or "").strip()
        self.form_name = (form_name or "").strip()

    @discord.ui.button(label="✅ Approve / อนุมัติ", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            # enforce one gender role
            try:
                to_remove_gender = [r for r in member.roles if r.id in GENDER_ROLE_IDS_ALL and (gender_role is None or r.id != gender_role.id)]
                if to_remove_gender:
                    await member.remove_roles(*to_remove_gender, reason="Verification: enforce single gender role")
            except discord.Forbidden:
                await interaction.followup.send("❌ ไม่มีสิทธิ์ถอดยศเพศเดิม", ephemeral=True)
                return

            # enforce one age role (only if new exists)
            if age_role:
                try:
                    to_remove_age = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL and r.id != age_role.id]
                    if to_remove_age:
                        await member.remove_roles(*to_remove_age, reason="Verification: enforce single age role")
                except discord.Forbidden:
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
                    await interaction.followup.send("❌ Missing permissions to add roles.", ephemeral=True)
                    return

            # วงเล็บชื่อเล่น
            if APPEND_FORM_NAME_TO_NICK and self.form_name:
                bot_me = interaction.guild.me or await interaction.guild.fetch_member(bot.user.id)
                try:
                    if bot_me and bot_me.guild_permissions.manage_nicknames and bot_me.top_role > member.top_role and member.guild.owner_id != member.id:
                        new_nick = build_parenthesized_nick(member, self.form_name)
                        current_nick = member.nick or ""
                        if new_nick and new_nick != current_nick:
                            await member.edit(nick=new_nick, reason="Verification: append form nickname")
                except Exception:
                    pass

            pending_verifications.discard(self.user.id)
        else:
            await interaction.followup.send("❌ Member or role not found.", ephemeral=True)

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

    @discord.ui.button(label="❌ Reject / ปฏิเสธ", style=discord.ButtonStyle.danger, custom_id="reject_button")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        pending_verifications.discard(self.user.id)
        try:
            await self.user.send(
                "❌ Your verification was rejected. Please contact admin.\n"
                "❌ การยืนยันตัวตนของคุณไม่ผ่าน กรุณาติดต่อแอดมิน"
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

# ====== Commands ======
@bot.command(name="verify_embed")
@commands.has_permissions(administrator=True)
async def verify_embed(ctx):
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

@bot.command(name="userinfo")
@commands.has_permissions(administrator=True)
async def userinfo(ctx, member: discord.Member):
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
                        pass

                await ctx.send(embed=new_embed)
                return

    await ctx.send("❌ No verification info found for this user.")

# ---------- Single user refresh ----------
@bot.command(name="refresh_age")
@commands.has_permissions(administrator=True)
async def refresh_age(ctx, member: discord.Member):
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

# ---------- All users refresh ----------
@bot.command(name="refresh_age_all")
@commands.has_permissions(administrator=True)
async def refresh_age_all(ctx):
    await ctx.send("⏳ กำลังรีเฟรชอายุทั้งเซิร์ฟเวอร์และบันทึก log ...")
    await _run_full_age_refresh(ctx.guild)
    await ctx.send("✅ เสร็จสิ้น (ดูรายละเอียดในห้อง log)")

# ====== Monthly scheduler (new) ======
async def _already_ran_this_month(log_ch: discord.TextChannel, tz: timezone) -> bool:
    now = datetime.now(tz)
    tag = f"[AGE-REFRESH] {now.year}-{now.month:02d}"
    try:
        async for m in log_ch.history(limit=200):
            if m.author == bot.user and m.content and tag in m.content:
                return True
    except Exception:
        pass
    return False

async def _monthly_age_refresh_daemon():
    tz = timezone(timedelta(hours=7))  # Asia/Bangkok
    await bot.wait_until_ready()
    while not bot.is_closed():
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)

        year = now_local.year
        month = now_local.month
        if now_local.day > 1 or (now_local.day == 1 and now_local.hour >= 6):
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        target_local = datetime(year, month, 1, 6, 0, 0, tzinfo=tz)
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
                if await _already_ran_this_month(log_ch, tz):
                    continue
                await _run_full_age_refresh(guild)
                await log_ch.send("✅ DONE")
        except Exception:
            pass

# ====== Persistent View Loader ======
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.add_view(VerificationView())
    if not getattr(bot, "_age_refresh_daemon_started", False):
        bot.loop.create_task(_monthly_age_refresh_daemon())
        bot._age_refresh_daemon_started = True

# ====== Run bot ======
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
