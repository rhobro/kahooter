import argparse as ap
import asyncio as asio
import base64 as b64
from urllib.parse import quote

import aiocometd as comet

from __init__ import *


class Kahoot:

    def __init__(self, pin: str, name: str, delay: float):
        self.pin = pin
        while not self.pin.isdigit():
            self.pin = input("Pin: ")
        self.name = name
        if self.name == "":
            self.name = input("Name (namerator): ")
            self.name = "namerator" if self.name == "" else self.name
        self.name = name.replace(" ", "")
        self.delay = delay
        self.loop = asio.get_event_loop()
        self.sess = rq.session()
        self.device = rand_device()

        self.sess_id = None
        self.sock = comet.Client("")

        # reserve place
        rsp = self.sess.get(f"https://kahoot.it/reserve/session/{pin}/?{t()}")
        if "x-kahoot-session-token" not in rsp.headers:
            print(f"Invalid code {pin}")
            return
        sess_token = rsp.headers["x-kahoot-session-token"]

        c = json.loads(rsp.content)
        challenge = c["challenge"]

        self.sess_id = decrypt_sess(challenge, sess_token)

        # get name
        if c["namerator"] or name == "namerator":
            self.name = namerator()
        print("Using name: " + self.name)

    def play(self):
        self.loop.run_until_complete(self._play())

    async def _play(self):
        # don't play if uninitialised
        if not self.sess_id:
            print("Uninitialized")

        # url for websocket
        url = f"wss://kahoot.it/cometd/{self.pin}/{self.sess_id}"

        async with comet.Client(url, ssl=True) as c:
            # subscribe to channels
            self.sock = c
            await self.sock.subscribe("/service/controller")
            await self.sock.subscribe("/service/player")
            await self.sock.subscribe("/service/status")

            # login
            await self._send("/service/controller", {
                "type": "login",
                "gameid": self.pin,
                "host": "kahoot.it",
                "name": self.name,
                "content": json.dumps(self.device)
            })
            # login response
            rsp = await self._recv()
            if rsp["type"] == "loginResponse":
                self.cid = rsp["cid"]
            else:
                print("No player CID returned")
                await self._close()
                return
            # status
            rsp = await self._recv()
            if rsp["type"] == "status":
                if "status" != "ACTIVE":
                    print("Quiz status is not active")
                    await self._close()
                    return

            # start dance
            async for raw_msg in self.sock:
                msg = raw_msg["data"]
                print(lookup(msg["id"]))

    async def _send(self, channel: str, data):
        await self.sock.publish(channel, data)

    async def _recv(self) -> dict:
        rsp = await self.sock.receive()
        if "data" in rsp:
            return rsp["data"]
        return rsp

    async def _close(self):
        try:
            await self.sock.close()
        except:
            pass


def decrypt_sess(js_key, sess_tok) -> str:
    """Decrypt Cometd path"""

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
    b64_sess_tok = b64.b64decode(sess_tok).decode("utf-8", "strict")

    # xor message and base64 session token
    cometd_path = ""
    for i, c in enumerate(b64_sess_tok):
        cometd_path += chr(ord(c) ^ ord(msg[i % len(msg)]))

    return cometd_path


def find_answers(details) -> list:
    cursor = 0
    answers = []

    # loop through all results
    while True:
        quizzes = sess.get(
            f"https://create.kahoot.it/rest/kahoots/?query={quote(details['quizTitle'])}&limit=100&cursor={cursor}")
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
                quiz = sess.get(f"https://create.kahoot.it/rest/kahoots/{e['card']['uuid']}/card/?includeKahoot=true")
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


codes = {
    1: "GET_READY",
    2: "START_QUESTION",
    3: "GAME_OVER",
    4: "TIME_UP",
    5: "PLAY_AGAIN",
    6: "ANSWER_SELECTED",
    7: "ANSWER_RESPONSE",
    8: "REVEAL_ANSWER",
    9: "START_QUIZ",
    10: "RESET_CONTROLLER",
    11: "SUBMIT_FEEDBACK",
    12: "FEEDBACK",
    13: "REVEAL_RANKING",
    14: "USERNAME_ACCEPTED",
    15: "USERNAME_REJECTED",
    16: "REQUEST_RECOVERY_DATA_FROM_PLAYER",
    17: "SEND_RECOVERY_DATA_TO_CONTROLLER",
    18: "JOIN_TEAM_MEMBERS",
    19: "JOIN_TEAM_MEMBERS_RESPONSE",
    20: "START_TEAM_TALK",
    21: "SKIP_TEAM_TALK",
    31: "IFRAME_CONTROLLER_EVENT",
    32: "SERVER_IFRAME_EVENT",
    40: "STORY_BLOCK_GET_READY",
    41: "REACTION_SELECTED",
    42: "REACTION_RESPONSE",
    43: "GAME_BLOCK_START",
    44: "GAME_BLOCK_END",
    45: "GAME_BLOCK_ANSWER",
    50: "SUBMIT_TWO_FACTOR",
    51: "TWO_FACTOR_AUTH_INCORRECT",
    52: "TWO_FACTOR_AUTH_CORRECT",
    53: "RESET_TWO_FACTOR_AUTH"
}


def lookup(code) -> str:
    if code in codes:
        return codes[code]
    return ""


def arg_start():
    parser = ap.ArgumentParser()
    parser.add_argument("-pin", "--pin", help="Pin of the quiz you are automating")
    parser.add_argument("-name", "--name", default="namerator",
                        help="Player name to use with the quiz (use \"namerator\" to use Kahoot's naming system)")
    parser.add_argument("-d", "--ans_delay", default="0", help="(optional) Delay before answering question")
    args = parser.parse_args()
    try:
        _ = args.pin
    except AttributeError:
        print("No \"code\" attribute passed")

    # k = Kahoot(args.pin, args.name, args.ans_delay)
    k = Kahoot("8200308", "namerator", 0)
    k.play()


if __name__ == "__main__":
    arg_start()
