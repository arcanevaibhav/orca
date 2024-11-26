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
        heartbeat = {
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
        try:
            if self.websocket.open:
                await self.websocket.send(json.dumps(heartbeat))
                self.last_activity_time = time.time()
                logger.debug("Sent heartbeat successfully.")
            else:
                logger.warning("WebSocket is closed. Reconnection required.")
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")

    def reset_activity(self):
        self.last_activity_time = time.time()


async def connect_to_wss(proxy_url, user_id, semaphore):
    user_agent = UserAgent(os=['windows', 'macos', 'linux'], browsers='chrome')
    random_user_agent = user_agent.random
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, proxy_url))

    async with semaphore:
        while True:
            try:
                headers = {"User-Agent": random_user_agent}
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                uri_list = ["wss://proxy2.wynd.network:4444/", "wss://proxy2.wynd.network:4650/"]
                uri = random.choice(uri_list)
                server_hostname = "proxy2.wynd.network"
                proxy = Proxy.from_url(proxy_url)

                logger.info(f"Connecting to {uri} via proxy {proxy_url}")
                async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, server_hostname=server_hostname,
                                         extra_headers=headers) as websocket:
                    heartbeat_manager = HeartbeatManager(websocket, user_id, device_id, random_user_agent, idle_timeout=30)
                    asyncio.create_task(heartbeat_manager.start_heartbeat())
                    await handle_messages(websocket, heartbeat_manager, device_id, user_id, random_user_agent)
            except (asyncio.TimeoutError, ConnectionError) as e:
                logger.warning(f"Connection error with proxy {proxy_url}: {e}. Retrying...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error: {e}. Retrying...")
                await asyncio.sleep(5)


async def handle_messages(websocket, heartbeat_manager, device_id, user_id, user_agent):
    while True:
        try:
            response = await asyncio.wait_for(websocket.recv(), timeout=30)
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
                        "version": "4.28.2"
                    }
                }
                await websocket.send(json.dumps(auth_response))
                logger.debug("Sent AUTH response.")

            elif message.get("action") == "PONG":
                pong_response = {"id": message["id"], "origin_action": "PONG"}
                await websocket.send(json.dumps(pong_response))
                logger.debug("Sent PONG response.")

        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for a message. Sending heartbeat.")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            break


async def load_user_data():
    try:
        with open("user_id.txt", "r") as file:
            user_ids = [line.strip() for line in file if line.strip()]
        if not user_ids:
            logger.error("No user IDs found.")
            return []
        logger.info(f"Loaded {len(user_ids)} user IDs.")
        return user_ids
    except FileNotFoundError:
        logger.error("user_id.txt file not found.")
        return []


async def load_proxies_for_user(index):
    proxy_file = f"proxy{index + 1}.txt"
    try:
        with open(proxy_file, "r") as file:
            proxies = [line.strip() for line in file if line.strip()]
        if not proxies:
            logger.warning(f"No proxies found in {proxy_file}.")
            return []
        logger.info(f"Loaded {len(proxies)} proxies from {proxy_file}.")
        return proxies
    except FileNotFoundError:
        logger.warning(f"Proxy file {proxy_file} not found.")
        return []


async def main():
    max_connections = int(os.getenv("MAX_CONNECTIONS", 100))
    semaphore = asyncio.Semaphore(max_connections)
    tasks = []

    user_ids = await load_user_data()
    if not user_ids:
        return

    for index, user_id in enumerate(user_ids):
        proxies = await load_proxies_for_user(index)
        if not proxies:
            continue
        for proxy in proxies:
            tasks.append(asyncio.create_task(connect_to_wss(proxy, user_id, semaphore)))

    if tasks:
        logger.info(f"Starting {len(tasks)} WebSocket tasks.")
        await asyncio.gather(*tasks)
    else:
        logger.error("No tasks to execute. Exiting.")


if __name__ == "__main__":
    logger.remove()
    logger.add("app.log", rotation="10 MB", level="INFO", format="{time} {level} {message}")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting gracefully.")
