import json
import os
import subprocess as sp
import time

import requests as rq

# recompile randua binary based on OS
os.system("go build -i -o go/bin go/randua.go")

# session to use for requests
sess = rq.session()


# util funcs used by both challenge and live


def rand_ua() -> str:
    return "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.1 Safari/605.1.15"
    child = sp.Popen("./go/bin/randua", stdout=sp.PIPE, stderr=sp.STDOUT)
    return child.stdout.read().decode()


def rand_device() -> dict:
    return {
        "userAgent": rand_ua(),
        "screen": {
            "width": 1980,
            "height": 1080
        }
    }


def namerator() -> str:
    name = sess.get("https://apis.kahoot.it/namerator")
    name = json.loads(name.content)
    return name["name"]


def t() -> int:
    return int(time.time() * 1000)


async def json_send(ws, obj):
    await ws.send(json.dumps(obj))


async def json_recv(ws):
    return json.loads(await ws.recv())
