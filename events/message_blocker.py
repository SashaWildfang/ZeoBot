import discord
from discord.ext import commands

# staff roles that are allowed to bypass the lock
STAFF_ROLE_IDS = {
    1358472532222808126, # Mod
    1358472588430676018, # Sr Mod
    1358472511133585564, # Admin
    1358472635234779207, # Sr Admin
    1416866395366359193, # Bad Dragon
    1358473248534167663  # Owner
}

class MessageBlocker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and system messages
        if message.author.bot or not message.guild:
            return

        # 1. Skip check for Staff/Admins
        if any(role.id in STAFF_ROLE_IDS for role in message.author.roles) or message.author.guild_permissions.administrator:
            return

        # 2. Try to get the ChannelLock cog to check if the channel is locked
        cog = self.bot.get_cog("ChannelLock")
        if not cog:
            return

        # 3. Check if 'locked_channels' attribute exists and if the current channel is in it
        locked_list = getattr(cog, "locked_channels", [])
        
        if message.channel.id in locked_list:
            try:
                # Delete the message
                await message.delete()
                
                # Try to DM the user a warning
                try:
                    embed = discord.Embed(
                        description=f"🚫 The channel **#{message.channel.name}** is currently under lockdown. Please wait for it to reopen.",
                        color=discord.Color.red()
                    )
                    await message.author.send(embed=embed)
                except discord.Forbidden:
                    pass # User has DMs closed
            except discord.HTTPException:
                pass # Bot might lack manage_messages permission

async def setup(bot):
    await bot.add_cog(MessageBlocker(bot))