import discord
from discord.ext import commands

class MuteManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.MUTED_ROLE_ID = 1360956830263541950

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Listens for any reaction added to a message.
        Using the 'raw' event ensures it works even for messages not in the bot's cache.
        """
        # Ignore reactions in DMs
        if not payload.guild_id or not payload.member:
            return

        # Ignore bot reactions to save resources
        if payload.member.bot:
            return

        # Check if the member has the muted role
        has_muted_role = any(role.id == self.MUTED_ROLE_ID for role in payload.member.roles)
        
        if has_muted_role:
            try:
                # Fetch the channel and the message
                channel = self.bot.get_channel(payload.channel_id)
                if not channel:
                    channel = await self.bot.fetch_channel(payload.channel_id)
                
                message = await channel.fetch_message(payload.message_id)
                
                # Remove the user's reaction
                await message.remove_reaction(payload.emoji, payload.member)
                
            except discord.Forbidden:
                print(f"Permission error: Cannot remove reaction in {channel.name}. Check bot permissions (Manage Messages).")
            except discord.HTTPException as e:
                print(f"Failed to remove reaction: {e}")

async def setup(bot):
    await bot.add_cog(MuteManager(bot))