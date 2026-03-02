import asyncio
import json
import sys
from colorama import init, Fore, Style

init()


class DirigentClient:
    def __init__(self, host="127.0.0.1", port=8888):
        self.host = host
        self.port = port

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            print(f"{Fore.GREEN}✓ Connected to Dirigent Engine{Style.RESET_ALL}\n")
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Cannot connect to Engine: {e}{Style.RESET_ALL}")
            return False

    async def chat(self):
        if not await self.connect():
            return

        print(f"{Fore.CYAN}=== DirigentAI CLI Terminal ==={Style.RESET_ALL}")
        print("Type 'exit' to disconnect.\n")

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, input, f"{Fore.YELLOW}>>> {Style.RESET_ALL}"
                )
                user_input = line.strip()

                if user_input.lower() in ["exit", "quit", "q"]:
                    break
                if not user_input:
                    continue

                # Send request
                payload = json.dumps({"text": user_input})
                self.writer.write(payload.encode() + b"\n")
                await self.writer.drain()

                # Receive response
                data = await self.reader.readline()
                if not data:
                    print(f"{Fore.RED}Connection to Engine lost.{Style.RESET_ALL}")
                    break

                response = json.loads(data.decode())
                if response.get("status") == "ok":
                    print(
                        f"\n{Fore.BLUE}DirigentAI:{Style.RESET_ALL} {response['response']}\n"
                    )
                else:
                    print(f"{Fore.RED}Error: {response.get('message')}{Style.RESET_ALL}")

            except EOFError:
                break
            except Exception as e:
                print(f"{Fore.RED}Communication error: {e}{Style.RESET_ALL}")
                break

        self.writer.close()
        await self.writer.wait_closed()


if __name__ == "__main__":
    client = DirigentClient()
    try:
        asyncio.run(client.chat())
    except KeyboardInterrupt:
        pass
