import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime
from pymongo import ReturnDocument
from db.database import get_connection

# --- CONFIGURATION ---
DAILY_LIMIT = 5
BYPASS_ROLE_ID = 1360260086500561237

# Foil Progression Emojis
# If you upload custom images to your server, replace these with the Discord ID format: "<:name:1234567890>"
FOIL_FULL = "⬛"
FOIL_SCRATCHED_1 = "▓"
FOIL_SCRATCHED_2 = "▒"

# Authentic themed scratchcards with real-world brutal odds.
# Most wins are heavily weighted towards 1.0x (Break Even / "Free Ticket")
TICKETS = {
    "bronze": {
        "name": "🍀 Lucky 7s",
        "cost": 50,
        "win_chance": 0.22,  # 1 in 4.54
        "payouts": {
            "🎟️": {"mult": 1.0, "weight": 60},  # Free Ticket (Break Even)
            "🍒": {"mult": 2.0, "weight": 25},
            "🍉": {"mult": 5.0, "weight": 10},
            "🔔": {"mult": 10.0, "weight": 4},
            "7️⃣": {"mult": 50.0, "weight": 1},
        }
    },
    "silver": {
        "name": "💸 10X Cash Multiplier",
        "cost": 250,
        "win_chance": 0.24,  # 1 in 4.16
        "payouts": {
            "🎟️": {"mult": 1.0, "weight": 55},
            "💵": {"mult": 2.0, "weight": 25},
            "💰": {"mult": 5.0, "weight": 12},
            "🎰": {"mult": 10.0, "weight": 7},
            "✖️": {"mult": 100.0, "weight": 1},
        }
    },
    "gold": {
        "name": "🌟 24K Gold Rush",
        "cost": 1000,
        "win_chance": 0.26,  # 1 in 3.84
        "payouts": {
            "🎟️": {"mult": 1.0, "weight": 50},
            "🪙": {"mult": 2.0, "weight": 25},
            "⭐": {"mult": 5.0, "weight": 15},
            "🔥": {"mult": 25.0, "weight": 8},
            "👑": {"mult": 250.0, "weight": 2},
        }
    },
    "nitro": {
        "name": "💎 Black Diamond",
        "cost": 2500,
        "win_chance": 0.28,  # 1 in 3.57
        "payouts": {
            "🎟️": {"mult": 1.0, "weight": 45},
            "💳": {"mult": 2.0, "weight": 25},
            "🥂": {"mult": 10.0, "weight": 15},
            "💎": {"mult": 50.0, "weight": 10},
            "🌌": {"mult": 2500.0, "weight": 1}, # The Grand Jackpot
        }
    }
}

class PlayAgainButton(discord.ui.Button):
    def __init__(self, cog, user, ticket_id):
        self.cog = cog
        self.user = user
        self.ticket_id = ticket_id
        ticket = TICKETS[ticket_id]
        
        super().__init__(style=discord.ButtonStyle.success, label=f"Buy Another ({ticket['cost']:,} Leaves)", emoji="🔄", row=3)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            return await interaction.response.send_message("Hey! Buy your own ticket!", ephemeral=True)
        await self.cog._handle_play(interaction, self.ticket_id)

class ScratchButton(discord.ui.Button):
    def __init__(self, x, y, hidden_emoji, view):
        super().__init__(style=discord.ButtonStyle.secondary, label=FOIL_FULL, row=y)
        self.x = x
        self.y = y
        self.hidden_emoji = hidden_emoji
        self.scratch_view = view
        self.scratch_level = 0  # 0=Full, 1=Scratch1, 2=Scratch2, 3=Revealed

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.scratch_view.user:
            return await interaction.response.send_message("Hey! Buy your own ticket!", ephemeral=True)
        
        self.scratch_level += 1
        
        if self.scratch_level == 1:
            self.label = FOIL_SCRATCHED_1
            await interaction.response.edit_message(view=self.scratch_view)
        elif self.scratch_level == 2:
            self.label = FOIL_SCRATCHED_2
            await interaction.response.edit_message(view=self.scratch_view)
        elif self.scratch_level == 3:
            self.label = self.hidden_emoji
            self.style = discord.ButtonStyle.primary
            self.disabled = True
            
            self.scratch_view.scratched_count += 1
            self.scratch_view.revealed_symbols.append(self.hidden_emoji)
            
            await self.scratch_view.check_game_state(interaction)

