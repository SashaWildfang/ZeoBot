import discord
from discord.ext import commands
from discord import app_commands, Interaction
from discord.ui import View, button

class HelpMenuButtons(View):
    def __init__(self):
        # Setting timeout to None allows buttons to stay responsive across bot restarts
        super().__init__(timeout=None)

    def get_main_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Command Help Directory",
            description=(
                "Click a button below to view the commands for that category.\n\n"
                "If you have any questions or need further assistance, please direct it to a staff member!"
            ),
            color=discord.Color.blurple()
        )
        return embed

    @button(label="Main Menu", style=discord.ButtonStyle.secondary, custom_id="help_btn_main", row=0)
    async def main_menu(self, interaction: Interaction, btn):
        await interaction.response.edit_message(embed=self.get_main_embed())

    @button(label="Fun (3)", style=discord.ButtonStyle.primary, custom_id="help_btn_fun", row=0)
    async def fun_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Fun Commands", color=discord.Color.green())
        embed.description = (
            "`/8ball [question]` — Ask the Magic 8-Ball a question.\n"
            "`/avatar [user/ID]` — View a user's profile picture.\n"
            "`/dice` — Roll a standard, 6-sided die.\n"
            "`/dice [sides]` — Roll a custom, multi-sided die (minimum 2 sides)."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="AutoMod (1)", style=discord.ButtonStyle.primary, custom_id="help_btn_automod", row=0)
    async def automod_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="AutoMod Commands", color=discord.Color.red())
        embed.description = (
            "`/automod list` — View the local filter list of blacklisted and prohibited words."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="Interactions (3)", style=discord.ButtonStyle.primary, custom_id="help_btn_interaction", row=0)
    async def interaction_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Interaction Commands", color=discord.Color.teal())
        embed.description = (
            "`/boop [user]` — Give another user a playful boop!\n"
            "`/hug [user]` — Send a hug to a user.\n"
            "`/settings` — Check your privacy settings."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="Bot Info (4)", style=discord.ButtonStyle.primary, custom_id="help_btn_bot", row=1)
    async def bot_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Bot & Server Commands", color=discord.Color.blue())
        embed.description = (
            "`/botinfo` — Get detailed information about Zeo.\n"
            "`/serverinfo` — Get information about the Server.\n"
            "`/staff` — View who is currently serving on the staff team.\n"
            "`/uptime` — View how long the bot process has been running."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="Economy (7)", style=discord.ButtonStyle.primary, custom_id="help_btn_economy", row=1)
    async def economy_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Economy Commands", color=discord.Color.gold())
        embed.description = (
            "`/daily` — Claim your daily Leaves.\n"
            "`/leaderboard [board]` — View high scores and ranking leaderboards.\n"
            "`/milestones` — Check your milestone reward progress in the server.\n"
            "`/patreon` — Learn details about subscriptions, ranks, and server Patreon perks.\n"
            "`/pay [user] [amount]` — Send Leaves to another user\n"
            "`/stats` — View your calculated server statistics.\n"
            "`/stats [user]` — Inspect stats of another member.\n"
            "`/wordle` — Play the Daily Wordle for Leaves and XP."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="Dating & Profiles (7)", style=discord.ButtonStyle.primary, custom_id="help_btn_dating", row=1)
    async def dating_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Dating & Profile Commands", color=discord.Color.magenta())
        embed.description = (
            "⚠️ **Requirements:** You must have the <@&1358469974552870913> role to use these commands. "
            "If you do not have it yet, please head over to <#1358485673991999721> to open a ticket.\n\n"
            "`/editfursona` — Modify the appearance and details of your fursona.\n"
            "`/editprofile` — Make changes to your personal dating/community profile.\n"
            "`/filter` — Set narrow profile parameters based on custom search filters.\n"
            "`/findmatch` — Automatically query profiles matching your preferences.\n"
            "`/profile` — View your personal profile\n"
            "`/profile [user]` — View a user's profile\n"
            "`/randomprofile` — Pull a random user's profile\n"
            "`/startprofile` — Begin the setup process to create your new profile."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="Punishments (2)", style=discord.ButtonStyle.primary, custom_id="help_btn_punish", row=2)
    async def punishment_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Enforcement Commands", color=discord.Color.dark_red())
        embed.description = (
            "`/muteduration` — Check precisely how much time remains on an active mute.\n"
            "`/punishments` — Display your logs of warnings or moderation strikes."
        )
        await interaction.response.edit_message(embed=embed)

    @button(label="Casino (5)", style=discord.ButtonStyle.primary, custom_id="help_btn_casino", row=2)
    async def casino_menu(self, interaction: Interaction, btn):
        embed = discord.Embed(title="Casino Commands", color=discord.Color.dark_green())
        embed.description = (
            "**🃏 Blackjack Games**\n"
            "`/blackjack Play [Bet]` — Start a game of Blackjack.\n"
            "`/blackjack View Odds` — View odds for Blackjack.\n\n"
            "**📈 Crash Games**\n"
            "`/crash Play [Bet]` — Start a game of Crash.\n"
            "`/crash View Odds` — View odds for Crash.\n\n"
            "**🎫 Scratch Off Tickets**\n"
            "`/scratchoff Buy & Play` — Buy and scratch a ticket.\n"
            "`/scratchoff View Odds` — View odds for Scratchoff.\n\n"
            "**🎰 Slot Machines**\n"
            "`/slots Spin` — Start a game of Slots.\n"
            "`/slots Jackpot` — Displays the current Jackpot Pool.\n"
            "`/slots Stats` — View your Slots Statistics.\n\n"
            "`/slots Odds` — View odds for Slots.\n"
            "`/slots Help` — Basic Help Command.\n"
            "**📊 General Metrics**\n"
            "`/casinostats` — Displays server Casino Stats.\n"
            "`/casinostats [user]` — Shows a user's overall casino statistics"
        )
        await interaction.response.edit_message(embed=embed)


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Command help for Kitty Kingdom")
    async def help(self, interaction: discord.Interaction):
        view = HelpMenuButtons()
        embed = view.get_main_embed()
        # Ephemeral is false so anyone can see the menu when generated
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

async def setup(bot):
    await bot.add_cog(Help(bot))