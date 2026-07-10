import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from typing import Optional
from db.database import get_connection

class CasinoStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.gambling_col = self.db["gambling"]
        self.logs_col = self.db["gambling_logs"]
        self.globals_col = self.db["globals"]

    def format_net(self, amount: int) -> str:
        """Formats net profit with a plus or minus sign."""
        if amount > 0:
            return f"📈 +{amount:,}"
        elif amount < 0:
            return f"📉 {amount:,}"
        return "⚖️ 0"

    async def get_current_jackpot(self) -> int:
        """Fetches the current progressive jackpot amount."""
        data = await self.globals_col.find_one({"_id": "casino_jackpot"})
        return data.get("amount", 5000) if data else 5000

    @app_commands.command(name="casinostats", description="View casino statistics for the entire server or a specific player.")
    @app_commands.describe(user="The user to view stats for (leave blank for server-wide stats)")
    async def casinostats(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await interaction.response.defer()

        # Route to the appropriate handler based on whether a user was provided
        if user is None:
            await self._handle_server_stats(interaction)
        else:
            await self._handle_user_stats(interaction, user)

    # ==========================================
    # SERVER-WIDE STATS
    # ==========================================
    async def _handle_server_stats(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # 1. Lifetime Server Aggregation
        pipeline_lifetime = [
            {"$group": {
                "_id": None,
                "total_spent": {"$sum": "$total_spent"},
                "total_won": {"$sum": "$total_won"},
                "total_spins": {"$sum": "$total_spins"}, # Kept field name same for DB backwards compatibility
                "biggest_win": {"$max": "$biggest_win"},
                "biggest_loss": {"$min": "$biggest_loss"} 
            }}
        ]
        lifetime_res = await self.gambling_col.aggregate(pipeline_lifetime).to_list(length=1)
        
        if not lifetime_res:
            return await interaction.followup.send("No gambling records exist on this server yet.")
            
        life = lifetime_res[0]
        life_net = life["total_won"] - life["total_spent"]

        # 2. Time-Based Server Aggregation (Weekly & Monthly)
        pipeline_time = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$facet": {
                "monthly": [
                    {"$group": {
                        "_id": None,
                        "spent": {"$sum": "$spent"},
                        "won": {"$sum": "$won"},
                        "net": {"$sum": "$net"}
                    }}
                ],
                "weekly": [
                    {"$match": {"timestamp": {"$gte": seven_days_ago}}},
                    {"$group": {
                        "_id": None,
                        "spent": {"$sum": "$spent"},
                        "won": {"$sum": "$won"},
                        "net": {"$sum": "$net"}
                    }}
                ]
            }}
        ]
        time_res = await self.logs_col.aggregate(pipeline_time).to_list(length=1)
        
        month_data = time_res[0].get("monthly", [])
        m_spent = month_data[0]["spent"] if month_data else 0
        m_won = month_data[0]["won"] if month_data else 0
        m_net = month_data[0]["net"] if month_data else 0

        week_data = time_res[0].get("weekly", [])
        w_spent = week_data[0]["spent"] if week_data else 0
        w_won = week_data[0]["won"] if week_data else 0
        w_net = week_data[0]["net"] if week_data else 0

        # 3. Get Current Jackpot
        current_jackpot = await self.get_current_jackpot()

        # 4. Build Embed
        # For the server, a negative net profit means the House (the server) is winning.
        embed = discord.Embed(
            title="🎲 Global Casino Statistics", 
            description="Overall economic health and activity of the server's casino (Slots, Blackjack, & Crash).",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="📊 Lifetime Server Economy",
            value=(
                f"**Games Played:** {life.get('total_spins', 0):,}\n"
                f"**Total Wagered:** <:leaf:1524758896659660831> {life.get('total_spent', 0):,}\n"
                f"**Total Paid Out:** <:leaf:1524758896659660831> {life.get('total_won', 0):,}\n"
                f"**House Profit/Loss:** {self.format_net(life_net * -1)}" 
            ),
            inline=False
        )

        embed.add_field(
            name="📅 Last 30 Days",
            value=(
                f"**Wagered:** <:leaf:1524758896659660831> {m_spent:,}\n"
                f"**Paid Out:** <:leaf:1524758896659660831> {m_won:,}\n"
                f"**House Net:** {self.format_net(m_net * -1)}"
            ),
            inline=True
        )
        embed.add_field(
            name="📆 Last 7 Days",
            value=(
                f"**Wagered:** <:leaf:1524758896659660831> {w_spent:,}\n"
                f"**Paid Out:** <:leaf:1524758896659660831> {w_won:,}\n"
                f"**House Net:** {self.format_net(w_net * -1)}"
            ),
            inline=True
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False) # Visual break

        embed.add_field(name="🚨 Progressive Jackpot", value=f"<:leaf:1524758896659660831> {current_jackpot:,}", inline=True)
        embed.add_field(name="📈 Largest Win", value=f"<:leaf:1524758896659660831> {life.get('biggest_win', 0):,}", inline=True)
        embed.add_field(name="📉 Largest Loss", value=f"<:leaf:1524758896659660831> {life.get('biggest_loss', 0):,}", inline=True)

        await interaction.followup.send(embed=embed)


    # ==========================================
    # INDIVIDUAL USER STATS
    # ==========================================
    async def _handle_user_stats(self, interaction: discord.Interaction, target_user: discord.User):
        user_id = target_user.id

        # 1. Fetch Lifetime Data
        lifetime_stats = await self.gambling_col.find_one({"discordId": user_id})
        if not lifetime_stats:
            return await interaction.followup.send(f"No gambling records found for **{target_user.display_name}**.")

        # 2. Fetch Time-Based Data via Aggregation
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        pipeline = [
            {"$match": {"discordId": user_id, "timestamp": {"$gte": thirty_days_ago}}},
            {"$facet": {
                "monthly": [
                    {"$group": {
                        "_id": None,
                        "spent": {"$sum": "$spent"},
                        "won": {"$sum": "$won"},
                        "net": {"$sum": "$net"}
                    }}
                ],
                "weekly": [
                    {"$match": {"timestamp": {"$gte": seven_days_ago}}},
                    {"$group": {
                        "_id": None,
                        "spent": {"$sum": "$spent"},
                        "won": {"$sum": "$won"},
                        "net": {"$sum": "$net"}
                    }}
                ]
            }}
        ]
        
        agg_result = await self.logs_col.aggregate(pipeline).to_list(length=1)
        
        month_data = agg_result[0].get("monthly", [])
        m_spent = month_data[0]["spent"] if month_data else 0
        m_won = month_data[0]["won"] if month_data else 0
        m_net = month_data[0]["net"] if month_data else 0

        week_data = agg_result[0].get("weekly", [])
        w_spent = week_data[0]["spent"] if week_data else 0
        w_won = week_data[0]["won"] if week_data else 0
        w_net = week_data[0]["net"] if week_data else 0

        # 3. Extract Last Win / Last Loss
        last_win = lifetime_stats.get("last_win", {})
        last_loss = lifetime_stats.get("last_loss", {})

        last_win_str = f"{last_win.get('amount', 0):,} <:leaf:1524758896659660831>\n`{last_win.get('symbols', 'Unknown')}`" if last_win else "None recorded"
        last_loss_str = f"{abs(last_loss.get('amount', 0)):,} <:leaf:1524758896659660831>\n`{last_loss.get('symbols', 'Unknown')}`" if last_loss else "None recorded"

        # 4. Build Embed
        color = discord.Color.green() if lifetime_stats.get("net_profit", 0) >= 0 else discord.Color.red()
        embed = discord.Embed(title=f"🎲 Casino Profile: {target_user.display_name}", color=color)
        embed.set_thumbnail(url=target_user.display_avatar.url)

        embed.add_field(
            name="📊 Lifetime Overall",
            value=(
                f"**Games Played:** {lifetime_stats.get('total_spins', 0):,}\n"
                f"**Wagered:** <:leaf:1524758896659660831> {lifetime_stats.get('total_spent', 0):,}\n"
                f"**Returned:** <:leaf:1524758896659660831> {lifetime_stats.get('total_won', 0):,}\n"
                f"**Net Profit:** {self.format_net(lifetime_stats.get('net_profit', 0))}"
            ),
            inline=False
        )

        embed.add_field(
            name="📅 Last 30 Days",
            value=(
                f"**Wagered:** <:leaf:1524758896659660831> {m_spent:,}\n"
                f"**Returned:** <:leaf:1524758896659660831> {m_won:,}\n"
                f"**Net Profit:** {self.format_net(m_net)}"
            ),
            inline=True
        )
        embed.add_field(
            name="📆 Last 7 Days",
            value=(
                f"**Wagered:** <:leaf:1524758896659660831> {w_spent:,}\n"
                f"**Returned:** <:leaf:1524758896659660831> {w_won:,}\n"
                f"**Net Profit:** {self.format_net(w_net)}"
            ),
            inline=True
        )

        embed.add_field(name="🏆 Last Win", value=last_win_str, inline=True)
        embed.add_field(name="💔 Last Loss", value=last_loss_str, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) 

        embed.add_field(name="📈 Largest Win", value=f"<:leaf:1524758896659660831> {lifetime_stats.get('biggest_win', 0):,}", inline=True)
        embed.add_field(name="📉 Largest Loss", value=f"<:leaf:1524758896659660831> {lifetime_stats.get('biggest_loss', 0):,}", inline=True)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CasinoStats(bot))