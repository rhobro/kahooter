import json
import os
import subprocess as sp
import time

import requests as rq

# recompile randua binary based on OS
os.system("go build -i -o go/bin go/randua.go")

# session to use for requests
sess = rq.session()


# use executable to generate random header
def rand_ua() -> str:
    child = sp.Popen("go/bin/randua", stdout=sp.PIPE, stderr=sp.STDOUT)
    return child.stdout.read().decode()


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
