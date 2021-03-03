# to test which is the best period to use

import threading as th

import numpy as np

from live import live_main

pin = 1528318

players = []

for p in np.linspace(0.1, 0.3, 25 + 1):
    t = th.Thread(target=live_main, args=(pin, str(p), p))
    t.start()
    players.append(t)

while True in [t.is_alive() for t in players]:
    continue
