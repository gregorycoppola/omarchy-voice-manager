-- Super+R opens the centered written-command box. Requires Skipper running.
-- Replace any existing Super+R binding before adding this one.
hl.unbind("SUPER + R")
o.bind("SUPER + R", "Skipper: type a command",
  "gapplication action io.github.gregorycoppola.Skipper type-command")
