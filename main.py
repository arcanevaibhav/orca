import asyncio
import random
import ssl
import json
import time
import uuid
from loguru import logger
from websockets_proxy import Proxy, proxy_connect

URILIST = [
    "ws://proxy2.wynd.network:80/",
    "wss://proxy2.wynd.network:443/",
    "wss://proxy2.wynd.network:4650/",
    "wss://proxy2.wynd.network:4444/",
    "wss://proxy2.wynd.network:0/"
]

async def connect_to_wss(proxy, user_id, uri):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, proxy))
    ssl_context = None

    if uri.startswith("wss://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    custom_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    logger.info(f"Proxy {proxy} Attempting connection to {uri} for User ID {user_id}")

    try:
        proxy_obj = Proxy.from_url(proxy)
        async with proxy_connect(uri, proxy=proxy_obj, ssl=ssl_context, extra_headers={
            "Origin": "chrome-extension://lkbnfiajjmbhnfledhphioinpickokdi",
            "User-Agent": custom_headers["User-Agent"]
        }) as websocket:
            
            async def send_ping():
                while True:
                    send_message = json.dumps({"id": str(uuid.uuid4()), "version": "1.0.0", "action": "PING", "data": {}})
                    logger.debug(send_message)
                    await websocket.send(send_message)
                    await asyncio.sleep(110)

            send_ping_task = asyncio.create_task(send_ping())

            try:
                while True:
                    response = await websocket.recv()
                    message = json.loads(response)
                    logger.info(message)

                    if message.get("action") == "AUTH":
                        auth_response = {
                            "id": message["id"],
                            "origin_action": "AUTH",
                            "result": {
                                "browser_id": device_id,
                                "user_id": user_id,
                                "user_agent": custom_headers['User-Agent'],
                                "timestamp": int(time.time()),
                                "device_type": "extension",
                                "version": "4.26.2",
                                "extension_id": "lkbnfiajjmbhnfledhphioinpickokdi"
                            }
                        }
                        logger.debug(auth_response)
                        await websocket.send(json.dumps(auth_response))
                    elif message.get("action") == "PONG":
                        pong_response = {"id": message["id"], "origin_action": "PONG"}
                        logger.debug(pong_response)
                        await websocket.send(json.dumps(pong_response))

            finally:
                send_ping_task.cancel()

    except Exception as e:
        logger.error(f"Error with proxy {proxy} for User ID {user_id}: {str(e)}")
        return None

async def main():
    # Parse the proxies and user IDs
    user_proxies = {}
    current_user = None

    try:
        with open("local_proxies.txt", "r") as file:
            for line in file:
                line = line.strip()
                if line == "---":
                    current_user = None
                elif current_user is None:
                    current_user = line
                    user_proxies[current_user] = []
                else:
                    user_proxies[current_user].append(line)
    except FileNotFoundError:
        logger.error("local_proxies.txt file not found. Exiting.")
        return

    if not user_proxies:
        logger.error("No user-proxy pairs available. Exiting.")
        return

    tasks = []

    # Launch tasks for each user and their proxies
    for user_id, proxies in user_proxies.items():
        if not proxies:
            logger.warning(f"No proxies available for User ID {user_id}. Skipping.")
            continue

        logger.info(f"Launching tasks for User ID {user_id} with proxies: {proxies}")
        for proxy in proxies:
            task = connect_to_wss(proxy, user_id, random.choice(URILIST))
            tasks.append(asyncio.create_task(task))

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
