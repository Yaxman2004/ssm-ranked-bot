import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from database import Database

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
db = Database()

# ── Rank thresholds ────────────────────────────────────────
RANKS = [
    (1600, "👑 Legend",   0x8B0000),
    (1400, "🌟 Champion", 0x9B59B6),
    (1200, "💎 Diamond",  0x00BFFF),
    (1000, "🥇 Gold",     0xFFD700),
    (800,  "⚔️ Iron",     0xC0C0C0),
    (0,    "🪨 Stone",    0x808080),
]

def get_rank(elo):
    for threshold, name, color in RANKS:
        if elo >= threshold:
            return name, color
    return "🪨 Stone", 0x808080

def calc_elo(winner_elo, loser_elo):
    k = 32 if max(winner_elo, loser_elo) < 1400 else 16
    expected = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    new_winner = round(winner_elo + k * (1 - expected))
    new_loser  = round(loser_elo  + k * (0 - (1 - expected)))
    return new_winner, new_loser

def elo_embed(title, desc, color=0x6c3bff):
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text="SSM Ranked • mineplex.com")
    return e

# ── Startup ────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Game("Super Smash Mobs | /queue"))
    print(f"✅ Logged in as {bot.user} | Servers: {len(bot.guilds)}")

# ── /register ──────────────────────────────────────────────
@bot.tree.command(name="register", description="Link your Minecraft IGN to start playing ranked.")
@app_commands.describe(ign="Your Minecraft username (case-sensitive)")
async def register(interaction: discord.Interaction, ign: str):
    uid = interaction.user.id
    if db.get_player(uid):
        await interaction.response.send_message(
            embed=elo_embed("Already Registered", f"You're already registered as **{db.get_player(uid)['ign']}**.\nUse `/profile` to see your stats.", 0xFF6B6B),
            ephemeral=True
        )
        return
    if db.ign_taken(ign):
        await interaction.response.send_message(
            embed=elo_embed("IGN Taken", f"**{ign}** is already registered to another account.", 0xFF6B6B),
            ephemeral=True
        )
        return
    db.register(uid, ign)
    rank_name, rank_color = get_rank(1000)
    e = elo_embed("✅ Registered!", f"Welcome to **SSM Ranked**, **{ign}**!\n\n**Starting Elo:** 1000\n**Rank:** {rank_name}\n\nUse `/queue` to find a match.", rank_color)
    e.set_thumbnail(url=f"https://mc-heads.net/avatar/{ign}/64")
    await interaction.response.send_message(embed=e)

# ── /queue ─────────────────────────────────────────────────
queue = {}  # guild_id -> list of (user_id, elo)

@bot.tree.command(name="queue", description="Enter the 1v1 ranked queue.")
async def queue_cmd(interaction: discord.Interaction):
    uid = interaction.user.id
    gid = interaction.guild_id
    player = db.get_player(uid)

    if not player:
        await interaction.response.send_message(
            embed=elo_embed("Not Registered", "You need to `/register` before queuing.", 0xFF6B6B),
            ephemeral=True
        )
        return

    if db.in_active_match(uid):
        await interaction.response.send_message(
            embed=elo_embed("Already in Match", "You're already in an active match. Use `/forfeit` to forfeit.", 0xFF6B6B),
            ephemeral=True
        )
        return

    if gid not in queue:
        queue[gid] = []

    # Check if already in queue
    if any(u == uid for u, _ in queue[gid]):
        await interaction.response.send_message(
            embed=elo_embed("Already Queuing", "You're already in the queue! Use `/leavequeue` to leave.", 0xFFD700),
            ephemeral=True
        )
        return

    queue[gid].append((uid, player["elo"]))
    await interaction.response.send_message(
        embed=elo_embed("🔍 Searching for Match...", f"**{player['ign']}** ({player['elo']} Elo) has entered the queue.\nPlayers in queue: **{len(queue[gid])}**", 0x6c3bff)
    )

    # Match found
    if len(queue[gid]) >= 2:
        p1_id, p1_elo = queue[gid].pop(0)
        p2_id, p2_elo = queue[gid].pop(0)
        p1 = db.get_player(p1_id)
        p2 = db.get_player(p2_id)
        match_id = db.create_match(p1_id, p2_id)

        e = discord.Embed(title="⚔️ Match Found!", color=0x00FF88)
        e.add_field(name="Player 1", value=f"<@{p1_id}>\n**{p1['ign']}** • {p1_elo} Elo", inline=True)
        e.add_field(name="vs", value="⚔️", inline=True)
        e.add_field(name="Player 2", value=f"<@{p2_id}>\n**{p2['ign']}** • {p2_elo} Elo", inline=True)
        e.add_field(name="How to play", value="Join **mineplex.com**, go to Super Smash Mobs and challenge your opponent!\nWhen done, the **winner** types `/win @loser`.", inline=False)
        e.add_field(name="Match ID", value=f"`#{match_id}`", inline=False)
        e.set_footer(text="SSM Ranked • You have 10 minutes to start your match.")
        await interaction.followup.send(content=f"<@{p1_id}> <@{p2_id}>", embed=e)

