import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CommandHandler,
    Application,
)

load_dotenv()

HUB_HOST = "127.0.0.1"
HUB_PORT = 8888

# Configure logging
import os
log_level_str = os.getenv("DIRIGENT_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("dirigent.telegram")

# Reduce noise from external libraries
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class TelegramBridge:
    def __init__(self, token, allowed_user_ids):
        self.token = token
        # Allowed IDs are stored as a set of strings for maximum security and speed
        self.allowed_user_ids = (
            set(map(str, allowed_user_ids)) if allowed_user_ids else set()
        )
        logger.info(f"Initialized with {len(self.allowed_user_ids)} allowed users.")
        if not self.allowed_user_ids:
            logger.info("No allowed users configured. Bot will only respond to /start command.")

    async def send_to_hub(self, text: str, user_id: str = "default"):
        """Send a message to Hub with session tracking per Telegram user."""
        start_time = time.time()
        try:
            reader, writer = await asyncio.open_connection(HUB_HOST, HUB_PORT)
            # Include session_id based on Telegram user for conversation continuity
            payload = json.dumps({
                "text": text,
                "session_id": f"telegram_{user_id}",
            })
            writer.write(payload.encode() + b"\n")
            await writer.drain()

            data = await reader.readline()
            writer.close()
            await writer.wait_closed()

            duration = time.time() - start_time
            if not data:
                return f"Connection to Dirigent Engine lost (took {duration:.2f}s)."

            response = json.loads(data.decode())
            logger.debug(f"Response received in {duration:.2f}s.")
            return response.get("response", "No response from Engine.")
        except Exception as e:
            return f"Error communicating with Engine: {e}"

    async def keep_typing(self, chat_id, context, stop_event):
        """Keeps the 'typing...' indicator active."""
        while not stop_event.is_set():
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(4)  # Telegram typing lasts ~5s
            except Exception:
                break

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # 1. Ignore messages without text, from bots, or if not from a user
        if not update.message or not update.message.text or not update.effective_user:
            logger.debug("Ignoring message without text or user")
            return
        if update.effective_user.is_bot:
            logger.debug(f"Ignoring message from bot: {update.effective_user.id}")
            return

        user_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id
        user_text = update.message.text
        
        logger.info(f"Received message from user {user_id} in chat {chat_id}: {user_text[:100]}")

        # 2. STRICT SECURITY CHECK
        # User CAN communicate with Core ONLY if their ID is in the allowlist.
        if user_id not in self.allowed_user_ids:
            logger.warning(f"Blocked message attempt from unknown ID: {user_id}")
            if not context.user_data.get("unauthorized_notified"):
                logger.info(f"Sending unauthorized notification to user {user_id}")
                try:
                    await update.message.reply_text(
                        f"Your ID ({user_id}) is not authorized. Communication with core is forbidden.\n"
                        "Enter this ID into your .env file (TELEGRAM_ALLOWED_USER_IDS)."
                    )
                    context.user_data["unauthorized_notified"] = True
                except Exception as e:
                    logger.error(f"Failed to send unauthorized notification: {e}")
            else:
                logger.debug(f"User {user_id} already notified, skipping")
            return

        # 3. If authorized, send message to core
        logger.info(f"Processing authorized message from {user_id}: {user_text[:50]}...")

        # Start typing indicator in background
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(
            self.keep_typing(chat_id, context, stop_typing)
        )

        try:
            # Communication with Core (pass user_id for session tracking)
            response = await self.send_to_hub(user_text, user_id=user_id)

            # Stop typing and send response
            stop_typing.set()
            await typing_task
            await update.message.reply_text(response)
        except Exception as e:
            stop_typing.set()
            await update.message.reply_text(f"System error: {e}")

    async def _send_command_to_hub(self, cmd: str, user_id: str) -> str:
        """Send a slash command to Hub and return response."""
        return await self.send_to_hub(cmd, user_id=user_id)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Received /start command from update: {update}")
        if not update.effective_user:
            logger.warning("No effective_user in update")
            return
        
        user_id = str(update.effective_user.id)
        first_name = update.effective_user.first_name or "User"
        logger.info(f"Processing /start for user {user_id} ({first_name})")

        welcome_msg = f"Hello {first_name}!\nYour Telegram User ID is: `{user_id}`\n\n"
        if user_id in self.allowed_user_ids:
            welcome_msg += (
                "✅ You are **authorized**.\n\n"
                "**Available commands:**\n"
                "/clear — Reset conversation history\n"
                "/workers — List hired specialists\n"
                "/status — Show firm status\n"
                "/help — Show this message\n\n"
                "You can now send messages to interact with DirigentAI."
            )
        else:
            welcome_msg += (
                "❌ You are **not on the allowed users list**.\n\n"
                "**To authorize yourself:**\n"
                "1. Copy your User ID above\n"
                "2. Add it to the `.env` file:\n"
                "   `TELEGRAM_ALLOWED_USER_IDS={your_id}`\n"
                "3. Restart the Telegram bot\n\n"
                "After authorization, you'll be able to use all commands."
            )
        
        try:
            # Try to reply to the message
            if update.message:
                await update.message.reply_text(welcome_msg, parse_mode='Markdown')
                logger.info(f"Sent welcome message to user {user_id}")
            elif update.effective_chat:
                # Fallback: send directly to chat
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=welcome_msg,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent welcome message to chat {update.effective_chat.id}")
            else:
                logger.error(f"Cannot send welcome message - no message or chat in update")
        except Exception as e:
            logger.error(f"Failed to send welcome message: {e}", exc_info=True)
            # Try one more time without Markdown
            try:
                if update.message:
                    await update.message.reply_text(welcome_msg.replace('`', '').replace('*', ''))
                elif update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=welcome_msg.replace('`', '').replace('*', '')
                    )
            except Exception as e2:
                logger.error(f"Also failed to send plain text: {e2}")

    async def _authorized_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str
    ):
        """Handle an authorized slash command by forwarding to Hub."""
        logger.info(f"Processing authorized command '{cmd}' from update: {update}")
        if not update.effective_user or not update.message:
            logger.warning(f"No effective_user or message in update for command '{cmd}'")
            return
        user_id = str(update.effective_user.id)
        logger.info(f"User {user_id} attempting command '{cmd}'")
        
        if user_id not in self.allowed_user_ids:
            logger.warning(f"User {user_id} not authorized for command '{cmd}'")
            await update.message.reply_text(
                f"❌ Unauthorized. Your User ID is: `{user_id}`\n\n"
                "Add this ID to `.env` file:\n"
                "`TELEGRAM_ALLOWED_USER_IDS={your_id}`\n\n"
                "Use `/start` to see your ID again.",
                parse_mode='Markdown'
            )
            return
        
        logger.info(f"User {user_id} authorized, forwarding command '{cmd}' to Hub")
        response = await self._send_command_to_hub(cmd, user_id)
        await update.message.reply_text(response)

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._authorized_command(update, context, "/clear")

    async def workers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._authorized_command(update, context, "/workers")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._authorized_command(update, context, "/status")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._authorized_command(update, context, "/help")

    def run(self):
        # Add lock file to prevent multiple instances
        lock_file = Path(".telegram_bot.lock")
        if lock_file.exists():
            # Check if the lock is stale (older than 30 seconds)
            lock_age = time.time() - lock_file.stat().st_mtime
            if lock_age > 30:
                logger.info(f"Removing stale lock file ({lock_age:.0f}s old).")
                lock_file.unlink(missing_ok=True)
            else:
                logger.error("Another Telegram bot instance appears to be running (lock file exists).")
                logger.error("If you're sure no other instance is running, delete '.telegram_bot.lock' and try again.")
                sys.exit(1)
        
        # Create lock file
        lock_file.touch()
        
        try:
            # Build application with conflict prevention settings
            logger.info(f"Building Telegram bot application with token: {self.token[:10]}...")
            application = (
                ApplicationBuilder()
                .token(self.token)
                .build()
            )

            # Add command handlers
            logger.info("Adding command handlers...")
            application.add_handler(CommandHandler("start", self.start_command))
            application.add_handler(CommandHandler("clear", self.clear_command))
            application.add_handler(CommandHandler("workers", self.workers_command))
            application.add_handler(CommandHandler("status", self.status_command))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(
                MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message)
            )

            logger.info(f"Bot active. Allowed users: {len(self.allowed_user_ids)}")
            logger.info(f"Start command available to all users.")
            
            # Start polling with drop_pending_updates to avoid conflicts
            logger.info("Starting polling for updates...")
            application.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            raise
        finally:
            # Clean up lock file on exit
            lock_file.unlink(missing_ok=True)


if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_ids_str = os.getenv("TELEGRAM_ALLOWED_USER_IDS")

    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN missing in .env!")
        sys.exit(1)

    allowed_ids = (
        [id.strip() for id in allowed_ids_str.split(",") if id.strip()]
        if allowed_ids_str
        else []
    )

    if not allowed_ids:
        logger.warning("TELEGRAM_ALLOWED_USER_IDS is empty. Bot will only respond to /start.")

    bridge = TelegramBridge(token, allowed_ids)
    bridge.run()
