"""
MegaBot - Single-File Fun + Anti-Raid Security Discord Bot
=============================================================
Deploy on Railway:
  1. Push this repo (bot.py, requirements.txt, README.md) to GitHub.
  2. On Railway: New Project -> Deploy from GitHub repo.
  3. Add a variable: DISCORD_TOKEN = your bot token (Variables tab).
     Optional: BOT_PREFIX (default "!").
  4. Set the Start Command to:  python bot.py
     (Railway auto-detects Python via requirements.txt / Nixpacks.)

Discord Developer Portal setup (before running):
  - Enable Privileged Gateway Intents: SERVER MEMBERS + MESSAGE CONTENT
  - Invite the bot with scopes: bot, applications.commands
"""

import asyncio
import datetime
import io
import json
import logging
import os
import random
import time
from collections import defaultdict, deque

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("megabot")

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents,
                    help_command=commands.DefaultHelpCommand())

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "security_config.json")
MAX_BYTES = 8 * 1024 * 1024  # 8MB cap for media downloads

DEFAULT_GUILD_CONFIG = {
    "log_channel_id": None,
    "raid_join_threshold": 6,
    "raid_join_window": 10,
    "raid_action": "kick",          # "kick" or "quarantine"
    "min_account_age_hours": 24,
    "auto_lockdown_on_raid": True,
    "spam_message_threshold": 6,
    "spam_window_seconds": 6,
    "spam_timeout_minutes": 5,
    "block_invite_links": True,
    "mass_mention_limit": 6,
    "quarantine_role_name": "Quarantined",
    "enabled": True,
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


ALL_CONFIG: dict = load_config()


def cfg(guild_id: int) -> dict:
    gid = str(guild_id)
    merged = DEFAULT_GUILD_CONFIG.copy()
    merged.update(ALL_CONFIG.get(gid, {}))
    ALL_CONFIG[gid] = merged
    return merged


async def download(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ValueError(f"Failed to download file (HTTP {resp.status}).")
            data = await resp.read()
            if len(data) > MAX_BYTES:
                raise ValueError("File is too large (max 8MB).")
            return data


# ---------------------------------------------------------------------------
# Data pools for fun commands
# ---------------------------------------------------------------------------

EIGHT_BALL_RESPONSES = [
    "It is certain.", "Without a doubt.", "You may rely on it.", "Yes, definitely.",
    "It is decidedly so.", "As I see it, yes.", "Most likely.", "Outlook good.",
    "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
    "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
    "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]

JOKES = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "I told my computer I needed a break, and it said no problem, it'll go to sleep.",
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I'm reading a book about anti-gravity. It's impossible to put down.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "What do you call fake spaghetti? An impasta.",
    "I would tell you a UDP joke, but you might not get it.",
    "Why do Java developers wear glasses? Because they don't C#.",
]

WOULD_YOU_RATHER = [
    ("have the ability to fly", "have the ability to turn invisible"),
    ("be able to speak every language", "be able to talk to animals"),
    ("always be 10 minutes late", "always be 20 minutes early"),
    ("fight one horse-sized duck", "fight 100 duck-sized horses"),
    ("have unlimited money", "have unlimited time"),
    ("never use social media again", "never watch another movie/show again"),
]

NEVER_HAVE_I_EVER = [
    "never have I ever fallen asleep in class/work.",
    "never have I ever forgotten someone's name right after being introduced.",
    "never have I ever sung in the shower.",
    "never have I ever pretended to be sick to skip something.",
    "never have I ever laughed so hard I cried.",
    "never have I ever sent a text to the wrong person.",
]

TRUTH_QUESTIONS = [
    "What's the most embarrassing thing that's happened to you?",
    "What's a secret talent you have that few people know about?",
    "What's the weirdest dream you've ever had?",
    "What's your biggest fear?",
    "What's the most childish thing you still do?",
]

DARE_PROMPTS = [
    "Send the last photo in your camera roll to the chat (if safe/appropriate!).",
    "Type your next 3 messages using only emojis.",
    "Let the group pick your Discord status for the next hour.",
    "Speak (or type) in rhymes for the next 5 minutes.",
    "Do your best impression of a robot in your next message.",
]

RIDDLES = [
    ("What has keys but no locks, space but no room, and you can enter but not go in?", "A keyboard"),
    ("The more you take, the more you leave behind. What am I?", "Footsteps"),
    ("What has a face and two hands but no arms or legs?", "A clock"),
    ("What gets wetter as it dries?", "A towel"),
    ("I speak without a mouth and hear without ears. What am I?", "An echo"),
]

COMPLIMENTS = [
    "You light up every server you're in.",
    "Your energy is honestly contagious.",
    "You have great taste — you're talking to a bot, after all.",
    "You're sharper than you give yourself credit for.",
    "The world's better with you in it.",
]

ROASTS = [
    "You're the reason the instructions say 'do not eat.'",
    "You bring everyone so much joy... when you leave the call.",
    "I'd explain it to you, but I left my crayons at home.",
    "You're not stupid, you just have bad luck thinking.",
    "If laughter is the best medicine, your face must be curing the world.",
]

FORTUNES = [
    "A pleasant surprise is waiting for you.",
    "Your hard work is about to pay off.",
    "Adventure awaits — say yes to the next opportunity.",
    "Someone appreciates you more than you know.",
    "A small risk today leads to a big reward tomorrow.",
]


# ---------------------------------------------------------------------------
# RPS interactive view
# ---------------------------------------------------------------------------

class RPSView(discord.ui.View):
    def __init__(self, author: discord.abc.User):
        super().__init__(timeout=30)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    async def _play(self, interaction: discord.Interaction, choice: str):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        outcome = self._judge(choice, bot_choice)
        embed = discord.Embed(title="🪨📄✂️ Rock Paper Scissors", color=discord.Color.blurple())
        embed.add_field(name="You chose", value=choice.capitalize())
        embed.add_field(name="I chose", value=bot_choice.capitalize())
        embed.add_field(name="Result", value=outcome, inline=False)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @staticmethod
    def _judge(p1: str, p2: str) -> str:
        if p1 == p2:
            return "It's a tie! 🤝"
        wins = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        return "You win! 🎉" if wins[p1] == p2 else "I win! 🤖"

    @discord.ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "rock")

    @discord.ui.button(label="Paper", emoji="📄", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "paper")

    @discord.ui.button(label="Scissors", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "scissors")


# ---------------------------------------------------------------------------
# FUN COMMANDS (24)
# ---------------------------------------------------------------------------

@bot.tree.command(name="say", description="Make the bot say something.")
@app_commands.describe(message="What should the bot say?")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("✅ Sent!", ephemeral=True)
    await interaction.channel.send(message)


@bot.tree.command(name="embedsay", description="Make the bot say something in a nice embed.")
@app_commands.describe(message="What should the embed say?", title="Optional embed title")
async def embedsay(interaction: discord.Interaction, message: str, title: str = None):
    embed = discord.Embed(description=message, color=discord.Color.random())
    if title:
        embed.title = title
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question.")
@app_commands.describe(question="Your yes/no question")
async def eight_ball(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.dark_purple())
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=random.choice(EIGHT_BALL_RESPONSES), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip", description="Flip a coin.")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 The coin landed on **{result}**!")


