-- Optional local voice setup. Launch launch-voice-preview.sh first.
-- Super+Space replaces Omarchy's menu; Skipper includes "open Omarchy main menu".
-- Hold both Super and R: capture. Release either key: stop and interpret.
hl.unbind("SUPER + SPACE")
o.bind("SUPER + SPACE", "Skipper: type a command",
  "gapplication action io.github.gregorycoppola.Skipper type-command")
hl.unbind("SUPER + R")
local skipperHeld = false
local skipperGate = (os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/skipper-voice-held"
local function gate(value)
  local file = io.open(skipperGate, "w")
  if file then file:write(value); file:close() end
end
gate("0")
o.bind("SUPER + R", "Skipper: hold to speak", function()
  if skipperHeld then return end
  skipperHeld = true
  gate("1")
  hl.exec_cmd("gapplication action io.github.gregorycoppola.Skipper.VoicePreview record-start")
end)
local function stop()
  if not skipperHeld then return end
  skipperHeld = false
  gate("0")
  hl.exec_cmd("gapplication action io.github.gregorycoppola.Skipper.VoicePreview record-stop")
end
-- Ignore remaining modifiers so releasing either key first closes the gate.
for _, key in ipairs({"R", "Super_L", "Super_R"}) do
  o.bind(key, nil, stop, {release=true, ignore_mods=true, non_consuming=true})
end
