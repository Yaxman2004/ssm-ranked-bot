import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from database import Database

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
db = Database()

# ── Role IDs ───────────────────────────────────────────────
HOST_ROLE_ID         = 1515755045214224424
VERIFIED_ROLE_ID     = None
LEADERBOARD_CHANNEL_ID = 1515424053215891556
leaderboard_message_id  = None  # stored after first post

RANK_ROLE_IDS = {
    "👑 Legend":   1515424826217598997,
    "🌟 Champion": 1515424760455237793,
    "💎 Diamond":  1515424726426718378,
    "🥇 Gold":     1515424666985168967,
    "⚔️ Iron":     1515424638107390142,
    "🪨 Stone":    1515424612991893614,
}

# ── Config ─────────────────────────────────────────────────
def get_match_channel_id():
    val = os.getenv("MATCH_CHANNEL_ID", "0").strip()
    return int(val) if val.isdigit() else 0

def get_results_channel_id():
    val = os.getenv("RESULTS_CHANNEL_ID", "0").strip()
    return int(val) if val.isdigit() else 0

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

# ── Role helpers ───────────────────────────────────────────
async def assign_rank_role(member: discord.Member, rank_name: str):
    """Remove all rank roles then assign the correct one."""
    try:
        all_rank_roles = [member.guild.get_role(rid) for rid in RANK_ROLE_IDS.values()]
        all_rank_roles = [r for r in all_rank_roles if r is not None]
        await member.remove_roles(*all_rank_roles, reason="Rank update")
        new_role = member.guild.get_role(RANK_ROLE_IDS.get(rank_name))
        if new_role:
            await member.add_roles(new_role, reason="Rank update")
    except Exception as e:
        print(f"Role assign error: {e}")


# ── Auto leaderboard ───────────────────────────────────────
async def build_leaderboard_embed():
    top = db.get_leaderboard(10)
    medals = ["🥇", "🥈", "🥉"]
    if not top:
        desc = "No players registered yet. Be the first with `/register`!"
    else:
        desc = ""
        for i, p in enumerate(top):
            rank_name, _ = get_rank(p["elo"])
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            desc += f"{medal} **{p['ign']}** — {p['elo']} Elo  {rank_name}  ({p['wins']}W/{p['losses']}L)\n"
    e = discord.Embed(title="🏆 SSM Ranked Leaderboard", description=desc, color=0xFFD700)
    e.set_footer(text="SSM Ranked • Updates every 5 minutes")
    return e

@tasks.loop(minutes=5)
async def update_leaderboard():
    global leaderboard_message_id
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel:
        return
    embed = await build_leaderboard_embed()
    try:
        if leaderboard_message_id:
            msg = await channel.fetch_message(leaderboard_message_id)
            await msg.edit(embed=embed)
        else:
            # Clear old messages and post fresh
            await channel.purge(limit=10)
            msg = await channel.send(embed=embed)
            leaderboard_message_id = msg.id
    except Exception as ex:
        print(f"Leaderboard update error: {ex}")
        try:
            await channel.purge(limit=10)
            msg = await channel.send(embed=embed)
            leaderboard_message_id = msg.id
        except:
            pass

# ── Welcome system ─────────────────────────────────────────
@bot.event
async def on_member_join(member: discord.Member):
    # Find announcements or general channel to welcome them
    welcome_channel = None
    for ch in member.guild.text_channels:
        if "general" in ch.name:
            welcome_channel = ch
            break

    if welcome_channel:
        e = discord.Embed(title=f"👋 Welcome, {member.display_name}!", color=0x6c3bff)
        e.description = (
            f"Welcome to **SSM Ranked** — the #1 competitive Super Smash Mobs community on Mineplex!\n\n"
            f"📌 Read the rules in <#rules>\n"
            f"❓ Learn how to play in <#how-to-play-ranked>\n"
            f"🤖 Register with `/register <IGN>` in <#bot-commands>\n\n"
            f"Once you register you'll automatically get your starting rank. Good luck! 🏆"
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text="SSM Ranked • mineplex.com")
        await welcome_channel.send(content=member.mention, embed=e)

