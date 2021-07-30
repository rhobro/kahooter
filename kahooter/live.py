import asyncio as asio
import base64 as b64
import random as rand
from urllib.parse import quote
import aiocometd as comet
from __init__ import *


class Kahooter:

    def __init__(self, pin: str, name: str, title_phrase: str, delay: float):
        self.pin = pin
        while not self.pin.isdigit():
            self.pin = input("Pin: ")
        self.name = name
        if self.name == "":
            self.name = input("Name (namerator): ")
            self.name = "namerator" if self.name == "" else self.name
        self.name = name.replace(" ", "")
        self.title_phrase = title_phrase
        while self.title_phrase == "":
            self.title_phrase = input("Title phrase: ")
        self.lag = delay
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
                # check for error
                if "error" in rsp:
                    print(f"Quiz not found. error={rsp['error']}")
                    return
                self.cid = rsp["cid"]

            else:
                print("No player CID returned")
                return
            # status
            rsp = await self._recv()
            if rsp["type"] == "status":
                if rsp["status"] != "ACTIVE":
                    print("Quiz status is not active")
                    return

            # start dance
            async for raw_msg in self.sock:
                msg = raw_msg["data"]
                msg_type = lookup_code(msg["id"])

                # confirmation of log in
                if msg_type == "USERNAME_ACCEPTED":
                    print("Logged in")

                # admin has started quiz - find answers
                elif msg_type == "START_QUIZ":
                    details = json.loads(msg["content"])

                    print(f"Quiz started - {len(details['quizQuestionAnswers'])} questions\n")

                    # find answers
                    self.questions, title = find(details, self.title_phrase)
                    # none found
                    if len(self.questions) == 0:
                        break
                    print(f"Playing quiz: {title}\n")

                # question about to be displayed
                elif msg_type == "GET_READY":
                    q = json.loads(msg["content"])

                    i = q["questionIndex"]
                    question = self.questions[i]["q"]
                    print(f"Q{i + 1}: {question}")

                # answer question
                elif msg_type == "START_QUESTION":
                    q = json.loads(msg["content"])

                    i = q["questionIndex"]
                    q_type = q["type"]
                    n_opt = q["quizQuestionAnswers"][i]

                    # locate answer
                    ans = self.questions[i]["a"]

                    # decide choices
                    if q_type == "open_ended":
                        choice = rand.choice(ans)["answer"]

                    elif q_type == "survey":
                            choice = rand.randint(0, n_opt - 1)

                    else:
                        if type(ans) is list:
                            # multiple answers
                            choice = [a["idx"] for a in ans]

                        elif type(ans) is dict:
                            # single answer
                            choice = ans["idx"]

                    # submit
                    await self._send("/service/controller", {
                        "id": lookup_status("GAME_BLOCK_ANSWER"),
                        "type": "message",
                        "gameid": self.pin,
                        "host": "kahoot.it",
                        "content": json.dumps({
                            "type": q_type,
                            "choice": choice,
                            "questionIndex": i,
                            "meta": {
                                "lag": self.lag,
                            }
                        })
                    })

                    print(strfy_ans(q_type, ans))

                # question finished
                elif msg_type == "REVEAL_ANSWER":
                    details = json.loads(msg["content"])

                    points_recv = details["points"] if "points" in details else 0
                    total_score = details["totalScore"]
                    print(f"Points Earned: {points_recv}\n"
                          f"Total Score: {total_score}\n")

                # quiz finished
                elif msg_type == "GAME_OVER":
                    details = json.loads(msg["content"])

                    rank = details["rank"]
                    n_correct = details["correctCount"]
                    n_incorrect = details["incorrectCount"]
                    total_score = details["totalScore"]

                    print(f"Rank: {rank}\n"
                          f"n Correct: {n_correct}\n"
                          f"n Incorrect: {n_incorrect}\n"
                          f"Total Score: {total_score}\n")

                # show medal type
                elif msg_type == "REVEAL_RANKING":
                    details = json.loads(msg["content"])

                    # on podium
                    if "podiumMedalType" in details:
                        medal_type = details["podiumMedalType"]
                        print(get_medal(medal_type))

                    # end
                    self.sock.close()

    async def _send(self, channel: str, data: dict):
        await self.sock.publish(channel, data)

    async def _recv(self) -> dict:
        rsp = await self.sock.receive()
        if "data" in rsp:
            return rsp["data"]
        return rsp