@bot.tree.command(name="roll", description="Roll dice, e.g. 2d6.")
@app_commands.describe(dice="Format: NdM, e.g. 2d6 rolls two 6-sided dice")
async def roll(interaction: discord.Interaction, dice: str = "1d6"):
    try:
        n, sides = dice.lower().split("d")
        n, sides = int(n), int(sides)
        if not (1 <= n <= 100) or not (2 <= sides <= 1000):
            raise ValueError
    except ValueError:
        await interaction.response.send_message("Invalid format! Use NdM like `2d6`.", ephemeral=True)
        return
    rolls = [random.randint(1, sides) for _ in range(n)]
    await interaction.response.send_message(
        f"🎲 Rolling {dice}: {', '.join(map(str, rolls))} (Total: **{sum(rolls)}**)"
    )


@bot.tree.command(name="rps", description="Play Rock Paper Scissors against the bot.")
async def rps(interaction: discord.Interaction):
    view = RPSView(interaction.user)
    await interaction.response.send_message("Choose your move:", view=view)


@bot.tree.command(name="guessnumber", description="Play a number guessing game (1-100).")
async def guessnumber(interaction: discord.Interaction):
    secret = random.randint(1, 100)
    await interaction.response.send_message(
        "🎯 I'm thinking of a number between 1 and 100! You have 6 tries. Type your guesses below."
    )

    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.content.isdigit()

    for attempt in range(6):
        try:
            msg = await bot.wait_for("message", check=check, timeout=20)
        except asyncio.TimeoutError:
            await interaction.followup.send(f"⌛ Time's up! The number was **{secret}**.")
            return
        guess = int(msg.content)
        if guess == secret:
            await interaction.followup.send(f"🎉 Correct! The number was **{secret}**. You got it in {attempt+1} tries!")
            return
        elif guess < secret:
            await interaction.followup.send("📈 Higher!")
        else:
            await interaction.followup.send("📉 Lower!")
    await interaction.followup.send(f"💀 Out of tries! The number was **{secret}**.")


