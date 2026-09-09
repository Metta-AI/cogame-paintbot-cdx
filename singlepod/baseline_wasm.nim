## Paintbot file-policy ABI v1. One instance owns one seat for one episode.
import baseline

{.emit: """
void NimMain(void);
__attribute__((constructor)) static void paintbot_runtime_init(void) { NimMain(); }
""".}

var
  policy: BaselineComponent
  inputFrame: string
  outputFrame: string
  initialized = false

proc paintbotInit(slot: int32) {.exportc: "paintbot_init", cdecl.} =
  if initialized or slot < 0 or slot >= 32:
    raise newException(ValueError, "invalid initialization")
  policy = initBaselineComponent(int(slot))
  initialized = true

proc paintbotBuffer(size: int32): pointer {.exportc: "paintbot_buffer", cdecl.} =
  if size < 0 or size > 16 * 1024 * 1024:
    raise newException(ValueError, "frame too large")
  inputFrame = newString(int(size))
  if size == 0: nil else: inputFrame[0].addr

proc addU32(target: var string, value: int) =
  for shift in countup(0, 24, 8):
    target.add(char((value shr shift) and 255))

proc paintbotStep(): pointer {.exportc: "paintbot_step", cdecl.} =
  if not initialized:
    raise newException(ValueError, "policy not initialized")
  let replies = policy.onMessage(inputFrame)
  outputFrame = ""
  outputFrame.addU32(replies.len)
  for reply in replies:
    outputFrame.addU32(reply.len)
    outputFrame.add(reply)
  outputFrame[0].addr

proc paintbotOutputSize(): int32 {.exportc: "paintbot_output_size", cdecl.} =
  int32(outputFrame.len)
