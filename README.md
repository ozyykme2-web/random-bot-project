# MegaBot — Fun Commands + Anti-Raid Security Discord Bot

A single-file `discord.py` bot with **47 slash commands**: 24 fun/game commands,
7 image/GIF/URL conversion tools, a full anti-raid security system, and 5
moderation commands.

## Repo structure
```
bot.py
requirements.txt
README.md
```

## Deploy on Railway

1. **Push this repo to GitHub** (just these 3 files).
2. On [Railway](https://railway.app): **New Project → Deploy from GitHub repo** → select this repo.
3. Railway auto-detects Python from `requirements.txt` and installs dependencies.
4. Go to your service's **Variables** tab and add:
   ```
   DISCORD_TOKEN = your_bot_token_here
   ```
   Optional:
   ```
   BOT_PREFIX = !
   ```
5. In **Settings → Deploy**, set the **Start Command** to:
   ```
   python bot.py
   ```
6. Deploy. Check the **Logs** tab — you should see `Logged in as ...`.

## Discord Developer Portal setup (before deploying)

1. Go to https://discord.com/developers/applications → **New Application**.
2. **Bot** tab → **Reset Token** → copy it into Railway's `DISCORD_TOKEN` variable.
3. Under **Privileged Gateway Intents**, enable:
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
4. **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Administrator` (simplest), or manually pick:
     `Kick Members, Ban Members, Moderate Members, Manage Channels, Manage Messages,
     Manage Roles, View Channels, Send Messages, Embed Links, Attach Files,
     Read Message History, Add Reactions`
5. Open the generated URL and invite the bot to your server.
6. In **Server Settings → Roles**, drag the bot's role **above** any roles it
   needs to kick/ban/timeout/quarantine.

> Slash commands sync globally on startup — this can take up to ~1 hour to
> appear everywhere the first time. Subsequent restarts sync instantly to
> servers that already saw the commands.

## Commands (47 total)

### 🎉 Fun / Games
`say` `embedsay` `8ball` `coinflip` `roll` `rps` `guessnumber` `trivia`
`wouldyourather` `neverhaveiever` `truth` `dare` `riddle` `joke` `compliment`
`roast` `fortune` `randomnumber` `choose` `reverse` `mock` `clap` `poll` `avatar`

### 🖼️ Media conversion
- `/imagetogif` — image attachment → `.gif`
- `/giftoimage` — GIF's first frame → `.png`
- `/urltoimage` — image URL → uploaded file
- `/imagetourl` — image attachment → direct CDN URL
- `/pixelate`, `/grayscale`, `/invert` — image filters

### 🛡️ Security / Anti-Raid
Automatic protections (always on while enabled):
- Raid detection (X joins within Y seconds → raid mode)
- Auto-lockdown of all text channels during a raid
- Auto-kick or auto-quarantine of new/young accounts joining during a raid
- Anti-spam message rate limiting → auto-timeout
- Anti-invite-link auto-deletion
- Anti mass-mention spam
- Full audit logging (joins/leaves/bans/lockdowns) to a channel you set

Admin commands (require Administrator permission):
```
/security setlog <channel>
/security lockdown
/security unlock
/security panic
/security toggle <true/false>
/security config
/security setthreshold <joins> <window_seconds>
/security raidaction <kick|quarantine>
/security blockinvites <true/false>
/security spamconfig <messages> <window_seconds> <timeout_minutes>
```

### 🔨 Moderation
`/kick` `/ban` `/timeout` `/purge` `/warn`

## Notes

- Security settings persist to `security_config.json`, written next to `bot.py`
  at runtime. **Railway's filesystem is ephemeral** — this file resets on
  redeploy. For permanent settings storage across redeploys, attach a Railway
  Volume mounted at the bot's working directory, or swap to a database.
- Image/GIF commands cap downloads at 8MB.
- The bot never rate-limits members with Administrator permission.
