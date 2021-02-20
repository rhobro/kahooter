import asyncio as asio
import base64 as b64

import websockets as wss

from challenge import *

# os.environ["http_proxy"] = "http://localhost:9090"
# os.environ["https_proxy"] = "http://localhost:9090"

code = 4952846
name = "namerator"
device = rand_device()
cid = ""


def main():
    # parser = ap.ArgumentParser()
    # parser.add_argument("-id", "--id", help="ID of the quiz you are automating")
    # parser.add_argument("-name", "--name", help="Character name to use with the quiz")
    # args = parser.parse_args()
    # code = args.code
    # name = args.name

    # request challenge
    challenge = sess.get(f"https://kahoot.it/reserve/session/{code}/?{t()}", verify=False)
    if "x-kahoot-session-token" not in challenge.headers.keys():
        print(f"Invalid code {code}")
        sys.exit(0)
    sess_tok = challenge.headers["x-kahoot-session-token"]
    challenge = json.loads(challenge.content)

    # decrypt cometd path
    # extract message and offset
    offset_equation = challenge["challenge"][challenge["challenge"].index("=") + 1:].strip()
    offset_equation = offset_equation[:offset_equation.index(";")].replace("\u2003", "")
    # offsetEquation = challenge["challenge"][0: max(0, challenge["challenge"].index(";"))].strip()
    tmp_msg = challenge["challenge"][challenge["challenge"].index("'"):]
    tmp_msg = tmp_msg[: tmp_msg.index(")")]
    tmp_msg = (tmp_msg if tmp_msg and len(tmp_msg) > 0 else "")[1: -1]
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


cli_id = ""
player_cid = ""
answers = []


async def async_main(url):
    global cli_id
    global player_cid
    global answers
    global latest_id
    global quiz_logic_running

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
                if rsp["channel"] == "/meta/connect":
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

                elif rsp["channel"] == "/service/controller":
                    if "data" in rsp.keys():
                        if rsp["data"]["type"] == "loginResponse":
                            player_cid = rsp["data"]["cid"]

                elif rsp["channel"] == "/service/player":
                    if "playerV2" in rsp["data"]["content"]:
                        await json_send(ws, [
                            {
                                "id": str(latest_id + 1),
                                "channel": "/service/controller",
                                "data": {
                                    "id": rsp["data"]["id"] + 2,
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
                    elif "defaultQuizData" in rsp["data"]["content"]:
                        answers = json.loads(rsp["data"]["content"])["defaultQuizData"]["quizQuestionAnswers"]

            # start quiz logic
            if not quiz_logic_running:
                asio.create_task(quiz(ws))
                quiz_logic_running = True


quiz_logic_running = False
latest_id = 0


async def quiz(ws):
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
