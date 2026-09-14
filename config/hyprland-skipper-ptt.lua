-- Super+R is hold-to-talk, never a toggle. Keycodes are XKB: R, left/right Super.
local r_code, left_super, right_super = 27, 133, 134
local pressed = {}
local recording = false
local sequence = 0
local session = tostring(os.time()) .. "-" .. tostring(math.random(100000, 999999))

local function send(state)
  sequence = sequence + 1
  local event = session .. ":" .. tostring(sequence) .. ":" .. state
  hl.dispatch(hl.dsp.exec_cmd("gapplication action io.github.gregorycoppola.Skipper ptt-event \"'" .. event .. "'\""))
end

local function chord_down()
  return pressed[r_code] and (pressed[left_super] or pressed[right_super])
end

local function release()
  if recording then
    recording = false
    send("up")
  end
end

-- Observe physical releases directly, even if focus, modifiers, or submaps change.
-- Ignore every other key and retain no typing history.
hl.on("input.keyboard.key", function(code, timestamp, state)
  if code ~= r_code and code ~= left_super and code ~= right_super then return end
  pressed[code] = state ~= 0
  if state == 0 and not chord_down() then release() end
end)

hl.unbind("SUPER + R") -- replaces Skipper's previous press binding
hl.bind("SUPER + R", function()
  if recording then return end
  recording = true
  send("down")
end, { description = "Skipper: hold to talk" })

-- A dropped release message or config reload must not leave the microphone open.
hl.timer(function()
  if recording then
    if chord_down() then send("hold") else release() end
  end
end, { timeout = 200, type = "repeat" })
