import os
import discord
from discord.ext import commands

# ====== CONFIGURATION ======
VERIFY_CHANNEL_ID = 1402889712888447037  # ห้องที่ใช้โพสต์ Embed ปุ่มยืนยัน
APPROVAL_CHANNEL_ID = 1402889786712395859  # ห้องรอแอดมินอนุมัติ

ROLE_ID_TO_GIVE = 1321268883088211981  # Role หลัก
ROLE_MALE = 1321268883025559689
ROLE_FEMALE = 1321268883025559688
ROLE_LGBT = 1321268883025559687
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

bot = commands.Bot(command_prefix="!", intents=intents)

# ====== Modal ======
class VerificationForm(discord.ui.Modal, title="Verify Identity / ยืนยันตัวตน"):
    name = discord.ui.TextInput(label="Name / ชื่อ", required=True)
    age = discord.ui.TextInput(label="Age (numbers only) / อายุ (ตัวเลขเท่านั้น)", required=True)
    gender = discord.ui.TextInput(label="Gender / เพศ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            age = int(self.age.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number for age, such as 18 or 25.\n"
                "❌ กรุณากรอกอายุเป็นตัวเลข เช่น 18 หรือ 25",
                ephemeral=True
            )
            return

        embed = discord.Embed(title="Verification Request / คำขอยืนยันตัวตน", color=discord.Color.orange())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Name / ชื่อ", value=self.name.value, inline=False)
        embed.add_field(name="Age / อายุ", value=self.age.value, inline=False)
        embed.add_field(name="Gender / เพศ", value=self.gender.value, inline=False)
        embed.set_footer(text=f"From: {interaction.user} | ID: {interaction.user.id}")

        channel = interaction.guild.get_channel(APPROVAL_CHANNEL_ID)
        if channel:
            view = ApproveRejectView(user=interaction.user, gender_text=self.gender.value, age_text=self.age.value)
            await channel.send(embed=embed, view=view)

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

    @discord.ui.button(label="✅ Approve / อนุมัติ", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.user.id)
        general_role = interaction.guild.get_role(ROLE_ID_TO_GIVE)

        male = {"male", "man", "boy", "ชาย", "เพศชาย", "ผู้ชาย"}
        female = {"female", "woman", "girl", "หญิง", "เพศหญิง", "ผู้หญิง"}

        gender_role_id = ROLE_LGBT
        if self.gender_text in male:
            gender_role_id = ROLE_MALE
        elif self.gender_text in female:
            gender_role_id = ROLE_FEMALE

        gender_role = interaction.guild.get_role(gender_role_id)

        try:
            age = int("".join(filter(str.isdigit, self.age_text)))
        except ValueError:
            age = -1

        if 10 <= age <= 15:
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

        if member and general_role and gender_role:
            await member.add_roles(general_role, reason="Verified")
            await member.add_roles(gender_role, reason="Gender")
            if age_role:
                await member.add_roles(age_role, reason="Age")

            role_msg = f"✅ You have been verified and received roles:\n- {general_role.name}\n- {gender_role.name}"
            if age_role:
                role_msg += f"\n- {age_role.name}"
            role_msg += "\n\n✅ คุณได้รับการยืนยันตัวตนและได้รับ Role:\n"
            role_msg += f"- {general_role.name}\n- {gender_role.name}"
            if age_role:
                role_msg += f"\n- {age_role.name}"

            try:
                await self.user.send(role_msg)
            except:
                pass

            await interaction.response.send_message("✅ Approved and roles assigned.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Member or role not found.", ephemeral=True)

        self.disable_all_items()
        await interaction.followup.edit_message(message_id=interaction.message.id, view=self)

    @discord.ui.button(label="❌ Reject / ปฏิเสธ", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.user.send(
                "❌ Your verification was rejected. Please contact admin.\n"
                "❌ การยืนยันตัวตนของคุณไม่ผ่าน กรุณาติดต่อแอดมิน"
            )
        except:
            pass
        await interaction.response.send_message("❌ Rejected.", ephemeral=True)
        self.disable_all_items()
        await interaction.followup.edit_message(message_id=interaction.message.id, view=self)

# ====== Embed Sender ======
async def send_verification_embed(channel: discord.TextChannel):
    embed = discord.Embed(
        title="📌 Welcome / ยินดีต้อนรับ",
        description="Click the button below to verify your identity.\nกดปุ่มด้านล่างเพื่อยืนยันตัวตนของคุณ",
        color=discord.Color.blue()
    )
    embed.set_image(url="https://i.imgur.com/B4w7hql.jpeg")
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

# ====== Run bot ======
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
