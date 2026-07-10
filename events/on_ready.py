import discord
from discord.ext import commands, tasks
from datetime import datetime
import asyncio
import platform
import psutil 
from collections import defaultdict

# ===============================
# ⚙️ Configuration
# ===============================
STATUS_ROTATION = [
    "Start your profile today /startprofile",
    "Check your stats /stats",
    "Hit the jackpot /slots spin",
    "Need help? Ask a staff member",
    "Check out patreon perks /patreon",
    "Spend your crabs in /store"
]

LOG_CHANNEL_ID = 1360344042705256660

# ===============================
# 🔘 View for Startup Button
# ===============================
class StartupView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="View Loaded Commands", 
        style=discord.ButtonStyle.grey, 
        emoji="📜",
        custom_id="zeo_startup_view_cmds" 
    )
    async def view_commands(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Get and Categorize Standard Commands
        prefix_groups = defaultdict(list)
        for c in sorted(self.bot.commands, key=lambda x: x.name):
            first_letter = c.name[0].upper()
            prefix_groups[first_letter].append(f"`{c.name}`")
        
        # 2. Get and Categorize Slash Commands
        slash_groups = defaultdict(list)
        for c in sorted(self.bot.tree.get_commands(), key=lambda x: x.name):
            first_letter = c.name[0].upper()
            slash_groups[first_letter].append(f"`/{c.name}`")
        
        embed = discord.Embed(
            title="🛠️ Loaded Commands List",
            description="Categorized alphabetically for easy navigation.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        def add_categorized_fields(title, groups):
            if not groups:
                embed.add_field(name=title, value="None", inline=False)
                return

            # Sort the group letters (A, B, C...)
            sorted_letters = sorted(groups.keys())
            
            current_chunk = ""
            for letter in sorted_letters:
                line = f"**{letter}** — {', '.join(groups[letter])}\n"
                
                # Check Discord's 1024 character limit per field
                if len(current_chunk) + len(line) > 1000:
                    embed.add_field(name=title, value=current_chunk, inline=False)
                    current_chunk = line
                else:
                    current_chunk += line

            if current_chunk:
                embed.add_field(name=title, value=current_chunk, inline=False)

        # Add fields for Prefix and Slash commands
        add_categorized_fields(f"Standard Commands ({len(self.bot.commands)})", prefix_groups)
        add_categorized_fields(f"Slash Commands ({len(self.bot.tree.get_commands())})", slash_groups)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===============================
# 🎓 OnReady Cog
# ===============================
class OnReady(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.utcnow()
        self.status_index = 0
        self.rotate_status.start()

    @commands.Cog.listener()
    async def on_ready(self):
        guilds = len(self.bot.guilds)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        ping = round(self.bot.latency * 1000, 2)
        
        total_prefix_cmds = len(self.bot.commands)
        total_slash_cmds = len(self.bot.tree.get_commands())
        total_cmds = total_prefix_cmds + total_slash_cmds

        print("\n" + "=" * 50)
        print(f"🤖 Zeo Bot is now online as {self.bot.user}!")
        print(f"📂 Commands Loaded: {total_cmds} ({total_slash_cmds} Slash, {total_prefix_cmds} Prefix)")
        print(f"📡 WebSocket Latency: {ping}ms")
        print("=" * 50 + "\n")

        embed = discord.Embed(
            title="✅ Zeo Bot Online",
            description=(
                "The bot has successfully connected to Discord.\n"
                "Currently logged in as **Sasha**"
            ),
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="🆔 Bot ID", value=f"`{self.bot.user.id}`", inline=True)
        embed.add_field(name="📡 Ping", value=f"`{ping} ms`", inline=True)
        embed.add_field(name="📂 Total Commands", value=f"`{total_cmds}`", inline=True)
        embed.add_field(name="🌐 Guilds", value=f"`{guilds}`", inline=True)
        embed.add_field(name="👥 Users", value=f"`{total_members:,}`", inline=True)
        embed.add_field(name="💻 System", value=f"`{platform.system()}`", inline=True)

        try:
            mem = psutil.virtual_memory()
            embed.add_field(name="🧠 Memory", value=f"`{mem.percent}% used`", inline=True)
        except Exception:
            pass

        embed.set_footer(text="Zeo Bot Startup Log", icon_url=self.bot.user.display_avatar.url)

        await asyncio.sleep(2)
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed, view=StartupView(self.bot))

    @tasks.loop(seconds=60)
    async def rotate_status(self):
        if not self.bot.is_ready():
            return

        status = STATUS_ROTATION[self.status_index % len(STATUS_ROTATION)]
        self.status_index += 1
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=status)
        )

    @rotate_status.before_loop
    async def before_rotate_status(self):
        await self.bot.wait_until_ready()

    @commands.command(name="uptime", help="Check how long the bot has been running.")
    async def uptime(self, ctx):
        delta = datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        await ctx.reply(f"🕒 **Uptime:** {hours}h {minutes}m {seconds}s")

    def cog_unload(self):
        self.rotate_status.cancel()

async def setup(bot):
    await bot.add_cog(OnReady(bot))
    print("✅ Loaded OnReady (Enhanced Startup)")