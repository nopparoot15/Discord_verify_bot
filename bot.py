import os
import re
import io
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta

# ====== CONFIGURATION ======
VERIFY_CHANNEL_ID = 1402889712888447037
APPROVAL_CHANNEL_ID = 1402889786712395859

ROLE_ID_TO_GIVE = 1321268883088211981
ROLE_MALE = 1321268883025559689
ROLE_FEMALE = 1321268883025559688
ROLE_LGBT = 1321268883025559687

# --- Age roles (ใส่ ID แล้วตามที่ให้มา) ---
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
    "ذكر", "رجل", "صبي",
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
    "महिला", "औरत", "लड़की", "ladki", "aurat", "عورت", "خातون",
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
    "lgbt", "lgbtq", "lgbtq+", "nonbinary", "non-binary", "nb", "enby",
    "trans", "transgender", "genderqueer", "bigender", "agender", "genderfluid",
    "queer", "other", "prefernottosay", "unspecified", "none",
    "เพศทางเลือก", "ไม่ระบุ", "อื่นๆ", "ไม่บอก", "ไบ", "ทอม", "ดี้", "สาวสอง", "สาวประเภทสอง",
    "非二元", "跨性别", "酷儿", "双性恋",
    "ノンバイナリー", "xジェンダー", "トランス", "クィア", "同性愛", "両性愛",
    "논바이너리", "트랜스", "퀴어", "양성애", "동성애",
    "androgynous", "pangender", "demiboy", "demigirl",
}
MALE_ALIASES   = {_norm_gender(x) for x in _MALE_ALIASES_RAW}
FEMALE_ALIASES = {_norm_gender(x) for x in _FEMALE_ALIASES_RAW}
LGBT_ALIASES   = {_norm_gender(x) for x in _LGBT_ALIASES_RAW}
MALE_PREFIXES = {_norm_gender(x) for x in ["ช", "ชา", "ชาย", "ผู้ช", "เพศช", "m", "ma", "masc", "man", "男", "おとこ", "だん", "남"]}
FEMALE_PREFIXES = {_norm_gender(x) for x in ["ห", "หญ", "หญิ", "หญิง", "ผู้ห", "เพศห", "f", "fe", "fem", "woman", "wo", "女", "おんな", "じょ", "여"]}

def resolve_gender_role_id(text: str) -> int:
    t = _norm_gender(text)
    if t in MALE_ALIASES or any(t.startswith(p) for p in MALE_PREFIXES):
        return ROLE_MALE
    if t in FEMALE_ALIASES or any(t.startswith(p) for p in FEMALE_PREFIXES):
        return ROLE_FEMALE
    if t in LGBT_ALIASES:
        return ROLE_LGBT
    return ROLE_LGBT

def resolve_age_role_id(age_text: str) -> int | None:
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

# ---------- NEW: helpers สำหรับคำสั่งรีเฟรชอายุ ----------
AGE_ROLE_IDS_ALL = [rid for rid in [
    ROLE_0_12, ROLE_13_15, ROLE_16_18, ROLE_19_21, ROLE_22_24,
    ROLE_25_29, ROLE_30_34, ROLE_35_39, ROLE_40_44, ROLE_45_49,
    ROLE_50_54, ROLE_55_59, ROLE_60_64, ROLE_65_UP
] if rid and rid > 0]

def _find_embed_field(embed: discord.Embed, *keys: str) -> str | None:
    """หาค่า field ตามคีย์ (case-insensitive, partial)"""
    keys = [k.lower() for k in keys]
    for f in embed.fields:
        name = (f.name or "").lower()
        if any(k in name for k in keys):
            return f.value
    return None

def _parse_sent_at(s: str) -> datetime | None:
    """parse 'dd/mm/YYYY HH:MM' เป็นเวลาเขต +7"""
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
    """ไล่ประวัติห้องอนุมัติ หา embed ล่าสุดที่ mention user นี้"""
    channel = member.guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        return None
    async for msg in channel.history(limit=500):
        if msg.author == bot.user and msg.embeds and member in msg.mentions:
            return msg.embeds[0]
    return None
# --------------------------------------------------------

