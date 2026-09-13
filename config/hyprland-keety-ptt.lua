-- Global hold-to-talk. Super+R was unused on this installation.
local keety_key = "R"
local keety_held = false
local keety_sequence = 0
local keety_session = tostring(os.time()) .. "-" .. tostring(math.random(100000, 999999))

local function keety_send(state)
  keety_sequence = keety_sequence + 1
  local event = keety_session .. ":" .. tostring(keety_sequence) .. ":" .. state
  -- A typed D-Bus action on the existing GTK app; it does not steal focus.
  hl.dispatch(hl.dsp.exec_cmd("gapplication action io.github.gregorycoppola.Keety ptt-event \"'" .. event .. "'\""))
end

local function keety_release()
  if keety_held then
    keety_held = false
    keety_send("up")
  end
end

hl.bind("SUPER + " .. keety_key, function()
  if not keety_held then
    keety_held = true
    keety_send("down")
  end
end, { description = "Keety: hold to talk" })

-- Releasing either part of the chord ends the take. Ordinary typing passes through.
for _, key in ipairs({ keety_key, "SUPER_L", "SUPER_R" }) do
  hl.bind(key, keety_release, {
    release = true,
    ignore_mods = true,
    non_consuming = true,
    description = "Keety: release to transcribe",
  })
end
