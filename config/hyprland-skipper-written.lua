-- Super+Shift+R opens the centered written-command box. Requires Skipper running.
-- Check the local binding before installing; this combination was free here.
o.bind("SUPER + SHIFT + R", "Skipper: type a command",
  "gapplication action io.github.gregorycoppola.Skipper type-command")
