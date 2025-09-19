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

# --- Consolidated age roles (ใส่ ID เอง; ถ้า =0 จะไม่ให้ยศอายุ / ไม่มี fallback) ---
ROLE_0_12    = 0
ROLE_13_15   = 0
ROLE_16_17   = 0
ROLE_18_20   = 0
ROLE_21_24   = 0
ROLE_25_34   = 0
ROLE_35_44   = 0
ROLE_45_54   = 0
ROLE_55_64   = 0
ROLE_65_UP   = 0

# Toggle: ให้บอทเติม (ชื่อเล่น) ต่อท้ายชื่อในดิสเวล่าอนุมัติ
APPEND_FORM_NAME_TO_NICK = True

# ====== DISCORD BOT SETUP ======
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents)
pending_verifications = set()

INVALID_CHARS = set("=+*/@#$%^&*()<>?|{}[]\"'\\~`")

# ====== Gender Normalizer & Aliases (Multilingual) ======
def _norm_gender(s: str) -> str:
    """Lowercase + strip + remove common separators to make matching forgiving."""
    s = (s or "").strip().lower()
    s = re.sub(r'[\s\.\-_\/\\]+', '', s)
    return s

# Male aliases
_MALE_ALIASES_RAW = {
    # Thai
    "ช", "ชา", "ชาย", "ผู้ชาย", "เพศชาย", "ผช", "ชายแท้", "หนุ่ม",
    # English
    "male", "man", "boy", "m", "masculine", "he", "him",
    # Chinese
    "男", "男性", "男生", "男人",
    # Japanese
    "男", "男性", "おとこ", "だんせい",
    # Korean
    "남", "남자", "남성",
    # Vietnamese
    "nam", "đàn ông", "dan ong", "con trai", "nam giới", "namgioi",
    # Indonesian / Malay
    "pria", "laki", "laki-laki", "lelaki", "cowok",
    # Filipino
    "lalaki",
    # Hindi / Urdu
    "पुरुष", "aadmi", "ladka", "पुरूष", "mard", "आदमी", "مرد",
    # Arabic
    "ذكر", "رجل", "صبي",
    # Turkish
    "erkek", "bay",
    # Russian / Ukrainian
    "мужчина", "парень", "мальчик", "чоловік", "хлопець",
    # European
    "hombre", "masculino", "chico", "varon", "varón",
    "homem", "masculino", "rapaz",
    "homme", "masculin", "garçon",
    "mann", "männlich", "junge",
    "uomo", "maschio", "ragazzo",
    "mezczyzna", "mężczyzna", "chlopak", "chłopak",
    "muž", "chlapec",
    "andras", "άνδρας", "arseniko", "αρσενικό", "agori", "αγόρι",
    # SE Asia more
    "ຜູ້ຊາຍ",
    "ប្រុស", "បុរស",
    "ယောက်ျား", "အမျိုးသား",
}

# Female aliases
_FEMALE_ALIASES_RAW = {
    # Thai
    "ห", "หญ", "หญิ", "หญิง", "ผู้หญิง", "เพศหญิง", "ผญ", "สาว", "ญ",
    # English
    "female", "woman", "girl", "f", "feminine", "she", "her",
    # Chinese
    "女", "女性", "女生", "女人",
    # Japanese
    "女", "女性", "おんな", "じょせい",
    # Korean
    "여", "여자", "여성",
    # Vietnamese
    "nữ", "phụ nữ", "con gái",
    # Indonesian / Malay
    "wanita", "perempuan", "cewek",
    # Filipino
    "babae", "dalaga",
    # Hindi / Urdu
    "महिला", "औरत", "लड़की", "ladki", "aurat", "عورت", "خاتون",
    # Arabic
    "أنثى", "امرأة", "بنت", "فتاة",
    # Turkish
    "kadın", "bayan", "kız",
    # Russian / Ukrainian
    "женщина", "девушка", "девочка", "жінка", "дівчина",
    # European
    "mujer", "femenino", "chica",
    "mulher", "feminina", "menina",
    "femme", "féminin", "fille",
    "frau", "weiblich", "mädchen",
    "donna", "femmina", "ragazza",
    "kobieta", "dziewczyna", "zenska", "żeńska",
    "žena", "dívka",
    "gynaika", "γυναίκα", "thyliko", "θηλυκό", "koritsi", "κορίτσι",
    # SE Asia more
    "ຜູ້ຍິງ",
    "ស្រី", "នារី",
    "မိန်းမ", "အမျိုးသမီး",
}

