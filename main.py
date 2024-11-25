import os
import asyncio
import random
import ssl
import json
import time
import uuid
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from fake_useragent import UserAgent


# Heartbeat Manager Class
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
                await self.reconnect()
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
            await self.reconnect()

    async def reconnect(self):
        logger.info("Attempting to reconnect WebSocket...")
        await asyncio.sleep(5)

    def reset_activity(self):
        self.last_activity_time = time.time()


# WebSocket Connection Logic
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
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error with proxy {socks5_proxy}: {e}")
                await asyncio.sleep(5)


# Message Handling Logic
async def handle_messages(websocket, heartbeat_manager, device_id, user_id, user_agent):
    while True:
        try:
            response = await websocket.recv()
            message = json.loads(response)
            logger.info(f"Received message: {message}")
            heartbeat_manager.reset_activity()

            if message.get("action") == "AUTH":
                auth_response = {
                    "id": message["id"],
                    "origin_action": "AUTH",
                    "result": {
                        "browser_id": device_id,
                        "user_id": user_id,
                        "user_agent": user_agent,
                        "timestamp": int(time.time()),
                        "device_type": "desktop",
                        "version": "4.28.2",
                    }
                }
                logger.debug(f"Sending auth response: {auth_response}")
                await websocket.send(json.dumps(auth_response))

            elif message.get("action") == "PONG":
                pong_response = {"id": message["id"], "origin_action": "PONG"}
                logger.debug(f"Sending pong response: {pong_response}")
                await websocket.send(json.dumps(pong_response))

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            break


# Add New User ID
def add_user():
    try:
        if os.path.exists("user_id.txt"):
            with open("user_id.txt", "r") as user_file:
                user_ids = user_file.read().splitlines()
        else:
            user_ids = []

        new_user_id = input("Enter the new User ID: ").strip()
        if not new_user_id:
            print("No User ID entered. Exiting...")
            return

        user_ids.append(new_user_id)
        with open("user_id.txt", "w") as user_file:
            user_file.write("\n".join(user_ids))

        proxy_file_name = f"proxy{len(user_ids)}.txt"
        with open(proxy_file_name, "w") as proxy_file:
            pass

        print(f"User ID '{new_user_id}' added successfully.")
        print(f"Created an empty proxy file: {proxy_file_name}")
        print("Please add proxies to the file manually and restart the script.")
        print("Exiting...")

    except Exception as e:
        print(f"An error occurred: {e}")


# Start the Script
async def start_script():
    print("Starting the main script...")
    try:
        with open("user_id.txt", "r") as user_file:
            user_ids = user_file.read().splitlines()

        proxies = []
        for i, user_id in enumerate(user_ids, start=1):
            proxy_file = f"proxy{i}.txt"
            if os.path.exists(proxy_file):
                with open(proxy_file, "r") as proxy_file_content:
                    proxy_list = proxy_file_content.read().splitlines()
                    if proxy_list:
                        proxies.append((user_id, proxy_list))
                    else:
                        print(f"Warning: '{proxy_file}' is empty. Skipping...")
            else:
                print(f"Warning: Proxy file '{proxy_file}' for User ID '{user_id}' not found. Skipping...")

        if not proxies:
            print("No valid proxies or user IDs found. Exiting...")
            return

    except FileNotFoundError as e:
        print(f"Error loading configuration: {e}")
        return

    max_connections = 500
    semaphore = asyncio.Semaphore(max_connections)

    print(f"Loaded {len(proxies)} user-proxy pairs. Starting connections...")
    tasks = [
        asyncio.create_task(connect_to_wss(proxy, user_id, semaphore))
        for user_id, proxy_list in proxies
        for proxy in proxy_list
    ]

    await asyncio.gather(*tasks)


# Main Menu
def main_menu():
    print("Main Menu:")
    print("1. Add a new user ID and create proxy file")
    print("2. Start the script with existing configurations")
    option = input("Select an option (1/2): ").strip()

    if option == "1":
        add_user()
    elif option == "2":
        asyncio.run(start_script())
    else:
        print("Invalid option. Exiting...")


if __name__ == "__main__":
    main_menu()
