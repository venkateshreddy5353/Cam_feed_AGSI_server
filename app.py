import cv2
import asyncio
import imagezmq
import imutils
import numpy as np
from datetime import datetime
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
imageHub = imagezmq.ImageHub()

class Camera:
    async def frames(self):

        frameDict = {}

        # initialize the dictionary which will contain  information regarding
        # when a device was last active, then store the last time the check
        # was made was now
        lastActive = {}
        lastActiveCheck = datetime.now()

        # stores the estimated number of Pis, active checking period, and
        # calculates the duration seconds to wait before making a check to
        # see if a device was active
        ESTIMATED_NUM_PIS = 4
        ACTIVE_CHECK_PERIOD = 10
        ACTIVE_CHECK_SECONDS = ESTIMATED_NUM_PIS * ACTIVE_CHECK_PERIOD
	

        while True:
            (rpiName, frame) = imageHub.recv_image()
            imageHub.send_reply(b'OK')
            # if a device is not in the last active dictionary then it means
            # that its a newly connected device
            if rpiName not in lastActive.keys():
                print("[INFO] receiving data from {}...".format(rpiName))

            # record the last active time for the device from which we just
            # received a frame
            lastActive[rpiName] = datetime.now()
            frameDict[rpiName] = frame
            # if current time *minus* last time when the active device check
            # was made is greater than the threshold set then do a check
            if (datetime.now() - lastActiveCheck).seconds > ACTIVE_CHECK_SECONDS:
                # loop over all previously active devices
                for (rpiName, ts) in list(lastActive.items()):
                    # remove the RPi from the last active and frame
                    # dictionaries if the device hasn't been active recently
                    if (datetime.now() - ts).seconds > ACTIVE_CHECK_SECONDS:
                        print("[INFO] lost connection to {}".format(rpiName))
                        lastActive.pop(rpiName)
                        frameDict.pop(rpiName)

                # set the last active check time as current time
                lastActiveCheck = datetime.now()
            frame_bytes = cv2.imencode(".jpg", frame)[1].tobytes()
            
            yield frame_bytes
            await asyncio.sleep(0.01)
            #print("sleep")


async def homepage(request):
    return templates.TemplateResponse("index.html", {"request": request})


async def stream(scope, receive, send):
    message = await receive()
    camera = Camera()

    if message["type"] == "http.request":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    [b"Content-Type", b"multipart/x-mixed-replace; boundary=frame"]
                ],
            }
        )
        while True:
            async for frame in camera.frames():
                data = b"".join(
                    [
                        b"--frame\r\n",
                        b"Content-Type: image/jpeg\r\n\r\n",
                        frame,
                        b"\r\n",
                    ]
                )
                await send(
                    {"type": "http.response.body", "body": data, "more_body": True}
                )


routes = [Route("/", endpoint=homepage), Mount("/stream/", stream)]
app = Starlette(debug=True, routes=routes)
