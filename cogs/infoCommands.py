import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import asyncio
import io
import uuid
import gc
from datetime import datetime

CONFIG_FILE = "info_channels.json"


class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "http://raw.thug4ff.com/info"
        self.generate_url = "http://profile.thug4ff.com/api/profile"
        self.session = aiohttp.ClientSession()
        self.config_data = self.load_config()
        self.cooldowns = {}

   

    

    def convert_unix_timestamp(self ,timestamp: int) -> str:
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')



    def check_request_limit(self, guild_id):
        try:
            return self.is_server_subscribed(guild_id) or not self.is_limit_reached(guild_id)
        except Exception as e:
            print(f"Error checking request limit: {e}")
            return False

    def load_config(self):
        default_config = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("global_settings", {})
                    loaded_config["global_settings"].setdefault("default_all_channels", False)
                    loaded_config["global_settings"].setdefault("default_cooldown", 30)
                    loaded_config["global_settings"].setdefault("default_daily_limit", 30)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config: {e}")
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")



    async def is_channel_allowed(self, ctx):
        try:
            guild_id = str(ctx.guild.id)
            allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])

            # Autoriser tous les salons si aucun salon n'a été configuré pour ce serveur
            if not allowed_channels:
                return True

            # Sinon, vérifier si le salon actuel est dans la liste autorisée
            return str(ctx.channel.id) in allowed_channels
        except Exception as e:
            print(f"Error checking channel permission: {e}")
            return False

    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for !info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        if str(channel.id) not in self.config_data["servers"][guild_id]["info_channels"]:
            self.config_data["servers"][guild_id]["info_channels"].append(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ {channel.mention} is now allowed for `!info` commands")
        else:
            await ctx.send(f"ℹ️ {channel.mention} is already allowed for `!info` commands")

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from !info commands")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        if guild_id in self.config_data["servers"]:
            if str(channel.id) in self.config_data["servers"][guild_id]["info_channels"]:
                self.config_data["servers"][guild_id]["info_channels"].remove(str(channel.id))
                self.save_config()
                await ctx.send(f"✅ {channel.mention} has been removed from allowed channels")
            else:
                await ctx.send(f"❌ {channel.mention} is not in the list of allowed channels")
        else:
            await ctx.send("ℹ️ This server has no saved configuration")

    @commands.hybrid_command(name="infochannels", description="List allowed channels")
    async def list_info_channels(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)

        if guild_id in self.config_data["servers"] and self.config_data["servers"][guild_id]["info_channels"]:
            channels = []
            for channel_id in self.config_data["servers"][guild_id]["info_channels"]:
                channel = ctx.guild.get_channel(int(channel_id))
                channels.append(f"• {channel.mention if channel else f'ID: {channel_id}'}")

            embed = discord.Embed(
                title="Allowed channels for !info",
                description="\n".join(channels),
                color=discord.Color.blue()
            )
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", self.config_data["global_settings"]["default_cooldown"])
            embed.set_footer(text=f"Current cooldown: {cooldown} seconds")
        else:
            embed = discord.Embed(
                title="Allowed channels for !info",
                description="All channels are allowed (no restriction configured)",
                color=discord.Color.blue()
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info", description="Displays information about a Free Fire player")
    @app_commands.describe(uid="FREE FIRE INFO")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply(" Invalid UID! It must:\n- Be only numbers\n- Have at least 6 digits", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send(" This command is not allowed in this channel.", ephemeral=True)



        cooldown = self.config_data["global_settings"]["default_cooldown"]
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", cooldown)

        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                return await ctx.send(f" Please wait {remaining}s before using this command again", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()
       

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as response:
                    if response.status == 404:
                        return await ctx.send(f" Player with UID `{uid}` not found.")
                    if response.status != 200:
                        return await ctx.send("API error. Try again later.")
                    data = await response.json()

            
            basic_info = data.get('basicInfo', {})
            captain_info = data.get('captainBasicInfo', {})
            clan_info = data.get('clanBasicInfo', {})
            credit_score_info = data.get('creditScoreInfo', {})
            pet_info = data.get('petInfo', {})
            profile_info = data.get('profileInfo', {})
            social_info = data.get('socialInfo', {})


            region = basic_info.get('region', 'Not found')

            embed = discord.Embed(
                title=" Player Information",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            embed.add_field(name="", value="\n".join([
                "**┌  ACCOUNT BASIC INFO**",
                f"**├─ Name**: {basic_info.get('nickname', 'Not found')}",
                f"**├─ UID**: `{uid}`",
                f"**├─ Level**: {basic_info.get('level', 'Not found')} (Exp: {basic_info.get('exp', '?')})",
                f"**├─ Region**: {region}",
                f"**├─ Likes**: {basic_info.get('liked', 'Not found')}",
                f"**├─ Honor Score**: {credit_score_info.get('creditScore', 'Not found')}",
                f"**└─ Signature**: {social_info.get('signature', 'None') or 'None'}"
            ]), inline=False)
          

            embed.add_field(name="", value="\n".join([
                "**┌  ACCOUNT ACTIVITY**",
                f"**├─ Most Recent OB**: {basic_info.get('releaseVersion', '?')}",
                f"**├─ Current BP Badges**: {basic_info.get('badgeCnt', 'Not found')}",
                f"**├─ BR Rank**: {'' if basic_info.get('showBrRank') else 'Not found'} {basic_info.get('rankingPoints', '?')}",
                f"**├─ CS Rank**: {'' if basic_info.get('showCsRank') else 'Not found'} {basic_info.get('csRankingPoints', '?')} ",
                f"**├─ Created At**: {self.convert_unix_timestamp(int(basic_info.get('createAt', 'Not found')))}",
                f"**└─ Last Login**: {self.convert_unix_timestamp(int(basic_info.get('lastLoginAt', 'Not found')))}"

            ]), inline=False)

            embed.add_field(name="", value="\n".join([
                "**┌  ACCOUNT OVERVIEW**",
                f"**├─ Avatar ID**: {profile_info.get('avatarId', 'Not found')}",
                f"**├─ Banner ID**: {basic_info.get('bannerId', 'Not found')}",
                f"**├─ Pin ID**: {captain_info.get('pinId', 'Not found') if captain_info else 'Default'}",
                f"**└─ Equipped Skills**: {profile_info.get('equipedSkills', 'Not found')}"
            ]), inline=False)

            embed.add_field(name="", value="\n".join([
                "**┌  PET DETAILS**",
                f"**├─ Equipped?**: {'Yes' if pet_info.get('isSelected') else 'Not Found'}",
                f"**├─ Pet Name**: {pet_info.get('name', 'Not Found')}",
                f"**├─ Pet Exp**: {pet_info.get('exp', 'Not Found')}",
                f"**└─ Pet Level**: {pet_info.get('level', 'Not Found')}"
            ]), inline=False)

            if clan_info:
                guild_info = [
                    "**┌  GUILD INFO**",
                    f"**├─ Guild Name**: {clan_info.get('clanName', 'Not found')}",
                    f"**├─ Guild ID**: `{clan_info.get('clanId', 'Not found')}`",
                    f"**├─ Guild Level**: {clan_info.get('clanLevel', 'Not found')}",
                    f"**├─ Live Members**: {clan_info.get('memberNum', 'Not found')}/{clan_info.get('capacity', '?')}"
                ]
                if captain_info:
                    guild_info.extend([
                        "**└─ Leader Info**:",
                        f"    **├─ Leader Name**: {captain_info.get('nickname', 'Not found')}",
                        f"    **├─ Leader UID**: `{captain_info.get('accountId', 'Not found')}`",
                        f"    **├─ Leader Level**: {captain_info.get('level', 'Not found')} (Exp: {captain_info.get('exp', '?')})",
                        f"    **├─ Last Login**: {self.convert_unix_timestamp(int(captain_info.get('lastLoginAt', 'Not found')))}",
                        f"    **├─ Title**: {captain_info.get('title', 'Not found')}",
                        f"    **├─ BP Badges**: {captain_info.get('badgeCnt', '?')}",
                        f"    **├─ BR Rank**: {'' if captain_info.get('showBrRank') else 'Not found'} {captain_info.get('rankingPoints', 'Not found')}",
                        f"    **└─ CS Rank**: {'' if captain_info.get('showCsRank') else 'Not found'} {captain_info.get('csRankingPoints', 'Not found')} "
                    ])
                embed.add_field(name="", value="\n".join(guild_info), inline=False)



            embed.set_footer(text="DEVELOPED BY 0x ACID")
            await ctx.send(embed=embed)

            if region and uid:
                try:
                    image_url = f"{self.generate_url}?uid={uid}"
                    print(f"Url d'image = {image_url}")
                    if image_url:
                        async with self.session.get(image_url) as img_file:
                            if img_file.status == 200:
                                with io.BytesIO(await img_file.read()) as buf:
                                    file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                                    await ctx.send(file=file)  # ✅ ENVOYER L'IMAGE
                                    print("Image envoyée avec succès")
                            else:
                                print(f"Erreur HTTP: {img_file.status}")
                except Exception as e:
                    print("Image generation failed:", e)

        except Exception as e:
            await ctx.send(f" Unexpected error: `{e}`")
        finally:
            gc.collect()


    async def cog_unload(self):
        await self.session.close()

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(
            title="❌ Player Not Found",
            description=(
                f"UID `{uid}` not found or inaccessible.\n\n"
                "⚠️ **Note:** IND servers are currently not working."
            ),
            color=0xE74C3C
        )
        embed.add_field(
            name="Tip",
            value="- Make sure the UID is correct\n- Try a different UID",
            inline=False
        )
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_error(self, ctx):
        await ctx.send(embed=discord.Embed(
            title="⚠️ API Error",
            description="The Free Fire API is not responding. Try again later.",
            color=0xF39C12
        ))



async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