# ── /leavequeue ────────────────────────────────────────────
@bot.tree.command(name="leavequeue", description="Leave the ranked queue.")
async def leavequeue(interaction: discord.Interaction):
    uid = interaction.user.id
    gid = interaction.guild_id
    if gid in queue and any(u == uid for u, _ in queue[gid]):
        queue[gid] = [(u, e) for u, e in queue[gid] if u != uid]
        await interaction.response.send_message(
            embed=elo_embed("Left Queue", "You have left the queue.", 0xFFD700),
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=elo_embed("Not in Queue", "You're not currently in the queue.", 0xFF6B6B),
            ephemeral=True
        )

# ── /win ───────────────────────────────────────────────────
pending_confirms = {}  # match_id -> {winner, loser, confirmed: False}

@bot.tree.command(name="win", description="Report yourself as the winner of your match.")
@app_commands.describe(opponent="The player you just beat")
async def win(interaction: discord.Interaction, opponent: discord.Member):
    uid = interaction.user.id
    oid = opponent.id

    if uid == oid:
        await interaction.response.send_message(
            embed=elo_embed("Invalid", "You can't report a win against yourself.", 0xFF6B6B),
            ephemeral=True
        )
        return

    winner = db.get_player(uid)
    loser  = db.get_player(oid)

    if not winner or not loser:
        await interaction.response.send_message(
            embed=elo_embed("Not Registered", "Both players must be registered.", 0xFF6B6B),
            ephemeral=True
        )
        return

    match = db.get_active_match(uid, oid)
    if not match:
        await interaction.response.send_message(
            embed=elo_embed("No Active Match", "No active match found between you two. Make sure you're both in a match together.", 0xFF6B6B),
            ephemeral=True
        )
        return

    # Store pending confirm
    pending_confirms[match["id"]] = {"winner": uid, "loser": oid, "match": match}

    e = discord.Embed(title="⚠️ Confirm Result", color=0xFFD700)
    e.description = (
        f"<@{oid}>, **{winner['ign']}** is reporting a win over you.\n\n"
        f"React with ✅ to **confirm** or ❌ to **dispute**.\n"
        f"*(You have 2 minutes to respond)*"
    )
    await interaction.response.send_message(content=f"<@{oid}>", embed=e)
    msg = await interaction.original_response()
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    def check(reaction, user):
        return user.id == oid and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=120.0, check=check)
    except asyncio.TimeoutError:
        await interaction.followup.send(
            embed=elo_embed("Timed Out", f"<@{oid}> did not respond in time. Result has been flagged for staff review.", 0xFF6B6B)
        )
        return

    if str(reaction.emoji) == "✅":
        # Process result
        new_w_elo, new_l_elo = calc_elo(winner["elo"], loser["elo"])
        w_gain = new_w_elo - winner["elo"]
        l_loss = new_l_elo - loser["elo"]

        db.record_result(match["id"], uid, oid, new_w_elo, new_l_elo)

        w_rank, w_color = get_rank(new_w_elo)
        l_rank, _       = get_rank(new_l_elo)

        e = discord.Embed(title="🏆 Match Result", color=w_color)
        e.add_field(
            name=f"🥇 Winner — {winner['ign']}",
            value=f"**{winner['elo']} → {new_w_elo}** (+{w_gain})\n{w_rank}",
            inline=True
        )
        e.add_field(
            name=f"💀 Loser — {loser['ign']}",
            value=f"**{loser['elo']} → {new_l_elo}** ({l_loss})\n{l_rank}",
            inline=True
        )
        e.set_footer(text=f"Match #{match['id']} • SSM Ranked")
        await interaction.followup.send(embed=e)

    elif str(reaction.emoji) == "❌":
        await interaction.followup.send(
            embed=elo_embed("⚠️ Result Disputed", f"<@{oid}> has disputed this result. A staff member will review match `#{match['id']}`.", 0xFF6B6B)
        )

