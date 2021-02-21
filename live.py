import asyncio as asio
import base64 as b64

import websockets as wss

from challenge import *

# os.environ["http_proxy"] = "http://localhost:9090"
# os.environ["https_proxy"] = "http://localhost:9090"

code = 1241593
name = "namerator"
device = rand_device()


def main():
    # parser = ap.ArgumentParser()
    # parser.add_argument("-id", "--id", help="ID of the quiz you are automating")
    # parser.add_argument("-name", "--name", help="Character name to use with the quiz")
    # args = parser.parse_args()
    # code = args.code
    # name = args.name

    # request challenge
    challenge = sess.get(f"https://kahoot.it/reserve/session/{code}/?{t()}")
    if "x-kahoot-session-token" not in challenge.headers.keys():
        print(f"Invalid code {code}")
        sys.exit(0)
    sess_tok = challenge.headers["x-kahoot-session-token"]
    challenge = json.loads(challenge.content)

    # decrypt cometd path
    # extract message and offset
    offset_equation = challenge["challenge"][challenge["challenge"].index("=") + 1:].strip()
    offset_equation = offset_equation[:offset_equation.index(";")].replace("\u2003", "")
    tmp_msg = challenge["challenge"][challenge["challenge"].index("'"):]
    tmp_msg = tmp_msg[1: tmp_msg.index(")") - 1]
    tmp_msg = (tmp_msg if tmp_msg and len(tmp_msg) > 0 else "")
    # reserve challenge to answer
    msg = ""
    for i, c in enumerate(tmp_msg):
        msg += chr((ord(c) * i + eval(offset_equation)) % 77 + 48)
    # base64 decode session token
    b64_sess_tok = b64.decodebytes(bytes(sess_tok, "utf-8")).decode("utf-8")
    # xor message and base64 session token
    cometd_path = ""
    for i, c in enumerate(b64_sess_tok):
        cometd_path += chr(ord(c) ^ ord(msg[i % len(msg)]))
    url = f"wss://kahoot.it/cometd/{code}/{cometd_path}"

    # get name
    global name
    if challenge["namerator"] or name == "namerator":
        name = namerator()
    name = name.replace(" ", "")
    print("Using name: " + name)

    asio.get_event_loop().run_until_complete(async_main(url))


cli_id = None
cid = None


async def async_main(url):
    global cli_id
    global cid
    global latest_id
    global logged_in
    global questions_started

    async with wss.connect(url) as ws:
        # handshake + connect
        await json_send(ws, [
            {
                "id": "1",
                "version": "1.0",
                "minimumVersion": "1.0",
                "channel": "/meta/handshake",
                "supportedConnectionTypes": ["websocket", "long-polling", "callback-polling"],
                "advice": {
                    "timeout": 60000,
                    "interval": 0
                },
                "ext": {
                    "ack": True,
                    "timesync": {
                        "tc": t(),
                        "l": 0,
                        "o": 0
                    }
                }
            }
        ])
        rsp = await json_recv(ws)
        cli_id = rsp[0]["clientId"]
        await json_send(ws, [
            {
                "id": str(int(rsp[0]["id"]) + 1),
                "channel": "/meta/connect",
                "connectionType": "websocket",
                "advice": {"timeout": 0},
                "clientId": cli_id,
                "ext": {
                    "ack": 0,
                    "timesync": {
                        "tc": t(),
                        "l": 100,
                        "o": 2260
                    }
                }
            }
        ])

        # start dance with router
        while True:
            rsp = await json_recv(ws)

            for rsp in rsp:
                if rsp["channel"] == "/service/controller":
                    if "data" in rsp.keys():
                        if rsp["data"]["type"] == "loginResponse":
                            if "cid" in rsp["data"].keys():
                                cid = rsp["data"]["cid"]
                            else:
                                print(f"Invalid code {code}")
                                sys.exit(0)

                elif rsp["channel"] == "/service/player":
                    if questions_started:
                        q = json.loads(rsp["data"]["content"])
                        if q["timeRemaining"] > 0:
                            req = {
                                "id": str(latest_id + 1),
                                "channel": "/service/controller",
                                "data": {
                                    "id": rsp["data"]["id"] + 1,
                                    "type": "message",
                                    "gameid": code,
                                    "host": "kahoot.it",
                                    "content": {
                                        "type": "quiz",
                                        "choice": 0,
                                        "questionIndex": q["questionIndex"],
                                        "meta": {"lag": 106}
                                    }
                                },
                                "clientId": cli_id,
                                "ext": {}
                            }

                            # switch between question types
                            if q["layout"] == "TRUE_FALSE":
                                # boolean questions
                                a = 3

                            # json dumps content and send
                            req["data"]["content"] = [json.dumps(req["data"]["content"])]
                            await json_send(ws, req)

                    else:
                        if "playerV2" in rsp["data"]["content"]:
                            await json_send(ws, [
                                {
                                    "id": str(latest_id + 1),
                                    "channel": "/service/controller",
                                    "data": {
                                        "id": rsp["data"]["id"] + 1,
                                        "type": "message",
                                        "gameid": code,
                                        "host": "kahoot.it",
                                        "content": ""
                                    },
                                    "clientId": cli_id,
                                    "ext": {}
                                }
                            ])
                            time.sleep(0.7)

                        elif "quizTitle" in rsp["data"]["content"]:
                            questions_started = True  # quiz admin has started the quiz

                elif rsp["channel"] == "/meta/connect":
                    # acknowledge client is alive
                    latest_id = int(rsp["id"]) + 1
                    await json_send(ws, [
                        {
                            "id": str(latest_id),
                            "channel": "/meta/connect",
                            "connectionType": "websocket",
                            "clientId": cli_id,
                            "ext": {
                                "ack": rsp["ext"]["ack"],
                                "timesync": {
                                    "tc": t(),
                                    "l": 100,
                                    "o": 2260
                                }
                            }
                        }
                    ], True)

            # start quiz logic
            if not logged_in:
                time.sleep(1)
                # join with player name
                await json_send(ws, [
                    {
                        "id": str(latest_id + 1),
                        "channel": "/service/controller",
                        "data": {
                            "type": "login",
                            "gameid": str(code),
                            "host": "kahoot.it",
                            "name": name,
                            "content": json.dumps(device)
                        },
                        "clientId": cli_id,
                        "ext": {}
                    }
                ])
                time.sleep(1)
                logged_in = True


logged_in = False
latest_id = 0
questions_started = False


async def json_send(ws, obj, ack=False):
    if not ack:
        print("SEND " + json.dumps(obj))
    await ws.send(json.dumps(obj))


async def json_recv(ws):
    rsp = await ws.recv()
    print("RECV " + rsp)
    return json.loads(rsp)


if __name__ == "__main__":
    main()
