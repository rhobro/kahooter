import base64 as b64

from challenge import *

uri = ""

if __name__ == "__main__":
    parser = ap.ArgumentParser()
    # parser.add_argument("-id", "--id", help="ID of the quiz you are automating")
    # parser.add_argument("-name", "--name", help="Character name to use with the quiz")
    # args = parser.parse_args()
    # code = args.code
    code = 8651841

    # request challenge
    challenge = sess.get(f"https://kahoot.it/reserve/session/{code}/?{time()}", verify=False)
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

    # get name
    if challenge["namerator"]:
        name = namerator()
    name = name.replace(" ", "")
    print("Using name: " + name)
