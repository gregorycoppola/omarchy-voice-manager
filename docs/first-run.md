# First run

Skipper 0.3.1 starts with a text command picker. It does not load a speech model
or record microphone audio.

## Install

Follow the plugin installation commands in [README](../README.md). Setup creates
a virtual environment using system PyGObject/Cairo and validates the intent
dataset bundled inside the plugin. No second repository is downloaded. Developers can set `OMARCHY_INTENT_DATASET=/path/to/dataset`
when both setting up and running Skipper to use an explicit external checkout.

## Try the picker

1. Press Super+R when the optional shortcut is installed.
2. Choose a verb or type a command. Tab accepts the highlighted choice.
3. Continue through argument levels. Enter runs a completed command.
4. Back/Shift+Tab returns; Escape cancels.

Open → file initially shows local recent-file history. Typing searches filenames
in the home directory. Switch offers workspaces, audio outputs, and microphones.
Enable/Disable offers explicit system states; Connect/Disconnect lists paired
Bluetooth devices. Unavailable backends are reported in the picker.

## Local data

Command history and settings stay outside the source checkout. File-search results
and recent-file paths can contain private information; do not share runtime status
files or history databases. See [data ownership](data-ownership.md).

Voice input through an optional external adapter remains planned. Previously saved
recordings can still be played in History; custom recognition and retranscription
are no longer part of Skipper.