def find(details: dict, title_phrase: str) -> tuple:
    cursor = 0
    answers = []
    title = ""

    # loop through all results
    while True:
        quizzes = sess.get(
            f"https://create.kahoot.it/rest/kahoots/?query={quote(title_phrase)}&limit=100&cursor={cursor}")
        quizzes = json.loads(quizzes.content)

        # no results
        if len(quizzes["entities"]) == 0:
            return []

        # find quiz
        for e in quizzes["entities"]:
            if e["card"]["type"] == details["quizType"] and \
                    e["card"]["number_of_questions"] == len(details["quizQuestionAnswers"]):
                # found it, request answers
                quiz = sess.get(f"https://create.kahoot.it/rest/kahoots/{e['card']['uuid']}/card/?includeKahoot=true")
                quiz = json.loads(quiz.content)
                title = quiz["card"]["title"]

                # compute null positions
                qs_pos = []
                for q in quiz["kahoot"]["questions"]:
                    qs_pos.append(None if q["type"] == "content" else 0)
                details_pos = []
                for a in details["quizQuestionAnswers"]:
                    details_pos.append(None if a is None else 0)
                # check match
                if qs_pos != details_pos:
                    continue

                for q in quiz["kahoot"]["questions"]:
                    choices = []

                    # avoid non-answering content question
                    if q["type"] != "content":
                        # has answers
                        for i, c in enumerate(q["choices"]):
                            if c["correct"]:
                                choices.append({
                                    "idx": i,
                                    "answer": c["answer"] if "answer" in c else ""
                                })
                    rand.shuffle(choices)

                    entry = {
                        "q": q["question"] if "question" in q else "{No question provided}\n",
                    }
                    if len(choices) == 0:
                        entry["a"] = None

                    elif q["type"] == "quiz":
                        # only 1 answer
                        entry["a"] = rand.choice(choices)

                    else:
                        # multiple answers
                        entry["a"] = choices
                    answers.append(entry)

                break

        if len(answers) != 0:
            break

        cursor += len(quizzes["entities"])

    return answers, title


def decrypt_sess(js_key: str, sess_tok: str) -> str:
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


def strfy_ans(q_type: str, ans) -> str:
    stmt = " - "

    if type(ans) is list:
        # multiple answers
        stmt += "\n - ".join([a["answer"] for a in ans])

    elif type(ans) is dict:
        # 1 answer
        stmt += ans["answer"]

    else:
        if q_type == "survey":
            stmt += "{It's a survey, who cares?}"

    return stmt


code_map = {
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


def lookup_code(code: int) -> str:
    if code in code_map:
        return code_map[code]
    return ""


def lookup_status(status: str) -> int:
    for c in code_map:
        if code_map[c] == status:
            return c
    return 0


medal_map = {
    "gold": "🥇",
    "silver": "🥈",
    "bronze": "🥉"
}


def get_medal(medal_type: str) -> str:
    if medal_type in medal_map:
        return medal_map[medal_type]
    return ""


def arg_start():
    parser = ap.ArgumentParser()
    parser.add_argument("-pin", "--pin", help="Pin of the quiz you are automating")
    parser.add_argument("-title_phrase", "--title_phrase", help="Search phrases in the quiz title")
    parser.add_argument("-name", "--name", default="namerator",
                        help="Player name to use with the quiz (use \"namerator\" to use Kahoot's naming system)")
    parser.add_argument("-d", "--ans_delay", default="0", help="(optional) Delay before answering question in ms")
    args = parser.parse_args()
    try:
        _ = args.pin
    except AttributeError:
        print("No \"code\" arg passed")
    try:
        _ = args.title_phrase
    except AttributeError:
        print("No \"title_phrase\" arg passed")

    k = Kahooter(args.pin, args.name, args.title_phrase, args.ans_delay)
    k.play()


# sample details
deets = {
    'quizType': 'quiz',
    'quizQuestionAnswers': [4, 2, 4, None, 4, 4, 4, None, 4, 4, 4]
}

if __name__ == "__main__":
    arg_start()
