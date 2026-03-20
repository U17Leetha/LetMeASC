# LetMeASC

`LetMeASC` is a serial-console helper for authorized firmware and hardware assessment. It does two things:

- extracts likely credential candidates from a firmware image
- replays serial login workflows against a device using those candidates

The tool now includes an interactive wizard so you do not have to hand-edit YAML to define a target.

## Install

Fastest install:

```bash
cd /Users/matt/Development/LetMeASC
./install.sh
```

That will:

- create or reuse `.venv`
- install Python dependencies
- install `LetMeASC` in editable mode
- create a `letmeasc` launcher in `~/.local/bin`

If `~/.local/bin` is not on your `PATH`, the installer tells you exactly what to add.

If you already use `pythos`, the shell-activated setup is still available:

```bash
cd /Users/matt/Development/LetMeASC
source ./bootstrap.sh
```

That will:

- use `pythos .venv` if `pythos` is installed in your shell
- otherwise create `.venv` with standard `python3 -m venv`
- activate the environment
- install `LetMeASC` in editable mode

Manual setup is still available:

```bash
cd /Users/matt/Development/LetMeASC
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick start

Create a device profile interactively:

```bash
letmeasc wizard --output profiles/my_board.yaml
```

The wizard asks how to reach the login prompt, what prompts look like, and what text means success or failure. It writes a ready-to-run profile.

Create a device profile by connecting to the board and replaying the steps you normally type:

```bash
letmeasc learn \
  --port /dev/ttyACM0 \
  --baud 115200 \
  --output profiles/my_board.yaml
```

`learn` connects to the live serial console, sends the steps you enter, captures the output after each step, and writes a profile skeleton from what it observed.

Create candidate lists from a firmware image:

```bash
letmeasc extract firmware.bin --out-dir wordlists
```

Run a serial profile with a password list:

```bash
letmeasc run \
  --profile profiles/example_board.yaml \
  --port /dev/ttyACM0 \
  --password-file wordlists/passwords.txt
```

Run one fixed username against a password list:

```bash
letmeasc run \
  --profile profiles/example_board.yaml \
  --port /dev/ttyACM0 \
  --username admin \
  --password-file wordlists/passwords.txt
```

Dry-run a profile and log the serial transcript without submitting credentials:

```bash
letmeasc run \
  --profile profiles/example_board.yaml \
  --port /dev/ttyACM0 \
  --password-file wordlists/passwords.txt \
  --dry-run
```

## Guided workflow

Use the wizard for normal setup. The generated profile still lives in YAML, but you only need to touch it if you want manual fine-tuning later.

The wizard supports:

- direct prompt targets with no pre-login steps
- one-trigger targets such as sending `\n` or `.l`
- menu-driven targets with multiple send/read/pause steps before every attempt
- password-only, username-only, and username+password flows
- configurable success, failure, and interesting-response detection

The live `learn` mode is the easiest starting point when you already know how to reach the prompt manually on a real board.

Use [profiles/example_board.yaml](/Users/matt/Development/LetMeASC/profiles/example_board.yaml) as a reference if you want to inspect what the wizard produces.

## Notes

- The serial device path is always overridable at runtime with `--port`.
- Success and failure detection are profile-driven because embedded targets vary widely.
- Transcript logging is enabled by default and helps tune prompt matching.
