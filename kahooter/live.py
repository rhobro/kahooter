import argparse as ap
import asyncio as asio
import base64 as b64
from urllib.parse import quote

import websockets as wss

from kahooter import *


def run(pin, name, delay=.0):
    # request challenge
    c_rq = sess.get(f"https://kahoot.it/reserve/session/{pin}/?{t()}")
    if "x-kahoot-session-token" not in c_rq.headers.keys():
        print(f"Invalid code {pin}")
        return
    c = json.loads(c_rq.content)

    # get name
    if c["namerator"] or name == "namerator":
        name = namerator()
    name = name.replace(" ", "")
    print("Using name: " + name)

    ws_url = f"wss://kahoot.it/cometd/{pin}/{decrypt_websock(c['challenge'], c_rq.headers['x-kahoot-session-token'])}"
    asio.get_event_loop().run_until_complete(live_async(ws_url, pin, name, delay))


ans = []


async def live_async(url, pin, name, delay):
    device = rand_device()
    logged_in = False
    latest_id = 0
    questions_started = False
    global ans

    async with wss.connect(url) as ws:

        # handshake + connect
        await send(ws, [{
            "id": "1",
            "version": "1.0",
            "minimumVersion": "1.0",
            "channel": "/meta/handshake",
            "supportedConnectionTypes": ["websocket", "long-polling", "callback-polling"],
            "advice": {
                "timeout": 60000,
                "interval": 0,
            },
            "ext": {
                "ack": True,
                "timesync": {"tc": t(), "l": 0, "o": 0}
            }
        }])
        rsp = await recv(ws)
        cli_id = rsp[0]["clientId"]
        await send(ws, [{
            "id": str(int(rsp[0]["id"]) + 1),
            "channel": "/meta/connect",
            "connectionType": "websocket",
            "advice": {"timeout": 0},
            "clientId": cli_id,
            "ext": {
                "ack": 0,
                "timesync": {"tc": t(), "l": 106, "o": 129}
            }
        }])

        # start dance with router
        dance = True
        while dance:
            rsp = await recv(ws)

            for rsp in rsp:
                if rsp["channel"] == "/service/controller":
                    if "data" in rsp.keys():
                        if rsp["data"]["type"] == "loginResponse":
                            if "cid" not in rsp["data"].keys():
                                print(f"Invalid code {pin}")
                                return

                elif rsp["channel"] == "/service/player":
                    msg = json.loads(rsp["data"]["content"])

                    if questions_started:
                        if "timeLeft" in msg.keys() and "getReadyTimeRemaining" not in msg.keys():
                            if msg["timeLeft"] > 0:
                                # answer
                                latest_id += 1
                                if type(ans[msg["questionIndex"]]) == dict:
                                    # single answer
                                    post_ans = ans[msg["questionIndex"]]["idx"]
                                    display_ans = ans[msg["questionIndex"]]["answer"]

                                elif type(ans[msg["questionIndex"]]) == list:
                                    # multiple answers
                                    post_ans = [a["idx"] for a in ans[msg["questionIndex"]]]
                                    display_ans = " | ".join([a["answer"] for a in ans[msg["questionIndex"]]])

                                req = [{
                                    "id": str(latest_id),
                                    "channel": "/service/controller",
                                    "data": {
                                        "id": 45,
                                        "type": "message",
                                        "gameid": str(pin),
                                        "host": "kahoot.it",
                                        "content": {
                                            "type": msg["gameBlockType"],
                                            "choice": post_ans,
                                            "questionIndex": msg["questionIndex"],
                                            "meta": {"lag": 127}
                                        }
                                    },
                                    "clientId": cli_id,
                                    "ext": {}
                                }]

                                # json dumps content and send
                                req[0]["data"]["content"] = json.dumps(req[0]["data"]["content"])
                                time.sleep(.25 + delay)
                                await send(ws, req)
                                print(f"Q{msg['questionIndex'] + 1}: {display_ans}")

                        elif "correctCount" in msg.keys():
                            # quiz finished
                            # disconnect
                            await send(ws, [{
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
                            dance = False

                    else:
                        # get answers
                        if "quizTitle" in msg.keys():
                            ans = find_answers(msg)

                            if len(ans) == 0:
                                print("Unable to find quiz answers, could be private")
                                return

                        if "playerV2" in rsp["data"]["content"]:
                            await send(ws, [{
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
                    await send(ws, [{
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
                await send(ws, [{
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


def decrypt_websock(js_key, sess_tok) -> str:
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

    return cometd_path


def find_answers(details) -> list:
    cursor = 0
    answers = []

    while True:
        quizzes = sess.get(
            f"https://create.kahoot.it/rest/kahoots/?query={quote(details['quizTitle'])}&limit=100&cursor={cursor}",
            verify=False)
        quizzes = json.loads(quizzes.content)

        # no results
        if len(quizzes["entities"]) == 0:
            return []

        # find quiz
        for e in quizzes["entities"]:
            if e["card"]["type"] == details["quizType"] and \
                    e["card"]["title"] == details["quizTitle"] and \
                    e["card"]["number_of_questions"] == len(details["quizQuestionAnswers"]):
                # found it, request answers
                quiz = sess.get(f"https://create.kahoot.it/rest/kahoots/{e['card']['uuid']}/card/?includeKahoot=true",
                                verify=False)
                quiz = json.loads(quiz.content)

                for q in quiz["kahoot"]["questions"]:
                    choices = []
                    for i, c in enumerate(q["choices"]):
                        if c["correct"]:
                            choices.append({
                                "idx": i,
                                "answer": c["answer"]
                            })

                    if len(choices) == 1:
                        # only 1 answer
                        answers.append(choices[0])
                    else:
                        # multiple answers
                        answers.append(choices)

                break

        if len(answers) != 0:
            break

        cursor += len(quizzes["entities"])

    return answers


if __name__ == "__main__":
    def arg_start():
        parser = ap.ArgumentParser()
        parser.add_argument("-pin", "--pin", help="Pin of the quiz you are automating")
        parser.add_argument("-name", "--name", default="namerator",
                            help="Character name to use with the quiz (use \"namerator\" to use Kahoot's naming system)")
        parser.add_argument("-d", "--ans_delay", default="0", help="(optional) Delay before answering question")
        args = parser.parse_args()
        try:
            _ = args.pin
        except AttributeError:
            print("No \"code\" attribute passed")

        run(args.pin, args.name, float(args.ans_delay))


    # arg_start()
    run("7682475", "namerator", 0)
