import json
import os
import subprocess as sp
import time
import argparse as ap
import requests as rq
from random_user_agent.user_agent import UserAgent
from random_user_agent.params import HardwareType, SoftwareType


# session to use for requests
sess = rq.session()


# UA setup
hardwares = [
    HardwareType.COMPUTER.value,
    HardwareType.MOBILE.value,
    HardwareType.MOBILE__PHONE.value,
    HardwareType.MOBILE__TABLET.value
]
softwares = [
    SoftwareType.WEB_BROWSER.value,
    SoftwareType.BROWSER__IN_APP_BROWSER.value
]
ua_gen = UserAgent(hardware_types=hardwares, sofware_types=softwares)


# UA func
def rand_ua() -> str:
    return ua_gen.get_random_user_agent()


# generate random device config
def rand_device() -> dict:
    return {
        "device": {
            "userAgent": rand_ua(),
            "screen": {
                "width": 1980,
                "height": 1080
            }
        }
    }


# use Kahoot's API to generate random names
def namerator() -> str:
    name = sess.get("https://apis.kahoot.it/namerator")
    name = json.loads(name.content)
    return name["name"]


# current time in milliseconds from UNIX epoch
def t() -> int:
    return int(time.time() * 1000)


async def send(ws, obj):
    await ws.send(json.dumps(obj))


async def recv(ws):
    return json.loads(await ws.recv())
