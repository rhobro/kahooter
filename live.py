import asyncio as asio
import base64 as b64
import random as rand

import websockets as wss

from challenge import *

# args
pin = None
name = None


def decrypt_websock(js_key, sess_tok):
    # decrypt cometd path

    # extract message and offset
    offset_equation = js_key[js_key.index("=") + 1:].strip()
    offset_equation = offset_equation[:offset_equation.index(";")].replace("\u2003", "")
    tmp_msg = js_key[js_key.index("'"):]
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

    return f"wss://kahoot.it/cometd/{pin}/{cometd_path}"


def main():
    global pin
    global name

    # request challenge
    c_rq = sess.get(f"https://kahoot.it/reserve/session/{pin}/?{t()}")
    if "x-kahoot-session-token" not in c_rq.headers.keys():
        print(f"Invalid code {pin}")
        sys.exit(0)
    c = json.loads(c_rq.content)

    # get name
    if c["namerator"] or name == "namerator":
        name = namerator()
    name = name.replace(" ", "")
    print("Using name: " + name)

    ws_url = decrypt_websock(c["challenge"], c_rq.headers["x-kahoot-session-token"])
    asio.get_event_loop().run_until_complete(async_main(ws_url))


async def async_main(url):
    device = rand_device()
    logged_in = False
    latest_id = 0
    questions_started = False

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
                    "timesync": {"tc": t(), "l": 0, "o": 0}
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
                    "timesync": {"tc": t(), "l": 100, "o": 2260}
                }
            }
        ])

        # start dance with router
        run = True
        while run:
            rsp = await json_recv(ws)

            for rsp in rsp:
                if rsp["channel"] == "/service/controller":
                    if "data" in rsp.keys():
                        if rsp["data"]["type"] == "loginResponse":
                            if "cid" not in rsp["data"].keys():
                                print(f"Invalid code {pin}")
                                sys.exit(0)

                elif rsp["channel"] == "/service/player":
                    if questions_started:
                        msg = json.loads(rsp["data"]["content"])

                        if "timeLeft" in msg.keys() and "getReadyTimeRemaining" not in msg.keys():
                            if msg["timeLeft"] > 0:
                                # answer
                                latest_id += 1
                                req = [{
                                    "id": str(latest_id),
                                    "channel": "/service/controller",
                                    "data": {
                                        "id": 45,
                                        "type": "message",
                                        "gameid": str(pin),
                                        "host": "kahoot.it",
                                        "content": {
                                            "type": "quiz",
                                            "questionIndex": msg["questionIndex"],
                                            "meta": {"lag": 127}
                                        }
                                    },
                                    "clientId": cli_id,
                                    "ext": {}
                                }]

                                ans = rand.randint(0, msg["quizQuestionAnswers"][msg["questionIndex"]] - 1)
                                if msg["type"] == "multiple_select_quiz":
                                    ans = [ans]

                                # json dumps content and send
                                req[0]["data"]["content"]["choice"] = ans
                                req[0]["data"]["content"] = json.dumps(req[0]["data"]["content"])
                                time.sleep(0.25)
                                await json_send(ws, req)
                                print(f"Q{msg['questionIndex'] + 1}: {ans}")

                        elif "correctCount" in msg.keys():
                            # quiz finished
                            # disconnect
                            await json_send(ws, [{
                                "id": str(latest_id + 1),
                                "channel": "/meta/disconnect",
                                "clientId": cli_id,
                                "ext": {
                                    "timesync": {"tc": t(), "l": 127, "o": 2196}
                                }
                            }])

                            # print summary
                            print(f"""\n\nCompleted Quiz
Player: {name}
 - Rank: {msg['rank']}
 - Score: {msg['totalScore']}
 - Correct: {msg['correctCount']} | Incorrect: {msg['incorrectCount']}""")
                            run = False

                    else:
                        if "playerV2" in rsp["data"]["content"]:
                            await json_send(ws, [{
                                "id": str(latest_id + 1),
                                "channel": "/service/controller",
                                "data": {
                                    "id": rsp["data"]["id"] + 1,
                                    "type": "message",
                                    "gameid": pin,
                                    "host": "kahoot.it",
                                    "content": ""
                                },
                                "clientId": cli_id,
                                "ext": {}
                            }])
                            time.sleep(0.7)

                        elif "quizTitle" in rsp["data"]["content"]:
                            questions_started = True  # quiz admin has started the quiz
                            print("Quiz commenced")

                elif rsp["channel"] == "/meta/connect":
                    # acknowledge client is alive
                    latest_id = int(rsp["id"]) + 1
                    await json_send(ws, [{
                        "id": str(latest_id),
                        "channel": "/meta/connect",
                        "connectionType": "websocket",
                        "clientId": cli_id,
                        "ext": {
                            "ack": rsp["ext"]["ack"],
                            "timesync": {"tc": t(), "l": 100, "o": 2260}
                        }
                    }])

            # start quiz logic
            if not logged_in:
                time.sleep(1)
                # join with player name
                await json_send(ws, [{
                    "id": str(latest_id + 1),
                    "channel": "/service/controller",
                    "data": {
                        "type": "login",
                        "gameid": str(pin),
                        "host": "kahoot.it",
                        "name": name,
                        "content": json.dumps(device)
                    },
                    "clientId": cli_id,
                    "ext": {}
                }])
                time.sleep(1)
                logged_in = True


async def json_send(ws, obj):
    await ws.send(json.dumps(obj))


async def json_recv(ws):
    return json.loads(await ws.recv())


def arg_start():
    parser = ap.ArgumentParser()
    parser.add_argument("-pin", "--pin", help="Pin of the quiz you are automating")
    parser.add_argument("-name", "--name",
                        help="Character name to use with the quiz (use \"namerator\" to use Kahoot's naming system)")
    args = parser.parse_args()
    try:
        _ = args.pin
    except AttributeError:
        print("No \"code\" attribute passed")
    try:
        _ = args.name
    except AttributeError:
        print("No \"name\" attribute passed")

    try:
        if int(args.pin) <= 0 and args.name == "":
            sys.exit(0)
    except ValueError:
        print("Invalid args")
        sys.exit(0)

    custom_start(args.pin, args.name)


def custom_start(c, n):
    global pin
    global name

    pin = c
    name = n

    main()


if __name__ == "__main__":
    arg_start()
