import discord
from discord.ext import commands
import asyncio
from collections import defaultdict, deque
import os  # <-- This will read your environment variable

# ------------------- CONFIGURATION -------------------
DEFAULT_ANTI_NUKE = True
BAN_THRESHOLD = 5
KICK_THRESHOLD = 5
CHANNEL_CREATE_THRESHOLD = 5
CHANNEL_DELETE_THRESHOLD = 5
ROLE_CREATE_THRESHOLD = 5
ROLE_DELETE_THRESHOLD = 5
TIME_WINDOW = 10  # seconds
# ---------------------------------------------------

intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Store per-guild data
guild_settings = {}
action_timestamps = defaultdict(lambda: defaultdict(lambda: deque()))

def is_admin(member):
    return member.guild_permissions.administrator

async def log_action(guild, message):
    settings = guild_settings.get(guild.id, {})
    log_channel_id = settings.get('log_channel')
    if log_channel_id:
        channel = guild.get_channel(log_channel_id)
        if channel:
            await channel.send(message)

def check_rate_limit(guild_id, action_type, threshold):
    now = asyncio.get_event_loop().time()
    timestamps = action_timestamps[guild_id][action_type]
    while timestamps and now - timestamps[0] > TIME_WINDOW:
        timestamps.popleft()
    timestamps.append(now)
    return len(timestamps) >= threshold

async def punish_perpetrator(guild, user, reason):
    try:
        await guild.ban(user, reason=reason)
        await log_action(guild, f"🔨 Banned {user.mention} ({user.id}) for: {reason}")
    except discord.Forbidden:
        await log_action(guild, f"❌ Could not ban {user.mention} – insufficient permissions.")
    except Exception as e:
        await log_action(guild, f"⚠️ Error banning {user.mention}: {e}")

# ------------------- EVENTS -------------------

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.event
async def on_member_ban(guild, user):
    settings = guild_settings.get(guild.id, {})
    if not settings.get('enabled', DEFAULT_ANTI_NUKE):
        return
    async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
        if entry.target.id == user.id:
            perpetrator = entry.user
            if is_admin(perpetrator):
                return
            if check_rate_limit(guild.id, 'ban', BAN_THRESHOLD):
                await punish_perpetrator(guild, perpetrator, f"Mass banning – {BAN_THRESHOLD} bans in {TIME_WINDOW}s")
            break

@bot.event
async def on_member_remove(member):
    guild = member.guild
    settings = guild_settings.get(guild.id, {})
    if not settings.get('enabled', DEFAULT_ANTI_NUKE):
        return
    async for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
        if entry.target.id == member.id:
            perpetrator = entry.user
            if is_admin(perpetrator):
                return
            if check_rate_limit(guild.id, 'kick', KICK_THRESHOLD):
                await punish_perpetrator(guild, perpetrator, f"Mass kicking – {KICK_THRESHOLD} kicks in {TIME_WINDOW}s")
            break

@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    settings = guild_settings.get(guild.id, {})
    if not settings.get('enabled', DEFAULT_ANTI_NUKE):
        return
    async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
        if entry.target.id == channel.id:
            perpetrator = entry.user
            if is_admin(perpetrator):
                return
            if check_rate_limit(guild.id, 'channel_create', CHANNEL_CREATE_THRESHOLD):
                await punish_perpetrator(guild, perpetrator, f"Mass channel creation – {CHANNEL_CREATE_THRESHOLD} creations in {TIME_WINDOW}s")
            break

@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    settings = guild_settings.get(guild.id, {})
    if not settings.get('enabled', DEFAULT_ANTI_NUKE):
        return
    async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        if entry.target.id == channel.id:
            perpetrator = entry.user
            if is_admin(perpetrator):
                return
            if check_rate_limit(guild.id, 'channel_delete', CHANNEL_DELETE_THRESHOLD):
                await punish_perpetrator(guild, perpetrator, f"Mass channel deletion – {CHANNEL_DELETE_THRESHOLD} deletions in {TIME_WINDOW}s")
            break

@bot.event
async def on_guild_role_create(role):
    guild = role.guild
    settings = guild_settings.get(guild.id, {})
    if not settings.get('enabled', DEFAULT_ANTI_NUKE):
        return
    async for entry in guild.audit_logs(action=discord.AuditLogAction.role_create, limit=1):
        if entry.target.id == role.id:
            perpetrator = entry.user
            if is_admin(perpetrator):
                return
            if check_rate_limit(guild.id, 'role_create', ROLE_CREATE_THRESHOLD):
                await punish_perpetrator(guild, perpetrator, f"Mass role creation – {ROLE_CREATE_THRESHOLD} creations in {TIME_WINDOW}s")
            break

@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    settings = guild_settings.get(guild.id, {})
    if not settings.get('enabled', DEFAULT_ANTI_NUKE):
        return
    async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
        if entry.target.id == role.id:
            perpetrator = entry.user
            if is_admin(perpetrator):
                return
            if check_rate_limit(guild.id, 'role_delete', ROLE_DELETE_THRESHOLD):
                await punish_perpetrator(guild, perpetrator, f"Mass role deletion – {ROLE_DELETE_THRESHOLD} deletions in {TIME_WINDOW}s")
            break

# ------------------- COMMANDS -------------------

@bot.command(name='anti-nuke')
@commands.has_permissions(administrator=True)
async def anti_nuke(ctx, action: str = None):
    if action is None:
        status = guild_settings.get(ctx.guild.id, {}).get('enabled', DEFAULT_ANTI_NUKE)
        await ctx.send(f"🛡️ Anti-nuke is currently **{'Enabled' if status else 'Disabled'}**.")
        return

    if action.lower() not in ['enable', 'disable']:
        await ctx.send("❌ Please specify `enable` or `disable`.")
        return

    if ctx.guild.id not in guild_settings:
        guild_settings[ctx.guild.id] = {'enabled': DEFAULT_ANTI_NUKE}

    if action.lower() == 'enable':
        guild_settings[ctx.guild.id]['enabled'] = True
        await ctx.send("✅ Anti-nuke protection **enabled**.")
    else:
        guild_settings[ctx.guild.id]['enabled'] = False
        await ctx.send("❌ Anti-nuke protection **disabled**.")

@bot.command(name='setlog')
@commands.has_permissions(administrator=True)
async def set_log(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send("❌ Please mention a channel, e.g., `!setlog #logs`")
        return
    if ctx.guild.id not in guild_settings:
        guild_settings[ctx.guild.id] = {'enabled': DEFAULT_ANTI_NUKE}
    guild_settings[ctx.guild.id]['log_channel'] = channel.id
    await ctx.send(f"📝 Log channel set to {channel.mention}")

# ------------------- RUN -------------------
if __name__ == '__main__':
    # Read the token from the environment variable
    TOKEN = os.environ.get('DISCORD_TOKEN')
    
    if TOKEN is None:
        print("❌ ERROR: DISCORD_TOKEN environment variable not set!")
        print("👉 Run: export DISCORD_TOKEN='your_token_here' before starting the bot.")
    else:
        print("✅ Token found! Starting bot...")
        bot.run(TOKEN)
