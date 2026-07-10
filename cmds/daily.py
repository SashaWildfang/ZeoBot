import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
from db.database import get_connection   # Motor client

BOOSTER_ROLE_ID = 1360260086500561237


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def users_col(self):
        db = get_connection()
        return db["users"]

    @app_commands.command(name="daily", description="Claim your daily Leaves")
    async def daily(self, interaction: discord.Interaction):
        # Prevent Discord timeouts
        await interaction.response.defer(thinking=True)

        user = interaction.user
        user_id = user.id
        now = datetime.now(timezone.utc)

        col = self.users_col()

        # --- LOAD USER DOCUMENT ---
        user_doc = await col.find_one({"discordId": user_id})

        if not user_doc:
            user_doc = {
                "discordId": user_id,
                "balance": 0,
                "streak": 0,
                "lastDaily": None,
                "createdAt": now,
                "updatedAt": now
            }
            await col.insert_one(user_doc)

        balance = user_doc.get("balance", 0)
        streak = user_doc.get("streak", 0)

        last_claim = user_doc.get("lastDaily")

        # --- FIX: BSON datetime → Python datetime ---
        if last_claim:
            try:
                last_claim = last_claim.replace(tzinfo=timezone.utc)
            except Exception:
                last_claim = None

        is_booster = any(role.id == BOOSTER_ROLE_ID for role in user.roles)
        base_amount = 250  # <-- INCREASED BASE AMOUNT
        bonus = 0

        # --- COOLDOWN CHECK (Midnight Reset) ---
        if last_claim and last_claim.date() == now.date():
            # Get the next midnight (UTC)
            next_claim_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining = next_claim_time - now

            hrs, rem = divmod(int(remaining.total_seconds()), 3600)
            mins = rem // 60

            readable = f"<t:{int(next_claim_time.timestamp())}:F> (in {hrs}h {mins}m)"

            if is_booster:
                next_day = (streak % 7) + 1 
                next_bonus = 100 * next_day  # <-- INCREASED MULTIPLIER
                next_gross = base_amount + next_bonus
                next_tax = int(next_gross * 0.05)
                next_net = next_gross - next_tax
                
                preview = (
                    f"💡 **Next reward:** {next_net} <:leaf:1524758896659660831> "
                    f"(After tax) [Day {next_day} streak]"
                )
            else:
                next_gross = base_amount
                next_tax = int(next_gross * 0.05)
                next_net = next_gross - next_tax
                
                preview = (
                    f"💡 **Next reward:** {next_net} <:leaf:1524758896659660831> (After tax)\n"
                    "Boost the server to get +100 to +700 bonuses with a streak!\n"
                    "Read more in <#1358485327030784071>"
                )

            return await interaction.followup.send(
                f"🕒 You already claimed your daily today! It resets on {readable}.\n\n{preview}"
            )

        # --- STREAK RESET (Calendar Days) ---
        if last_claim:
            days_diff = (now.date() - last_claim.date()).days
            if days_diff > 1:
                streak = 0

        # --- AWARD REWARD ---
        streak += 1
        cycle_day = (streak - 1) % 7 + 1

        if is_booster:
            bonus = 100 * cycle_day  # <-- INCREASED MULTIPLIER

        total_gross = base_amount + bonus
        tax = int(total_gross * 0.05)
        net_total = total_gross - tax

        new_balance = balance + net_total

        # 1. Update User Record
        await col.update_one(
            {"discordId": user_id},
            {
                "$set": {
                    "balance": new_balance,
                    "streak": streak,
                    "lastDaily": now,
                    "updatedAt": now
                },
                "$setOnInsert": {"createdAt": now}
            },
            upsert=True
        )

        # 2. Add Tax to Casino Jackpot
        if tax > 0:
            globals_col = get_connection()["globals"]
            await globals_col.update_one(
                {"_id": "casino_jackpot"},
                {"$inc": {"amount": tax}},
                upsert=True
            )

        # --- NEXT REWARD PREVIEW ---
        next_day = (streak % 7) + 1
        next_bonus = 100 * next_day if is_booster else 0  # <-- INCREASED MULTIPLIER
        next_gross = base_amount + next_bonus
        next_tax = int(next_gross * 0.05)
        next_net = next_gross - next_tax

        # Predict the exact midnight timestamp for tomorrow
        next_claim_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        readable = f"<t:{int(next_claim_time.timestamp())}:F> (<t:{int(next_claim_time.timestamp())}:R>)"

        # --- EMBED ---
        embed = discord.Embed(
            title="🎁 Daily Reward Claimed!",
            description=(
                f"You received **{net_total} <:leaf:1524758896659660831>**!\n"
                f"*(A 5% tax of **{tax} <:leaf:1524758896659660831>** went towards the server jackpot)*"
            ),
            color=discord.Color.orange(),
            timestamp=now
        )

        embed.set_footer(text=f"Total: {new_balance} Leaves")
        embed.set_thumbnail(url=user.display_avatar.url)

        if is_booster:
            embed.add_field(
                name="🔥 Streak Bonus",
                value=f"Streak: **{streak}**\nDay {cycle_day} bonus: **+{bonus}**",
                inline=False
            )
        else:
            embed.add_field(
                name="💡 Want Streak Bonuses?",
                value=(
                    "Boost the server to earn up to **+700** daily <:leaf:1524758896659660831>!\n"
                    "Your streak never resets unless you miss a full day.\n"
                    "Read more in <#1358485327030784071>"
                ),
                inline=False
            )

        embed.add_field(
            name="⏭️ Next Claim",
            value=(
                f"{readable}\n"
                f"**Next reward:** {next_net} <:leaf:1524758896659660831> (After tax)"
                f"{f' [Day {next_day} streak]' if is_booster else ''}"
            ),
            inline=False
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Daily(bot))