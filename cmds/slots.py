import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime
from pymongo import ReturnDocument
from db.database import get_connection

# --- CONFIGURATION ---
NITRO_ROLE_ID = 1360260086500561237
MIN_BET = 25
JACKPOT_CONTRIBUTION = 1 # 5% of losing bets goes to the global jackpot
BASE_JACKPOT = 100000          # What the jackpot resets to after someone wins it

# Custom Emoji Strings
PAW_BROWN = "<:paw_brown:1506386117379883008>"
PAW_BLACK = "<:paw_black:1506386099482792037>"
PAW_WHITE = "<:paw_white:1506386132730908814>"
PAW_YELLOW = "<:paw_yellow:1506386002976051382>"
PAW_ORANGE = "<:paw_orange:1506385978527322252>"
PAW_RED = "<:paw_red:1506385961653637181>"
PAW_GREEN = "<:paw_green:1506385943043641415>"
PAW_BLUE = "<:paw_blue:1506386051634036868>"
PAW_PURPLE = "<:paw_purple:1506386067002097805>"
PAW_PINK = "<:paw_pink:1506386080637911142>"
GOLD_MOUSE = "<:gold_mouse:1506387138118287420>"

# Result Emotes
EMOTE_YES = "<:yes:1506394068513722428>"
EMOTE_EQUAL = "<:equal:1506394051409346724>"
EMOTE_BLUE_EQUAL = "<:blue_equal:1506397046754775080>"
EMOTE_UP = "<:up:1506396328559906886>"
EMOTE_DOWN = "<:down:1506396307470680246>"

# Emojis ordered from least rare to most rare
SLOT_SYMBOLS = [
    PAW_BROWN, PAW_BLACK, PAW_WHITE, PAW_YELLOW, PAW_ORANGE, 
    PAW_RED, PAW_GREEN, PAW_BLUE, PAW_PURPLE, PAW_PINK, GOLD_MOUSE
]

# Emojis and their corresponding payouts (Multiplier of the bet)
PAYOUTS = {
    PAW_BROWN: 1.5,
    PAW_BLACK: 2,
    PAW_WHITE: 3,
    PAW_YELLOW: 5,
    PAW_ORANGE: 8,
    PAW_RED: 12,
    PAW_GREEN: 20,
    PAW_BLUE: 35,
    PAW_PURPLE: 50,
    PAW_PINK: 75,
    GOLD_MOUSE: "JACKPOT"
}

