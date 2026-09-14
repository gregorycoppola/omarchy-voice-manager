# Third-party notices

Skipper's original code is licensed under GPL-3.0-only. This does not change the
licenses of the third-party components below.

## Bundled virtual keyboard protocol

`tests/keyboard/virtual-keyboard-unstable-v1.xml` retains its original permissive
license and copyright notices for Kristian Høgsberg, Intel Corporation,
Collabora, Ltd., and Purism SPC. The complete notice is embedded in that file.
It is used by the test-only virtual keyboard helper.

## Separately downloaded speech model

Skipper downloads, but does not bundle in its Git repository, the INT8 ONNX
conversion of NVIDIA Parakeet TDT 0.6B v3 by istupakov. The conversion's pinned
model card declares CC BY 4.0:

- Original model: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- ONNX conversion and attribution:
  https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/tree/8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce
- Model license: https://creativecommons.org/licenses/by/4.0/

The downloaded README preserves the model card. Skipper uses the pinned
conversion unchanged; see `model-manifest.json` for revision and weight hashes.
The GPL grant for Skipper does not relicense these model files.

## External dependencies

Python dependencies listed in `requirements.lock`, the optional Playwright
browser integration, and system dependencies (including Omarchy, Quickshell,
Hyprland, GTK, GLib, Cairo, and PipeWire) retain their upstream licenses and
notices. Setup installs Python packages separately through pip; it does not
vendor their source or binaries in this repository. Consult each installed
package's distribution metadata and upstream license for its terms.