@bot.tree.command(name="trivia", description="Get a random trivia question.")
async def trivia(interaction: discord.Interaction):
    import html as htmllib
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        async with session.get("https://opentdb.com/api.php?amount=1&type=multiple") as resp:
            data = await resp.json()
    if not data.get("results"):
        await interaction.followup.send("Couldn't fetch a trivia question, try again later.")
        return
    q = data["results"][0]
    question = htmllib.unescape(q["question"])
    correct = htmllib.unescape(q["correct_answer"])
    choices = [htmllib.unescape(a) for a in q["incorrect_answers"]] + [correct]
    random.shuffle(choices)
    letters = ["🇦", "🇧", "🇨", "🇩"]
    desc = "\n".join(f"{letters[i]} {c}" for i, c in enumerate(choices))
    embed = discord.Embed(title="🧠 Trivia Time!", description=f"**{question}**\n\n{desc}", color=discord.Color.teal())
    msg = await interaction.followup.send(embed=embed)
    for e in letters[:len(choices)]:
        await msg.add_reaction(e)

    def check(reaction, user):
        return user.id == interaction.user.id and reaction.message.id == msg.id and str(reaction.emoji) in letters

    try:
        reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=20)
        picked = choices[letters.index(str(reaction.emoji))]
        if picked == correct:
            await interaction.followup.send("✅ Correct!")
        else:
            await interaction.followup.send(f"❌ Wrong! The correct answer was **{correct}**.")
    except asyncio.TimeoutError:
        await interaction.followup.send(f"⌛ Time's up! The correct answer was **{correct}**.")


@bot.tree.command(name="wouldyourather", description="Get a random 'would you rather' question.")
async def wouldyourather(interaction: discord.Interaction):
    a, b = random.choice(WOULD_YOU_RATHER)
    await interaction.response.send_message(f"🤔 Would you rather **{a}** or **{b}**?")


@bot.tree.command(name="neverhaveiever", description="Get a random 'never have I ever' statement.")
async def neverhaveiever(interaction: discord.Interaction):
    await interaction.response.send_message(f"🙊 {random.choice(NEVER_HAVE_I_EVER)}")


@bot.tree.command(name="truth", description="Get a random truth question.")
async def truth(interaction: discord.Interaction):
    await interaction.response.send_message(f"💬 Truth: {random.choice(TRUTH_QUESTIONS)}")