class ScratchoffView(discord.ui.View):
    def __init__(self, cog, interaction, ticket_id, grid, winning_symbol):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.original_interaction = interaction
        self.user = interaction.user
        self.ticket_id = ticket_id
        self.ticket_data = TICKETS[ticket_id]
        self.bet = self.ticket_data["cost"]
        
        self.grid = grid
        self.winning_symbol = winning_symbol
        self.game_over = False
        
        self.scratched_count = 0
        self.revealed_symbols = []
        
        for i, symbol in enumerate(self.grid):
            row = i // 3
            self.add_item(ScratchButton(x=i, y=row, hidden_emoji=symbol, view=self))

    async def on_timeout(self):
        if not self.game_over:
            self.game_over = True
            for child in self.children:
                child.disabled = True
            await self.cog.resolve_game(self.original_interaction, self.user, self.ticket_id, self, is_timeout=True)

    @discord.ui.button(label="Auto-Scratch All", style=discord.ButtonStyle.success, emoji="🪙", row=3)
    async def reveal_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("Hey! Buy your own ticket!", ephemeral=True)
        await self.cog.resolve_game(interaction, self.user, self.ticket_id, self)

    async def check_game_state(self, interaction: discord.Interaction):
        counts = {}
        for sym in self.revealed_symbols:
            counts[sym] = counts.get(sym, 0) + 1
            if counts[sym] == 3:
                return await self.cog.resolve_game(interaction, self.user, self.ticket_id, self, forced_win_symbol=sym)
                
        if self.scratched_count == 9:
            return await self.cog.resolve_game(interaction, self.user, self.ticket_id, self)
            
        embed = self.cog.build_embed(self.user, self.ticket_id, is_playing=True)
        await interaction.response.edit_message(embed=embed, view=self)