# ── /forfeit ───────────────────────────────────────────────
@bot.tree.command(name="forfeit", description="Forfeit your current match.")
async def forfeit(interaction: discord.Interaction):
    uid = interaction.user.id
    match = db.get_active_match_single(uid)
    if not match:
        await interaction.response.send_message(
            embed=elo_embed("No Active Match", "You don't have an active match.", 0xFF6B6B),
            ephemeral=True
        )
        return

    opp_id = match["p2_id"] if match["p1_id"] == uid else match["p1_id"]
    loser   = db.get_player(uid)
    winner  = db.get_player(opp_id)
    new_w_elo, new_l_elo = calc_elo(winner["elo"], loser["elo"])
    w_gain = new_w_elo - winner["elo"]
    l_loss = new_l_elo - loser["elo"]
    db.record_result(match["id"], opp_id, uid, new_w_elo, new_l_elo)

    e = discord.Embed(title="🏳️ Forfeit", color=0xFF6B6B)
    e.description = (
        f"**{loser['ign']}** has forfeited.\n\n"
        f"🥇 **{winner['ign']}**: {winner['elo']} → **{new_w_elo}** (+{w_gain})\n"
        f"💀 **{loser['ign']}**: {loser['elo']} → **{new_l_elo}** ({l_loss})"
    )
    await interaction.response.send_message(embed=e)

