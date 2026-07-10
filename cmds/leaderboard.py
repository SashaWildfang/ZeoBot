import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection 
import math
import asyncio

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.gambling_col = self.db["gambling"]

    def format_number(self, number: float) -> str:
        """Formats large numbers into k, m, b and properly handles negative values."""
        is_negative = number < 0
        num = abs(number)
        
        if num >= 1_000_000_000:
            res = f"{num / 1_000_000_000:.1f}b"
        elif num >= 1_000_000:
            res = f"{num / 1_000_000:.1f}m"
        elif num >= 1_000:
            res = f"{num / 1_000:.1f}k"
        else:
            res = f"{int(num):,}"
            
        return f"-{res}" if is_negative else res

    def format_time(self, seconds: float) -> str:
        """Formats seconds into mo, d, h, m, s"""
        sec = int(seconds)
        months, sec = divmod(sec, 2592000) # Assuming ~30 days per month
        days, sec = divmod(sec, 86400)
        hours, sec = divmod(sec, 3600)
        minutes, sec = divmod(sec, 60)
        
        parts = []
        if months > 0: parts.append(f"{months}mo")
        if days > 0: parts.append(f"{days}d")
        if hours > 0: parts.append(f"{hours}h")
        if minutes > 0: parts.append(f"{minutes}m")
        if sec > 0 or not parts: parts.append(f"{sec}s")
        
        return ", ".join(parts)

    async def fetch_sorted_users(self, metric: str):
        # Map metrics to: (Collection, DB Field, Sort Order, Query Filter)
        metrics_map = {
            "balance": (self.users_col, "balance", -1, {"balance": {"$gte": 1}}),
            "level": (self.users_col, "level", -1, {"level": {"$gte": 2}}),
            "msgs": (self.users_col, "msgCount", -1, {"msgCount": {"$gte": 1}}),
            "bumps": (self.users_col, "bumps", -1, {"bumps": {"$gte": 1}}), 
            "monthly_bumps": (self.users_col, "monthly_bumps", -1, {"monthly_bumps": {"$gte": 1}}),
            
            # VC Metrics
            "vc_time_total": (self.users_col, "vc_time_total", -1, {"vc_time_total": {"$gte": 1}}),
            "vc_time_monthly": (self.users_col, "vc_time_monthly", -1, {"vc_time_monthly": {"$gte": 1}}),
            
            # Casino Metrics
            "casino_profit": (self.gambling_col, "net_profit", -1, {"total_spins": {"$gte": 1}}),
            "casino_spins": (self.gambling_col, "total_spins", -1, {"total_spins": {"$gte": 1}}),
            "casino_biggest_win": (self.gambling_col, "biggest_win", -1, {"biggest_win": {"$gt": 0}}),
            # Biggest Loss uses an Ascending sort (1) to put the lowest (most negative) numbers at the top!
            "casino_biggest_loss": (self.gambling_col, "biggest_loss", 1, {"biggest_loss": {"$lt": 0}}), 
        }
        
        if metric not in metrics_map:
            return [], None
            
        col, field, sort_order, query = metrics_map[metric]
        
        cursor = col.find(
            query,
            {"discordId": 1, field: 1}
        ).sort(field, sort_order)

        data = await cursor.to_list(length=2000) 
        return data, field

    async def generate_leaderboard_page(self, guild: discord.Guild, metric: str, page: int, user_id: int):
        data, field = await self.fetch_sorted_users(metric)
        
        pretty_names = {
            "balance": "Leaves", # <--- Updated to display as Leaves
            "level": "Level",
            "msgs": "Messages",
            "bumps": "Total Server Bumps", 
            "monthly_bumps": "Monthly Server Bumps", 
            "vc_time_total": "Total VC Time",
            "vc_time_monthly": "Monthly VC Time",
            "casino_profit": "Net Casino Profit",
            "casino_spins": "Total Slots Spins",
            "casino_biggest_win": "Biggest Casino Win",
            "casino_biggest_loss": "Biggest Casino Loss"
        }
        metric_title = pretty_names.get(metric, metric.capitalize())
        
        if not data:
            embed = discord.Embed(title=f"🏆 {metric_title} Leaderboard", description="No data available yet.", color=discord.Color.dark_gray())
            return embed, 1
        
        # 1. Calculate Server Total for the metric
        server_total = sum(doc.get(field, 0) for doc in data)
        
        # 2. Filter for members currently in the server and find user's contribution
        members = []
        user_value = 0
        for doc in data:
            uid = doc.get("discordId")
            val = doc.get(field, 0)
            if not uid: continue
            
            uid_int = int(uid)
            if uid_int == user_id:
                user_value = val

            member = guild.get_member(uid_int)
            if member and not member.bot:
                members.append((uid_int, val))

        total_valid_users = len(members)
        if total_valid_users == 0:
            embed = discord.Embed(title=f"🏆 {metric_title} Leaderboard", description="No users meet the requirements.", color=discord.Color.dark_gray())
            return embed, 1

        # 3. Pagination Logic
        per_page = 20
        max_page = max(1, math.ceil(total_valid_users / per_page))
        page = max(1, min(page, max_page))
        start = (page - 1) * per_page
        end = start + per_page

        embed = discord.Embed(
            title=f"🏆 {metric_title} Leaderboard (Page {page}/{max_page})",
            color=discord.Color.gold()
        )

        # 4. List Generation
        content = ""
        for idx, (uid, value) in enumerate(members[start:end], start=start + 1):
            member = guild.get_member(uid)
            if not member: continue
            
            name = f"{member.display_name}"
            
            # Use appropriate formatting based on metric type
            if metric in ["vc_time_total", "vc_time_monthly"]:
                formatted_val = self.format_time(value)
            else:
                formatted_val = self.format_number(value)
                
            line = f"`#{idx:>2}` {name} — {formatted_val}"
            if uid == user_id:
                content += f"**{line}**\n"
            else:
                content += f"{line}\n"

        # 5. FOOTER: "Rank #X of Y users"
        user_rank = next((i + 1 for i, (uid, _) in enumerate(members) if uid == user_id), None)
        if user_rank:
            footer_text = f"You are ranked #{user_rank} of {total_valid_users} users"
        else:
            footer_text = f"Total Users: {total_valid_users}"
        
        embed.set_footer(text=footer_text)

        # 6. Dynamic Stats Field
        if metric in ["casino_biggest_win", "casino_biggest_loss"]:
            stat_val = (
                f"**Server Record:** {self.format_number(data[0].get(field, 0))}\n"
                f"**Your Personal Record:** {self.format_number(user_value)}"
            )
        elif metric in ["vc_time_total", "vc_time_monthly"]:
            percentage = (user_value / server_total * 100) if server_total != 0 else 0
            stat_val = (
                f"**Total {metric_title}:** {self.format_time(server_total)}\n"
                f"**Your Contribution:** {percentage:.2f}% ({self.format_time(user_value)})"
            )
        else:
            percentage = (user_value / server_total * 100) if server_total != 0 else 0
            stat_val = (
                f"**Total {metric_title}:** {self.format_number(server_total)}\n"
                f"**Your Contribution:** {percentage:.2f}%"
            )

        embed.add_field(
            name=f"📊 Server {metric_title} Stats",
            value=stat_val,
            inline=False
        )

        embed.description = content or "No data to display."
        return embed, max_page

    @app_commands.command(name="leaderboard", description="View the server leaderboard")
    @app_commands.describe(metric="Select a leaderboard type")
    @app_commands.choices(metric=[
        app_commands.Choice(name="🍁 Leaves", value="balance"), 
        app_commands.Choice(name="⭐ Level", value="level"),
        app_commands.Choice(name="💬 Messages", value="msgs"),
        app_commands.Choice(name="⬆️ Total Bumps", value="bumps"), 
        app_commands.Choice(name="📅 Monthly Bumps", value="monthly_bumps"), 
        app_commands.Choice(name="🎙️ Total VC Time", value="vc_time_total"),
        app_commands.Choice(name="📆 Monthly VC Time", value="vc_time_monthly"),
        app_commands.Choice(name="🎰 Net Casino Profit", value="casino_profit"),
        app_commands.Choice(name="🎰 Total Slots Spins", value="casino_spins"),
        app_commands.Choice(name="📈 Biggest Casino Win", value="casino_biggest_win"),
        app_commands.Choice(name="📉 Biggest Casino Loss", value="casino_biggest_loss")
    ])
    async def leaderboard(self, interaction: discord.Interaction, metric: app_commands.Choice[str]):
        await interaction.response.defer()
        current_page = 1

        async def update_reactions(msg, page, max_p):
            try:
                await msg.clear_reactions()
                if page > 1: await msg.add_reaction("⬅️")
                if page < max_p: await msg.add_reaction("➡️")
            except: pass

        embed, max_page = await self.generate_leaderboard_page(interaction.guild, metric.value, current_page, interaction.user.id)
        message = await interaction.followup.send(embed=embed)
        
        if max_page <= 1: return

        await update_reactions(message, current_page, max_page)

        def check(reaction, user):
            return user == interaction.user and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                emoji = str(reaction.emoji)
                old_page = current_page

                if emoji == "⬅️" and current_page > 1:
                    current_page -= 1
                elif emoji == "➡️" and current_page < max_page:
                    current_page += 1
                
                if current_page != old_page:
                    embed, _ = await self.generate_leaderboard_page(interaction.guild, metric.value, current_page, interaction.user.id)
                    await message.edit(embed=embed)
                    await update_reactions(message, current_page, max_page)
                else:
                    await message.remove_reaction(reaction.emoji, user)

            except asyncio.TimeoutError:
                try: await message.clear_reactions()
                except: pass
                break

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))