@bot.tree.command(name="dare", description="Get a random dare.")
async def dare(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔥 Dare: {random.choice(DARE_PROMPTS)}")


@bot.tree.command(name="riddle", description="Get a random riddle (answer hidden in spoiler).")
async def riddle(interaction: discord.Interaction):
    question, answer = random.choice(RIDDLES)
    await interaction.response.send_message(f"🧩 {question}\n\nAnswer: ||{answer}||")


@bot.tree.command(name="joke", description="Get a random joke.")
async def joke(interaction: discord.Interaction):
    await interaction.response.send_message(f"😂 {random.choice(JOKES)}")


@bot.tree.command(name="compliment", description="Get a nice compliment (optionally for someone else).")
@app_commands.describe(user="Who to compliment (optional)")
async def compliment(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    await interaction.response.send_message(f"💖 {target.mention}, {random.choice(COMPLIMENTS)}")


@bot.tree.command(name="roast", description="Get a silly, light-hearted roast.")
@app_commands.describe(user="Who to roast (optional)")
async def roast(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    await interaction.response.send_message(f"🔥 {target.mention}, {random.choice(ROASTS)}")


@bot.tree.command(name="fortune", description="Crack open a virtual fortune cookie.")
async def fortune(interaction: discord.Interaction):
    await interaction.response.send_message(f"🥠 {random.choice(FORTUNES)}")


@bot.tree.command(name="randomnumber", description="Get a random number in a range.")
@app_commands.describe(minimum="Minimum value", maximum="Maximum value")
async def randomnumber(interaction: discord.Interaction, minimum: int = 1, maximum: int = 100):
    if minimum >= maximum:
        await interaction.response.send_message("Minimum must be less than maximum!", ephemeral=True)
        return
    await interaction.response.send_message(f"🔢 Your random number: **{random.randint(minimum, maximum)}**")


@bot.tree.command(name="choose", description="Let the bot choose between options for you.")
@app_commands.describe(options="Comma-separated list of options")
async def choose(interaction: discord.Interaction, options: str):
    choices = [o.strip() for o in options.split(",") if o.strip()]
    if len(choices) < 2:
        await interaction.response.send_message("Give me at least 2 comma-separated options!", ephemeral=True)
        return
    await interaction.response.send_message(f"🤖 I choose: **{random.choice(choices)}**")


@bot.tree.command(name="reverse", description="Reverse your text.")
@app_commands.describe(text="Text to reverse")
async def reverse(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"🔁 {text[::-1]}")


@bot.tree.command(name="mock", description="MoCk TeXt LiKe ThIs.")
@app_commands.describe(text="Text to mock")
async def mock(interaction: discord.Interaction, text: str):
    mocked = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
    await interaction.response.send_message(mocked)


@bot.tree.command(name="clap", description="Add 👏 claps between every word.")
@app_commands.describe(text="Text to clap-ify")
async def clap(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(" 👏 ".join(text.split()))


@bot.tree.command(name="poll", description="Create a quick yes/no poll.")
@app_commands.describe(question="The poll question")
async def poll(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.gold())
    embed.set_footer(text=f"Poll by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await msg.add_reaction("🤷")


@bot.tree.command(name="avatar", description="Get a user's avatar in full size.")
@app_commands.describe(user="Whose avatar to fetch (default: yourself)")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    embed = discord.Embed(title=f"{target.display_name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# ---------------------------------------------------------------------------
# MEDIA COMMANDS (7): image <-> gif <-> url
# ---------------------------------------------------------------------------

@bot.tree.command(name="imagetogif", description="Convert an image attachment into a GIF file.")
@app_commands.describe(image="Image attachment to convert")
async def imagetogif(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()
    try:
        raw = await download(image.url)
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        buf = io.BytesIO()
        im.save(buf, format="GIF")
        buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, filename="converted.gif"))
    except Exception as e:
        await interaction.followup.send(f"❌ Conversion failed: {e}")


@bot.tree.command(name="giftoimage", description="Extract the first frame of a GIF as a PNG image.")
@app_commands.describe(gif="GIF attachment to convert")
async def giftoimage(interaction: discord.Interaction, gif: discord.Attachment):
    await interaction.response.defer()
    try:
        raw = await download(gif.url)
        im = Image.open(io.BytesIO(raw))
        im.seek(0)
        frame = im.convert("RGBA")
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, filename="frame.png"))
    except Exception as e:
        await interaction.followup.send(f"❌ Conversion failed: {e}")


@bot.tree.command(name="urltoimage", description="Download an image from a URL and upload it as a file.")
@app_commands.describe(url="Direct link to an image")
async def urltoimage(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    try:
        raw = await download(url)
        im = Image.open(io.BytesIO(raw))
        fmt = (im.format or "PNG").upper()
        buf = io.BytesIO()
        im.save(buf, format=fmt)
        buf.seek(0)
        ext = fmt.lower() if fmt.lower() != "jpeg" else "jpg"
        await interaction.followup.send(file=discord.File(buf, filename=f"image.{ext}"))
    except Exception as e:
        await interaction.followup.send(f"❌ Couldn't fetch/convert that URL: {e}")


@bot.tree.command(name="imagetourl", description="Upload an image and get a direct CDN URL back.")
@app_commands.describe(image="Image attachment to host")
async def imagetourl(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()
    try:
        raw = await download(image.url)
        buf = io.BytesIO(raw)
        buf.seek(0)
        msg = await interaction.followup.send(
            content="📎 Hosted your image — direct link below:",
            file=discord.File(buf, filename=image.filename),
            wait=True,
        )
        direct_url = msg.attachments[0].url
        await interaction.followup.send(f"🔗 {direct_url}")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to host image: {e}")


@bot.tree.command(name="pixelate", description="Pixelate an image for a retro effect.")
@app_commands.describe(image="Image to pixelate", strength="Pixel block size (2-40, default 8)")
async def pixelate(interaction: discord.Interaction, image: discord.Attachment, strength: int = 8):
    await interaction.response.defer()
    try:
        strength = max(2, min(strength, 40))
        raw = await download(image.url)
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        w, h = im.size
        small = im.resize((max(1, w // strength), max(1, h // strength)), Image.BILINEAR)
        result = small.resize((w, h), Image.NEAREST)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, filename="pixelated.png"))
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}")


@bot.tree.command(name="grayscale", description="Convert an image to grayscale.")
@app_commands.describe(image="Image to convert")
async def grayscale(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()
    try:
        raw = await download(image.url)
        im = Image.open(io.BytesIO(raw)).convert("L")
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, filename="grayscale.png"))
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}")


@bot.tree.command(name="invert", description="Invert the colors of an image.")
@app_commands.describe(image="Image to invert")
async def invert(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()
    try:
        raw = await download(image.url)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        inverted = ImageOps.invert(im)
        buf = io.BytesIO()
        inverted.save(buf, format="PNG")
        buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, filename="inverted.png"))
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}")


# ---------------------------------------------------------------------------
# SECURITY / ANTI-RAID
# ---------------------------------------------------------------------------

join_times: dict = defaultdict(deque)
message_times: dict = defaultdict(lambda: defaultdict(deque))
raid_mode: dict = defaultdict(bool)
locked_channels: dict = defaultdict(set)


async def log_event(guild: discord.Guild, embed: discord.Embed):
    ch_id = cfg(guild.id).get("log_channel_id")
    if not ch_id:
        return
    channel = guild.get_channel(ch_id)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def lockdown_guild(guild: discord.Guild, reason: str):
    locked = locked_channels[guild.id]
    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is not False:
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
                locked.add(channel.id)
        except discord.Forbidden:
            continue
    await log_event(guild, discord.Embed(title="🔒 Server Locked Down", description=reason, color=discord.Color.red()))


async def unlock_guild(guild: discord.Guild, reason: str):
    locked = locked_channels[guild.id]
    for channel in list(guild.text_channels):
        if channel.id in locked:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = None
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            except discord.Forbidden:
                pass
    locked.clear()
    raid_mode[guild.id] = False
    await log_event(guild, discord.Embed(title="🔓 Server Unlocked", description=reason, color=discord.Color.green()))


async def handle_suspicious_member(member: discord.Member, gcfg: dict):
    guild = member.guild
    action = gcfg["raid_action"]
    try:
        if action == "kick":
            await member.kick(reason="Anti-raid: suspicious new account during raid window")
            note = "kicked"
        else:
            role = discord.utils.get(guild.roles, name=gcfg["quarantine_role_name"])
            if role is None:
                role = await guild.create_role(name=gcfg["quarantine_role_name"], reason="Anti-raid quarantine role")
                for channel in guild.channels:
                    try:
                        await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                    except discord.Forbidden:
                        pass
            await member.add_roles(role, reason="Anti-raid: quarantined suspicious new account")
            note = "quarantined"
        embed = discord.Embed(
            title="🛡️ Suspicious Account Actioned",
            description=f"{member.mention} (`{member}`) was **{note}** for being a new account during a raid.",
            color=discord.Color.orange(),
        )
        await log_event(guild, embed)
    except discord.Forbidden:
        pass


async def enter_raid_mode(guild: discord.Guild, gcfg: dict):
    alert = discord.Embed(
        title="🚨 RAID DETECTED",
        description=(
            f"Unusual join activity detected ({gcfg['raid_join_threshold']}+ joins in "
            f"{gcfg['raid_join_window']}s). Raid mode activated."
        ),
        color=discord.Color.red(),
    )
    await log_event(guild, alert)
    if gcfg["auto_lockdown_on_raid"]:
        await lockdown_guild(guild, reason="Automatic raid protection")


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    gcfg = cfg(guild.id)
    if not gcfg["enabled"]:
        return

    now = time.time()
    dq = join_times[guild.id]
    dq.append(now)
    while dq and now - dq[0] > gcfg["raid_join_window"]:
        dq.popleft()

    account_age = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
    embed = discord.Embed(
        title="📥 Member Joined",
        description=f"{member.mention} (`{member}`)",
        color=discord.Color.green(),
    )
    embed.add_field(name="Account Age", value=f"{account_age:.1f} hours")
    embed.set_footer(text=f"ID: {member.id}")
    await log_event(guild, embed)

    if len(dq) >= gcfg["raid_join_threshold"]:
        if not raid_mode[guild.id]:
            raid_mode[guild.id] = True
            await enter_raid_mode(guild, gcfg)
        if account_age < gcfg["min_account_age_hours"]:
            await handle_suspicious_member(member, gcfg)


@bot.event
async def on_member_remove(member: discord.Member):
    embed = discord.Embed(title="📤 Member Left", description=f"`{member}` left the server.", color=discord.Color.dark_grey())
    await log_event(member.guild, embed)


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    embed = discord.Embed(title="🔨 Member Banned", description=f"`{user}` was banned.", color=discord.Color.dark_red())
    await log_event(guild, embed)


def contains_invite(content: str) -> bool:
    lowered = content.lower()
    return any(x in lowered for x in ["discord.gg/", "discord.com/invite/", "discordapp.com/invite/"])


async def punish_spammer(member: discord.Member, gcfg: dict, reason: str):
    try:
        await member.timeout(datetime.timedelta(minutes=gcfg["spam_timeout_minutes"]), reason=reason)
        embed = discord.Embed(
            title="⏱️ Member Timed Out",
            description=f"{member.mention} (`{member}`) timed out for {gcfg['spam_timeout_minutes']} min.\nReason: {reason}",
            color=discord.Color.orange(),
        )
        await log_event(member.guild, embed)
    except discord.Forbidden:
        pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    gcfg = cfg(message.guild.id)
    if gcfg["enabled"]:
        member = message.author
        skip_limits = isinstance(member, discord.Member) and member.guild_permissions.administrator

        if not skip_limits:
            if len(message.mentions) + len(message.role_mentions) >= gcfg["mass_mention_limit"]:
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                await punish_spammer(member, gcfg, reason="Mass mention spam")
                return

            if gcfg["block_invite_links"] and contains_invite(message.content):
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                try:
                    await message.channel.send(f"{member.mention} ⚠️ Discord invite links aren't allowed here.", delete_after=6)
                except discord.Forbidden:
                    pass
                return

            now = time.time()
            dq = message_times[message.guild.id][member.id]
            dq.append(now)
            while dq and now - dq[0] > gcfg["spam_window_seconds"]:
                dq.popleft()
            if len(dq) >= gcfg["spam_message_threshold"]:
                dq.clear()
                await punish_spammer(member, gcfg, reason="Message spam")

    await bot.process_commands(message)


# --- /security command group ---

security_group = app_commands.Group(name="security", description="Anti-raid & security configuration")


@security_group.command(name="setlog", description="Set the mod-log channel for security events.")
@app_commands.checks.has_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    gcfg = cfg(interaction.guild.id)
    gcfg["log_channel_id"] = channel.id
    save_config(ALL_CONFIG)
    await interaction.response.send_message(f"✅ Security log channel set to {channel.mention}.")


@security_group.command(name="lockdown", description="Manually lock down all text channels.")
@app_commands.checks.has_permissions(administrator=True)
async def lockdown(interaction: discord.Interaction):
    await interaction.response.defer()
    await lockdown_guild(interaction.guild, reason=f"Manual lockdown by {interaction.user}")
    await interaction.followup.send("🔒 Server locked down.")


@security_group.command(name="unlock", description="Remove lockdown and restore channel permissions.")
@app_commands.checks.has_permissions(administrator=True)
async def unlock(interaction: discord.Interaction):
    await interaction.response.defer()
    await unlock_guild(interaction.guild, reason=f"Manual unlock by {interaction.user}")
    await interaction.followup.send("🔓 Server unlocked.")


@security_group.command(name="toggle", description="Enable or disable the anti-raid/security system.")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction, enabled: bool):
    gcfg = cfg(interaction.guild.id)
    gcfg["enabled"] = enabled
    save_config(ALL_CONFIG)
    await interaction.response.send_message(f"🛡️ Security system {'enabled' if enabled else 'disabled'}.")


