import asyncio
import json
import shutil
import textwrap
from pathlib import Path
from colorama import Fore, Style, init

init()

COMMAND_ROWS = [
    ("/clear", "reset history"),
    ("/workers", "list workers"),
    ("/status", "firm status"),
    ("/help", "show commands"),
    ("exit", "disconnect"),
]

BOX_H = "\u2500"
BOX_V = "\u2502"
BOX_TL = "\u250c"
BOX_TR = "\u2510"
BOX_BL = "\u2514"
BOX_BR = "\u2518"
PROMPT_BAR = "\u258f"
ARROW = "\u276f"
THINK_FRAMES = ["\u2801", "\u2802", "\u2804", "\u2802"]
SESSION_FILE = Path("memory/cli_session.json")


class DirigentClient:
    def __init__(self, host="127.0.0.1", port=8888):
        self.host = host
        self.port = port
        self._typing_stop: asyncio.Event | None = None
        self._typing_task: asyncio.Task | None = None
        self.session_id = self._load_session_id()

    def _load_session_id(self) -> str:
        if SESSION_FILE.exists():
            try:
                data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                session_id = data.get("session_id", "default_cli_session")
                if session_id:
                    return session_id
            except Exception:
                pass
        return "default_cli_session"

    def _save_session_id(self):
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps({"session_id": self.session_id}, indent=2), encoding="utf-8")

    def _terminal_width(self) -> int:
        width = shutil.get_terminal_size(fallback=(100, 30)).columns
        return max(72, min(width, 120))

    def _line(self, char: str = BOX_H) -> str:
        return char * self._terminal_width()

    def _center(self, text: str, color: str = Fore.WHITE):
        print(f"{color}{text:^{self._terminal_width()}}{Style.RESET_ALL}")

    def _print_header(self):
        print()
        self._center("dirigentai", Fore.WHITE)
        self._center("local-first multi-agent console", Fore.LIGHTBLACK_EX)
        print()

    def _print_hero_prompt(self):
        width = min(self._terminal_width() - 10, 92)
        text = "ask, delegate, inspect workers, or run /help"
        text = text[: max(10, width - 4)]
        print(f"    {Fore.BLUE}{PROMPT_BAR}{Style.RESET_ALL} {Fore.WHITE}{text:<{width}}{Style.RESET_ALL}")
        print()
        meta = (
            f"{Fore.BLUE}Build{Style.RESET_ALL}  "
            f"{Fore.WHITE}Interactive CLI{Style.RESET_ALL}  "
            f"{Fore.LIGHTBLACK_EX}{self.host}:{self.port}{Style.RESET_ALL}"
        )
        print(f"    {meta}")
        hints = "tab switch agent    ctrl+p commands    /doctor check config"
        print(f"{Fore.LIGHTBLACK_EX}{hints:>{self._terminal_width()}}{Style.RESET_ALL}")
        print()

    def _print_commands(self):
        row = "    ".join(
            f"{Fore.CYAN}{command}{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}{description}{Style.RESET_ALL}"
            for command, description in COMMAND_ROWS
        )
        print(f"{Fore.LIGHTBLACK_EX}{self._line()}{Style.RESET_ALL}")
        print(f"  {row}")
        print(f"{Fore.LIGHTBLACK_EX}{self._line()}{Style.RESET_ALL}\n")

    def _print_welcome(self):
        self._print_header()
        self._print_hero_prompt()
        self._print_commands()

    def _render_panel(self, label: str, text: str, color: str = Fore.BLUE):
        width = min(self._terminal_width() - 2, 110)
        inner = width - 4
        wrapped_lines = []
        for paragraph in (text or "").splitlines() or [""]:
            if not paragraph.strip():
                wrapped_lines.append("")
                continue
            wrapped_lines.extend(textwrap.wrap(paragraph, width=inner) or [""])

        print(f"{color}{BOX_TL}{BOX_H * (width - 2)}{BOX_TR}{Style.RESET_ALL}")
        print(f"{color}{BOX_V}{Style.RESET_ALL} {label:<{inner}} {color}{BOX_V}{Style.RESET_ALL}")
        for line in wrapped_lines:
            print(f"{color}{BOX_V}{Style.RESET_ALL} {line:<{inner}} {color}{BOX_V}{Style.RESET_ALL}")
        print(f"{color}{BOX_BL}{BOX_H * (width - 2)}{BOX_BR}{Style.RESET_ALL}\n")

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self._save_session_id()
            self._render_panel("connected", f"Dirigent Engine at {self.host}:{self.port} | session {self.session_id}", Fore.GREEN)
            return True
        except Exception as exc:
            self._render_panel("connection error", f"Cannot connect to Engine: {exc}", Fore.RED)
            return False

    async def _show_typing(self):
        i = 0
        while not self._typing_stop.is_set():
            frame = THINK_FRAMES[i % len(THINK_FRAMES)]
            print(f"\r{Fore.LIGHTBLACK_EX}dirigent thinking {frame}{Style.RESET_ALL}", end="", flush=True)
            i += 1
            await asyncio.sleep(0.35)
        print("\r" + " " * 40 + "\r", end="", flush=True)

    def _start_typing(self):
        self._typing_stop = asyncio.Event()
        self._typing_task = asyncio.create_task(self._show_typing())

    async def _stop_typing(self):
        if self._typing_stop:
            self._typing_stop.set()
        if self._typing_task:
            await self._typing_task

    async def chat(self):
        if not await self.connect():
            return

        self._print_welcome()

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, input, f"{Fore.BLUE}{ARROW}{Style.RESET_ALL} {Fore.WHITE}user{Style.RESET_ALL} "
                )
                user_input = line.strip()

                if user_input.lower() in {"exit", "quit", "q"}:
                    break
                if not user_input:
                    continue

                payload = json.dumps({"text": user_input, "source": "cli", "session_id": self.session_id})
                self.writer.write(payload.encode() + b"\n")
                await self.writer.drain()

                self._start_typing()
                data = await self.reader.readline()
                await self._stop_typing()

                if not data:
                    self._render_panel("connection error", "Connection to Engine was lost.", Fore.RED)
                    break

                response = json.loads(data.decode())
                returned_session_id = response.get("session_id")
                if returned_session_id and returned_session_id != self.session_id:
                    self.session_id = returned_session_id
                    self._save_session_id()
                if response.get("status") == "ok":
                    self._render_panel("dirigent", response.get("response", ""), Fore.BLUE)
                else:
                    self._render_panel("error", response.get("message", "Unknown error"), Fore.RED)

            except EOFError:
                break
            except Exception as exc:
                await self._stop_typing()
                self._render_panel("communication error", str(exc), Fore.RED)
                break

        self.writer.close()
        await self.writer.wait_closed()
        print(f"{Fore.LIGHTBLACK_EX}session closed{Style.RESET_ALL}")


if __name__ == "__main__":
    client = DirigentClient()
    try:
        asyncio.run(client.chat())
    except KeyboardInterrupt:
        pass
