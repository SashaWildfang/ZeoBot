import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, time, timedelta
from zoneinfo import ZoneInfo
from db.database import get_connection

# Constants
YOUR_GUILD_ID_HERE = 1358452494128250940
NITRO_ROLE_ID = 1360260086500561237
BOOST_CHANNEL_ID = 1362519485650833468
MONTHLY_PAYOUT_CHANNEL_ID = 1362519485650833468
ANNOUNCEMENT_CHANNEL_ID = 1358485236073238528
ANNOUNCEMENT_PING_ROLE_ID = 1363972415822237747
BOOST_REWARD = 750

# Reordered Highest to Lowest
PATREON_TIERS = {
    1362502871639396362: 4000,   # Tier 3
    1362502662721114245: 2000,   # Tier 2
    1362102163693633818: 1000    # Tier 1
}

# Set timezone explicitly to Mountain Time and trigger at 11:59 PM
LOCAL_TZ = ZoneInfo("America/Denver")
PAYOUT_TIME = time(hour=23, minute=59, tzinfo=LOCAL_TZ)

def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m"
    return f"{int(minutes)}m"

class Payouts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monthly_payouts_loop.start()

    @tasks.loop(time=PAYOUT_TIME)
    async def monthly_payouts_loop(self):
        now_local = datetime.now(LOCAL_TZ)
        tomorrow = now_local + timedelta(days=1)
        
        # If tomorrow is the 1st, then today is the last day of the month!
        if tomorrow.day == 1:
            try:
                await self.process_monthly_payouts()
            except Exception as e:
                print(f"Error in monthly payout loop: {e}")

    @monthly_payouts_loop.before_loop
    async def before_monthly_payouts_loop(self):
        await self.bot.wait_until_ready()

    async def process_monthly_payouts(self):
        guild = self.bot.get_guild(YOUR_GUILD_ID_HERE)
        if not guild:
            return

        payout_channel = self.bot.get_channel(MONTHLY_PAYOUT_CHANNEL_ID)
        if not payout_channel:
            return

        db = get_connection()
        users_col = db.users
        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now(LOCAL_TZ)

        # ==========================================
        # 1. PATREON & NITRO PAYOUTS
        # ==========================================
        recipients_by_role = {
            NITRO_ROLE_ID: [],
            **{role_id: [] for role_id in PATREON_TIERS}
        }

        for member in guild.members:
            payout = 0
            matched_role = None

            for role_id, amount in PATREON_TIERS.items():
                if discord.utils.get(member.roles, id=role_id):
                    payout += amount
                    matched_role = role_id
                    break

            if discord.utils.get(member.roles, id=NITRO_ROLE_ID):
                payout += 500
                recipients_by_role[NITRO_ROLE_ID].append(member)

            if matched_role:
                recipients_by_role[matched_role].append(member)

            if payout > 0:
                await users_col.update_one(
                    {"discordId": int(member.id)},
                    {"$inc": {"balance": payout}, "$set": {"updated_at": now_utc}},
                    upsert=True
                )

        embed = discord.Embed(
            title="💸 Monthly Perk Payouts Complete!",
            description="Thank you for supporting the server ❤️",
            color=discord.Color.green(),
            timestamp=now_utc
        )

        mention_text = []

        for role_id, members in recipients_by_role.items():
            if not members:
                continue

            role = guild.get_role(role_id)
            if not role:
                continue
                
            member_list = "\n".join(f"{m.mention}" for m in members)
            embed.add_field(
                name=f"{role.name} ({len(members)} Member{'s' if len(members) != 1 else ''})",
                value=member_list,
                inline=False
            )
            mention_text.append(role.mention)

        embed.set_footer(text=f"Processed • {now_utc.strftime('%B %d, %Y %H:%M UTC')}")

        try:
            await payout_channel.send(content=" ".join(mention_text), embed=embed)
        except Exception:
            pass

        for role_id, members in recipients_by_role.items():
            if role_id not in PATREON_TIERS or not members:
                continue

            role = guild.get_role(role_id)
            amount = PATREON_TIERS[role_id]

            thank_you_embed = discord.Embed(
                title="🎉 Thank You for Subscribing on Patreon!",
                description=(
                    f"Big shoutout to our **{role.name}** supporters!\n\n"
                    f"You received **{amount}** <:leaf:1524758896659660831> this month as a thank-you for being amazing patrons 💖\n"
                    f"Your support keeps the community strong!"
                ),
                color=discord.Color.purple(),
                timestamp=now_utc
            )
            thank_you_embed.add_field(
                name="This Month's Supporters:",
                value="\n".join(member.mention for member in members),
                inline=False
            )
            thank_you_embed.set_footer(text="We appreciate you more than you know!")

            try:
                await payout_channel.send(embed=thank_you_embed)
            except Exception:
                pass


        # ==========================================
        # 2. TOP BUMPER PAYOUTS
        # ==========================================
        announcement_channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        
        if announcement_channel:
            # Since this runs on the last day of the current month, we query the CURRENT month string
            target_month_str = f"{now_local.year}-{now_local.month:02d}"

            cursor = users_col.find(
                {"last_bump_month": target_month_str, "monthly_bumps": {"$gt": 0}}
            ).sort("monthly_bumps", -1).limit(3)
            
            top_bumpers = await cursor.to_list(length=3)

            if top_bumpers:
                rewards = [5000, 2500, 1000]
                medals = ["🥇", "🥈", "🥉"]
                bump_results = []

                for idx, bumper in enumerate(top_bumpers):
                    user_id = bumper.get("discordId")
                    bumps = bumper.get("monthly_bumps", 0)
                    reward = rewards[idx]
                    medal = medals[idx]

                    await users_col.update_one(
                        {"discordId": user_id},
                        {"$inc": {"balance": reward}, "$set": {"updated_at": now_utc}}
                    )

                    member = guild.get_member(user_id)
                    name = member.mention if member else f"<@{user_id}>"
                    bump_results.append(f"{medal} **{name}** — **{bumps} Bumps** (+{reward} <:leaf:1524758896659660831>)")

                bump_embed = discord.Embed(
                    title="🏆 Monthly Bump Leaderboard Winners!",
                    description=f"A massive thank you to everyone who helped grow the server this month! The top 3 bumpers have received their rewards:\n\n" + "\n\n".join(bump_results),
                    color=discord.Color.gold(),
                    timestamp=now_utc
                )
                bump_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
                bump_embed.set_footer(text="Use /bump every 2 hours to climb the ranks next month!")

                try:
                    await announcement_channel.send(
                        content=f"<@&{ANNOUNCEMENT_PING_ROLE_ID}>", 
                        embed=bump_embed
                    )
                except Exception as e:
                    print(f"Failed to send bump announcement: {e}")

            # ==========================================
            # 3. TOP VC TIME PAYOUTS
            # ==========================================
            vc_cursor = users_col.find(
                {"vc_month": target_month_str, "vc_time_monthly": {"$gt": 0}}
            ).sort("vc_time_monthly", -1).limit(3)

            top_vc_users = await vc_cursor.to_list(length=3)

            if top_vc_users:
                vc_rewards = [5000, 2500, 1000]
                medals = ["🥇", "🥈", "🥉"]
                vc_results = []

                for idx, vc_user in enumerate(top_vc_users):
                    user_id = vc_user.get("discordId")
                    vc_seconds = vc_user.get("vc_time_monthly", 0)
                    reward = vc_rewards[idx]
                    medal = medals[idx]

                    await users_col.update_one(
                        {"discordId": user_id},
                        {"$inc": {"balance": reward}, "$set": {"updated_at": now_utc}}
                    )

                    member = guild.get_member(user_id)
                    name = member.mention if member else f"<@{user_id}>"
                    formatted_time = format_duration(vc_seconds)
                    vc_results.append(f"{medal} **{name}** — **{formatted_time}** (+{reward} <:leaf:1524758896659660831>)")

                vc_embed_description = (
                    "We have added a Monthly & Total VC Time Leaderboard. We will be rolling out the same monthly reward system as we did with the bumps.\n\n"
                    "You can go to <#1358485820100706314> and type `/leaderboard Total VC Time` or `/leaderboard Monthly VC Time` to view the stats board at any time.\n\n"
                    "**REWARDS FOR MONTHLY TOP 3 POSITIONS:**\n"
                    "🥇 #1 Spot: 5000 <:leaf:1524758896659660831>\n"
                    "🥈 #2 Spot: 2500 <:leaf:1524758896659660831>\n"
                    "🥉 #3 Spot: 1000 <:leaf:1524758896659660831>\n\n"
                    "**This Month's Winners:**\n" + "\n".join(vc_results)
                )

                vc_embed = discord.Embed(
                    title="🎙️ Monthly VC Time Leaderboard Winners!",
                    description=vc_embed_description,
                    color=discord.Color.from_rgb(114, 137, 218), # Discord Blurple
                    timestamp=now_utc
                )
                vc_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

                try:
                    await announcement_channel.send(
                        content=f"<@&{ANNOUNCEMENT_PING_ROLE_ID}>", 
                        embed=vc_embed
                    )
                except Exception as e:
                    print(f"Failed to send VC announcement: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if message.type in (
            discord.MessageType.premium_guild_subscription,
            discord.MessageType.premium_guild_tier_1,
            discord.MessageType.premium_guild_tier_2,
            discord.MessageType.premium_guild_tier_3,
        ):
            db = get_connection()
            users_col = db.users
            
            await users_col.update_one(
                {"discordId": int(message.author.id)},
                {"$inc": {"balance": BOOST_REWARD}, "$set": {"last_boost_reward_timestamp": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
                upsert=True
            )

            channel = self.bot.get_channel(BOOST_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="🚀 Nitro Boost Reward!",
                    description=(
                        f"{message.author.mention} just boosted the server and earned **{BOOST_REWARD}** <:leaf:1524758896659660831>. "
                        "Thank you so much for the Boost!"
                    ),
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text=f"Sent • {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}")
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

async def setup(bot):
    await bot.add_cog(Payouts(bot))