@security_group.command(name="config", description="View current security configuration.")
@app_commands.checks.has_permissions(administrator=True)
async def config_view(interaction: discord.Interaction):
    gcfg = cfg(interaction.guild.id)
    embed = discord.Embed(title="🛡️ Security Configuration", color=discord.Color.blue())
    for k, v in gcfg.items():
        embed.add_field(name=k, value=str(v), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@security_group.command(name="setthreshold", description="Set raid join threshold (joins within the window).")
@app_commands.checks.has_permissions(administrator=True)
async def setthreshold(interaction: discord.Interaction, joins: int, window_seconds: int):
    gcfg = cfg(interaction.guild.id)
    gcfg["raid_join_threshold"] = max(2, joins)
    gcfg["raid_join_window"] = max(3, window_seconds)
    save_config(ALL_CONFIG)
    await interaction.response.send_message(f"✅ Raid threshold set: {joins} joins within {window_seconds}s triggers raid mode.")


@security_group.command(name="raidaction", description="Set what happens to suspicious accounts during a raid.")
@app_commands.describe(action="kick or quarantine")
@app_commands.choices(action=[
    app_commands.Choice(name="kick", value="kick"),
    app_commands.Choice(name="quarantine", value="quarantine"),
])
@app_commands.checks.has_permissions(administrator=True)
async def raidaction(interaction: discord.Interaction, action: app_commands.Choice[str]):
    gcfg = cfg(interaction.guild.id)
    gcfg["raid_action"] = action.value
    save_config(ALL_CONFIG)
    await interaction.response.send_message(f"✅ Raid action set to **{action.value}**.")


@security_group.command(name="blockinvites", description="Toggle blocking of Discord invite links.")
@app_commands.checks.has_permissions(administrator=True)
async def blockinvites(interaction: discord.Interaction, enabled: bool):
    gcfg = cfg(interaction.guild.id)
    gcfg["block_invite_links"] = enabled
    save_config(ALL_CONFIG)
    await interaction.response.send_message(f"✅ Invite link blocking {'enabled' if enabled else 'disabled'}.")


@security_group.command(name="spamconfig", description="Configure anti-spam message rate limiting.")
@app_commands.checks.has_permissions(administrator=True)
async def spamconfig(interaction: discord.Interaction, messages: int, window_seconds: int, timeout_minutes: int):
    gcfg = cfg(interaction.guild.id)
    gcfg["spam_message_threshold"] = max(2, messages)
    gcfg["spam_window_seconds"] = max(2, window_seconds)
    gcfg["spam_timeout_minutes"] = max(1, timeout_minutes)
    save_config(ALL_CONFIG)
    await interaction.response.send_message(f"✅ Anti-spam: {messages} msgs/{window_seconds}s → {timeout_minutes}min timeout.")


@security_group.command(name="panic", description="PANIC: instantly lock down the server.")
@app_commands.checks.has_permissions(administrator=True)
async def panic(interaction: discord.Interaction):
    await interaction.response.defer()
    await lockdown_guild(interaction.guild, reason=f"PANIC button pressed by {interaction.user}")
    await interaction.followup.send("🚨 PANIC LOCKDOWN ENGAGED. Use `/security unlock` when safe.")


bot.tree.add_command(security_group)


# ---------------------------------------------------------------------------
# MODERATION (5)
# ---------------------------------------------------------------------------

@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked {member.mention} — {reason}")


@bot.tree.command(name="ban", description="Ban a member from the server.")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(member="Member to ban", reason="Reason for the ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned {member.mention} — {reason}")


@bot.tree.command(name="timeout", description="Timeout a member for a number of minutes.")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(member="Member to timeout", minutes="Duration in minutes", reason="Reason")
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"⏱️ Timed out {member.mention} for {minutes} minutes — {reason}")


@bot.tree.command(name="purge", description="Delete a number of recent messages in this channel.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete (max 100)")
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)


@bot.tree.command(name="warn", description="Warn a member (sends them a DM notice).")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(member="Member to warn", reason="Reason for the warning")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.send(f"⚠️ You have been warned in **{interaction.guild.name}**: {reason}")
    except discord.Forbidden:
        pass
    await interaction.response.send_message(f"⚠️ Warned {member.mention} — {reason}")


# ---------------------------------------------------------------------------
# READY / STARTUP
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | /help"), status=discord.Status.online)
    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} slash commands globally.")
    except Exception as e:
        log.exception(f"Slash command sync failed: {e}")


def main():
    if not TOKEN:
        raise SystemExit("No DISCORD_TOKEN found. Set it in Railway's Variables tab (or a local .env).")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
