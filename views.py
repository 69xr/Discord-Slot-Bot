import discord
from datetime import datetime, timezone
from typing import Any
from config import config
from db import get_slot_by_id

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def days_left(expiry_iso: str) -> int:
    try:
        expiry = datetime.fromisoformat(expiry_iso)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return max((expiry - utcnow()).days, 0)
    except Exception:
        return 0

def format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%B %d, %Y")
    except Exception:
        return iso

def build_slot_embed(slot_row: Any) -> discord.Embed:
    """Construct a clean, rich embed for displaying slot details."""
    remaining = days_left(slot_row["expiry_date"])
    
    if remaining == 0:
        status_str = "🔴 Expired"
        color = 0xFF4444
    elif remaining <= 3:
        status_str = f"🟠 {remaining} days left"
        color = 0xFFA500
    else:
        status_str = f"🟢 {remaining} days left"
        color = 0x00FFFF

    embed = discord.Embed(
        title=f"{slot_row['slot_name']}'s Slot",
        description="Exclusive slot details & verified owner information.",
        color=color,
    )
    
    if slot_row["thumbnail_url"]:
        embed.set_thumbnail(url=slot_row["thumbnail_url"])

    embed.add_field(name="👤 Owner", value=f"<@{slot_row['owner_id']}>", inline=True)
    embed.add_field(name="🪧 Slot Name", value=slot_row["slot_name"], inline=True)
    embed.add_field(
        name="🕒 Duration",
        value=f"{slot_row['duration_days']}d — ({status_str})",
        inline=True,
    )

    embed.add_field(name="🔑 Unique Slot ID", value=f"```{slot_row['custom_id']}```", inline=False)
    embed.add_field(name="📅 Purchased", value=format_date(slot_row["purchase_date"]), inline=True)
    embed.add_field(name="⏰ Expires", value=format_date(slot_row["expiry_date"]), inline=True)

    # Clean Markdown contact link formatting fix
    contact = slot_row["contact_link"].strip()
    contact_url = contact if contact.startswith(("http://", "https://")) else f"https://{contact}"

    embed.add_field(
        name="🔗 Direct Contact",
        value=f"[Click Here to Contact]({contact_url})\n`{contact}`",
        inline=False,
    )

    rating_val = float(slot_row["rating"] or 5.0)
    vouch_count = int(slot_row["vouch_count"] or 0)
    star_full = int(round(rating_val))
    stars = "★" * star_full + "☆" * (5 - star_full)
    
    penalties = int(slot_row["penalties"] or 0)
    max_pings = int(slot_row["max_daily_pings"] or 2)
    penalty_str = f" | ⚠️ **Penalties:** `{penalties}/3`" if penalties > 0 else ""

    embed.add_field(
        name="⭐ Rating & Rules",
        value=f"{stars} **{rating_val:.1f}/5.0** ({vouch_count} vouch{'es' if vouch_count != 1 else ''})\n📢 **Daily Mention Limit:** `{max_pings}` pings/day{penalty_str}",
        inline=False,
    )

    if slot_row["banner_url"]:
        embed.set_image(url=slot_row["banner_url"])

    embed.set_footer(text="✨ Powered by Slot System", icon_url=config.BOT_ICON_URL or None)
    return embed

class BuyNowButton(discord.ui.Button):
    def __init__(self, slot_id: int):
        super().__init__(
            label="Buy Slot",
            style=discord.ButtonStyle.success,
            emoji="🛒",
            custom_id=f"buy_slot:{slot_id}",
        )
        self.slot_id = slot_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be used in a server.", ephemeral=True)
            return

        slot = get_slot_by_id(self.slot_id)
        if not slot:
            await interaction.followup.send("❌ Slot no longer available.", ephemeral=True)
            return

        server_owner = guild.owner
        server_owner_id = server_owner.id if server_owner else (config.SERVER_OWNER_ID or guild.owner_id)

        # Send DM notification to Server Owner if DMs open
        if server_owner:
            try:
                dm_embed = discord.Embed(
                    title="🛒 New Slot Purchase Inquiry!",
                    description=(
                        f"User **{interaction.user.mention}** (`{interaction.user}`) wants to buy a slot!\n\n"
                        f"**Slot Name:** {slot['slot_name']}\n"
                        f"**Slot Owner:** <@{slot['owner_id']}>\n"
                        f"**Slot Channel:** <#{slot['channel_id']}>"
                    ),
                    color=0x00FF7F,
                )
                await server_owner.send(embed=dm_embed)
            except Exception:
                pass

        dm_view = discord.ui.View()
        dm_view.add_item(
            discord.ui.Button(
                label="DM Server Owner",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/users/{server_owner_id}",
                emoji="💬",
            )
        )

        await interaction.followup.send(
            content=(
                f"🛒 **Want to purchase {slot['slot_name']}'s Slot?**\n\n"
                f"Please DM the Server Owner <@{server_owner_id}> directly to complete your purchase.\n"
            ),
            view=dm_view,
            ephemeral=True,
        )

class SlotView(discord.ui.View):
    def __init__(self, slot_row: dict):
        super().__init__(timeout=None)
        self.slot_id = slot_row["id"]

        if config.RULES_URL:
            self.add_item(discord.ui.Button(
                label="Slot Rules", style=discord.ButtonStyle.link, url=config.RULES_URL, emoji="📜"
            ))
        
        contact = (slot_row.get("contact_link") or "").strip()
        if contact:
            url = contact if contact.startswith(("http://", "https://")) else f"https://{contact}"
            self.add_item(discord.ui.Button(
                label="Contact Owner", style=discord.ButtonStyle.link,
                url=url, emoji="🔗"
            ))

        self.add_item(BuyNowButton(self.slot_id))

class RenewalDMView(discord.ui.View):
    def __init__(self, slot_id: int):
        super().__init__(timeout=None)
        self.slot_id = slot_id

    @discord.ui.button(
        label="Request Slot Renewal",
        style=discord.ButtonStyle.primary,
        emoji="🔄",
        custom_id="request_slot_renewal",
    )
    async def request_renewal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        slot = get_slot_by_id(self.slot_id)
        if not slot:
            await interaction.followup.send("❌ Slot record not found.", ephemeral=True)
            return

        guild = interaction.client.get_guild(slot["guild_id"])
        server_owner = guild.owner if guild else None
        server_owner_id = server_owner.id if server_owner else (config.SERVER_OWNER_ID or 0)

        # Notify Server Owner of Renewal Request
        if server_owner:
            try:
                dm_embed = discord.Embed(
                    title="🔄 Slot Renewal Request!",
                    description=(
                        f"Slot owner **{interaction.user.mention}** (`{interaction.user}`) requests a renewal!\n\n"
                        f"**Slot Name:** {slot['slot_name']}\n"
                        f"**Slot Channel:** <#{slot['channel_id']}>\n"
                        f"**Current Expiry:** {format_date(slot['expiry_date'])}"
                    ),
                    color=0x00FFFF,
                )
                await server_owner.send(embed=dm_embed)
            except Exception:
                pass

        await interaction.followup.send(
            content=(
                f"✅ **Renewal Request Sent!** The server owner (<@{server_owner_id}>) has been notified of your request to renew **{slot['slot_name']}**.\n"
                f"You can also message the server owner directly: https://discord.com/users/{server_owner_id}"
            ),
            ephemeral=True,
        )
