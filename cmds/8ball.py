# 8ball.py
import discord
from discord.ext import commands
from discord import app_commands
import random

RESPONSES = [
    "🎱 It is certain.",
    "🎱 Without a doubt.",
    "🎱 Yes – definitely.",
    "🎱 You may rely on it.",
    "🎱 Most likely.",
    "🎱 Outlook good.",
    "🎱 Yes.",
    "🎱 Signs point to yes.",
    "🎱 Reply hazy, try again.",
    "🎱 Ask again later.",
    "🎱 Better not tell you now.",
    "🎱 Cannot predict now.",
    "🎱 Concentrate and ask again.",
    "🎱 Don’t count on it.",
    "🎱 My reply is no.",
    "🎱 My sources say no.",
    "🎱 Outlook not so good.",
    "🎱 Very doubtful."
]

class Magic8Ball(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question!")
    @app_commands.describe(question="Your yes/no question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        response = random.choice(RESPONSES)
        embed = discord.Embed(
            title="🎱 The Magic 8-Ball says...",
            description=f"**Q:** {question}\n**A:** {response}",
            color=discord.Color.from_str("#d69238")
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    print("✅ Loaded 8Ball Cog")
    await bot.add_cog(Magic8Ball(bot))
