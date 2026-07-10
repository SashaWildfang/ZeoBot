import discord
from discord.ext import commands
from discord import app_commands

# Define roles considered as staff


# Designated Channel and Category IDs
BOT_COMMANDS_CHANNEL_ID = 1358485820100706314 # Bot Commands / Wordle Channel
CASINO_CHANNEL_ID = 1508896560266612756       # Dedicated Casino / Gambling Channel
DATING_CATEGORY_IDS = [1358487125661585658, 1358487031117906033]

class EnforceCommandChannel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Bind the check to the command tree when the cog loads
        self.bot.tree.interaction_check = self.global_channel_check

    async def global_channel_check(self, interaction: discord.Interaction) -> bool:
        # Only check slash commands
        if interaction.type != discord.InteractionType.application_command:
            return True

        # Skip if it's a DM or outside a guild
        if not interaction.guild or not interaction.channel:
            return True

        command_name = interaction.data.get("name")
        
        # 1. Check for Dating specific commands (Category restriction)
        dating_commands = ["randomprofile", "filter", "findmatch", "startprofile"]
        if command_name in dating_commands:
            # Check if the channel is within one of the allowed categories
            if getattr(interaction.channel, "category_id", None) not in DATING_CATEGORY_IDS:
                msg = "❌ You can only use this command within the designated 18+ Categories."
                await self.send_error_message(interaction, msg)
                return False  # Cancels the command
            return True 

        # 2. Check for the Casino/Gambling commands (Specific channel restriction)
        gambling_commands = ["slots", "scratchoff", "blackjack", "crash", "roulette", "casinostats"]
        if command_name in gambling_commands:
            if interaction.channel.id != CASINO_CHANNEL_ID:
                msg = f"❌ You can only use casino commands in <#{CASINO_CHANNEL_ID}>."
                await self.send_error_message(interaction, msg)
                return False  # Cancels the command
            return True

        # 3. Check for Wordle (Specific channel restriction)
        if command_name == "wordle":
            if interaction.channel.id != BOT_COMMANDS_CHANNEL_ID:
                msg = f"❌ You can only play Wordle in <#{BOT_COMMANDS_CHANNEL_ID}>."
                await self.send_error_message(interaction, msg)
                return False  # Cancels the command
            return True

        # 4. Allow all other commands to be run anywhere
        return True

    async def send_error_message(self, interaction: discord.Interaction, msg: str):
        """Helper to handle sending the ephemeral error message."""
        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(EnforceCommandChannel(bot))