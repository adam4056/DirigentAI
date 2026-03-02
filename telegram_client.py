import asyncio
import json
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CommandHandler,
)

load_dotenv()

HUB_HOST = "127.0.0.1"
HUB_PORT = 8888


class TelegramBridge:
    def __init__(self, token, allowed_user_ids):
        self.token = token
        # Allowed IDs are stored as a set of strings for maximum security and speed
        self.allowed_user_ids = (
            set(map(str, allowed_user_ids)) if allowed_user_ids else set()
        )
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [Telegram]: Initialized with {len(self.allowed_user_ids)} allowed users."
        )

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
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [Telegram]: Response received in {duration:.2f}s."
            )
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
            return
        if update.effective_user.is_bot:
            return

        user_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id

        # 2. STRICT SECURITY CHECK
        # User CAN communicate with Core ONLY if their ID is in the allowlist.
        if user_id not in self.allowed_user_ids:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [Security]: Blocked message attempt from unknown ID: {user_id}"
            )
            if not context.user_data.get("unauthorized_notified"):
                await update.message.reply_text(
                    f"Your ID ({user_id}) is not authorized. Communication with core is forbidden.\n"
                    "Enter this ID into your .env file (TELEGRAM_ALLOWED_USER_IDS)."
                )
                context.user_data["unauthorized_notified"] = True
            return

        # 3. If authorized, send message to core
        user_text = update.message.text
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [Telegram]: Message from {user_id}: {user_text[:50]}..."
        )

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

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return

        user_id = str(update.effective_user.id)
        first_name = update.effective_user.first_name

        # /start ALWAYS prints User ID (for easy onboarding)
        welcome_msg = f"Hello {first_name}!\nYour Telegram User ID is: {user_id}\n\n"

        if user_id in self.allowed_user_ids:
            welcome_msg += "✅ You are authorized and can communicate with Dirigent."
        else:
            welcome_msg += "❌ You are not on the allowed users list.\nEnter your ID into the system configuration."

        await update.message.reply_text(welcome_msg)

    def run(self):
        application = ApplicationBuilder().token(self.token).build()

        # Handler for /start command
        application.add_handler(CommandHandler("start", self.start_command))

        # Handler for all other text messages
        application.add_handler(
            MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message)
        )

        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Telegram]: Bot active.")
        application.run_polling()


if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_ids_str = os.getenv("TELEGRAM_ALLOWED_USER_IDS")

    if not token:
        print("CRITICAL ERROR: TELEGRAM_BOT_TOKEN missing in .env!")
        sys.exit(1)

    allowed_ids = (
        [id.strip() for id in allowed_ids_str.split(",") if id.strip()]
        if allowed_ids_str
        else []
    )

    if not allowed_ids:
        print(
            "WARNING: TELEGRAM_ALLOWED_USER_IDS is empty. Bot will only respond to /start."
        )

    bridge = TelegramBridge(token, allowed_ids)
    bridge.run()
