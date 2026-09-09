## Validate every recorded state hash using the unchanged upstream replay engine.
import std/os
import ctf/[replays, sim]
let recording = parseReplayBytes(readFile(paramStr(1)))
var config = defaultGameConfig()
config.update(recording.configJson)
var replaySim = initSimServer(config)
var player = initReplayPlayer(recording)
player.mismatchQuit = true
while player.hashIndex < recording.hashes.len:
  player.stepReplay(replaySim)
doAssert not player.hashValidationFailed
doAssert recording.hashes.len > 0
echo "Verified ", recording.hashes.len, " replay hashes"
