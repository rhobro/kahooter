import argparse as ap
import json
import subprocess as sp
import time

import requests as rq

sess = rq.session()


def run(c_id, name):
    ua = rand_ua()
    # request challenge
    challenge = sess.get(f"https://kahoot.it/rest/challenges/{c_id}?includeKahoot=true", verify=False)
    challenge = json.loads(challenge.content)
    if "kahoot" not in challenge.keys():
        print("Challenge ended")
        return

    # get name
    if challenge["game_options"]["namerator"] or name == "namerator":
        name = namerator()
    elif name is None:
        while name is None or "":
            name = input("Player name: ")
    name = name.replace(" ", "")
    print("Using name: " + name)

    # join challenge
    cid = sess.post(f"https://kahoot.it/rest/challenges/{c_id}/join/?nickname={name}", verify=False)
    cid = json.loads(cid.content)
    cid = cid["playerCid"]

    # answer questions
    for i, q in enumerate(challenge["kahoot"]["questions"]):
        ans_sub = {
            "quizId": challenge["quizId"],
            "quizTitle": challenge["kahoot"]["title"],
            "quizType": challenge["kahoot"]["quizType"],
            "quizMaster": challenge["quizMaster"],
            "sessionId": challenge["pin"],
            "device": {
                "userAgent": ua,
                "screen": {
                    "width": 1980,
                    "height": 1080
                }
            },
            "gameMode": challenge["game_options"]["scoring_version"],
            "gameOptions": 0,
            "kickedPlayers": [],
            "numQuestions": len(challenge["kahoot"]["questions"]),
            "startTime": challenge["startTime"],
            "question": q
        }

        try:
            ans_sub["hostOrganisationId"] = challenge["hostOrganisationId"]
            ans_sub["organisationId"] = challenge["organisationId"]
        except KeyError:
            pass

        ans_sub["question"]["index"] = i
        ans_sub["question"]["duration"] = ans_sub["question"].pop("time")
        ans_sub["question"]["startTime"] = 0
        ans_sub["question"]["skipped"] = False
        ans_sub["question"]["format"] = ans_sub["question"].pop("questionFormat")
        ans_sub["question"]["lag"] = 0
        ans_sub["question"]["answers"] = []

        for j, c in enumerate(q["choices"]):
            if c["correct"]:
                ans_sub["question"]["answers"].append({
                    "receivedTime": t(),
                    "reactionTime": 0,
                    "playerId": name,
                    "playerCid": cid,
                    "choiceIndex": j,
                    "text": c["answer"],
                    "isCorrect": c["correct"],
                    "points": 1000 * q["pointsMultiplier"],
                    "bonusPoints": {
                        "answerStreakBonus": 500 * q["pointsMultiplier"]
                    }
                })
        print(f"Q{i + 1}: " + ", ".join([c["answer"] for c in q["choices"] if c["correct"]]))

        # post answer
        sess.post(f"https://kahoot.it/rest/challenges/{c_id}/answers", json=ans_sub, verify=False)


def rand_ua() -> str:
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
    name = sess.get("https://apis.kahoot.it/namerator", verify=False)
    name = json.loads(name.content)
    return name["name"]


def t() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    def arg_start():
        parser = ap.ArgumentParser()
        parser.add_argument("-id", "--id", help="ID of the quiz you are automating")
        parser.add_argument("-name", "--name", help="Character name to use with the quiz")
        args = parser.parse_args()
        run(args.id, args.name)


    arg_start()
