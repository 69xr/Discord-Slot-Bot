import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
import asyncio
import logging

from config import config
from db import (
    create_slot,
    get_slot_by_channel,
    get_slot_by_id,
    get_all_slots,
    update_slot,
    delete_slot,
    get_daily_pings,
    increment_daily_pings,
    add_penalty,
    reset_penalties,
    has_vouched,
    record_vouch,
    generate_custom_id,
    audit,
)
from views import build_slot_embed, SlotView, days_left, utcnow

log = logging.getLogger("slotbot")

async def log_action(bot: commands.Bot, title: str, description: str, color: int = 0x00FFFF):
    if not config.LOG_CHANNEL_ID:
        return
    ch = bot.get_channel(config.LOG_CHANNEL_ID)
    if ch and isinstance(ch, discord.TextChannel):
        embed = discord.Embed(title=title, description=description, color=color, timestamp=utcnow())
        if config.BOT_ICON_URL:
            embed.set_footer(text="Slot Bot Audit", icon_url=config.BOT_ICON_URL)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

async def get_or_create_slot_category(guild: discord.Guild) -> discord.CategoryChannel:
    """Ensure max 10 slots per category. Auto-creates new category when full (e.g. SLOTS, SLOTS 2, SLOTS 3)."""
    prefix = config.SLOT_CATEGORY_PREFIX.strip().upper()

    matching_cats = [
        c for c in guild.categories
        if c.name.upper().startswith(prefix)
    ]

    def get_num(cat: discord.CategoryChannel) -> int:
        part = cat.name.upper().replace(prefix, "").strip()
        return int(part) if part.isdigit() else 1

    matching_cats.sort(key=get_num)

    if matching_cats:
        last_cat = matching_cats[-1]
        text_channels = [ch for ch in last_cat.channels if isinstance(ch, discord.TextChannel)]
        if len(text_channels) < 10:
            return last_cat
        else:
            next_num = get_num(last_cat) + 1
            new_cat_name = f"{config.SLOT_CATEGORY_PREFIX} {next_num}"
            return await guild.create_category(name=new_cat_name)
    else:
        return await guild.create_category(name=config.SLOT_CATEGORY_PREFIX)

class SlotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.expiry_check.start()

    def cog_unload(self):
        self.expiry_check.cancel()

    # --- 1. SLASH COMMAND: /slot ---
    @app_commands.command(name="slot", description="Create a new slot channel with embed and buttons.")
    @app_commands.describe(
        owner="The slot owner",
        slot_name="Title of the slot",
        duration_days="Duration in days",
        contact_link="Contact URL (Discord, website, etc.)",
        thumbnail_url="Optional thumbnail image URL",
        banner_url="Optional banner image URL",
        custom_id="Optional custom slot ID",
        max_daily_pings="Max daily @here/@everyone pings allowed (default: 2)",
    )
    @app_commands.default_permissions(manage_channels=True)
    async def create_slot_cmd(
        self,
        interaction: discord.Interaction,
        owner: discord.Member,
        slot_name: str,
        duration_days: int,
        contact_link: str,
        thumbnail_url: Optional[str] = None,
        banner_url: Optional[str] = None,
        custom_id: Optional[str] = None,
        max_daily_pings: Optional[int] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be used inside a server.", ephemeral=True)
            return

        category = await get_or_create_slot_category(guild)
        daily_pings = max_daily_pings if max_daily_pings is not None else config.DEFAULT_MAX_DAILY_PINGS

        # Permission Overwrites: Everyone can read/view, ONLY Slot Owner can write!
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True, read_messages=True, send_messages=False
            ),
            owner: discord.PermissionOverwrite(
                view_channel=True, read_messages=True, send_messages=True,
                attach_files=True, embed_links=True, mention_everyone=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, read_messages=True, send_messages=True,
                manage_channels=True, manage_messages=True
            ),
        }

        channel = await guild.create_text_channel(
            name=f"slot-{owner.name}".lower()[:100],
            overwrites=overwrites,
            category=category,
            topic=f"Slot owned by {owner}",
        )

        now = utcnow()
        expiry = now + timedelta(days=duration_days)
        cid = custom_id or generate_custom_id()

        slot_id = create_slot(
            guild_id=guild.id,
            channel_id=channel.id,
            owner_id=owner.id,
            slot_name=slot_name,
            custom_id=cid,
            purchase_date=now.isoformat(),
            expiry_date=expiry.isoformat(),
            duration_days=duration_days,
            thumbnail_url=thumbnail_url,
            banner_url=banner_url,
            contact_link=contact_link,
            max_daily_pings=daily_pings,
        )

        row = get_slot_by_id(slot_id)
        slot_view = SlotView(dict(row))
        await channel.send(embed=build_slot_embed(row), view=slot_view)
        self.bot.add_view(slot_view)

        await interaction.followup.send(
            f"✅ Slot created in **{category.name}** for {owner.mention}: {channel.mention}",
            ephemeral=True,
        )

        audit("slot_create", interaction.user.id, f"slot_id={slot_id} owner_id={owner.id}")
        await log_action(
            self.bot,
            "🆕 Slot Created",
            f"**By:** {interaction.user.mention}\n"
            f"**Owner:** {owner.mention}\n"
            f"**Slot Name:** {slot_name}\n"
            f"**Category:** `{category.name}`\n"
            f"**Channel:** {channel.mention}",
            color=0x00FF7F,
        )

    # --- 2. SLASH COMMAND: /manage_slot ---
    @app_commands.command(name="manage_slot", description="Unified management command for slots (edit, renew, pings, delete).")
    @app_commands.describe(
        action="Action to perform",
        value="Input value (e.g. days to extend, new ping limit, or new contact link)",
        channel="Optional: Specific slot channel (leave empty to apply ping limit globally to all slots)",
    )
    @app_commands.default_permissions(manage_channels=True)
    async def manage_slot_cmd(
        self,
        interaction: discord.Interaction,
        action: Literal["Renew Days", "Set Ping Limit", "Reset Penalties", "Edit Contact Link", "Delete Slot"],
        value: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if action == "Set Ping Limit":
            if not value or not value.isdigit() or int(value) < 0:
                await interaction.followup.send("❌ Please provide a valid ping limit in `value` (e.g. 2).", ephemeral=True)
                return
            limit = int(value)

            if channel:
                slot = get_slot_by_channel(channel.id)
                if not slot:
                    await interaction.followup.send("❌ No slot record found for that channel.", ephemeral=True)
                    return
                update_slot(slot["id"], max_daily_pings=limit)
                updated = get_slot_by_id(slot["id"])
                async for msg in channel.history(limit=20):
                    if msg.author == self.bot.user and msg.embeds:
                        await msg.edit(embed=build_slot_embed(updated))
                        break
                await interaction.followup.send(f"✅ Updated daily mention limit for <#{channel.id}> to `{limit}` pings/day.", ephemeral=True)
                audit("set_ping_limit", interaction.user.id, f"slot_id={slot['id']} limit={limit}")
            else:
                from db import set_global_ping_limit
                set_global_ping_limit(limit)
                all_slots = get_all_slots()
                count = 0
                for r in all_slots:
                    ch = self.bot.get_channel(r["channel_id"])
                    if ch and isinstance(ch, discord.TextChannel):
                        try:
                            async for msg in ch.history(limit=20):
                                if msg.author == self.bot.user and msg.embeds:
                                    updated_r = get_slot_by_id(r["id"])
                                    await msg.edit(embed=build_slot_embed(updated_r))
                                    count += 1
                                    break
                        except Exception:
                            pass
                await interaction.followup.send(f"✅ Updated daily mention limit for **ALL** {count} slots to `{limit}` pings/day and refreshed all embeds!", ephemeral=True)
                audit("set_ping_limit_global", interaction.user.id, f"limit={limit}")
            return

        if not channel:
            await interaction.followup.send("❌ Please select the `channel` parameter for this action.", ephemeral=True)
            return

        slot = get_slot_by_channel(channel.id)
        if not slot:
            await interaction.followup.send("❌ No slot record found for that channel.", ephemeral=True)
            return

        if action == "Renew Days":
            if not value or not value.isdigit() or int(value) <= 0:
                await interaction.followup.send("❌ Please provide a positive number of days in `value` (e.g. 7 or 30).", ephemeral=True)
                return
            add_days = int(value)
            current_expiry = datetime.fromisoformat(slot["expiry_date"])
            if current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=timezone.utc)
            base_time = max(current_expiry, utcnow())
            new_expiry = base_time + timedelta(days=add_days)
            update_slot(slot["id"], expiry_date=new_expiry.isoformat(), duration_days=slot["duration_days"] + add_days)
            
            updated = get_slot_by_id(slot["id"])
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.embeds:
                    await msg.edit(embed=build_slot_embed(updated))
                    break

            await interaction.followup.send(f"✅ Added **{add_days} days** to slot **{slot['slot_name']}**.", ephemeral=True)
            audit("slot_renew", interaction.user.id, f"slot_id={slot['id']} add_days={add_days}")

        elif action == "Reset Penalties":
            reset_penalties(slot["id"])
            updated = get_slot_by_id(slot["id"])
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.embeds:
                    await msg.edit(embed=build_slot_embed(updated))
                    break
            await interaction.followup.send(f"✅ Penalties reset to `0/3` for slot **{slot['slot_name']}**.", ephemeral=True)
            audit("reset_penalties", interaction.user.id, f"slot_id={slot['id']}")

        elif action == "Edit Contact Link":
            if not value:
                await interaction.followup.send("❌ Please enter a new contact link in `value`.", ephemeral=True)
                return
            update_slot(slot["id"], contact_link=value.strip())
            updated = get_slot_by_id(slot["id"])
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.embeds:
                    await msg.edit(embed=build_slot_embed(updated), view=SlotView(dict(updated)))
                    break
            await interaction.followup.send(f"✅ Contact link updated to `{value}`.", ephemeral=True)
            audit("slot_edit_contact", interaction.user.id, f"slot_id={slot['id']}")

        elif action == "Delete Slot":
            delete_slot(slot["id"])
            try:
                await channel.delete(reason=f"Removed by {interaction.user}")
            except Exception:
                pass
            await interaction.followup.send(f"✅ Slot **{slot['slot_name']}** and its channel were removed.", ephemeral=True)
            audit("slot_remove", interaction.user.id, f"slot_id={slot['id']}")

    # --- 3. SLASH COMMAND: /vouch ---
    @app_commands.command(name="vouch", description="Add a rating/vouch to a slot channel (once per user).")
    @app_commands.describe(channel="The slot channel", stars="Rating from 1 to 5")
    async def vouch_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel, stars: int):
        if not 1 <= stars <= 5:
            await interaction.response.send_message("❌ Stars rating must be between 1 and 5.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        slot = get_slot_by_channel(channel.id)
        if not slot:
            await interaction.followup.send("❌ No slot found in that channel.", ephemeral=True)
            return

        if has_vouched(slot["id"], interaction.user.id):
            await interaction.followup.send("❌ You already vouched for this slot.", ephemeral=True)
            return

        record_vouch(slot["id"], interaction.user.id, stars)
        updated = get_slot_by_id(slot["id"])

        async for msg in channel.history(limit=20):
            if msg.author == self.bot.user and msg.embeds:
                await msg.edit(embed=build_slot_embed(updated))
                break

        await interaction.followup.send(f"✅ Vouch recorded ({stars}★).", ephemeral=True)
        audit("vouch", interaction.user.id, f"slot_id={slot['id']} stars={stars}")

    # --- EVENT LISTENER: MENTION & PERMISSION MONITOR ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        slot = get_slot_by_channel(message.channel.id)
        if not slot:
            return

        is_owner = message.author.id == slot["owner_id"]
        is_admin = message.author.guild_permissions.manage_channels

        # Enforce "Only Slot Owner can write"
        if not is_owner and not is_admin:
            try:
                await message.delete()
                warn = await message.channel.send(
                    f"⛔ {message.author.mention}, only the slot owner (<@{slot['owner_id']}>) is permitted to post here."
                )
                await asyncio.sleep(4)
                await warn.delete()
            except Exception:
                pass
            return

        # Check @here / @everyone mentions
        has_ping = message.mention_everyone or "@here" in message.content or "@everyone" in message.content
        if not has_ping:
            return

        today_str = utcnow().strftime("%Y-%m-%d")
        max_pings = slot["max_daily_pings"] or 2
        current_pings = get_daily_pings(slot["id"], today_str)

        if current_pings >= max_pings:
            try:
                await message.delete()
            except Exception:
                pass

            new_penalties = add_penalty(slot["id"])
            audit("penalty_issued", message.author.id, f"slot_id={slot['id']} penalties={new_penalties}")

            if new_penalties >= 3:
                delete_slot(slot["id"])
                await log_action(
                    self.bot,
                    "🚨 Slot Dismissed (3 Penalties)",
                    f"**Slot Name:** {slot['slot_name']}\n**Owner:** <@{slot['owner_id']}>\n"
                    f"**Reason:** 3 penalties reached for exceeding mention limit (`{max_pings}` pings/day).",
                    color=0xFF0000,
                )
                try:
                    await message.channel.send(
                        f"🚨 **Slot Dismissed!** <@{slot['owner_id']}> reached **3 penalties** for mention rule violations. Deleting channel..."
                    )
                    await asyncio.sleep(4)
                    await message.channel.delete(reason="Dismissed: 3 mention penalties reached")
                except Exception:
                    pass
            else:
                await message.channel.send(
                    f"⚠️ **PENALTY ISSUED!** <@{slot['owner_id']}>\n"
                    f"Daily mention limit of **{max_pings}** pings/day exceeded!\n"
                    f"**Current Penalties:** `{new_penalties}/3` *(Reaching 3 penalties dismisses the slot)*."
                )
        else:
            new_count = increment_daily_pings(slot["id"], today_str)
            note = await message.channel.send(
                f"📢 **Mention Recorded:** <@{slot['owner_id']}> used ping `{new_count}/{max_pings}` for today."
            )
            await asyncio.sleep(8)
            try:
                await note.delete()
            except Exception:
                pass

    # --- BACKGROUND TASK: SLOT EXPIRY CHECK ---
    @tasks.loop(hours=6)
    async def expiry_check(self):
        rows = get_all_slots()
        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            if channel is None:
                delete_slot(row["id"])
                continue

            remaining = days_left(row["expiry_date"])
            if remaining <= 0:
                try:
                    await channel.send("⏰ **Slot expired and is being removed.**")
                    await asyncio.sleep(3)
                    await channel.delete(reason="Slot expired")
                except Exception:
                    pass
                delete_slot(row["id"])
                audit("slot_expired", row["owner_id"], f"slot_id={row['id']}")
                continue

            if remaining <= 3:
                owner = self.bot.get_user(row["owner_id"])
                if owner:
                    try:
                        await owner.send(f"⚠️ Your slot **{row['slot_name']}** expires in **{remaining} day(s)**!")
                    except Exception:
                        pass

            try:
                async for msg in channel.history(limit=20):
                    if msg.author == self.bot.user and msg.embeds:
                        await msg.edit(embed=build_slot_embed(row))
                        break
            except Exception:
                pass

    @expiry_check.before_loop
    async def before_expiry_check(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(SlotCog(bot))