# ====== Modal ======
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    name = discord.ui.TextInput(
        label="Nickname / ชื่อเล่น",
        placeholder="ชื่อเล่น • 2–32 ตัว",
        style=discord.TextStyle.short,
        min_length=2, max_length=32, required=True
    )
    age = discord.ui.TextInput(
        label="Age (numbers only) / อายุ (ตัวเลขเท่านั้น)",
        placeholder="เช่น 21 (ตัวเลข 1–3 หลัก)",
        style=discord.TextStyle.short,
        min_length=1, max_length=3, required=True
    )
    gender = discord.ui.TextInput(
        label="Gender / เพศ",
        placeholder="ชาย / หญิง / LGBT",
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
        if not re.fullmatch(r"\d{1,3}", age_str):
            await interaction.followup.send(
                "❌ Invalid age. Use numbers only (1–3 digits).\n"
                "❌ อายุไม่ถูกต้อง กรุณาใส่เป็นตัวเลขล้วน 1–3 หลัก",
                ephemeral=True
            )
            return

        nick = (self.name.value or "").strip()
        if len(nick) < 2 or len(nick) > 32 or any(ch.isdigit() for ch in nick) or any(c in INVALID_CHARS for c in nick):
            await interaction.followup.send(
                "❌ Nickname is invalid.\n"
                "• EN: This nickname will be set as your server name. Letters only, 2–32 chars; no digits/symbols/emoji.\n"
                "• TH: ชื่อเล่นนี้จะถูกตั้งเป็นชื่อในเซิร์ฟเวอร์ ต้องเป็นตัวอักษรล้วน 2–32 ตัว ห้ามตัวเลข/สัญลักษณ์/อีโมจิ",
                ephemeral=True
            )
            return
        if contains_emoji(nick):
            await interaction.followup.send("❌ ชื่อเล่นไม่ถูกต้อง: ห้ามใช้อีโมจิ", ephemeral=True)
            return

        if any(ch.isdigit() for ch in self.gender.value) or any(c in INVALID_CHARS for c in self.gender.value):
            await interaction.followup.send(
                "❌ Gender is invalid. Text only (e.g., Male / Female / LGBT).\n"
                "❌ เพศไม่ถูกต้อง กรุณาพิมพ์เป็นตัวอักษรเท่านั้น (เช่น ชาย / หญิง / LGBT)",
                ephemeral=True
            )
            return
        if contains_emoji(self.gender.value):
            await interaction.followup.send("❌ เพศไม่ถูกต้อง: ห้ามใช้อีโมจิ (พิมพ์ ชาย / หญิง / LGBT)", ephemeral=True)
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
            "✅ ส่งคำขอยืนยันตัวตนแล้ว กรุณารอการอนุมัติจากแอดมิน\n",
            ephemeral=True
        )

