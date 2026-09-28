# 🤖 Discord Slot Bot (High-Performance Modular Edition)

A high-performance, lightweight, and modular Discord bot built with `discord.py` and `SQLite` for managing server rental slots, user vouches, automated duration expiries, daily mention limits (`@here` / `@everyone`), and direct purchase inquiries.

---

## ✨ Features & Architecture Highlights

- **📂 Auto-Category Allocation (Max 10 Slots / Category)**:
  - Dynamically organizes slot text channels into categories (`SLOTS`, `SLOTS 2`, `SLOTS 3`...).
  - Capped at **10 slot channels per category**. Automatically creates new category channels as your server grows!

- **🔒 Showcase Channel Permissions**:
  - All server members can view and read slot channels to browse services.
  - **ONLY the Slot Owner** (and server admins/bot) can send messages. Non-owner messages are automatically deleted.

- **🛒 Direct Purchase via Owner DM**:
  - Eliminates ticket channel clutter.
  - Clicking **"Buy Now"** notifies the Server Owner via DM and gives the buyer a direct link button (`https://discord.com/users/<SERVER_OWNER_ID>`).

- **📢 Mention Limit & Penalty System**:
  - Tracks daily `@here` and `@everyone` pings per slot.
  - Exceeding the daily limit deletes the message and issues a penalty (`1/3`, `2/3`).
  - **3-Penalty Dismissal**: Reaching 3 penalties automatically dismisses the slot, deletes the channel, and records an audit log.

- **⚡ Live Embed Refresh**:
  - Updating daily mention limits via `/manage_slot` live-refreshes embeds across **all active slot channels** in real-time.

- **🛡️ 100% Restart Persistence**:
  - Uses SQLite in **WAL (Write-Ahead Logging)** mode.
  - Interactive UI buttons (`Buy Now`, `Contact Owner`) and background tasks survive bot restarts seamlessly.

---

## 📂 File Structure

```text
Slots Bot/
├── .env.example       # Environment configuration template
├── requirements.txt   # Python dependencies (discord.py, python-dotenv)
├── README.md          # Full project documentation
├── config.py          # Environment settings loader & validator
├── db.py              # SQLite database manager (WAL mode & foreign keys)
├── views.py           # Embed builder & persistent UI buttons
├── cogs.py            # Slash commands, auto-category logic & mention monitor
└── main.py            # Bot launcher & application command error handler
```

---

## 🎮 Slash Command Reference

### 1. `/slot`
> **Permission:** Manage Channels  
> **Description:** Create a new slot channel with embed & buttons.  
> **Options:**
> - `owner` *(Member, required)*: The slot owner.
> - `slot_name` *(String, required)*: Title of the slot (e.g. `Termwave`).
> - `duration_days` *(Integer, required)*: Duration in days.
> - `contact_link` *(String, required)*: Direct contact URL or invite.
> - `thumbnail_url` *(String, optional)*: Image URL for top-right thumbnail.
> - `banner_url` *(String, optional)*: Image URL for bottom banner.
> - `custom_id` *(String, optional)*: Custom 16-digit slot ID.
> - `max_daily_pings` *(Integer, optional)*: Custom daily mention limit (default: `2`).

---

### 2. `/manage_slot`
> **Permission:** Manage Channels  
> **Description:** Unified management tool for slots.  
> **Options:**
> - `action` *(Literal, required)*: Select from:
>   - **`Renew Days`**: Extend duration (specify days in `value`).
>   - **`Set Ping Limit`**: Set max daily pings (leave `channel` empty for global update across all rooms).
>   - **`Reset Penalties`**: Clear warnings back to `0/3`.
>   - **`Edit Contact Link`**: Update contact URL (specify link in `value`).
>   - **`Delete Slot`**: Remove slot and delete channel.
> - `value` *(String, optional)*: Input value based on selected action.
> - `channel` *(Channel, optional)*: Target slot channel.

---

### 3. `/vouch`
> **Permission:** Everyone  
> **Description:** Submit a 1 to 5 star rating for a slot channel.  
> **Options:**
> - `channel` *(Channel, required)*: Slot channel to vouch for.
> - `stars` *(Integer, required)*: Rating from `1` to `5`.

---

## 🚀 Setup & Deployment Guide

### 1. Clone & Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory (refer to `.env.example`):
```env
DISCORD_TOKEN=your_bot_token_here
GUILD_ID=123456789012345678
LOG_CHANNEL_ID=123456789012345678
SERVER_OWNER_ID=123456789012345678
BOT_ICON_URL=https://example.com/icon.png
RULES_URL=https://discord.com/terms
DEFAULT_MAX_DAILY_PINGS=2
SLOT_CATEGORY_PREFIX=SLOTS
```

### 3. Run the Bot
```bash
python main.py
```

---

## 💡 Future Ideas & Enhancements

1. **Vouch Reviews/Comments**: Allow users to leave an optional written review alongside their star rating.
2. **Owner Analytics Command**: `/slot_stats` for owners to see total vouches, remaining days, and daily ping usage.
3. **Automated Renewal DM Reminders**: Send interactive renewal buttons directly to slot owners 3 days prior to expiration.
"# Discord-Slot-Bot" 
"# Discord-Slot-Bot" 
"# Discord-Slot-Bot" 
