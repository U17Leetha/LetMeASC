from __future__ import annotations

import time
from pathlib import Path

import serial

from letmeasc.ports import format_serial_ports
from letmeasc.profile import (
    LoginConfig,
    MatchRule,
    Profile,
    SerialConfig,
    Step,
    save_profile,
)


def run_wizard(output_path: str | Path) -> Path:
    target = Path(output_path)
    print("LetMeASC profile wizard")
    print("Answer the prompts and a device profile will be written for you.")
    print("")

    name = ask("Profile name", target.stem)
    baud = ask_int("Baud rate", 115200)
    timeout = ask_float("Serial timeout in seconds", 0.2)
    startup_delay = ask_float("Delay after opening the port", 2.0)
    inter_attempt_delay = ask_float("Delay between attempts", 0.6)
    transcript_path = ask("Transcript log path", "transcript.log")

    flow = ask_choice(
        "How do you reach the credential prompt?",
        [
            ("direct", "It is already there or appears by itself"),
            ("trigger", "I send one thing first, then the login prompt appears"),
            ("menu", "I have to navigate through one or more menu steps"),
        ],
        default="direct",
    )

    login_mode = ask_choice(
        "What kind of credential flow is this?",
        [
            ("password_only", "Password only"),
            ("username_only", "Username only"),
            ("username_password", "Username then password"),
        ],
        default="password_only",
    )

    connect_steps = build_connect_steps()
    pre_attempt_steps = build_pre_attempt_steps(flow)
    login = build_login(login_mode)
    success = build_rule_list("Success", "Enter text or regex that means login worked")
    failure = build_rule_list("Failure", "Enter text or regex that means login failed")
    interesting = build_rule_list(
        "Interesting", "Enter text or regex for responses worth stopping on"
    )

    profile = Profile(
        name=name,
        serial=SerialConfig(
            baud=baud,
            timeout=timeout,
            startup_delay=startup_delay,
            initial_read_quiet_time=0.5,
            initial_read_max_total=2.0,
            inter_attempt_delay=inter_attempt_delay,
        ),
        connect_steps=connect_steps,
        pre_attempt_steps=pre_attempt_steps,
        login=login,
        success=success,
        failure=failure,
        interesting=interesting,
        transcript_path=transcript_path,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    save_profile(profile, target)
    print("")
    print(f"Profile written to {target}")
    print(
        "Run it with: letmeasc run --profile "
        f"{target} --port /dev/ttyACM0 --password-file wordlists/passwords.txt"
    )
    return target


def run_live_wizard(output_path: str | Path, port: str, baud: int = 115200) -> Path:
    target = Path(output_path)
    print("LetMeASC live profile wizard")
    print(f"Connecting to {port} at {baud} baud.")
    print(
        "You will enter the same serial steps you normally type, and LetMeASC will build a profile from that session."
    )
    print("")

    name = ask("Profile name", target.stem)
    timeout = ask_float("Serial timeout in seconds", 0.2)
    startup_delay = ask_float("Delay after opening the port", 2.0)
    inter_attempt_delay = ask_float("Delay between attempts", 0.6)
    transcript_path = ask("Transcript log path", "transcript.log")

    try:
        ser = serial.Serial(port, baud, timeout=timeout)
    except serial.SerialException as exc:
        message = [f"Could not open serial port {port}: {exc}"]
        available = format_serial_ports()
        if available:
            message.append("")
            message.append(available)
        message.append("")
        message.append(
            "Tip: on Linux the device is often /dev/ttyACM0 or /dev/ttyUSB0."
        )
        raise SystemExit("\n".join(message))
    try:
        time.sleep(startup_delay)
        banner = read_available(ser, quiet_time=0.5, max_total=2.0)
        if banner.strip():
            print("")
            print("Initial device output:")
            print(banner)
        else:
            print("")
            print("No initial banner captured.")

        connect_steps = []
        if ask_yes_no("Record an initial read after connection in the profile?", True):
            connect_steps = [Step(action="read", quiet_time=0.5, max_total=2.0)]

        login_mode = ask_choice(
            "What kind of credential flow is this?",
            [
                ("password_only", "Password only"),
                ("username_only", "Username only"),
                ("username_password", "Username then password"),
            ],
            default="password_only",
        )

        print("")
        print("Manual navigation capture")
        print(
            "Enter the exact text you send to reach the credential prompt. Use \\n for Enter."
        )
        print("Press Enter on an empty line when there are no more pre-login steps.")

        pre_attempt_steps: list[Step] = []
        observed_chunks: list[str] = [banner] if banner else []
        step_index = 1
        while True:
            text = ask_allow_empty(f"Step {step_index} text")
            if text == "":
                break

            decoded = decode_escapes(text)
            if not has_flush(pre_attempt_steps):
                pre_attempt_steps.append(Step(action="flush"))
            pre_attempt_steps.append(Step(action="send", text=decoded))

            pause = ask_float(f"Pause after step {step_index}", 0.4)
            if pause > 0:
                pre_attempt_steps.append(Step(action="sleep", seconds=pause))
            quiet_time = ask_float(f"Quiet time after step {step_index}", 0.4)
            max_total = ask_float(f"Max read time after step {step_index}", 1.5)
            pre_attempt_steps.append(
                Step(action="read", quiet_time=quiet_time, max_total=max_total)
            )

            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write(decoded.encode())
            time.sleep(pause)
            output = read_available(ser, quiet_time=quiet_time, max_total=max_total)
            observed_chunks.append(output)

            print("")
            print(f"Output after step {step_index}:")
            print(output if output.strip() else "<no output>")

            if ask_yes_no("Did that reach the credential prompt?", False):
                break
            step_index += 1

        prompt_rule = None
        if ask_yes_no(
            "Wait for a credential prompt before sending the credential?", True
        ):
            prompt_suggestion = suggest_rule_text(observed_chunks)
            prompt_rule = ask_rule_with_default("prompt", prompt_suggestion)
            pre_attempt_steps.append(
                Step(
                    action="wait_for",
                    quiet_time=ask_float(
                        "Quiet time while waiting for the prompt", 0.3
                    ),
                    max_total=ask_float("Max time to wait for the prompt", 2.5),
                    match=prompt_rule,
                    optional=ask_yes_no("Should prompt waiting be optional?", True),
                )
            )

        login = build_login_with_default(login_mode, prompt_rule)
        success = build_rule_list(
            "Success", "Enter text or regex that means login worked"
        )
        failure = build_rule_list(
            "Failure", "Enter text or regex that means login failed"
        )
        interesting = build_rule_list(
            "Interesting", "Enter text or regex for responses worth stopping on"
        )

        profile = Profile(
            name=name,
            serial=SerialConfig(
                baud=baud,
                timeout=timeout,
                startup_delay=startup_delay,
                initial_read_quiet_time=0.5,
                initial_read_max_total=2.0,
                inter_attempt_delay=inter_attempt_delay,
            ),
            connect_steps=connect_steps,
            pre_attempt_steps=pre_attempt_steps,
            login=login,
            success=success,
            failure=failure,
            interesting=interesting,
            transcript_path=transcript_path,
        )
    finally:
        ser.close()

    target.parent.mkdir(parents=True, exist_ok=True)
    save_profile(profile, target)
    print("")
    print(f"Profile written to {target}")
    print(
        "Run it with: letmeasc run --profile "
        f"{target} --port {port} --password-file wordlists/passwords.txt"
    )
    return target


def build_connect_steps() -> list[Step]:
    want_initial_read = ask_yes_no(
        "Read and log initial banner/output after connect?", True
    )
    if not want_initial_read:
        return []
    return [Step(action="read", quiet_time=0.5, max_total=2.0)]


def build_pre_attempt_steps(flow: str) -> list[Step]:
    if flow == "direct":
        want_wait = ask_yes_no("Wait for a prompt before each attempt?", True)
        if not want_wait:
            return []
        return [build_wait_step(optional=False)]

    steps = [Step(action="flush")]
    if flow == "trigger":
        steps.extend(build_send_sequence(single_step=True))
    else:
        steps.extend(build_send_sequence(single_step=False))

    want_final_wait = ask_yes_no(
        "Wait for a login or password prompt after those steps?", True
    )
    if want_final_wait:
        optional = ask_yes_no("Should that final wait be optional?", True)
        steps.append(build_wait_step(optional=optional))
    else:
        want_tail_read = ask_yes_no("Read some output after the steps anyway?", True)
        if want_tail_read:
            steps.append(Step(action="read", quiet_time=0.4, max_total=1.5))
    return steps


def build_send_sequence(single_step: bool) -> list[Step]:
    steps: list[Step] = []
    count_default = 1 if single_step else 2
    count = ask_int(
        "How many send steps happen before each login attempt?",
        count_default,
        minimum=1,
    )
    for index in range(1, count + 1):
        text = ask(f"Text to send for step {index} (use \\n for Enter)")
        steps.append(Step(action="send", text=decode_escapes(text)))
        sleep_seconds = ask_float(
            f"Pause after step {index}", 0.3 if index == 1 else 0.5
        )
        if sleep_seconds > 0:
            steps.append(Step(action="sleep", seconds=sleep_seconds))
        want_read = ask_yes_no(f"Read output after step {index}?", True)
        if want_read:
            steps.append(
                Step(
                    action="read",
                    quiet_time=ask_float(f"Quiet time after step {index}", 0.4),
                    max_total=ask_float(f"Max read time after step {index}", 1.5),
                )
            )
    return steps


def build_login(mode: str) -> LoginConfig:
    username_prompt = None
    password_prompt = None
    if mode in {"username_only", "username_password"}:
        username_prompt = build_prompt_rule("username")
    if mode in {"password_only", "username_password"}:
        password_prompt = build_prompt_rule("password")
    return LoginConfig(
        mode=mode,
        username_prompt=username_prompt,
        password_prompt=password_prompt,
        submit_suffix=decode_escapes(
            ask("What should be sent after each credential?", "\\n")
        ),
    )


def build_login_with_default(mode: str, prompt_rule: MatchRule | None) -> LoginConfig:
    username_prompt = None
    password_prompt = None
    if mode in {"username_only", "username_password"}:
        username_prompt = build_prompt_rule_with_default("username", prompt_rule)
    if mode in {"password_only", "username_password"}:
        password_prompt = build_prompt_rule_with_default("password", prompt_rule)
    return LoginConfig(
        mode=mode,
        username_prompt=username_prompt,
        password_prompt=password_prompt,
        submit_suffix=decode_escapes(
            ask("What should be sent after each credential?", "\\n")
        ),
    )


def build_prompt_rule(label: str) -> MatchRule | None:
    wait = ask_yes_no(
        f"Should LetMeASC wait for a {label} prompt before sending it?", True
    )
    if not wait:
        return None
    return ask_rule(f"{label} prompt", f"How should the {label} prompt be matched?")


def build_prompt_rule_with_default(
    label: str, default_rule: MatchRule | None
) -> MatchRule | None:
    wait = ask_yes_no(
        f"Should LetMeASC wait for a {label} prompt before sending it?", True
    )
    if not wait:
        return None
    if default_rule is not None and ask_yes_no(
        f"Reuse the observed prompt rule for {label}?", True
    ):
        return default_rule
    return ask_rule(f"{label} prompt", f"How should the {label} prompt be matched?")


def build_wait_step(optional: bool) -> Step:
    rule = ask_rule("prompt", "How should the prompt be matched?")
    quiet_time = ask_float("Quiet time while waiting for the prompt", 0.3)
    max_total = ask_float("Max time to wait for the prompt", 2.5)
    return Step(
        action="wait_for",
        quiet_time=quiet_time,
        max_total=max_total,
        match=rule,
        optional=optional,
    )


def build_rule_list(label: str, helper: str) -> list[MatchRule]:
    print("")
    print(f"{label} detection")
    print(helper)
    rules: list[MatchRule] = []
    while ask_yes_no(
        f"Add a {label.lower()} rule?", label != "Interesting" and not rules
    ):
        rules.append(ask_rule(label.lower(), f"Create a {label.lower()} match rule"))
    return rules


def ask_rule(label: str, prompt: str) -> MatchRule:
    mode = ask_choice(
        prompt,
        [
            ("text", f"Plain text contains match for {label}"),
            ("regex", f"Regex match for {label}"),
        ],
        default="text",
    )
    value = ask(f"Enter the {mode} for {label}")
    case_insensitive = ask_yes_no("Case-insensitive match?", True)
    if mode == "text":
        return MatchRule(text=value, case_insensitive=case_insensitive)
    return MatchRule(regex=value, case_insensitive=case_insensitive)


def ask_rule_with_default(label: str, default_text: str | None) -> MatchRule:
    mode = ask_choice(
        f"How should the {label} be matched?",
        [
            ("text", f"Plain text contains match for {label}"),
            ("regex", f"Regex match for {label}"),
        ],
        default="text",
    )
    value = ask(
        f"Enter the {mode} for {label}",
        default_text if mode == "text" else None,
    )
    case_insensitive = ask_yes_no("Case-insensitive match?", True)
    if mode == "text":
        return MatchRule(text=value, case_insensitive=case_insensitive)
    return MatchRule(regex=value, case_insensitive=case_insensitive)


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def ask_allow_empty(prompt: str) -> str:
    return input(f"{prompt}: ")


def ask_yes_no(prompt: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        value = input(f"{prompt} [{default_text}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter y or n.")


def ask_choice(prompt: str, options: list[tuple[str, str]], default: str) -> str:
    print(prompt)
    for key, description in options:
        marker = " (default)" if key == default else ""
        print(f"  {key}: {description}{marker}")
    valid = {key for key, _description in options}
    while True:
        value = input(f"Choice [{default}]: ").strip().lower()
        if not value:
            return default
        if value in valid:
            return value
        print(f"Choose one of: {', '.join(sorted(valid))}")


def ask_int(prompt: str, default: int, minimum: int | None = None) -> int:
    while True:
        raw = ask(prompt, str(default))
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue
        if minimum is not None and value < minimum:
            print(f"Enter a value greater than or equal to {minimum}.")
            continue
        return value


def ask_float(prompt: str, default: float) -> float:
    while True:
        raw = ask(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            print("Enter a number.")


def decode_escapes(value: str) -> str:
    return value.encode("utf-8").decode("unicode_escape")


def read_available(
    ser: serial.Serial, quiet_time: float = 0.4, max_total: float = 2.0
) -> str:
    data = b""
    start = time.time()
    last_data = start

    while time.time() - start < max_total:
        waiting = ser.in_waiting
        if waiting:
            chunk = ser.read(waiting)
            data += chunk
            last_data = time.time()
        elif time.time() - last_data > quiet_time:
            break
        time.sleep(0.05)

    return data.decode(errors="ignore")


def suggest_rule_text(chunks: list[str]) -> str | None:
    for chunk in reversed(chunks):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        for line in reversed(lines):
            if len(line) <= 80:
                return line
    return None


def has_flush(steps: list[Step]) -> bool:
    return any(step.action == "flush" for step in steps)
