import discord
from discord.ext import commands

# ===============================
# ⚙️ Configuration
# ===============================
TARGET_USER_ID = 164577223162986498
BOT_USER_ID = 1360027676881981531

class ZeoDaddy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # 1. Ignore if the message is from a bot
        if message.author.bot:
            return

        # 2. Check if the specific user (Sasha) sent the message
        if message.author.id == TARGET_USER_ID:
            
            # 3. Clean the message to check for the phrase
            content = message.content.strip()
            
            # 4. Check for the specific phrase and if it mentions/targets the bot
            # We use lower() to make it case-insensitive
            if "whose your daddy" in content.lower():
                # We check if the bot is mentioned or if it's just the phrase in chat
                if str(BOT_USER_ID) in content or self.bot.user.mentioned_in(message):
                    
                    # 5. Reply directly to the user
                    try:
                        await message.reply("You are, Sasha Wildfang. 🫡")
                    except discord.HTTPException as e:
                        print(f"[Zeo] Failed to reply: {e}")

async def setup(bot):
    await bot.add_cog(ZeoDaddy(bot))