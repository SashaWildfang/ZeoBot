import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime
from pymongo import ReturnDocument
from db.database import get_connection

# --- CONFIGURATION ---
MIN_BET = 25
BLACKJACK_PAYOUT = 2.5  # 1.5x profit (Original bet + 1.5x)
WIN_PAYOUT = 2.0        # 1.0x profit (Original bet + 1x)

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, 
    "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11
}

def calculate_hand(hand):
    """Calculates the best possible value of a blackjack hand."""
    value = sum(card['value'] for card in hand)
    aces = sum(1 for card in hand if card['rank'] == 'A')
    
    while value > 21 and aces:
        value -= 10
        aces -= 1
        
    return value

class PlayAgainView(discord.ui.View):
    def __init__(self, cog, user, bet):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.user = user
        self.bet = bet
        
        # Dynamically set the label to show the wager amount (Using text "Leaves" since custom emotes don't render in button text)
        self.play_again.label = f"Play Again ({self.bet:,} Leaves)"

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="🔄")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("This isn't your table!", ephemeral=True)
        
        # Start a new game with the same base bet
        await self.cog._handle_play(interaction, self.bet)

class BlackjackView(discord.ui.View):
    def __init__(self, cog, interaction, bet, player_hand, dealer_hand, deck):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.original_interaction = interaction
        self.user = interaction.user
        self.dealer_hand = dealer_hand
        self.deck = deck
        self.game_over = False
        
        # Track multiple hands and corresponding bets for Splitting/Doubling
        self.player_hands = [player_hand]
        self.bets = [bet]
        self.current_hand_index = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your table!", ephemeral=True)
            return False
        return True

    async def update_button_states(self):
        """Dynamically enables/disables special action buttons based on eligibility."""
        current_hand = self.player_hands[self.current_hand_index]
        
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "Double Down":
                    child.disabled = len(current_hand) != 2
                elif child.label == "Split":
                    child.disabled = not (
                        len(self.player_hands) == 1 and 
                        len(current_hand) == 2 and 
                        current_hand[0]['value'] == current_hand[1]['value']
                    )

    async def on_timeout(self):
        if not self.game_over:
            self.game_over = True
            for child in self.children:
                child.disabled = True
            
            results = ["timeout"] * len(self.player_hands)
            await self.cog.resolve_game_multiple(
                self.original_interaction, self.user, self.bets, 
                self.player_hands, self.dealer_hand, results, self
            )

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.success)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_hand = self.player_hands[self.current_hand_index]
        current_hand.append(self.deck.pop())
        player_value = calculate_hand(current_hand)

        if player_value > 21:
            if self.current_hand_index < len(self.player_hands) - 1:
                self.current_hand_index += 1
                await self.update_button_states()
                embed = self.cog.build_embed(self.user, self.bets, self.player_hands, self.dealer_hand, self.current_hand_index, hidden_dealer=True)
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await self.finish_game(interaction)
        else:
            await self.update_button_states()
            embed = self.cog.build_embed(self.user, self.bets, self.player_hands, self.dealer_hand, self.current_hand_index, hidden_dealer=True)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.danger)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_hand_index < len(self.player_hands) - 1:
            self.current_hand_index += 1
            await self.update_button_states()
            embed = self.cog.build_embed(self.user, self.bets, self.player_hands, self.dealer_hand, self.current_hand_index, hidden_dealer=True)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await self.finish_game(interaction)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.primary)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_data = await self.cog.users_col.find_one({"discordId": self.user.id})
        current_balance = user_data.get("balance", 0) if user_data else 0
        current_bet = self.bets[self.current_hand_index]

        if current_balance < current_bet:
            return await interaction.response.send_message(f"❌ Insufficient funds to Double Down! Required: {current_bet:,} <:leaf:1524758896659660831>", ephemeral=True)

        await self.cog.users_col.update_one({"discordId": self.user.id}, {"$inc": {"balance": -current_bet}})
        self.bets[self.current_hand_index] *= 2

        current_hand = self.player_hands[self.current_hand_index]
        current_hand.append(self.deck.pop())

        if self.current_hand_index < len(self.player_hands) - 1:
            self.current_hand_index += 1
            await self.update_button_states()
            embed = self.cog.build_embed(self.user, self.bets, self.player_hands, self.dealer_hand, self.current_hand_index, hidden_dealer=True)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await self.finish_game(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.secondary)
    async def split(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_data = await self.cog.users_col.find_one({"discordId": self.user.id})
        current_balance = user_data.get("balance", 0) if user_data else 0
        base_bet = self.bets[0]

        if current_balance < base_bet:
            return await interaction.response.send_message(f"❌ Insufficient funds to Split! Required: {base_bet:,} <:leaf:1524758896659660831>", ephemeral=True)

        await self.cog.users_col.update_one({"discordId": self.user.id}, {"$inc": {"balance": -base_bet}})
        
        card1 = self.player_hands[0][0]
        card2 = self.player_hands[0][1]
        
        self.player_hands = [
            [card1, self.deck.pop()],
            [card2, self.deck.pop()]
        ]
        self.bets = [base_bet, base_bet]
        
        await self.update_button_states()
        embed = self.cog.build_embed(self.user, self.bets, self.player_hands, self.dealer_hand, self.current_hand_index, hidden_dealer=True)
        await interaction.response.edit_message(embed=embed, view=self)

    async def finish_game(self, interaction: discord.Interaction):
        self.game_over = True

        active_values = [calculate_hand(h) for h in self.player_hands if calculate_hand(h) <= 21]

        if active_values:
            max_player_val = max(active_values)
            
            # --- THE "SMART HOUSE" DEALER LOGIC ---
            while True:
                d_val = calculate_hand(self.dealer_hand)
                
                # Stop if dealer busted or hit 21
                if d_val >= 21:
                    break
                    
                # Stop if the dealer is beating the player's best hand
                if d_val > max_player_val:
                    break
                    
                # If dealer is tying the player
                if d_val == max_player_val:
                    if d_val >= 17:
                        # Safely accept the push (hitting on 17+ is statistically too risky even for a smart dealer)
                        break
                    else:
                        # Don't settle for a low push (like 15 vs 15), keep hitting
                        self.dealer_hand.append(self.deck.pop())
                        continue
                
                # If the dealer is LOSING to the player, they MUST hit.
                # Standing guarantees a loss, so a smart dealer will hit a 17 or 18 if the player has 19 or 20!
                if d_val < max_player_val:
                    self.dealer_hand.append(self.deck.pop())

        dealer_value = calculate_hand(self.dealer_hand)
        
        results = []
        for hand in self.player_hands:
            p_val = calculate_hand(hand)
            if p_val > 21:
                results.append("bust")
            elif dealer_value > 21:
                results.append("dealer_bust")
            elif p_val == dealer_value:
                results.append("push")
            elif p_val > dealer_value:
                if p_val == 21 and len(hand) == 2 and len(self.player_hands) == 1:
                    results.append("blackjack")
                else:
                    results.append("win")
            else:
                results.append("loss")

        await self.cog.resolve_game_multiple(
            interaction, self.user, self.bets, 
            self.player_hands, self.dealer_hand, results, self
        )


class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.gambling_col = self.db["gambling"]
        self.logs_col = self.db["gambling_logs"]
        self.globals_col = self.db["globals"]

    def create_deck(self):
        deck = [{"rank": r, "suit": s, "value": v} for s in SUITS for r, v in RANKS.items()]
        random.shuffle(deck)
        return deck

    def format_single_card(self, card):
        return f"`{card['suit']} {card['rank']}`"

    def format_hand(self, hand, hidden=False):
        if hidden:
            return f"{self.format_single_card(hand[0])} `❓ ?`"
        return " ".join([self.format_single_card(card) for card in hand])

    async def add_to_jackpot(self, amount: int):
        await self.globals_col.find_one_and_update(
            {"_id": "casino_jackpot"},
            {"$inc": {"amount": amount}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    def build_embed(self, user, bets, player_hands, dealer_hand, current_index=0, hidden_dealer=True, final_statuses=None):
        if hidden_dealer:
            dealer_val_display = f"{dealer_hand[0]['value']} + ?"
        else:
            dealer_val_display = str(calculate_hand(dealer_hand))

        color = discord.Color.blurple()
        status_msg = "🟢 **Your Turn** - *Choose an action...*"
        
        if final_statuses:
            if any(s in ["win", "blackjack", "dealer_bust"] for s in final_statuses):
                color = discord.Color.green()
                status_msg = "🎉 **Game Finished!**"
            elif all(s in ["loss", "bust", "timeout"] for s in final_statuses):
                color = discord.Color.red()
                status_msg = "❌ **Dealer Wins.**"
            else:
                color = discord.Color.gold()
                status_msg = "🤝 **Game Finished (Push or Mixed)**"

        embed = discord.Embed(title="Blackjack", description=status_msg, color=color)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

        embed.add_field(
            name="Dealer's Hand", 
            value=f"> {self.format_hand(dealer_hand, hidden_dealer)}\n> Value: **{dealer_val_display}**", 
            inline=False
        )
        
        for i, hand in enumerate(player_hands):
            hand_val = calculate_hand(hand)
            hand_text = self.format_hand(hand)
            
            hand_title = f"Your Hand {i+1}" if len(player_hands) > 1 else "Your Hand"
            if not final_statuses and i == current_index and len(player_hands) > 1:
                hand_title = f"➡️ {hand_title} (Active)"
                
            status_suffix = ""
            if final_statuses:
                fs = final_statuses[i]
                if fs == "blackjack": status_suffix = " 🌟 **BLACKJACK!**"
                elif fs == "dealer_bust": status_suffix = " 🎉 **Win!**"
                elif fs == "win": status_suffix = " 🎉 **Win!**"
                elif fs == "push": status_suffix = " 🔄 **Push**"
                elif fs == "bust": status_suffix = " 💥 **Bust!**"
                elif fs == "timeout": status_suffix = " ⏰ **Timeout!**"
                else: status_suffix = " ❌ **Loss**"

            embed.add_field(
                name=hand_title,
                value=f"> {hand_text}\n> Value: **{hand_val}**{status_suffix}",
                inline=False
            )
            
        total_wager = sum(bets)
        # Footers do not support custom emotes, using the word "Leaves"
        embed.set_footer(text=f"Total Wager: {total_wager:,} Leaves")
        return embed

    async def update_gambling_stats(self, user_id: int, spent: int, won: int, final_hand: str):
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
            update_data["$set"]["last_win"] = {"amount": net, "symbols": f"BJ: {final_hand}", "timestamp": now}
        elif net < 0:
            update_data["$set"]["last_loss"] = {"amount": net, "symbols": f"BJ: {final_hand}", "timestamp": now}

        await self.gambling_col.update_one({"discordId": user_id}, update_data, upsert=True)
        await self.logs_col.insert_one({
            "discordId": user_id, "spent": spent, "won": won, "net": net, 
            "symbols": f"BJ: {final_hand}", "timestamp": now, "game": "blackjack"
        })

    async def resolve_game_multiple(self, interaction, user, bets, player_hands, dealer_hand, results, view):
        total_payout = 0
        total_bet = sum(bets)
        breakdown_lines = []

        d_val = calculate_hand(dealer_hand)

        for i, result in enumerate(results):
            bet = bets[i]
            payout = 0
            hand = player_hands[i]
            p_val = calculate_hand(hand)
            reason = ""

            # Determine why the player won/lost/tied
            if result == "blackjack":
                payout = int(bet * BLACKJACK_PAYOUT)
                reason = "Natural 21"
            elif result == "win":
                payout = int(bet * WIN_PAYOUT)
                reason = f"Your {p_val} beat Dealer's {d_val}"
            elif result == "dealer_bust":
                payout = int(bet * WIN_PAYOUT)
                reason = f"Dealer busted with {d_val}"
            elif result == "push":
                payout = bet # Return their wager
                reason = f"Push ({p_val} vs {d_val})"
            elif result == "bust":
                reason = f"You busted with {p_val}"
            elif result == "loss":
                reason = f"Dealer's {d_val} beat your {p_val}"
            elif result == "timeout":
                reason = "Timeout"

            total_payout += payout
            hand_prefix = f"Hand {i+1}: " if len(player_hands) > 1 else ""
            
            # Append the reason next to the payout amount
            if payout > bet:
                breakdown_lines.append(f"• {hand_prefix}**Won {payout:,} <:leaf:1524758896659660831>** ─ *{reason}*")
            elif payout == bet:
                breakdown_lines.append(f"• {hand_prefix}**Returned {payout:,} <:leaf:1524758896659660831>** ─ *{reason}*")
            else:
                breakdown_lines.append(f"• {hand_prefix}**Lost {bet:,} <:leaf:1524758896659660831>** ─ *{reason}*")

        if total_payout > 0:
            await self.users_col.update_one({"discordId": user.id}, {"$inc": {"balance": total_payout}})
        
        net_profit = total_payout - total_bet
        if net_profit < 0:
            await self.add_to_jackpot(abs(net_profit))

        final_hand_str = " | ".join(["".join(c['rank'] for c in h) for h in player_hands])
        await self.update_gambling_stats(user.id, total_bet, total_payout, final_hand_str)

        embed = self.build_embed(user, bets, player_hands, dealer_hand, hidden_dealer=False, final_statuses=results)
        
        summary_msg = "**Results:**\n" + "\n".join(breakdown_lines)
        if net_profit > 0:
            summary_msg += f"\n\n📈 **Net Profit: +{net_profit:,} <:leaf:1524758896659660831>**"
        elif net_profit < 0:
            summary_msg += f"\n\n📉 **Net Loss: {net_profit:,} <:leaf:1524758896659660831>**"
        else:
            summary_msg += f"\n\n🤝 **Net Result: Break Even**"
            
        embed.description = summary_msg

        if "timeout" in results:
            end_view = None
        else:
            end_view = PlayAgainView(self, user, bets[0])

        if interaction.response.is_done():
            try:
                await interaction.edit_original_response(embed=embed, view=end_view)
            except discord.errors.NotFound:
                await interaction.message.edit(embed=embed, view=end_view)
        else:
            await interaction.response.edit_message(embed=embed, view=end_view)

    @app_commands.command(name="blackjack", description="Play a game of Blackjack or view the odds.")
    @app_commands.describe(
        action="Select an action",
        bet="Amount to wager (Required for 'Play')"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="🃏 Play", value="play"),
        app_commands.Choice(name="📊 View Odds", value="odds")
    ])
    async def blackjack(self, interaction: discord.Interaction, action: str, bet: int = 25):
        if action == "play":
            await self._handle_play(interaction, bet)
        elif action == "odds":
            await self._handle_odds(interaction)

    async def _handle_play(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer()
        user_id = interaction.user.id

        if bet < MIN_BET:
            return await interaction.followup.send(f"Error: Minimum wager is {MIN_BET} <:leaf:1524758896659660831>.", ephemeral=True)

        user_data = await self.users_col.find_one({"discordId": user_id})
        current_balance = user_data.get("balance", 0) if user_data else 0

        if current_balance < bet:
            return await interaction.followup.send(
                f"Error: Insufficient funds. Required: {bet:,} <:leaf:1524758896659660831>. Balance: {current_balance:,} <:leaf:1524758896659660831>", 
                ephemeral=True
            )

        await self.users_col.update_one({"discordId": user_id}, {"$inc": {"balance": -bet}})

        deck = self.create_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        player_val = calculate_hand(player_hand)
        dealer_val = calculate_hand(dealer_hand)

        if player_val == 21:
            if dealer_val == 21:
                await self.resolve_game_multiple(interaction, interaction.user, [bet], [player_hand], dealer_hand, ["push"], None)
            else:
                await self.resolve_game_multiple(interaction, interaction.user, [bet], [player_hand], dealer_hand, ["blackjack"], None)
            return

        view = BlackjackView(self, interaction, bet, player_hand, dealer_hand, deck)
        await view.update_button_states()
        embed = self.build_embed(interaction.user, [bet], [player_hand], dealer_hand, current_index=0, hidden_dealer=True)

        await interaction.followup.send(embed=embed, view=view)

    async def _handle_odds(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Blackjack Odds & Rules",
            description="Welcome to the tables. Here is how the server calculates your game and edge.",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="Payouts", 
            value=(
                "**Blackjack (21 on first two cards):** 3:2 (Returns Wager + 1.5x)\n"
                "**Standard Win:** 1:1 (Returns Wager + 1x)\n"
                "**Dealer Bust:** 1:1 (Returns Wager + 1x)\n"
                "**Tie / Push:** 🔄 **Wager Returned**"
            ), 
            inline=False
        )
        
        embed.add_field(
            name="Rules & The Smart Dealer", 
            value=(
                "• Minimum Bet: **25 <:leaf:1524758896659660831>**\n"
                "• **Smart Dealer AI:** Unlike standard casinos, the dealer plays to win. If the dealer is standing on 17 but you have an 18, the dealer realizes they are mathematically guaranteed to lose and will choose to hit to try and beat you!\n"
                "• All losing wagers are deposited into the **Global Slots Jackpot**."
            ), 
            inline=False
        )

        embed.add_field(
            name="Advanced Moves", 
            value=(
                "• **Double Down:** Double your active bet on opening card pairs to receive *exactly one* final card.\n"
                "• **Splitting:** If your starting cards share the same numeric point value, you can match your initial wager to split them into two independent hands."
            ), 
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))