class Scratchoff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.gambling_col = self.db["gambling"]
        self.logs_col = self.db["gambling_logs"]
        self.globals_col = self.db["globals"]

    def generate_ticket(self, ticket_id):
        ticket = TICKETS[ticket_id]
        symbols_list = list(ticket["payouts"].keys())
        grid = []
        
        is_winner = random.random() < ticket["win_chance"]
        winning_sym = None

        if is_winner:
            weights = [ticket["payouts"][s]["weight"] for s in symbols_list]
            winning_sym = random.choices(symbols_list, weights=weights, k=1)[0]
            grid.extend([winning_sym] * 3)
            
            remaining_slots = 6
            while remaining_slots > 0:
                filler = random.choice(symbols_list)
                if filler != winning_sym and grid.count(filler) < 2:
                    grid.append(filler)
                    remaining_slots -= 1
        else:
            # NEAR MISS ENGINE: Tease the player with high multipliers
            sorted_symbols = sorted(symbols_list, key=lambda s: ticket["payouts"][s]["mult"], reverse=True)
            tease_sym = random.choice(sorted_symbols[:2]) # Pick one of the top 2 symbols
            
            grid.extend([tease_sym, tease_sym])
            
            remaining_slots = 7
            while remaining_slots > 0:
                filler = random.choice(symbols_list)
                if grid.count(filler) < 2:
                    grid.append(filler)
                    remaining_slots -= 1
                    
        random.shuffle(grid)
        return grid, winning_sym

    async def add_to_jackpot(self, amount: int):
        await self.globals_col.find_one_and_update(
            {"_id": "casino_jackpot"},
            {"$inc": {"amount": amount}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    def build_embed(self, user, ticket_id, is_playing=True, won_amount=0, winning_symbol=None):
        ticket = TICKETS[ticket_id]
        
        if is_playing:
            color = discord.Color.blurple()
            desc = "**Scratch the foil!** Click the blocks multiple times to scratch them off. Find **3 matching symbols** to win."
        elif won_amount > 0:
            color = discord.Color.green()
            if won_amount == ticket["cost"]:
                desc = f"🎟️ **FREE TICKET!** You matched three {winning_symbol} and won your **{won_amount:,} <:leaf:1524758896659660831>** back!"
            else:
                desc = f"🎉 **WINNER!** You matched three {winning_symbol} and won **{won_amount:,} <:leaf:1524758896659660831>**!"
        else:
            color = discord.Color.red()
            desc = "❌ **Tough luck!** Not a winning ticket."

        embed = discord.Embed(title=ticket["name"], description=desc, color=color)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        
        # Build the dynamic Prize Legend
        legend_parts = [f"{sym} **{data['mult']}x**" for sym, data in ticket["payouts"].items()]
        embed.add_field(name="Prize Legend", value="> " + " | ".join(legend_parts), inline=False)
        
        embed.set_footer(text=f"Ticket Cost: {ticket['cost']:,} Leaves | Match 3 to Win")
        return embed

    async def update_gambling_stats(self, user_id: int, spent: int, won: int, symbols: str):
        net = won - spent
        now = datetime.utcnow()
        stats = await self.gambling_col.find_one({"discordId": user_id}) or {}
        
        biggest_win = stats.get("biggest_win", 0)
        biggest_loss = stats.get("biggest_loss", 0)
        
        if won > biggest_win: biggest_win = won
        if net < biggest_loss: biggest_loss = net 

        update_data = {
            "$inc": {"total_spent": spent, "total_won": won, "net_profit": net, "total_spins": 1},
            "$set": {"biggest_win": biggest_win, "biggest_loss": biggest_loss}
        }

        if net > 0:
            update_data["$set"]["last_win"] = {"amount": net, "symbols": f"Scratch: {symbols}", "timestamp": now}
        elif net < 0:
            update_data["$set"]["last_loss"] = {"amount": net, "symbols": f"Scratch: {symbols}", "timestamp": now}

        await self.gambling_col.update_one({"discordId": user_id}, update_data, upsert=True)
        await self.logs_col.insert_one({
            "discordId": user_id, "spent": spent, "won": won, "net": net, 
            "symbols": f"Scratch: {symbols}", "timestamp": now, "game": "scratchoff"
        })

    async def resolve_game(self, interaction, user, ticket_id, view, is_timeout=False, forced_win_symbol=None):
        view.game_over = True
        ticket = TICKETS[ticket_id]
        bet = ticket["cost"]
        
        buttons_to_remove = []
        
        for child in view.children:
            if isinstance(child, ScratchButton):
                child.label = child.hidden_emoji
                child.disabled = True
                
                sym = forced_win_symbol or view.winning_symbol
                if sym and child.hidden_emoji == sym:
                    child.style = discord.ButtonStyle.success
                else:
                    child.style = discord.ButtonStyle.secondary
            else:
                buttons_to_remove.append(child)

        for btn in buttons_to_remove:
            view.remove_item(btn)

        if not is_timeout:
            view.add_item(PlayAgainButton(self, user, ticket_id))

        payout = 0
        final_sym = forced_win_symbol or view.winning_symbol
        
        if final_sym:
            multiplier = ticket["payouts"][final_sym]["mult"]
            payout = int(bet * multiplier)
            await self.users_col.update_one({"discordId": user.id}, {"$inc": {"balance": payout}})
        else:
            await self.add_to_jackpot(bet)

        formatted_grid = "".join(view.grid[:3]) + " | " + "".join(view.grid[3:6]) + " | " + "".join(view.grid[6:])
        await self.update_gambling_stats(user.id, bet, payout, formatted_grid)

        embed = self.build_embed(user, ticket_id, is_playing=False, won_amount=payout, winning_symbol=final_sym)
        if is_timeout:
            embed.description += "\n*(Ticket auto-revealed due to timeout)*"

        if interaction.response.is_done():
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except discord.errors.NotFound:
                await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    # ==========================================
    # THE UNIFIED /SCRATCHOFF COMMAND
    # ==========================================
    @app_commands.command(name="scratchoff", description="Buy a scratch-off ticket or view the win probabilities.")
    @app_commands.describe(
        action="Select whether to play a game or view the ticket odds",
        ticket_type="Select a ticket tier (Required if choosing 'Play')"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="🎟️ Buy & Play", value="play"),
            app_commands.Choice(name="📊 View Odds", value="odds")
        ],
        ticket_type=[
            app_commands.Choice(name="🍀 Lucky 7s (50 Leaves)", value="bronze"),
            app_commands.Choice(name="💸 10X Cash Multiplier (250 Leaves)", value="silver"),
            app_commands.Choice(name="🌟 24K Gold Rush (1000 Leaves)", value="gold"),
            app_commands.Choice(name="💎 Black Diamond [Nitro Exclusive] (2500 Leaves)", value="nitro")
        ]
    )
    async def scratchoff(self, interaction: discord.Interaction, action: str, ticket_type: str = "bronze"):
        if action == "play":
            await self._handle_play(interaction, ticket_type)
        elif action == "odds":
            await self._handle_odds(interaction)

    # --- ACTION HANDLERS ---

    async def _handle_play(self, interaction: discord.Interaction, ticket_type: str):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        ticket = TICKETS[ticket_type]
        bet = ticket["cost"]

        if ticket_type == "nitro":
            has_role = False
            if hasattr(interaction.user, "roles"):
                has_role = any(role.id == BYPASS_ROLE_ID for role in interaction.user.roles)
            if not has_role:
                return await interaction.followup.send(
                    "❌ **Access Denied!** The `💎 Black Diamond` scratchcard is exclusively available to Nitro members.", 
                    ephemeral=True
                )

        user_data = await self.users_col.find_one({"discordId": user_id}) or {}
        current_balance = user_data.get("balance", 0)

        if current_balance < bet:
            return await interaction.followup.send(
                f"Error: Insufficient funds for a {ticket['name']} ticket. Required: {bet:,} <:leaf:1524758896659660831>. Balance: {current_balance:,} <:leaf:1524758896659660831>", 
                ephemeral=True
            )

        has_bypass = False
        if hasattr(interaction.user, "roles"):
            has_bypass = any(role.id == BYPASS_ROLE_ID for role in interaction.user.roles)

        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        scratch_data = user_data.get("scratch_data", {"date": today_str, "count": 0})
        
        if scratch_data.get("date") != today_str:
            scratch_data = {"date": today_str, "count": 0}

        if not has_bypass and scratch_data["count"] >= DAILY_LIMIT:
            return await interaction.followup.send(
                f"❌ You have reached your daily limit of **{DAILY_LIMIT} scratch-offs**. Come back tomorrow or get Nitro for unlimited plays!", 
                ephemeral=True
            )

        scratch_data["count"] += 1
        await self.users_col.update_one(
            {"discordId": user_id}, 
            {
                "$inc": {"balance": -bet},
                "$set": {"scratch_data": scratch_data}
            }
        )

        grid, winning_sym = self.generate_ticket(ticket_type)

        view = ScratchoffView(self, interaction, ticket_type, grid, winning_sym)
        embed = self.build_embed(interaction.user, ticket_type, is_playing=True)

        if interaction.message:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    async def _handle_odds(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Scratch-Off Commission: Win Odds & Prize Tables",
            description="All lottery tickets follow calibrated configurations imitating actual public payout distribution sheets.",
            color=discord.Color.blurple()
        )

        for key, card in TICKETS.items():
            pct = card["win_chance"] * 100
            ratio = 100 / (card["win_chance"] * 100)
            
            payout_lines = []
            for sym, details in card["payouts"].items():
                payout_lines.append(f"{sym} `{details['mult']}x`")
                
            payout_str = " | ".join(payout_lines)
            
            if key == "nitro":
                title_str = f"{card['name']} (Cost: {card['cost']} <:leaf:1524758896659660831>) 🔒 Nitro Exclusive"
            else:
                title_str = f"{card['name']} (Cost: {card['cost']} <:leaf:1524758896659660831>)"
            
            embed.add_field(
                name=title_str,
                value=f"> **Overall Win Chance:** `{pct:.1f}%` *(approx. 1 in {ratio:.2f})*\n> **Rewards:** {payout_str}",
                inline=False
            )

        embed.add_field(
            name="📜 Purchase Limits",
            value=(
                f"• Regular players are restricted to **{DAILY_LIMIT} purchases per day**.\n"
                f"• **Nitro** members receive an **unlimited bypass** on all lotto queues."
            ),
            inline=False
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Scratchoff(bot))