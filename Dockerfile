# ✅ Base image
FROM python:3.11-slim

# ✅ Set work directory
WORKDIR /app

# ✅ Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy source code
COPY . .

# ✅ Set environment variables (optional)
# ENV DISCORD_BOT_TOKEN=your_token_here  ← แนะนำให้ใช้ผ่าน Railway หรือ .env แทน

# ✅ Run bot
CMD ["python", "bot.py"]