# LGBT / non-binary / unspecified → map to LGBT role
_LGBT_ALIASES_RAW = {
    # English & common
    "lgbt", "lgbtq", "lgbtq+", "nonbinary", "non-binary", "nb", "enby",
    "trans", "transgender", "genderqueer", "bigender", "agender", "genderfluid",
    "queer", "other", "prefernottosay", "unspecified", "none",
    # Thai
    "เพศทางเลือก", "ไม่ระบุ", "อื่นๆ", "ไม่บอก", "ไบ", "ทอม", "ดี้", "สาวสอง", "สาวประเภทสอง",
    # Chinese / JP / KR (selected)
    "非二元", "跨性别", "酷儿", "双性恋",
    "ノンバイナリー", "xジェンダー", "トランス", "クィア", "同性愛", "両性愛",
    "논바이너리", "트랜스", "퀴어", "양성애", "동성애",
    # Others
    "androgynous", "pangender", "demiboy", "demigirl",
}

MALE_ALIASES   = {_norm_gender(x) for x in _MALE_ALIASES_RAW}
FEMALE_ALIASES = {_norm_gender(x) for x in _FEMALE_ALIASES_RAW}
LGBT_ALIASES   = {_norm_gender(x) for x in _LGBT_ALIASES_RAW}

# Accept prefixes (short-hand startswith)
MALE_PREFIXES = {_norm_gender(x) for x in [
    "ช", "ชา", "ชาย", "ผู้ช", "เพศช",
    "m", "ma", "masc", "man",
    "男", "おとこ", "だん", "남",
]}
FEMALE_PREFIXES = {_norm_gender(x) for x in [
    "ห", "หญ", "หญิ", "หญิง", "ผู้ห", "เพศห",
    "f", "fe", "fem", "woman", "wo",
    "女", "おんな", "じょ", "여",
]}

def resolve_gender_role_id(text: str) -> int:
    t = _norm_gender(text)
    if t in MALE_ALIASES or any(t.startswith(p) for p in MALE_PREFIXES):
        return ROLE_MALE
    if t in FEMALE_ALIASES or any(t.startswith(p) for p in FEMALE_PREFIXES):
        return ROLE_FEMALE
    if t in LGBT_ALIASES:
        return ROLE_LGBT
    # Fallback: keep inclusive by default
    return ROLE_LGBT

def resolve_age_role_id(age_text: str) -> int | None:
    """
    จับคู่ช่วงอายุแบบรวบ (ไม่มี fallback):
    - ถ้าช่วงที่ตรงกันมีการตั้ง Role ID (>0) จะคืนค่านั้น
    - ถ้ายังไม่ได้ตั้ง (==0) จะคืน None เพื่อไม่ให้ยศอายุ
    """
    try:
        age = int((age_text or "").strip())
    except ValueError:
        return None

    slots = [
        ((0, 12), ROLE_0_12),
        ((13, 15), ROLE_13_15),
        ((16, 17), ROLE_16_17),
        ((18, 20), ROLE_18_20),
        ((21, 24), ROLE_21_24),
        ((25, 34), ROLE_25_34),
        ((35, 44), ROLE_35_44),
        ((45, 54), ROLE_45_54),
        ((55, 64), ROLE_55_64),
        ((65, 200), ROLE_65_UP),  # 65+
    ]

    for (lo, hi), rid in slots:
        if lo <= age <= hi and rid > 0:
            return rid
    return None

# ====== Helpers ======
async def build_avatar_attachment(user: discord.User):
    """
    Download user's avatar and return as a Discord File attachment, preferring WEBP 512, falling back to PNG 512.
    Returns (file, filename) or (None, None) on failure.
    """
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
    """Create a shallow copy of important visual bits of an embed (title, desc, color, fields, image)."""
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
    """
    คืนค่านิคเนมรูปแบบ: <base> (<form_name>)
    - ลบ (...) ท้ายชื่อเดิมถ้ามี เพื่อไม่ซ้ำซ้อน
    - จำกัดความยาว 32 ตัวอักษรตามข้อกำหนด Discord
    """
    base = (member.nick or member.name or "").strip()
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

