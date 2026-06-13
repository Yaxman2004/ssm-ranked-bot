# SSM Ranked Bot 🏆

Discord Elo bot for Super Smash Mobs ranked on Mineplex.

---

## Setup Guide

### 1. Create the Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** → name it `SSM Ranked`
3. Go to **Bot** tab → click **Add Bot**
4. Under **Privileged Gateway Intents**, enable:
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. Copy your **Bot Token** (you'll need this later)
6. Go to **OAuth2 → URL Generator**
   - Scopes: `bot` + `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Add Reactions`, `Manage Roles`
7. Open the generated URL and invite the bot to your server

---

### 2. Deploy to Railway (Free)

1. Go to https://railway.app and sign up with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Push this folder to a GitHub repo first:
   ```
   git init
   git add .
   git commit -m "initial commit"
   gh repo create ssm-ranked-bot --public --push
   ```
4. Select your repo on Railway
5. Go to **Variables** tab and add:
   - `DISCORD_TOKEN` = your bot token from step 1
6. Railway will auto-detect the Procfile and deploy

---

### 3. Bot Commands

| Command | Description |
|---|---|
| `/register <ign>` | Link your Minecraft username and join ranked |
| `/queue` | Enter the 1v1 matchmaking queue |
| `/leavequeue` | Leave the queue |
| `/win @opponent` | Report yourself as the winner (opponent must confirm) |
| `/forfeit` | Forfeit your current match |
| `/profile [@user]` | View Elo, rank, W/L, streak |
| `/leaderboard` | Top 10 players |
| `/history [@user]` | Last 10 match results |
| `/setelo @user <elo>` | *(Staff)* Manually set a player's Elo |
| `/forcewinner @winner @loser` | *(Staff)* Force a match result |

---

### 4. Rank Tiers

| Rank | Elo |
|---|---|
| 👑 Legend | 1600+ |
| 🌟 Champion | 1400–1599 |
| 💎 Diamond | 1200–1399 |
| 🥇 Gold | 1000–1199 |
| ⚔️ Iron | 800–999 |
| 🪨 Stone | 0–799 |

---

### 5. How a Match Works

1. Player A runs `/queue`
2. Player B runs `/queue`
3. Bot announces the match with both players tagged
4. Both join Mineplex and play SSM
5. Winner runs `/win @loser`
6. Loser gets a DM to confirm (✅) or dispute (❌)
7. On confirm → Elo updates and result posts automatically

---

### Elo Formula

Uses standard Elo with:
- **K=32** below 1400 Elo (faster movement)
- **K=16** at 1400+ Elo (slower movement at top ranks)
- Starting Elo: **1000**