# ── /profile ───────────────────────────────────────────────
@bot.tree.command(name="profile", description="View your or another player's ranked profile.")
@app_commands.describe(user="Leave blank to see your own profile")
async def profile(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    player = db.get_player(target.id)
    if not player:
        await interaction.response.send_message(
            embed=elo_embed("Not Found", f"{'That player is' if user else 'You are'} not registered.", 0xFF6B6B),
            ephemeral=True
        )
        return

    rank_name, rank_color = get_rank(player["elo"])
    total = player["wins"] + player["losses"]
    wr = round((player["wins"] / total) * 100, 1) if total > 0 else 0
    streak = player["streak"]
    streak_str = f"🔥 {streak} win streak" if streak >= 2 else (f"❄️ {abs(streak)} loss streak" if streak <= -2 else "—")

    e = discord.Embed(title=f"{player['ign']}'s Profile", color=rank_color)
    e.set_thumbnail(url=f"https://mc-heads.net/avatar/{player['ign']}/64")
    e.add_field(name="Rank",    value=rank_name,           inline=True)
    e.add_field(name="Elo",     value=f"**{player['elo']}**", inline=True)
    e.add_field(name="Streak",  value=streak_str,          inline=True)
    e.add_field(name="Wins",    value=str(player["wins"]),  inline=True)
    e.add_field(name="Losses",  value=str(player["losses"]),inline=True)
    e.add_field(name="Win Rate",value=f"{wr}%",            inline=True)
    e.set_footer(text="SSM Ranked • mineplex.com")
    await interaction.response.send_message(embed=e)

# ── /leaderboard ───────────────────────────────────────────
@bot.tree.command(name="leaderboard", description="View the top 10 ranked players.")
async def leaderboard(interaction: discord.Interaction):
    top = db.get_leaderboard()
    if not top:
        await interaction.response.send_message(
            embed=elo_embed("No Players Yet", "Nobody is registered yet. Be the first with `/register`!"),
            ephemeral=True
        )
        return

    medals = ["🥇", "🥈", "🥉"]
    desc = ""
    for i, p in enumerate(top):
        rank_name, _ = get_rank(p["elo"])
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        desc += f"{medal} **{p['ign']}** — {p['elo']} Elo  {rank_name}  ({p['wins']}W/{p['losses']}L)\n"

    e = discord.Embed(title="🏆 SSM Ranked Leaderboard", description=desc, color=0xFFD700)
    e.set_footer(text="SSM Ranked • Top 10 Players")
    await interaction.response.send_message(embed=e)

# ── /history ───────────────────────────────────────────────
@bot.tree.command(name="history", description="View your last 10 match results.")
@app_commands.describe(user="Leave blank for your own history")
async def history(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    player = db.get_player(target.id)
    if not player:
        await interaction.response.send_message(
            embed=elo_embed("Not Found", "That player is not registered.", 0xFF6B6B),
            ephemeral=True
        )
        return

    matches = db.get_history(target.id)
    if not matches:
        await interaction.response.send_message(
            embed=elo_embed("No Matches", "No matches played yet."),
            ephemeral=True
        )
        return

    desc = ""
    for m in matches:
        won = m["winner_id"] == target.id
        opp_ign = m["loser_ign"] if won else m["winner_ign"]
        elo_change = m["winner_elo_after"] - m["winner_elo_before"] if won else m["loser_elo_after"] - m["loser_elo_before"]
        sign = "+" if elo_change > 0 else ""
        icon = "✅" if won else "❌"
        desc += f"{icon} vs **{opp_ign}** — `{sign}{elo_change}` Elo\n"

    e = discord.Embed(title=f"{player['ign']}'s Match History", description=desc, color=0x6c3bff)
    e.set_footer(text="Last 10 matches • SSM Ranked")
    await interaction.response.send_message(embed=e)

# ── /setelo (staff only) ───────────────────────────────────
@bot.tree.command(name="setelo", description="[Staff] Manually set a player's Elo.")
@app_commands.describe(user="The player to adjust", elo="New Elo value")
@app_commands.checks.has_permissions(manage_guild=True)
async def setelo(interaction: discord.Interaction, user: discord.Member, elo: int):
    player = db.get_player(user.id)
    if not player:
        await interaction.response.send_message(embed=elo_embed("Not Found", "That player is not registered.", 0xFF6B6B), ephemeral=True)
        return
    db.set_elo(user.id, elo)
    await interaction.response.send_message(
        embed=elo_embed("✅ Elo Updated", f"**{player['ign']}**'s Elo set to **{elo}**.", 0x00FF88)
    )

# ── /forcewinner (staff only) ──────────────────────────────
@bot.tree.command(name="forcewinner", description="[Staff] Force a match result between two players.")
@app_commands.describe(winner="The winning player", loser="The losing player")
@app_commands.checks.has_permissions(manage_guild=True)
async def forcewinner(interaction: discord.Interaction, winner: discord.Member, loser: discord.Member):
    w = db.get_player(winner.id)
    l = db.get_player(loser.id)
    if not w or not l:
        await interaction.response.send_message(embed=elo_embed("Not Found", "Both players must be registered.", 0xFF6B6B), ephemeral=True)
        return
    match = db.get_active_match(winner.id, loser.id)
    if not match:
        match = db.create_match(winner.id, loser.id)
        match = {"id": match}
    new_w, new_l = calc_elo(w["elo"], l["elo"])
    db.record_result(match["id"], winner.id, loser.id, new_w, new_l)
    await interaction.response.send_message(
        embed=elo_embed("✅ Result Forced", f"**{w['ign']}** wins over **{l['ign']}**.\n{w['elo']} → **{new_w}** | {l['elo']} → **{new_l}**", 0x00FF88)
    )

@setelo.error
@forcewinner.error
async def staff_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(embed=elo_embed("No Permission", "You need **Manage Server** permission to use this command.", 0xFF6B6B), ephemeral=True)

# ── Run ────────────────────────────────────────────────────
bot.run(os.getenv("DISCORD_TOKEN"))
