import asyncio
import random
import ssl
import json
import time
import uuid
import os
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from fake_useragent import UserAgent

# === Utility Functions ===

def display_menu():
    print("\nMain Menu:")
    print("1. Add a new user ID and proxies")
    print("2. Start the script with existing configurations")
    choice = input("Select an option (1/2): ")
    return choice

def add_new_user():
    user_id = input("Enter the new User ID: ").strip()
    if not user_id:
        print("User ID cannot be empty.")
        return

    try:
        with open("user_id.txt", "a") as user_file:
            user_file.write(f"{user_id}\n")
        print(f"User ID '{user_id}' added successfully.")

        proxy_file_name = f"proxy{sum(1 for _ in open('user_id.txt'))}.txt"
        print(f"Creating proxy file: {proxy_file_name}")

        proxies = []
        print("Enter proxies one by one (leave blank and press Enter to stop):")
        while True:
            proxy = input("Enter proxy (format: socks5://user:pass@host:port): ").strip()
            if not proxy:
                break
            proxies.append(proxy)

        if proxies:
            with open(proxy_file_name, "w") as proxy_file:
                proxy_file.write("\n".join(proxies))
            print(f"{len(proxies)} proxies saved to '{proxy_file_name}'.")
        else:
            print(f"No proxies entered. '{proxy_file_name}' will remain empty.")

    except Exception as e:
        print(f"Error adding new user: {e}")

# === Main Script ===

class HeartbeatManager:
    def __init__(self, websocket, user_id, device_id, user_agent, idle_timeout=30):
        self.websocket = websocket
        self.user_id = user_id
        self.device_id = device_id
        self.user_agent = user_agent
        self.idle_timeout = idle_timeout
        self.last_activity_time = time.time()

    async def start_heartbeat(self):
        while True:
            if time.time() - self.last_activity_time >= self.idle_timeout:
                await self.send_heartbeat()
            await asyncio.sleep(1)

    async def send_heartbeat(self):
        send_message = {
            "id": str(uuid.uuid4()),
            "version": "1.0.0",
            "action": "PING",
            "data": {
                "browser_id": self.device_id,
                "user_id": self.user_id,
                "user_agent": self.user_agent,
                "timestamp": int(time.time()),
                "device_type": "desktop",
                "version": "4.28.2"
            }
        }
        logger.debug(f"Sending heartbeat ping: {send_message}")
        try:
            if self.websocket.open:
                await self.websocket.send(json.dumps(send_message))
                self.last_activity_time = time.time()
            else:
                logger.warning("WebSocket is closed. Attempting to reconnect.")
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")

    def reset_activity(self):
        self.last_activity_time = time.time()


async def connect_to_wss(socks5_proxy, user_id, semaphore):
    user_agent = UserAgent(os=['windows', 'macos', 'linux'], browsers='chrome')
    random_user_agent = user_agent.random
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))

    async with semaphore:
        while True:
            try:
                custom_headers = {"User-Agent": random_user_agent}
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                urilist = ["wss://proxy2.wynd.network:4444/", "wss://proxy2.wynd.network:4650/"]
                uri = random.choice(urilist)
                server_hostname = "proxy2.wynd.network"
                proxy = Proxy.from_url(socks5_proxy)

                logger.debug(f"Attempting connection to {uri} using proxy {socks5_proxy}")
                async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, server_hostname=server_hostname,
                                         extra_headers=custom_headers) as websocket:
                    heartbeat_manager = HeartbeatManager(websocket, user_id, device_id, random_user_agent, idle_timeout=30)
                    asyncio.create_task(heartbeat_manager.start_heartbeat())
                    await handle_messages(websocket, heartbeat_manager, device_id, user_id, random_user_agent)

            except (ConnectionError, TimeoutError) as e:
                logger.error(f"Connection error with proxy {socks5_proxy}: {e}")
                await asyncio.sleep(5)  # Retry after a delay
            except Exception as e:
                logger.error(f"Unexpected error with proxy {socks5_proxy}: {e}")
                await asyncio.sleep(5)  # Retry after a delay


async def handle_messages(websocket, heartbeat_manager, device_id, user_id, user_agent):
    while True:
        try:
            response = await websocket.recv()
            message = json.loads(response)
            logger.info(f"Received message: {message}")
            heartbeat_manager.reset_activity()

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            break


async def main():
    while True:
        choice = display_menu()
        if choice == "1":
            add_new_user()
        elif choice == "2":
            break
        else:
            print("Invalid choice. Please select 1 or 2.")

    # Start with existing user configurations
    user_ids = []
    proxies = {}
    try:
        with open("user_id.txt", "r") as f:
            user_ids = [line.strip() for line in f if line.strip()]

        for index, user_id in enumerate(user_ids):
            proxy_file = f"proxy{index + 1}.txt"
            try:
                with open(proxy_file, "r") as proxy_f:
                    proxies[user_id] = [line.strip() for line in proxy_f if line.strip()]
            except FileNotFoundError:
                logger.warning(f"Proxy file '{proxy_file}' not found. Skipping user '{user_id}'.")

    except FileNotFoundError:
        logger.error("File 'user_id.txt' not found. Please add users first.")
        return

    max_connections = 500
    semaphore = asyncio.Semaphore(max_connections)
    tasks = []

    for user_id, user_proxies in proxies.items():
        for proxy in user_proxies:
            tasks.append(asyncio.create_task(connect_to_wss(proxy, user_id, semaphore)))

    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.error("No tasks to run. Exiting.")


if __name__ == "__main__":
    asyncio.run(main())