# ====== Views (Approve/Reject) ======
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
        gender_role_id = resolve_gender_role_id(self.gender_text)
        gender_role = interaction.guild.get_role(gender_role_id)
        age_role_id = resolve_age_role_id(self.age_text)
        age_role = interaction.guild.get_role(age_role_id) if age_role_id else None

        if member and general_role and gender_role:
            roles_to_add = [general_role, gender_role]
            if age_role:
                roles_to_add.append(age_role)
            try:
                await member.add_roles(*roles_to_add, reason="Verified")
            except discord.Forbidden:
                await interaction.followup.send("❌ Missing permissions to add roles.", ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send("⚠️ Failed to add roles due to HTTP error.", ephemeral=True)
                return

            nick_msg = ""
            if APPEND_FORM_NAME_TO_NICK and self.form_name:
                bot_me = interaction.guild.me or await interaction.guild.fetch_member(bot.user.id)
                try:
                    if not bot_me or not bot_me.guild_permissions.manage_nicknames:
                        nick_msg = "⚠️ บอทไม่มีสิทธิ์ Manage Nicknames"
                    elif member.guild.owner_id == member.id:
                        nick_msg = "⚠️ เปลี่ยนชื่อเจ้าของเซิร์ฟเวอร์ไม่ได้"
                    elif bot_me.top_role <= member.top_role:
                        nick_msg = "⚠️ ลำดับ role ของบอทต่ำกว่าหรือเท่ากับสมาชิก เปลี่ยนชื่อไม่ได้"
                    else:
                        new_nick = build_parenthesized_nick(member, self.form_name)
                        current_nick = member.nick or ""
                        if new_nick and new_nick != current_nick:
                            await member.edit(nick=new_nick, reason="Verification: append form nickname")
                except discord.Forbidden:
                    nick_msg = "⚠️ สิทธิ์ไม่พอในการตั้งชื่อ"
                except discord.HTTPException:
                    nick_msg = "⚠️ ตั้งชื่อไม่สำเร็จ (HTTP error)"

            pending_verifications.discard(self.user.id)

            try:
                await self.user.send(
                    "✅ Your verification has been approved!\n"
                    "✅ คุณได้รับการอนุมัติแล้วและได้รับ Role ที่เกี่ยวข้อง"
                )
            except Exception:
                pass

            if nick_msg:
                await interaction.followup.send(nick_msg, ephemeral=True)
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

# ====== Embed Sender ======
async def send_verification_embed(channel: discord.TextChannel):
    embed = discord.Embed(
        title="📌 Welcome / ยินดีต้อนรับ",
        description="Click the button below to verify your identity.\nกดปุ่มด้านล่างเพื่อยืนยันตัวตนของคุณ",
        color=discord.Color.blue()
    )
    embed.set_image(url="https://i.pinimg.com/originals/da/79/68/da7968c54b12ba7ebf7dfd70dd1faaf2.gif")
    embed.set_footer(text="Verification System / ระบบยืนยันตัวตนโดย Bot")
    await channel.send(embed=embed, view=VerificationView())

# ====== Persistent View Loader ======
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.add_view(VerificationView())

# ====== Admin commands ======
@bot.command(name="verify_embed")
@commands.has_permissions(administrator=True)
async def verify_embed(ctx):
    channel = ctx.guild.get_channel(VERIFY_CHANNEL_ID)
    if not channel:
        await ctx.send("❌ VERIFY_CHANNEL_ID not found.")
        return
    await send_verification_embed(channel)
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

# ---------- NEW: refresh age command ----------
@bot.command(name="refresh_age")
@commands.has_permissions(administrator=True)
async def refresh_age(ctx, member: discord.Member):
    """
    รีเฟรชยศอายุตาม Age / อายุ + 📅 Sent at ใน embed ล่าสุดของผู้ใช้คนนั้น
    วิธีใช้: $refresh_age @user
    """
    embed = await _latest_verification_embed_for(member)
    if not embed:
        await ctx.send("❌ ไม่พบข้อมูลคำขอยืนยันล่าสุดของผู้ใช้นี้ในห้องอนุมัติ")
        return

    age_text = _find_embed_field(embed, "age", "อายุ")
    sent_text = _find_embed_field(embed, "sent at")
    if not age_text or not sent_text:
        await ctx.send("❌ ข้อมูลใน embed ไม่ครบ (Age หรือ Sent at หาย)")
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

    # หา role ใหม่จากอายุปัจจุบัน
    new_age_role_id = resolve_age_role_id(str(new_age))
    new_age_role = ctx.guild.get_role(new_age_role_id) if new_age_role_id else None

    # หายศอายุเดิมทั้งหมดออกก่อน
    to_remove = [r for r in member.roles if r.id in AGE_ROLE_IDS_ALL]
    if to_remove:
        try:
            await member.remove_roles(*to_remove, reason=f"Refresh age → now {new_age}")
        except discord.Forbidden:
            await ctx.send("❌ ไม่มีสิทธิ์ถอดยศอายุของสมาชิกคนนี้")
            return

    # ใส่ยศใหม่ (ถ้ามีการแมป)
    if new_age_role:
        try:
            await member.add_roles(new_age_role, reason=f"Refresh age → now {new_age}")
        except discord.Forbidden:
            await ctx.send(f"⚠️ ถอดยศเดิมแล้ว แต่เพิ่มยศใหม่ไม่สำเร็จ: {new_age_role.name}")
            return

    # สรุปผล
    got = new_age_role.name if new_age_role else "— (ไม่มี role สำหรับช่วงนี้)"
    await ctx.send(f"✅ อัปเดตอายุเป็น **{new_age}** ปี และตั้งยศอายุเป็น **{got}** ให้กับ {member.mention} แล้ว")

# ====== Run bot ======
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