# ====== Modal ======
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    # เปลี่ยน label ตามที่ขอ: Nickname / ชื่อเล่น
    name = discord.ui.TextInput(label="Nickname / ชื่อเล่น", required=True)
    age = discord.ui.TextInput(label="Age (numbers only) / อายุ (ตัวเลขเท่านั้น)", required=True)
    gender = discord.ui.TextInput(label="Gender / เพศ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        # ACK ทันที กัน timeout
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        # เช็คซ้ำ
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
                "❌ Please enter a valid number for age (1–3 digits, no symbols or letters).\n"
                "❌ กรุณากรอกอายุเป็นตัวเลขล้วน ไม่เกิน 3 หลัก และห้ามมีสัญลักษณ์หรือตัวอักษร เช่น + / a ข",
                ephemeral=True
            )
            return

        if any(ch.isdigit() for ch in self.name.value) or any(c in INVALID_CHARS for c in self.name.value):
            await interaction.followup.send(
                "❌ Nickname should not contain numbers or symbols.\n❌ ชื่อเล่นห้ามมีตัวเลขหรือสัญลักษณ์",
                ephemeral=True
            )
            return

        if any(ch.isdigit() for ch in self.gender.value) or any(c in INVALID_CHARS for c in self.gender.value):
            await interaction.followup.send(
                "❌ Gender should not contain numbers or symbols.\n❌ เพศห้ามมีตัวเลขหรือสัญลักษณ์",
                ephemeral=True
            )
            return

        pending_verifications.add(interaction.user.id)

        embed = discord.Embed(title="📋 Verification Request / คำขอยืนยันตัวตน", color=discord.Color.orange())
        embed.set_thumbnail(url="attachment://avatar_placeholder.png")  # จะถูกแก้เป็นชื่อจริงตอนแนบไฟล์
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
                form_name=self.name.value,  # ส่งชื่อเล่นไปใช้ตอนอนุมัติ
            )

            # --- แนบ avatar เป็นไฟล์เพื่อกันภาพหาย ---
            avatar_file, filename = await build_avatar_attachment(interaction.user)
            if avatar_file and filename:
                embed.set_thumbnail(url=f"attachment://{filename}")
                await channel.send(
                    content=interaction.user.mention,
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
                    file=avatar_file,
                )
            else:
                # fallback (อาจหายเมื่อเปลี่ยนรูป)
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await channel.send(
                    content=interaction.user.mention,
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
                )

        await interaction.followup.send(
            "✅ Your verification request has been submitted. Please wait for admin approval.\n"
            "✅ ส่งคำขอยืนยันตัวตนแล้ว กรุณารอการอนุมัติจากแอดมิน",
            ephemeral=True
        )

# ====== View: Button to open Modal ======
class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Identity / ยืนยันตัวตน", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerificationForm())

# ====== View: Approve or Reject ======
class ApproveRejectView(discord.ui.View):
    def __init__(self, user: discord.User, gender_text: str, age_text: str, form_name: str):
        super().__init__(timeout=None)
        self.user = user
        self.gender_text = (gender_text or "").strip()
        self.age_text = (age_text or "").strip()
        self.form_name = (form_name or "").strip()

    @discord.ui.button(label="✅ Approve / อนุมัติ", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1) ACK กัน timeout
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        # 2) หา member
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

        # 3) ให้ roles ทีเดียว
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

            # --- NEW: อัปเดตนิคเนมให้มี (ชื่อเล่น) ---
            if APPEND_FORM_NAME_TO_NICK:
                try:
                    new_nick = build_parenthesized_nick(member, self.form_name)
                    if new_nick and new_nick != (member.nick or member.name):
                        await member.edit(nick=new_nick, reason="Verification: append form nickname")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

            pending_verifications.discard(self.user.id)

            # DM ผู้ใช้ (ignore errors)
            try:
                await self.user.send(
                    "✅ Your verification has been approved!\n"
                    "✅ คุณได้รับการอนุมัติแล้วและได้รับ Role ที่เกี่ยวข้อง"
                )
            except Exception:
                pass

            await interaction.followup.send("✅ Approved and roles assigned.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Member or role not found.", ephemeral=True)

        # 4) ปิดปุ่ม และแก้ label
        for child in self.children:
            child.disabled = True
            if getattr(child, "custom_id", None) == "approve_button":
                child.label = "✅ You approved this. / คุณอนุมัติคำขอนี้แล้ว"

        # 5) อัปเดต view
        try:
            await interaction.message.edit(view=self)
        except discord.NotFound:
            pass

    @discord.ui.button(label="❌ Reject / ปฏิเสธ", style=discord.ButtonStyle.danger, custom_id="reject_button")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        pending_verifications.discard(self.user.id)

        try:
            await self.user.send(
                "❌ Your verification was rejected. Please contact admin.\n"
                "❌ การยืนยันตัวตนของคุณไม่ผ่าน กรุณาติดต่อแอดมิน"
            )
        except Exception:
            pass

        await interaction.followup.send("❌ Rejected.", ephemeral=True)

        for child in self.children:
            child.disabled = True
            if getattr(child, "custom_id", None) == "reject_button":
                child.label = "❌ You rejected this. / คุณปฏิเสธคำขอนี้"

        try:
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
    # Register persistent Verify button
    bot.add_view(VerificationView())

# ====== Admin command to resend embed ======
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
    """
    ดึงคำขอยืนยันล่าสุดของ user จากห้อง APPROVAL
    - ถ้าโพสต์ต้นฉบับมีไฟล์ avatar แนบอยู่ จะดึงไฟล์นั้นมา re-attach ใหม่
      เพื่อให้ thumbnail แสดงผลได้ (attachment://...) ในข้อความนี้ด้วย
    """
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

# ====== Run bot ======
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