# ── Startup ────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Game("Super Smash Mobs | /queue"))
    print(f"✅ Logged in as {bot.user} | Servers: {len(bot.guilds)}")
    print(f"📢 MATCH_CHANNEL_ID = {get_match_channel_id()}")
    print(f"📢 RESULTS_CHANNEL_ID = {get_results_channel_id()}")
    update_leaderboard.start()

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

    # Assign Gold role automatically
    await assign_rank_role(interaction.user, rank_name)

    e = elo_embed("✅ Registered!", f"Welcome to **SSM Ranked**, **{ign}**!\n\n**Starting Elo:** 1000\n**Rank:** {rank_name}\n\nYou've been given the **{rank_name}** role!\nUse `/queue` to find a match.", rank_color)
    e.set_thumbnail(url=f"https://mc-heads.net/avatar/{ign}/64")
    await interaction.response.send_message(embed=e)

# ── Request Host Button ────────────────────────────────────
class RequestHostView(discord.ui.View):
    def __init__(self, match_id, p1_id, p2_id):
        super().__init__(timeout=900)
        self.match_id = match_id
        self.p1_id = p1_id
        self.p2_id = p2_id
        self.host_requested = False

    @discord.ui.button(label="🎮 Request a Host", style=discord.ButtonStyle.primary)
    async def request_host(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1_id, self.p2_id]:
            await interaction.response.send_message(
                embed=elo_embed("Not Your Match", "Only the players in this match can request a host.", 0xFF6B6B),
                ephemeral=True
            )
            return

        if self.host_requested:
            await interaction.response.send_message(
                embed=elo_embed("Already Requested", "A host has already been requested for this match.", 0xFFD700),
                ephemeral=True
            )
            return

        self.host_requested = True
        button.disabled = True
        button.label = "🎮 Host Requested..."
        await interaction.message.edit(view=self)

        # Use role ID directly — no name matching issues
        host_role = interaction.guild.get_role(HOST_ROLE_ID)
        host_ping = host_role.mention if host_role else "**@Match Host**"

        e = discord.Embed(title="🎮 Host Needed!", color=0xFF8C00)
        e.description = (
            f"{host_ping} — a host is needed for match `#{self.match_id}`!\n\n"
            f"<@{self.p1_id}> vs <@{self.p2_id}>\n\n"
            f"Use `/hostaccept {self.match_id}` to claim this match."
        )
        e.set_footer(text="SSM Ranked • First available host please respond")
        await interaction.response.send_message(
            content=host_role.mention if host_role else "Match Host needed",
            embed=e
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ── /queue ─────────────────────────────────────────────────
queue = {}

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

    if any(u == uid for u, _ in queue[gid]):
        await interaction.response.send_message(
            embed=elo_embed("Already Queuing", "You're already in the queue! Use `/leavequeue` to leave.", 0xFFD700),
            ephemeral=True
        )
        return

    queue[gid].append((uid, player["elo"]))
    await interaction.response.send_message(
        embed=elo_embed("🔍 Searching for Match...", f"**{player['ign']}** ({player['elo']} Elo) entered the queue.\nPlayers in queue: **{len(queue[gid])}**", 0x6c3bff)
    )

    if len(queue[gid]) >= 2:
        p1_id, p1_elo = queue[gid].pop(0)
        p2_id, p2_elo = queue[gid].pop(0)
        p1 = db.get_player(p1_id)
        p2 = db.get_player(p2_id)
        match_id = db.create_match(p1_id, p2_id)

        mid = get_match_channel_id()
        match_channel = bot.get_channel(mid) if mid != 0 else None

        e = discord.Embed(title="⚔️ Match Found!", color=0x00FF88)
        e.add_field(name="Player 1", value=f"<@{p1_id}>\n**{p1['ign']}** • {p1_elo} Elo", inline=True)
        e.add_field(name="VS", value="⚔️", inline=True)
        e.add_field(name="Player 2", value=f"<@{p2_id}>\n**{p2['ign']}** • {p2_elo} Elo", inline=True)
        e.add_field(name="📋 Format", value="**Best of 3** — First to 2 wins\nKit switching allowed between games", inline=False)
        e.add_field(
            name="🎮 Hosting",
            value="If either of you has **Celestial or Divine** rank on Mineplex, go ahead and host the MPS lobby!\nIf not, click the button below to request a host.",
            inline=False
        )
        e.add_field(name="✅ When Done", value="Winner runs `/win @opponent` to report the result.", inline=False)
        e.set_footer(text=f"Match #{match_id} • SSM Ranked • 15 minutes to start")

        view = RequestHostView(match_id, p1_id, p2_id)

        if match_channel:
            await match_channel.send(content=f"<@{p1_id}> <@{p2_id}>", embed=e, view=view)
        else:
            await interaction.followup.send(content=f"<@{p1_id}> <@{p2_id}>", embed=e, view=view)

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

# ── /hostaccept ────────────────────────────────────────────
@bot.tree.command(name="hostaccept", description="Accept hosting a match. Match Hosts only.")
@app_commands.describe(match_id="The match ID shown in the host request")
async def hostaccept(interaction: discord.Interaction, match_id: int):
    host_role = interaction.guild.get_role(HOST_ROLE_ID)
    if not host_role or host_role not in interaction.user.roles:
        await interaction.response.send_message(
            embed=elo_embed("No Permission", "Only **Match Hosts** can use this command.", 0xFF6B6B),
            ephemeral=True
        )
        return

    match = db.get_match_by_id(match_id)
    if not match or match["status"] != "active":
        await interaction.response.send_message(
            embed=elo_embed("Match Not Found", f"No active match found with ID `#{match_id}`.", 0xFF6B6B),
            ephemeral=True
        )
        return

    p1 = db.get_player(match["p1_id"])
    p2 = db.get_player(match["p2_id"])

    e = discord.Embed(title="🎮 Host Confirmed!", color=0x00FF88)
    e.description = (
        f"**{interaction.user.display_name}** is hosting match `#{match_id}`!\n\n"
        f"<@{match['p1_id']}> (**{p1['ign']}**) and <@{match['p2_id']}> (**{p2['ign']}**)\n"
        f"Join **{interaction.user.display_name}**'s MPS lobby on Mineplex now!\n\n"
        f"**Format:** Best of 3 — First to 2 wins\n"
        f"**Kit switching** allowed between games."
    )
    e.set_footer(text=f"Match #{match_id} • SSM Ranked")
    await interaction.response.send_message(content=f"<@{match['p1_id']}> <@{match['p2_id']}>", embed=e)

# ── /applyhost ─────────────────────────────────────────────
@bot.tree.command(name="applyhost", description="Apply to become a Match Host (requires Celestial or Divine rank on Mineplex).")
@app_commands.describe(ign="Your Minecraft IGN", rank="Your Mineplex rank")
@app_commands.choices(rank=[
    app_commands.Choice(name="Celestial", value="Celestial"),
    app_commands.Choice(name="Divine",    value="Divine"),
])
async def applyhost(interaction: discord.Interaction, ign: str, rank: str):
    staff_channel = None
    for ch in interaction.guild.text_channels:
        if "staff-chat" in ch.name or "admin-chat" in ch.name:
            staff_channel = ch
            break

    e = discord.Embed(title="🎮 New Host Application", color=0x6c3bff)
    e.add_field(name="Discord", value=f"<@{interaction.user.id}>", inline=True)
    e.add_field(name="IGN",     value=ign,                          inline=True)
    e.add_field(name="Rank",    value=rank,                         inline=True)
    e.set_footer(text="Use /approvehost or /denyhost to respond")

    if staff_channel:
        await staff_channel.send(embed=e)
        await interaction.response.send_message(
            embed=elo_embed("✅ Application Sent!", "Your host application has been sent to staff.\nWe'll review it and get back to you soon!", 0x00FF88),
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=elo_embed("Received", "Application received. Please also DM a staff member directly.", 0xFFD700),
            ephemeral=True
        )

# ── /approvehost (staff only) ──────────────────────────────
@bot.tree.command(name="approvehost", description="[Staff] Approve a Match Host application.")
@app_commands.describe(user="The player to approve")
@app_commands.checks.has_permissions(manage_guild=True)
async def approvehost(interaction: discord.Interaction, user: discord.Member):
    host_role = interaction.guild.get_role(HOST_ROLE_ID)
    if not host_role:
        await interaction.response.send_message(
            embed=elo_embed("Role Not Found", "Match Host role not found. Check the role ID.", 0xFF6B6B),
            ephemeral=True
        )
        return
    await user.add_roles(host_role)
    await interaction.response.send_message(
        embed=elo_embed("✅ Approved", f"<@{user.id}> is now a **Match Host**!", 0x00FF88)
    )
    try:
        await user.send(embed=elo_embed(
            "🎮 Host Application Approved!",
            "Congrats! You're now a **Match Host** in SSM Ranked.\n\n"
            "When players need a host they'll click a button and you'll get pinged.\n"
            "Use `/hostaccept <match_id>` to claim a match and host the MPS lobby.\n\n"
            "Thank you for supporting the community! 🙏",
            0x00FF88
        ))
    except:
        pass

# ── /denyhost (staff only) ────────────────────────────────
@bot.tree.command(name="denyhost", description="[Staff] Deny a Match Host application.")
@app_commands.describe(user="The player to deny", reason="Reason for denial")
@app_commands.checks.has_permissions(manage_guild=True)
async def denyhost(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    await interaction.response.send_message(
        embed=elo_embed("❌ Denied", f"<@{user.id}>'s host application denied.\nReason: {reason}", 0xFF6B6B)
    )
    try:
        await user.send(embed=elo_embed(
            "Host Application Update",
            f"Your Match Host application was not approved at this time.\n**Reason:** {reason}\n\nYou're welcome to reapply in the future!",
            0xFF6B6B
        ))
    except:
        pass

# ── /win ───────────────────────────────────────────────────
@bot.tree.command(name="win", description="Report yourself as the winner of your Best of 3 match.")
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
            embed=elo_embed("No Active Match", "No active match found between you two.", 0xFF6B6B),
            ephemeral=True
        )
        return

    e = discord.Embed(title="⚠️ Confirm Result", color=0xFFD700)
    e.description = (
        f"<@{oid}>, **{winner['ign']}** is reporting a win over you in your Best of 3.\n\n"
        f"✅ = Confirm\n❌ = Dispute\n\n*(2 minutes to respond)*"
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
            embed=elo_embed("Timed Out", f"<@{oid}> didn't respond. Result flagged for staff review.", 0xFF6B6B)
        )
        return

    if str(reaction.emoji) == "✅":
        new_w_elo, new_l_elo = calc_elo(winner["elo"], loser["elo"])
        w_gain = new_w_elo - winner["elo"]
        l_loss = new_l_elo - loser["elo"]
        db.record_result(match["id"], uid, oid, new_w_elo, new_l_elo)

        w_rank, w_color = get_rank(new_w_elo)
        l_rank, _       = get_rank(new_l_elo)

        # Update rank roles for both players
        winner_member = interaction.guild.get_member(uid)
        loser_member  = interaction.guild.get_member(oid)
        if winner_member:
            await assign_rank_role(winner_member, w_rank)
        if loser_member:
            await assign_rank_role(loser_member, l_rank)

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

        # Rank up/down notification
        old_w_rank, _ = get_rank(winner["elo"])
        old_l_rank, _ = get_rank(loser["elo"])
        if w_rank != old_w_rank:
            e.add_field(name="🎉 Rank Up!", value=f"**{winner['ign']}** ranked up to **{w_rank}**!", inline=False)
        if l_rank != old_l_rank:
            e.add_field(name="📉 Rank Down", value=f"**{loser['ign']}** dropped to **{l_rank}**.", inline=False)

        e.set_footer(text=f"Match #{match['id']} • Best of 3 • SSM Ranked")

        rid = get_results_channel_id()
        results_channel = bot.get_channel(rid) if rid != 0 else None
        if results_channel:
            await results_channel.send(embed=e)
            await interaction.followup.send(
                embed=elo_embed("✅ Result Recorded", f"Match result posted in {results_channel.mention}!", 0x00FF88),
                ephemeral=True
            )
        else:
            await interaction.followup.send(embed=e)

    elif str(reaction.emoji) == "❌":
        dispute_channel = None
        for ch in interaction.guild.text_channels:
            if "dispute" in ch.name:
                dispute_channel = ch
                break
        dispute_mention = dispute_channel.mention if dispute_channel else "#🚨・disputes"
        await interaction.followup.send(
            embed=elo_embed(
                "⚠️ Result Disputed",
                f"<@{oid}> has disputed this result.\n"
                f"Both players head to {dispute_mention} with Match ID `#{match['id']}` and your explanation.\n"
                f"Staff will review within 24 hours.",
                0xFF6B6B
            )
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

    # Update rank roles
    w_rank, _ = get_rank(new_w_elo)
    l_rank, _ = get_rank(new_l_elo)
    winner_member = interaction.guild.get_member(opp_id)
    loser_member  = interaction.guild.get_member(uid)
    if winner_member:
        await assign_rank_role(winner_member, w_rank)
    if loser_member:
        await assign_rank_role(loser_member, l_rank)

    e = discord.Embed(title="🏳️ Forfeit", color=0xFF6B6B)
    e.description = (
        f"**{loser['ign']}** forfeited match `#{match['id']}`.\n\n"
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
    e.add_field(name="Rank",     value=rank_name,              inline=True)
    e.add_field(name="Elo",      value=f"**{player['elo']}**", inline=True)
    e.add_field(name="Streak",   value=streak_str,             inline=True)
    e.add_field(name="Wins",     value=str(player["wins"]),    inline=True)
    e.add_field(name="Losses",   value=str(player["losses"]),  inline=True)
    e.add_field(name="Win Rate", value=f"{wr}%",               inline=True)
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
    rank_name, _ = get_rank(elo)
    await assign_rank_role(user, rank_name)
    await interaction.response.send_message(
        embed=elo_embed("✅ Elo Updated", f"**{player['ign']}**'s Elo set to **{elo}** ({rank_name}).", 0x00FF88)
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
        mid = db.create_match(winner.id, loser.id)
        match = {"id": mid}
    new_w, new_l = calc_elo(w["elo"], l["elo"])
    db.record_result(match["id"], winner.id, loser.id, new_w, new_l)
    w_rank, _ = get_rank(new_w)
    l_rank, _ = get_rank(new_l)
    await assign_rank_role(winner, w_rank)
    await assign_rank_role(loser, l_rank)
    await interaction.response.send_message(
        embed=elo_embed("✅ Result Forced", f"**{w['ign']}** wins over **{l['ign']}**.\n{w['elo']} → **{new_w}** ({w_rank}) | {l['elo']} → **{new_l}** ({l_rank})", 0x00FF88)
    )

@setelo.error
@forcewinner.error
@approvehost.error
@denyhost.error
async def staff_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(embed=elo_embed("No Permission", "You need **Manage Server** permission to use this.", 0xFF6B6B), ephemeral=True)

# ── Run ────────────────────────────────────────────────────
bot.run(os.getenv("DISCORD_TOKEN"))
