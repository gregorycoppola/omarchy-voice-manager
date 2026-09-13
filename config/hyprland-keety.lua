-- This machine: keep Keety on the MacBook panel, across its workspaces.
-- Install with: require("hypr.keety") in ~/.config/hypr/hyprland.lua
o.window({ class = "^io\\.github\\.gregorycoppola\\.Keety$" }, {
  monitor = "eDP-1",
  float = true,
  pin = true,
  size = { 1100, 700 },
  center = true,
})
