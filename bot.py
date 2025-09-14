import os
import re
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
ROLE_0_10 = 1402907371696558131
ROLE_10_15 = 1344232758129594379
ROLE_16_20 = 1344232891093090377
ROLE_21_28 = 1344232979647565924
ROLE_29_35 = 1344233048593403955
ROLE_36_UP = 1344233119229939763

# ====== DISCORD BOT SETUP ======
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents)
pending_verifications = set()

INVALID_CHARS = set("=+*/@#$%^&*()<>?|{}[]\"'\\~`")

# ====== Modal ======
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    name = discord.ui.TextInput(label="Name / ชื่อ", required=True)
    age = discord.ui.TextInput(label="Age (numbers only) / อายุ (ตัวเลขเท่านั้น)", required=True)
    gender = discord.ui.TextInput(label="Gender / เพศ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id in pending_verifications:
            await interaction.response.send_message(
                "❗ You already submitted a verification request. Please wait for admin review.\n"
                "❗ คุณได้ส่งคำขอไปแล้ว กรุณารอการอนุมัติจากแอดมิน",
                ephemeral=True
            )
            return

        age_str = self.age.value.strip()
        if not re.fullmatch(r"\d{1,3}", age_str):
            await interaction.response.send_message(
                "❌ Please enter a valid number for age (1–3 digits, no symbols or letters).\n"
                "❌ กรุณากรอกอายุเป็นตัวเลขล้วน ไม่เกิน 3 หลัก และห้ามมีสัญลักษณ์หรือตัวอักษรใดๆ เช่น + / a ข",
                ephemeral=True
            )
            return

        if any(char.isdigit() for char in self.name.value) or any(c in INVALID_CHARS for c in self.name.value):
            await interaction.response.send_message("❌ Name should not contain numbers or symbols.\n❌ ชื่อห้ามมีตัวเลขหรือสัญลักษณ์", ephemeral=True)
            return

        if any(char.isdigit() for char in self.gender.value) or any(c in INVALID_CHARS for c in self.gender.value):
            await interaction.response.send_message("❌ Gender should not contain numbers or symbols.\n❌ เพศห้ามมีตัวเลขหรือสัญลักษณ์", ephemeral=True)
            return

        pending_verifications.add(interaction.user.id)

        embed = discord.Embed(title="📋 Verification Request / คำขอยืนยันตัวตน", color=discord.Color.orange())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Name / ชื่อ", value=self.name.value, inline=False)
        embed.add_field(name="Age / อายุ", value=self.age.value, inline=False)
        embed.add_field(name="Gender / เพศ", value=self.gender.value, inline=False)

        now = datetime.now(timezone(timedelta(hours=7)))
        embed.add_field(name="📅 Sent at", value=now.strftime("%d/%m/%Y %H:%M"), inline=False)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        channel = interaction.guild.get_channel(APPROVAL_CHANNEL_ID)
        if channel:
            view = ApproveRejectView(user=interaction.user, gender_text=self.gender.value, age_text=self.age.value)
            await channel.send(content=interaction.user.mention, embed=embed, view=view)

        await interaction.response.send_message(
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
    def __init__(self, user: discord.User, gender_text: str, age_text: str):
        super().__init__(timeout=None)
        self.user = user
        self.gender_text = gender_text.strip().lower()
        self.age_text = age_text.strip()

    @discord.ui.button(label="✅ Approve / อนุมัติ", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1) ACK ไว้ก่อนกัน timeout
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        # 2) หา member (ถ้า cache ไม่เจอ ลอง fetch)
        member = interaction.guild.get_member(self.user.id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(self.user.id)
            except Exception:
                await interaction.followup.send("❌ Member not found in guild.", ephemeral=True)
                return

        general_role = interaction.guild.get_role(ROLE_ID_TO_GIVE)

        male = {"male", "man", "m", "boy", "ชาย", "เพศชาย", "ผู้ชาย", "ช"}
        female = {"female", "f", "woman", "girl", "หญิง", "เพศหญิง", "ผู้หญิง", "ญ"}

        gender_role_id = ROLE_LGBT
        if self.gender_text in male:
            gender_role_id = ROLE_MALE
        elif self.gender_text in female:
            gender_role_id = ROLE_FEMALE

        gender_role = interaction.guild.get_role(gender_role_id)

        try:
            age = int(self.age_text)
        except ValueError:
            age = -1

        if 0 <= age <= 10:
            age_role_id = ROLE_0_10
        elif 10 < age <= 15:
            age_role_id = ROLE_10_15
        elif 16 <= age <= 20:
            age_role_id = ROLE_16_20
        elif 21 <= age <= 28:
            age_role_id = ROLE_21_28
        elif 29 <= age <= 35:
            age_role_id = ROLE_29_35
        elif age >= 36:
            age_role_id = ROLE_36_UP
        else:
            age_role_id = None

        age_role = interaction.guild.get_role(age_role_id) if age_role_id else None

        # 3) ให้ roles ทีเดียว ลดเวลา
        if member and general_role and gender_role:
            roles_to_add = [general_role, gender_role]
            if age_role:
                roles_to_add.append(age_role)
            try:
                await member.add_roles(*roles_to_add, reason="Verified")
            except discord.Forbidden:
                await interaction.followup.send("❌ Missing permissions to add roles.", ephemeral=True)
                return

            pending_verifications.discard(self.user.id)

            # DM ผู้ใช้ (ไม่ให้ fail ทำล้ม flow)
            try:
                await self.user.send("✅ Your verification has been approved!\n✅ คุณได้รับการอนุมัติแล้วและได้รับ Role ที่เกี่ยวข้อง")
            except Exception:
                pass

            # 4) ตอบกลับผ่าน followup (เพราะเรา defer ไปแล้ว)
            await interaction.followup.send("✅ Approved and roles assigned.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Member or role not found.", ephemeral=True)

        # 5) ปิดปุ่ม และแก้ label ที่ปุ่มที่กด
        for child in self.children:
            child.disabled = True
            if getattr(child, "custom_id", None) == "approve_button":
                child.label = "✅ You approved this. / คุณอนุมัติคำขอนี้แล้ว"

        # 6) แก้ view บนข้อความเดิม
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
            await self.user.send("❌ Your verification was rejected. Please contact admin.\n❌ การยืนยันตัวตนของคุณไม่ผ่าน กรุณาติดต่อแอดมิน")
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
    # ดึงข้อความล่าสุดในห้อง APPROVAL_CHANNEL_ID ที่เกี่ยวกับ user นี้
    channel = ctx.guild.get_channel(APPROVAL_CHANNEL_ID)
    if not channel:
        await ctx.send("❌ APPROVAL_CHANNEL_ID not found.")
        return

    async for message in channel.history(limit=200):
        if message.author == bot.user and message.embeds and message.mentions:
            if member in message.mentions:
                embed = message.embeds[0]
                await ctx.send(embed=embed)
                return

    await ctx.send("❌ No verification info found for this user.")

# ====== Run bot ======
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
