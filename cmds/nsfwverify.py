import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import time
from db.database import get_connection

# ====== Constants ======
MOD_AND_HIGHER_ROLE_IDS = {
    1358472557862457537,  # Jr Mod
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

DISCORD_MEMBER_ROLE_ID = 1358469854725931038
NSFW_ROLE_ID = 1358469974552870913
BOT_LOGS_CHANNEL_ID = 1360344042705256660
NSFW_WELCOME_CHANNEL_ID = 1358487735811182682

# NSFW & Dating resource channels
NSFW_ANNOUNCEMENTS = 1359520996561781009
NSFW_RULES = 1358487818057289848
NSFW_GUIDE = 1359520956913029291
NSFW_ROLES = 1358487300245295104
NSFW_INTRO = 1358487186151837866
DATING_RULES = 1358487325944057918
SERVER_INTROS = 1496875154314231828
INTRODUCTIONS_HELP = 1496743217390157935
INTRO_NOTIFICATIONS = 1497237389741920446
PROFILE_VIEWER = 1496746762713432104

# Category for auto-detect behavior
NSFW_VERIFICATION_CATEGORY_ID = 1362461644768411758
# =======================

# -------------------------------------------------------
# 🧭 Confirmation View
# -------------------------------------------------------
class ConfirmVerifyView(discord.ui.View):
    def __init__(self, target: discord.Member, on_confirm):
        super().__init__(timeout=60)
        self.target = target
        self.on_confirm = on_confirm

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.on_confirm(interaction, self.target)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❎ NSFW verification cancelled.", view=self)


# -------------------------------------------------------
# 🔞 NSFW Verify Cog (Mongo Edition)
# -------------------------------------------------------
class NSFWVerify(commands.Cog):
    """NSFW Verification handler using MongoDB."""

    def __init__(self, bot):
        self.bot = bot

    def _user_is_mod_plus(self, member: discord.Member) -> bool:
        return any(role.id in MOD_AND_HIGHER_ROLE_IDS for role in member.roles)

    def _users_col(self):
        db = get_connection()
        return db["users"]

    def _pick_ticket_user_without_nsfw(self, channel: discord.TextChannel, guild: discord.Guild):
        nsfw_role = guild.get_role(NSFW_ROLE_ID)
        if nsfw_role is None:
            return None, []

        def eligible(m: discord.Member) -> bool:
            return (not m.bot) and (not self._user_is_mod_plus(m)) and (nsfw_role not in m.roles)

        candidates = [m for m in channel.members if isinstance(m, discord.Member) and eligible(m)]
        if len(candidates) == 1:
            return candidates[0], candidates
        elif len(candidates) > 1:
            return None, candidates
        else:
            return None, []

    async def _do_verify(self, interaction: discord.Interaction, author: discord.Member, user: discord.Member):
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("⚠️ This command can only be used in a server.", ephemeral=True)
            return

        member_role = guild.get_role(DISCORD_MEMBER_ROLE_ID)
        nsfw_role = guild.get_role(NSFW_ROLE_ID)

        if not member_role or not nsfw_role:
            await interaction.followup.send("⚠️ Required roles are missing in the server.", ephemeral=True)
            return

        # Must already be verified
        if member_role not in user.roles:
            await interaction.followup.send(
                f"❌ {user.mention} must be a verified Discord Member before they can be NSFW-verified.",
                ephemeral=True
            )
            return

        if nsfw_role in user.roles:
            await interaction.followup.send(
                f"⚠️ {user.mention} is **already NSFW-verified**.",
                ephemeral=True
            )
            return

        # Grant NSFW role
        await user.add_roles(nsfw_role, reason=f"NSFW verified by {author}")

        # MongoDB update
        try:
            users = self._users_col()
            now = datetime.utcnow().isoformat()

            users.update_one(
                {"discordId": user.id},
                {
                    "$set": {
                        "updatedAt": now,
                        "nsfwVerifiedBy": author.id,
                        "nsfwVerifiedAt": now
                    },
                    "$setOnInsert": {
                        "createdAt": now
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"❌ MongoDB error while NSFW verifying: {e}")

        # Log action
        log_channel = guild.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🔞 NSFW Verification Logged",
                description=(
                    f"**Verified Member:** {user.mention} (`{user.id}`)\n"
                    f"**Verified By:** {author.mention} (`{author.id}`)"
                ),
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="NSFW Verification Log")
            embed.set_thumbnail(url=user.display_avatar.url)
            await log_channel.send(embed=embed)

        # Welcome message
        welcome_channel = guild.get_channel(NSFW_WELCOME_CHANNEL_ID)
        if welcome_channel:
            embed = discord.Embed(
                title="🔞 NSFW Access Granted",
                description=(
                    f"Welcome to the 18+ side of the server, {user.mention}!\n\n"
                    f"Please read through the following channels to get yourself set up:"
                ),
                color=discord.Color.magenta(),
                timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            embed.add_field(
                name="👋 Introductions",
                value=(
                    f"• <#{SERVER_INTROS}> — Random Intros are shown here on a 3-hour interval\n"
                    f"• <#{INTRODUCTIONS_HELP}> — General Command information about setting up a profile\n"
                    f"• <#{INTRO_NOTIFICATIONS}> — Opt-in to get pinged whenever someone makes a profile"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💖 Matchmaking & Profiles",
                value=(
                    f"• <#{NSFW_ROLES}> — Grab your pronouns, sexuality, and dating preference roles.\n"
                    f"• <#{PROFILE_VIEWER}> — The central hub for the dating bot! Head here to use the following commands:\n"
                    f" ↳ **`/startprofile`** — Create your dating profile card from scratch.\n"
                    f" ↳ **`/editprofile`** — Update your profile fields (ensure your dropdown choices are set correctly!).\n"
                    f" ↳ **`/findmatch`** — Search for highly accurate compatibility matches based on your profile!"
                ),
                inline=False
            )
            
            embed.set_footer(text="Enjoy your time in the NSFW side of Kitty Kingdom!")
            
            await welcome_channel.send(content=user.mention, embed=embed)

        await interaction.followup.send(f"✅ {user.mention} has been NSFW-verified and granted access.", ephemeral=True)

    # -------------------------------------------------------
    # 🧭 Command: /nsfwverify
    # -------------------------------------------------------
    @app_commands.command(
        name="nsfwverify",
        description="Give a user NSFW access (Mod+ only). If no user is provided, auto-detects from the channel."
    )
    @app_commands.describe(user="(Optional) The user to NSFW-verify. If omitted, auto-detects in NSFW Verification category.")
    async def nsfwverify(self, interaction: discord.Interaction, user: discord.Member | None = None):
        author = interaction.user

        # Permission check
        if not isinstance(author, discord.Member) or not self._user_is_mod_plus(author):
            await interaction.response.send_message(
                "🚫 You do not have permission to use this command. (Mod+ only)",
                ephemeral=True
            )
            return

        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("⚠️ Use this command in a server text channel.", ephemeral=True)
            return

        # Category restriction (only when user is omitted)
        if user is None:
            if not interaction.channel.category or interaction.channel.category.id != NSFW_VERIFICATION_CATEGORY_ID:
                await interaction.response.send_message(
                    "⚠️ Ticket Must be in The ** Claimed Tickets** section to use this command",
                    ephemeral=True
                )
                return

        # Auto-detect target if none provided
        target = user
        candidates = []
        if target is None:
            target, candidates = self._pick_ticket_user_without_nsfw(interaction.channel, interaction.guild)

        if target is None:
            if candidates:
                mentions = ", ".join(m.mention for m in candidates[:10])
                more = " (and more...)" if len(candidates) > 10 else ""
                await interaction.response.send_message(
                    f"⚠️ Multiple possible users found: {mentions}{more}\n"
                    f"Please run `/nsfwverify user:@person` to specify exactly who.",
                    ephemeral=True
                )
                return
            else:
                await interaction.response.send_message(
                    "⚠️ I couldn’t find a single user here who isn’t NSFW verified.\n"
                    "Please run `/nsfwverify user:@person` instead.",
                    ephemeral=True
                )
                return

        # ==========================================
        # NEW LOGIC: Block if they haven't run /getjoinapp
        # ==========================================
        if not hasattr(self.bot, 'join_app_checks'):
            self.bot.join_app_checks = {}

        last_check = self.bot.join_app_checks.get((author.id, target.id))
        
        # 7200 seconds = 2 hours. They must have checked the app within the last 2 hours.
        if not last_check or (time.time() - last_check) > 7200:
            return await interaction.response.send_message(
                f"🛑 **Cross-Check Required:** You must review {target.mention}'s Join Application before granting NSFW access.\n\n"
                f"Please run `/getjoinapp target_user:{target.id}` to cross-check their Date of Birth with their provided ID.",
                ephemeral=True
            )

        # Confirm action
        await interaction.response.defer(ephemeral=True)

        async def on_confirm(confirm_interaction: discord.Interaction, confirmed_target: discord.Member):
            if not self._user_is_mod_plus(confirm_interaction.user):
                await confirm_interaction.followup.send("🚫 You no longer have permission to do that.", ephemeral=True)
                return
            await self._do_verify(interaction, author, confirmed_target)

        view = ConfirmVerifyView(target, on_confirm)
        await interaction.followup.send(
            content=f"Are you sure you want to NSFW-verify {target.mention}?",
            view=view,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(NSFWVerify(bot))