import argparse as ap

from __init__ import *


def run(c_id, name):
    ua = rand_ua()
    # request challenge
    challenge = sess.get(f"https://kahoot.it/rest/challenges/{c_id}?includeKahoot=true")
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
    cid = sess.post(f"https://kahoot.it/rest/challenges/{c_id}/join/?nickname={name}")
    cid = json.loads(cid.content)
    cid = cid["playerCid"]

    # answer questions
    for i, q in enumerate(challenge["kahoot"]["questions"]):
        # is answerable?
        try:
            if q["type"] == "content":
                raise Exception()
        except:
            print("Passing content question")
            continue

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
        if q["type"] == "jumble":
            ans_sub["question"]["answers"].append({
                "receivedTime": t(),
                "reactionTime": 0,
                "playerId": name,
                "playerCid": cid,
                "selectedJumbleOrder": list(range(len(q["choices"]))),
                "choiceIndex": -1,
                "text": "|".join([c["answer"] for c in q["choices"]]),
                "isCorrect": True,
                "points": 0,
                "bonusPoints": {
                    "answerStreakBonus": 0
                }
            })
            if q["points"]:
                ans_sub["question"]["answers"][-1]["points"] = 1000 * q["pointsMultiplier"]
                ans_sub["question"]["answers"][-1]["bonusPoints"]["answerStreakBonus"] = 500 * q["pointsMultiplier"]

        elif q["type"] == "survey":
            continue

        else:
            for j, c in enumerate(q["choices"]):
                if c["correct"]:
                    ans_sub["question"]["answers"].append({
                        "receivedTime": t(),
                        "reactionTime": 0,
                        "playerId": name,
                        "playerCid": cid,
                        "choiceIndex": j,
                        "isCorrect": c["correct"],
                        "points": 0,
                        "bonusPoints": {
                            "answerStreakBonus": 0
                        }
                    })
                    if "answer" in c.keys():
                        ans_sub["question"]["answers"][-1]["text"] = c["answer"]
                    
                    if "pointsMultiplier" in q.keys():
                        if q["pointsMultiplier"]:
                            ans_sub["question"]["answers"][-1]["points"] = 1000 * q["pointsMultiplier"]
                            ans_sub["question"]["answers"][-1]["bonusPoints"]["answerStreakBonus"] = 500 * q[
                                "pointsMultiplier"]

        print(f"Q{i + 1}: " + ", ".join([c["answer"] for c in q["choices"] if c["correct"] and "answer" in c.keys()]))
        # post answer
        sess.post(f"https://kahoot.it/rest/challenges/{c_id}/answers", json=ans_sub)


if __name__ == "__main__":
    def arg_start():
        parser = ap.ArgumentParser()
        parser.add_argument("-id", "--id", help="ID of the quiz you are automating")
        parser.add_argument("-name", "--name", help="Character name to use with the quiz")
        args = parser.parse_args()
        run(args.id, args.name)


    arg_start()