# Weighted probabilities for selecting WHICH symbol wins in the 5% Win bucket
SYMBOL_WEIGHTS = [
    35.0,  # Brown (Common)
    20.0,  # Black
    15.0,  # White
    10.0,  # Yellow
    8.0,   # Orange
    5.0,   # Red
    3.0,   # Green
    2.0,   # Blue
    1.0,   # Purple
    0.8,   # Pink (Ultra Rare)
    0.2    # Gold Mouse (Jackpot)
]

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.gambling_col = self.db["gambling"]
        self.globals_col = self.db["globals"]
        self.logs_col = self.db["gambling_logs"]

    async def get_or_create_jackpot(self):
        """Fetches the current global jackpot or creates it if it doesn't exist."""
        data = await self.globals_col.find_one({"_id": "casino_jackpot"})
        if not data:
            await self.globals_col.insert_one({"_id": "casino_jackpot", "amount": BASE_JACKPOT})
            return BASE_JACKPOT
        return data.get("amount", BASE_JACKPOT)

    async def add_to_jackpot(self, amount: int) -> int:
        """Atomically adds a portion of lost bets to the global jackpot and returns the new total."""
        result = await self.globals_col.find_one_and_update(
            {"_id": "casino_jackpot"},
            {"$inc": {"amount": amount}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return result.get("amount", BASE_JACKPOT) if result else BASE_JACKPOT

    async def reset_jackpot(self):
        """Resets the global jackpot after it is won."""
        await self.globals_col.update_one(
            {"_id": "casino_jackpot"},
            {"$set": {"amount": BASE_JACKPOT}},
            upsert=True
        )

    async def update_gambling_stats(self, user_id: int, spent: int, won: int, spin_symbols: str):
        """Updates lifetime stats, tracks extreme highs/lows, and logs history for /casinostats."""
        net = won - spent
        now = datetime.utcnow()
        stats = await self.gambling_col.find_one({"discordId": user_id}) or {}
        
        biggest_win = stats.get("biggest_win", 0)
        biggest_loss = stats.get("biggest_loss", 0)
        
        if won > biggest_win:
            biggest_win = won
        if net < biggest_loss:
            biggest_loss = net 

        update_data = {
            "$inc": {
                "total_spent": spent,
                "total_won": won,
                "net_profit": net,
                "total_spins": 1
            },
            "$set": {
                "biggest_win": biggest_win,
                "biggest_loss": biggest_loss
            }
        }

        # Track the most recent wins and losses
        if net > 0:
            update_data["$set"]["last_win"] = {"amount": net, "symbols": spin_symbols, "timestamp": now}
        elif net < 0:
            update_data["$set"]["last_loss"] = {"amount": net, "symbols": spin_symbols, "timestamp": now}

        # 1. Update main gambling profile
        await self.gambling_col.update_one(
            {"discordId": user_id},
            update_data,
            upsert=True
        )

        # 2. Insert into history log for weekly/monthly calculations
        await self.logs_col.insert_one({
            "discordId": user_id,
            "spent": spent,
            "won": won,
            "net": net,
            "symbols": spin_symbols,
            "timestamp": now
        })

    def generate_spin(self):
        """
        Rolls for the outcome category first (5% Win, 50% Return, 45% Loss).
        Then generates the corresponding visual symbols to match.
        """
        outcome_roll = random.random()
        
        if outcome_roll < 0.05:
            # 5% Chance: WIN (Match 3)
            sym = random.choices(SLOT_SYMBOLS, weights=SYMBOL_WEIGHTS, k=1)[0]
            return [sym, sym, sym]
            
        elif outcome_roll < 0.55:
            # 50% Chance: NO CHANGE (Match 2)
            # Pick the symbol that matches
            sym1 = random.choices(SLOT_SYMBOLS, weights=SYMBOL_WEIGHTS, k=1)[0]
            # Pick a different symbol for the spoiler
            other_symbols = [s for s in SLOT_SYMBOLS if s != sym1]
            sym2 = random.choice(other_symbols)
            
            spin = [sym1, sym1, sym2]
            random.shuffle(spin) # Randomize placement (e.g. A-B-A, A-A-B, B-A-A)
            return spin
            
        else:
            # 45% Chance: LOSS (No Match)
            # Sample 3 completely distinct symbols
            return random.sample(SLOT_SYMBOLS, 3)

    def get_spin_message(self, spin, current_jackpot, bet_amount):
        s1, s2, s3 = spin[0], spin[1], spin[2]

        # 1. THE MEGA WIN
        if s1 == s2 == s3 == GOLD_MOUSE:
            return current_jackpot, f"🚨 **JACKPOT!** +{current_jackpot:,} <:leaf:1524758896659660831>"

        # 2. MATCH 3 (The regular dopamine hit)
        if s1 == s2 == s3:
            payout = int(bet_amount * PAYOUTS[s1]) # Ensures currency remains whole numbers
            return payout, f"{EMOTE_YES} {payout:,} <:leaf:1524758896659660831>"

        # 3. THE NEAR MISS (The psychological hook)
        if s1 == s2 or s2 == s3 or s1 == s3:
            match_symbol = s1 if s1 == s2 or s1 == s3 else s2
            
            if match_symbol == GOLD_MOUSE:
                teaser = f"😱 **SO CLOSE!** {bet_amount:,} <:leaf:1524758896659660831>"
            elif match_symbol == PAW_PINK:
                teaser = f"😩 *Oof...* {bet_amount:,} <:leaf:1524758896659660831>"
            else:
                teaser = f"{EMOTE_EQUAL} {bet_amount:,} <:leaf:1524758896659660831>"
                
            return bet_amount, teaser

        # 4. THE LOSS (Empty string so nothing displays)
        return 0, ""

    # ==========================================
    # THE UNIFIED /SLOTS COMMAND
    # ==========================================
    @app_commands.command(name="slots", description="Play the slots, check the jackpot, view odds, or view stats.")
    @app_commands.describe(
        action="Select a slots function",
        bet="Amount to wager (e.g. 25, 'all', 'half')",
        spins="Number of spins 1-25 (Nitro only, for 'Spin')"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="🎰 Spin", value="spin"),
        app_commands.Choice(name="🚨 Jackpot", value="jackpot"),
        app_commands.Choice(name="📊 Stats", value="stats"),
        app_commands.Choice(name="🎲 Odds", value="odds"),
        app_commands.Choice(name="❓ Help", value="help")
    ])
    async def slots(self, interaction: discord.Interaction, action: str, bet: str = "25", spins: int = 1):
        
        if action == "spin":
            await self._handle_spin(interaction, bet, spins)
        elif action == "jackpot":
            await self._handle_jackpot(interaction)
        elif action == "stats":
            await self._handle_stats(interaction)
        elif action == "odds":
            await self._handle_odds(interaction)
        elif action == "help":
            await self._handle_help(interaction)

    # --- ACTION HANDLERS ---

    async def _handle_spin(self, interaction: discord.Interaction, bet_str: str, spins: int):
        await interaction.response.defer()
        user_id = interaction.user.id

        if spins < 1 or spins > 25:
            return await interaction.followup.send("Error: Spin count must be between 1 and 25.", ephemeral=True)

        has_nitro = any(role.id == NITRO_ROLE_ID for role in interaction.user.roles)
        if spins > 1 and not has_nitro:
            return await interaction.followup.send("Error: Multi-spin functionality is restricted to Nitro Boosters.", ephemeral=True)

        # Parse the wager input
        user_data = await self.users_col.find_one({"discordId": user_id})
        current_balance = user_data.get("balance", 0) if user_data else 0

        bet_str = str(bet_str).lower().strip()
        
        if bet_str == "all":
            bet = current_balance // spins
        elif bet_str == "half":
            bet = (current_balance // 2) // spins
        else:
            try:
                bet = int(bet_str)
            except ValueError:
                return await interaction.followup.send("Error: Wager must be a valid number, 'all', or 'half'.", ephemeral=True)

        if bet < MIN_BET:
            return await interaction.followup.send(
                f"Error: Wager per spin must be at least {MIN_BET} <:leaf:1524758896659660831>. *(If you bet 'all'/'half' on multiple spins, your split balance may be too low).* ", 
                ephemeral=True
            )

        total_cost = bet * spins

        if current_balance < total_cost:
            return await interaction.followup.send(
                f"Error: Insufficient funds. Required: {total_cost:,} <:leaf:1524758896659660831>. Current Balance: {current_balance:,} <:leaf:1524758896659660831>", 
                ephemeral=True
            )

        await self.users_col.update_one({"discordId": user_id}, {"$inc": {"balance": -total_cost}})
        
        current_jackpot = await self.get_or_create_jackpot()
        total_winnings = 0
        jackpot_won = False
        jackpot_contribution = 0
        
        # We will store each spin result as a tuple: (payout_amount, string_representation)
        spin_results_list = []

        for i in range(spins):
            spin = self.generate_spin()
            payout, message = self.get_spin_message(spin, current_jackpot, bet)
            total_winnings += payout
            
            if payout == current_jackpot and spin[0] == GOLD_MOUSE:
                jackpot_won = True
                
            if payout == 0:
                jackpot_contribution += int(bet * JACKPOT_CONTRIBUTION)
                
            if message:
                spin_str = f"{''.join(spin)} {message}"
            else:
                spin_str = f"{''.join(spin)}"
                
            spin_results_list.append((payout, spin_str))
            
            # Logs the exact spin configuration to the database
            await self.update_gambling_stats(user_id, spent=bet, won=payout, spin_symbols=" | ".join(spin))

        # Sort the results so the highest payouts are at the top
        spin_results_list.sort(key=lambda x: x[0], reverse=True)
        spin_results_str = "\n".join([result[1] for result in spin_results_list])

        if total_winnings > 0:
            await self.users_col.update_one({"discordId": user_id}, {"$inc": {"balance": total_winnings}})
            
        if jackpot_won:
            await self.reset_jackpot()
            current_jackpot = BASE_JACKPOT
        elif jackpot_contribution > 0:
            # Safely and atomically increment the jackpot
            current_jackpot = await self.add_to_jackpot(jackpot_contribution)

        # Determine Embed Title & Color
        if total_winnings > total_cost:
            color = discord.Color.green()
            embed_title = "Slots Results: Profit"
        elif total_winnings < total_cost:
            color = discord.Color.red()
            embed_title = "Slots Results: Loss"
        else:
            color = discord.Color.gold()
            embed_title = "Slots Results: Even"

        if jackpot_won: 
            color = discord.Color.brand_green()

        embed = discord.Embed(title=embed_title, description=spin_results_str, color=color)
        embed.add_field(name="Wager", value=f"<:leaf:1524758896659660831> {total_cost:,}", inline=True)
        embed.add_field(name="Return", value=f"<:leaf:1524758896659660831> {total_winnings:,}", inline=True)
        
        # Format the Earnings Output
        net = total_winnings - total_cost
        if net > 0:
            net_str = f"{EMOTE_UP} +{net:,}"
        elif net < 0:
            net_str = f"{EMOTE_DOWN} {net:,}"
        else:
            net_str = f"{EMOTE_BLUE_EQUAL} 0"
            
        embed.add_field(name="Earnings", value=net_str, inline=True)
        embed.set_footer(text=f"Jackpot: {current_jackpot:,} Leaves")
        
        await interaction.followup.send(embed=embed)

    async def _handle_jackpot(self, interaction: discord.Interaction):
        jackpot = await self.get_or_create_jackpot()
        embed = discord.Embed(
            title="Progressive Jackpot Status",
            description=(
                f"**Current Pool:** {jackpot:,} <:leaf:1524758896659660831>\n\n"
                f"*Note: All losing wagers are contributed to this pool. A {GOLD_MOUSE} {GOLD_MOUSE} {GOLD_MOUSE} result awards the entire pool.*"
            ),
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

    async def _handle_stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        stats = await self.gambling_col.find_one({"discordId": interaction.user.id})
        
        if not stats:
            return await interaction.followup.send("No gambling records found for your account.", ephemeral=True)

        spent = stats.get("total_spent", 0)
        won = stats.get("total_won", 0)
        net = stats.get("net_profit", 0)
        spins = stats.get("total_spins", 0)
        biggest_win = stats.get("biggest_win", 0)
        biggest_loss = stats.get("biggest_loss", 0)

        color = discord.Color.green() if net >= 0 else discord.Color.red()

        embed = discord.Embed(title=f"Gambling Statistics: {interaction.user.display_name}", color=color)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Total Spins", value=f"{spins:,}", inline=False)
        embed.add_field(name="Total Wagered", value=f"{spent:,}", inline=True)
        embed.add_field(name="Total Returned", value=f"{won:,}", inline=True)
        
        # Calculate Earnings Output for Stats Screen
        if net > 0:
            lifetime_net_str = f"{EMOTE_UP} +{net:,}"
        elif net < 0:
            lifetime_net_str = f"{EMOTE_DOWN} {net:,}"
        else:
            lifetime_net_str = f"{EMOTE_BLUE_EQUAL} 0"
            
        embed.add_field(name="Lifetime Profit/Loss", value=lifetime_net_str, inline=False)
        embed.add_field(name="Largest Single Win", value=f"<:leaf:1524758896659660831> {biggest_win:,}", inline=True)
        embed.add_field(name="Largest Single Loss", value=f"<:leaf:1524758896659660831> {biggest_loss:,}", inline=True)

        await interaction.followup.send(embed=embed)

    async def _handle_odds(self, interaction: discord.Interaction):
        """Calculates and displays the exact probabilities of winning dynamically based on new 45/50/5 outcome forced logic."""
        total_weight = sum(SYMBOL_WEIGHTS)
        
        # Calculate probabilities of hitting specific Match 3s given the 5% overall bucket
        probs = {sym: (weight / total_weight) * 0.05 for sym, weight in zip(SLOT_SYMBOLS, SYMBOL_WEIGHTS)}
        
        embed = discord.Embed(
            title="🎰 Slot Machine Odds & Payouts",
            description="The slot machine forces a fixed outcome probability. Within the 5% Winning bracket, here are the odds for specific paws.",
            color=discord.Color.blurple()
        )
        
        # Split into two strings to avoid Discord's 1024 character limit per field
        match_3_text_1 = ""
        match_3_text_2 = ""
        
        for idx, (sym, win_chance) in enumerate(probs.items()):
            if win_chance > 0:
                one_in = int(round(1 / win_chance))
                percent = win_chance * 100
                
                payout = PAYOUTS.get(sym, 0)
                reward_str = f"🏆 **{payout}x Wager**" if isinstance(payout, (int, float)) else f"🚨 **{payout}**"
                text_to_add = f"**{sym} {sym} {sym}** ➔ {percent:.5f}% (1 in {one_in:,})\n└ *Reward:* {reward_str}\n\n"
                
                # First 6 symbols go in field 1, rest in field 2
                if idx < 6:
                    match_3_text_1 += text_to_add
                else:
                    match_3_text_2 += text_to_add
                
        embed.add_field(name="Match 3 Outcomes (Common) - 5% Total", value=match_3_text_1.strip(), inline=False)
        embed.add_field(name="Match 3 Outcomes (Rare)", value=match_3_text_2.strip(), inline=False)
        
        # Static probabilities based on the new logic
        embed.add_field(
            name="Match 2 Outcomes", 
            value=f"**Any 2 matching symbols** ➔ 50.00% (1 in 2)\n└ *Reward:* 🔄 **1x Wager** (Bet returned)", 
            inline=False
        )
        
        embed.add_field(
            name="No Match (Loss)", 
            value=f"**3 completely different symbols** ➔ 45.00% (1 in 2.22)\n└ *Reward:* ❌ **0x Wager** (Loss)", 
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

    async def _handle_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Slot Machine Documentation",
            description=(
                f"**Overview**\n"
                f"Wagers must be at least {MIN_BET} <:leaf:1524758896659660831> per spin. "
                f"Matching three symbols awards the specified multiplier. Matching two symbols returns the original wager.\n\n"
                f"**Usage**\n"
                f"`/slots action:Spin bet:100` - Spin the machine once for 100 Leaves.\n"
                f"`/slots action:Spin bet:all` - Bet your entire balance on a single spin.\n"
                f"`/slots action:Spin bet:half spins:5` - Bet half your balance split across 5 consecutive spins *(Nitro Boosters Only)*."
            ),
            color=discord.Color.gold()
        )
        
        # Split payouts to avoid the 1024 character limit on embed fields
        payouts_list = [f"{symbol} {symbol} {symbol} ➔ **{multiplier}x** Wager" for symbol, multiplier in PAYOUTS.items() if multiplier != "JACKPOT"]
        
        payout_str_1 = "\n".join(payouts_list[:6])
        payout_str_2 = "\n".join(payouts_list[6:])
        payout_str_2 += f"\n{GOLD_MOUSE} {GOLD_MOUSE} {GOLD_MOUSE} ➔ **Progressive Jackpot**"
        
        embed.add_field(name="Payout Table (Common Paws)", value=payout_str_1, inline=False)
        embed.add_field(name="Payout Table (Rare Paws)", value=payout_str_2, inline=False)
        embed.add_field(name="Match 2", value="Any 2 matching symbols ➔ **1x** (Wager returned)", inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Slots(bot))