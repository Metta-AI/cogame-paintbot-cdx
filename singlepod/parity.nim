## Emit real fog-limited frames with native baseline replies for WASM parity.
import std/[base64, json, os]
import ../arena/game_runtime
import baseline
import ctf/sim

let ticks = 240
let config = """{"players":[{"name":"a"},{"name":"b"}],"slots":[{"team":"red"},{"team":"blue"}],"minPlayers":2,"maxTicks":240,"maxGames":1,"barrageMaxPerSec":0,"allowDeprecatedModes":true}"""
var game = initArenaGame(config, 2, 7)
var policy = initBaselineComponent(0)
let output = open(paramStr(1), fmWrite)
for tick in 0 .. ticks:
  let step = game.step([SeatMessage(seat: 1, payload: "\x84\x14")])
  let frame = step.messages[0].payload
  let replies = policy.onMessage(frame)
  var encoded: seq[string]
  for reply in replies: encoded.add(encode(reply))
  output.writeLine($ %*{"frame": encode(frame), "replies": encoded})
  if step.done: break
output.close()
