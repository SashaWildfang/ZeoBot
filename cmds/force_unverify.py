import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from db.database import get_connection  # Motor client

# ===============================
# Role Constants
# ===============================

HELPER_ROLE_ID = 1358470318087340342

STAFF_ROLE_IDS = {
    HELPER_ROLE_ID,       # Helper
    1358472557862457537,  # Jr Mod
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

HIGHER_STAFF_ROLE_IDS = STAFF_ROLE_IDS - {HELPER_ROLE_ID}

OWNER_ROLE_ID = 1358473248534167663
UNVERIFIED_ROLE_ID = 1358469817191104716
BOT_LOGS_CHANNEL_ID = 1360344042705256660

# ===============================
# ForceUnverify Cog
# ===============================

class ForceUnverify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def users_col(self):
        db = get_connection()
        return db["users"]

    # -------------------------------
    # 🔐 Permission Helpers
    # -------------------------------

    def is_staff(self, member: discord.Member) -> bool:
        return any(role.id in STAFF_ROLE_IDS for role in member.roles)
        
    def has_higher_staff_role(self, member: discord.Member) -> bool:
        return any(role.id in HIGHER_STAFF_ROLE_IDS for role in member.roles)

    def is_owner(self, member: discord.Member) -> bool:
        return any(role.id == OWNER_ROLE_ID for role in member.roles)

    # -------------------------------
    # 🚫 Force Unverify Command
    # -------------------------------

    @app_commands.command(
        name="forceunverify",
        description="Force-unverify a user by mention or ID (works even if they are not in the server)."
    )
    @app_commands.describe(user_or_id="Mention a user (@user) or paste their Discord ID")
    async def forceunverify(
        self,
        interaction: discord.Interaction,
        user_or_id: str
    ):
        await interaction.response.defer(ephemeral=True)

        author = interaction.user
        guild = interaction.guild
        now = datetime.now(timezone.utc)
        col = self.users_col()

        # ===============================
        # 🔐 Helper+ Permission Check
        # ===============================
        if not self.is_staff(author):
            return await interaction.followup.send(
                "🚫 You do not have permission to use this command (**Helper+ only**)."
            )

        # ===============================
        # ⏳ DB-Backed Helper Daily Limit Check
        # ===============================
        is_helper_only = not self.has_higher_staff_role(author)
        today_str = now.strftime("%Y-%m-%d")
        
        # Fetch the staff member's DB profile to check usage
        author_data = await col.find_one({"discordId": author.id}) or {}
        usage_data = author_data.get("helperUsage", {"date": today_str, "count": 0})

        if is_helper_only:
            # Reset if it's a new day in the database
            if usage_data.get("date") != today_str:
                usage_data = {"date": today_str, "count": 0}
            
            # Block if they hit the limit
            if usage_data["count"] >= 3:
                return await interaction.followup.send(
                    "🚫 **Daily Limit Reached:** You have already used your 3 `forceunverify` commands for today. "
                    "Try again tomorrow!"
                )

        # ===============================
        # Parse User Mention or Discord ID
        # ===============================
        cleaned_input = user_or_id.replace("<@", "").replace("!", "").replace(">", "").strip()
        
        try:
            target_id = int(cleaned_input)
        except ValueError:
            return await interaction.followup.send("❌ Invalid input. Please provide a valid user mention or Discord ID.")

        # ===============================
        # Attempt Member Fetch (OPTIONAL)
        # ===============================
        member: discord.Member | None = None
        try:
            member = await guild.fetch_member(target_id)
        except discord.NotFound:
            member = None
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ I do not have permission to fetch members."
            )

        # ===============================
        # Staff Protection (only if member exists)
        # ===============================
        if member:
            is_target_staff = any(role.id in STAFF_ROLE_IDS for role in member.roles)
            is_author_owner = self.is_owner(author)

            if is_target_staff and not is_author_owner:
                return await interaction.followup.send(
                    "⚠️ You cannot force-unverify another staff member (**Owner only**)."
                )

        # ===============================
        # Role Handling (only if member exists)
        # ===============================
        unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
        bot_log_channel = guild.get_channel(BOT_LOGS_CHANNEL_ID)

        if member:
            try:
                roles_to_remove = [
                    role for role in member.roles
                    if role != guild.default_role
                ]

                if roles_to_remove:
                    await member.remove_roles(
                        *roles_to_remove,
                        reason=f"Force unverified by {author}"
                    )

                if unverified_role:
                    await member.add_roles(
                        unverified_role,
                        reason=f"Force unverified by {author}"
                    )

            except discord.Forbidden:
                return await interaction.followup.send(
                    "❌ I don't have permission to modify that user."
                )

        # ===============================
        # MongoDB Target Update (ALWAYS)
        # ===============================
        await col.update_one(
            {"discordId": target_id},
            {
                "$set": {
                    "updatedAt": now,
                    "forceUnverified": True
                },
                "$setOnInsert": {
                    "discordId": target_id,
                    "createdAt": now
                }
            },
            upsert=True
        )

        # ===============================
        # MongoDB Author Limit Update & Success Message
        # ===============================
        status_line = (
            "• Roles removed & Unverified applied"
            if member
            else "• User not in server (DB-only flag update)"
        )

        quota_line = ""
        if is_helper_only:
            # Increment DB usage
            usage_data["count"] += 1
            await col.update_one(
                {"discordId": author.id},
                {
                    "$set": {"helperUsage": usage_data},
                    "$setOnInsert": {"createdAt": now}
                },
                upsert=True
            )
            
            remaining = 3 - usage_data["count"]
            quota_line = f"\n📊 **Helper Quota:** `{remaining}`/3 uses remaining today."

        await interaction.followup.send(
            f"🔁 **Force-unverify complete** for `<@{target_id}>`.\n"
            f"{status_line}\n"
            f"• Verified history kept intact.{quota_line}"
        )

        # ===============================
        # Logging (Embed)
        # ===============================
        if bot_log_channel:
            embed = discord.Embed(
                title="🛑 Force Unverify",
                color=discord.Color.red(),
                timestamp=now
            )

            embed.add_field(
                name="Staff",
                value=f"{author.mention}\n`{author.id}`",
                inline=True
            )

            embed.add_field(
                name="Target",
                value=f"<@{target_id}>\n`{target_id}`",
                inline=True
            )

            embed.add_field(
                name="Result",
                value=(
                    "Roles removed & Unverified applied"
                    if member
                    else "User not in server — database-only flag update"
                ),
                inline=False
            )

            await bot_log_channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ForceUnverify(bot))