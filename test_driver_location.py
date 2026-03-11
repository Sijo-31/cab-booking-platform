import asyncio
import websockets
import json
import random

async def send_location():

    uri = "ws://127.0.0.1:8000/ws/driver_location"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:

                print("Connected")

                lat = 9.9816
                lng = 76.2999

                while True:

                    lat += random.uniform(-0.0003, 0.0003)
                    lng += random.uniform(-0.0003, 0.0003)

                    data = {
                        "driver_id": 1,
                        "lat": lat,
                        "lng": lng
                    }

                    await ws.send(json.dumps(data))
                    print("Location sent:", data)

                    await asyncio.sleep(2)

        except Exception as e:
            print("Reconnecting...", e)
            await asyncio.sleep(2)


asyncio.run(send_location())