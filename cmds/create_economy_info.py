import discord
from discord.ext import commands
from discord import app_commands

TARGET_CHANNEL_ID = 1358485327030784071

# Updated Role IDs to match the new system
NITRO_ROLE_ID = 1360260086500561237
NITRO_BOOSTER_ROLE_ID = 1498492008648544277 # Server Booster
PATREON_ROLE_T1 = 1362102163693633818  # Royal Kitten
PATREON_ROLE_T2 = 1362502662721114245  # Kitten Guardian
PATREON_ROLE_T3 = 1362502871639396362  # Legendary Neko

class EconomyInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create_economy_info", description="Create economy overview and leveling info embeds.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create_economy_info(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        try:
            channel = guild.get_channel(TARGET_CHANNEL_ID)
            if not channel:
                await interaction.followup.send("❌ Could not find the target channel.", ephemeral=True)
                return

            nitro = guild.get_role(NITRO_ROLE_ID)
            booster = guild.get_role(NITRO_BOOSTER_ROLE_ID)
            t1 = guild.get_role(PATREON_ROLE_T1)
            t2 = guild.get_role(PATREON_ROLE_T2)
            t3 = guild.get_role(PATREON_ROLE_T3)

            # Currency Embed
            currency_embed = discord.Embed(
                title="<:leaf:1524758896659660831> What are Leaves ?",
                description=(
                    "<:leaf:1524758896659660831> are our server currency! You can earn them by being an active and engaged member of the community.\n\n"
                    "Here's how you can earn them:\n"
                    "• **Chatting** in server text channels — be social and participate in conversations\n"
                    "• **Hanging out in VC** — earn <:leaf:1524758896659660831> & ✨ passively just by talking in voice channels\n"
                    "• **Boosting the Server** — helps the community grow and rewards you with <:leaf:1524758896659660831> monthly\n"
                    "• Becoming a **Patreon Member** — supports the server and earn monthly Leaves\n"
                    "• Completing your **/daily** — free <:leaf:1524758896659660831> once every 24hrs\n"
                    "• Playing the **/wordle** — earn <:leaf:1524758896659660831> by solving the daily word puzzle\n\n"
                    "Each message you send grants you **30-50** <:leaf:1524758896659660831> (and VC time grants periodic <:leaf:1524758896659660831> too!), adjusted by your Leaf Multiplier.\n"
                    "You can use your <:leaf:1524758896659660831> in the **/store** to buy special **roles**, **personal boosters**, and **dating profile perks**!"
                ),
                color=discord.Color.blue()
            )

            # Store Embed
            store_embed = discord.Embed(
                title="🛒 About the Store & Boosters",
                description=(
                    "The **/store view** menu is where you spend your <:leaf:1524758896659660831> on cool stuff!\n\n"
                    "**What you can buy:**\n"
                    "• **Permanent Roles** ✨ — Show off your wealth or vibes.\n"
                    "• **Personal Boosters** 🚀 — Buy 1d 2x ✨/Leaf boosters, or 1d Dating Profile weight boosters!\n\n"
                    "🌀 **The Rotating Shop:**\n"
                    "The store features **Daily Deals** and **Weekly Deals** that rotate out automatically! Check back often to snag limited-time roles before they are gone.\n\n"
                    "🔥 **Stacking Boosters:**\n"
                    "If you activate multiple of the same booster from your inventory, they **add time**! (e.g., Using two 1d XP boosters gives you 2 days of 2x XP)."
                ),
                color=discord.Color.teal()
            )

            # Leveling & Perks Embed
            leveling_embed = discord.Embed(
                title="📈 Leveling & Multiplier System",
                description=(
                    "Our server uses a leveling system that rewards you for being active. You gain **25 to 50 Base XP** per message, plus continuous XP for being active in Voice Channels!\n\n"
                    "💡 **Passive Multipliers & Perks:**\n"
                    f"• {nitro.mention if nitro else 'Nitro'} — **+15% ✨ & + 15% <:leaf:1524758896659660831> | + 1.0x Dating Profile Weight**\n"
                    f"• {t1.mention if t1 else 'Royal Kitten'} — **+10% ✨** | **+1.5x Profile Weight**\n"
                    f"• {t2.mention if t2 else 'Kitten Guardian'} — **+20% ✨** | **+2.0x Profile Weight**\n"
                    f"• {t3.mention if t3 else 'Legendary Neko'} — **+40% ✨** | **+2.5x Profile Weight**\n\n"
                    "*(Note: Your Profile Weight increases how often you appear in hourly dating intros!)*\n\n"
                    "📆 **✨ XP Events:**\n"
                    "• Watch out for **Server-Wide XP Weekends** which double everyone's gains!\n"
                    "• Use `/stats` to view your current active multiplier breakdown."
                ),
                color=discord.Color.gold()
            )

            # Store Commands Embed
            commands_embed = discord.Embed(
                title="📦 Store & Inventory Commands",
                description=(
                    "Here is how to navigate the new economy system:\n\n"
                    "**Store Commands:**\n"
                    "• `/store view` — Browse the shop categories and active rotations.\n"
                    "• `/store buy [item_id]` — Purchase an item using its ID tag.\n\n"
                    "**Inventory Commands:**\n"
                    "• `/inventory view` — View your consumables and see your **Active Boosters**.\n"
                    "• `/inventory viewroles` — View all the cosmetic roles you own.\n"
                    "• `/inventory equiprole [roleID]` — Equip an owned role to your profile.\n"
                    "• `/inventory removerole [roleID]` — Remove an equipped role.\n"
                    "• `/inventory use [itemID]` — Activate a consumable booster from your bag!"
                ),
                color=discord.Color.orange()
            )

            # Send all embeds
            await channel.send(embed=currency_embed)
            await channel.send(embed=store_embed)
            await channel.send(embed=leveling_embed)
            await channel.send(embed=commands_embed)

            await interaction.followup.send("✅ Economy info embeds have been posted!", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Something went wrong: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EconomyInfo(bot))