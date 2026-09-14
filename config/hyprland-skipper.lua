-- This machine: keep Skipper on the MacBook panel, across its workspaces.
-- Install with: require("hypr.skipper") in ~/.config/hypr/hyprland.lua
o.window({ class = "^io\\.github\\.gregorycoppola\\.Skipper$" }, {
  monitor = "eDP-1",
  float = true,
  pin = true,
  size = { 1100, 700 },
  center = true,
})

-- Keep confirmation compact and centered above the main Skipper window.
o.window({ class = "^io\\.github\\.gregorycoppola\\.Skipper$", title = "^Skipper — Confirm command$" }, {
  size = { 560, 280 },
  center = true,
})
