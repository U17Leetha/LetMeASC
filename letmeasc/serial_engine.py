from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import serial

from letmeasc.profile import LoginConfig, MatchRule, Profile, Step


@dataclass
class Credential:
    username: str | None = None
    password: str | None = None


@dataclass
class AttemptResult:
    credential: Credential
    pre_output: str
    response: str
    outcome: str


class SerialRunner:
    def __init__(self, profile: Profile, port: str, transcript_path: str | None = None):
        self.profile = profile
        self.port = port
        self.transcript_path = Path(transcript_path or profile.transcript_path)
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self._transcript = self.transcript_path.open("a", encoding="utf-8")

    def run(self, credentials: Iterable[Credential], dry_run: bool = False) -> AttemptResult | None:
        ser = serial.Serial(
            self.port,
            self.profile.serial.baud,
            timeout=self.profile.serial.timeout,
        )
        try:
            time.sleep(self.profile.serial.startup_delay)
            banner = self.read_available(
                ser,
                quiet_time=self.profile.serial.initial_read_quiet_time,
                max_total=self.profile.serial.initial_read_max_total,
            )
            self._log("initial", banner)
            self.execute_steps(ser, self.profile.connect_steps)

            for credential in credentials:
                pre_output = self.execute_steps(ser, self.profile.pre_attempt_steps)

                if dry_run:
                    self._log("dry-run", f"would try {credential}")
                    time.sleep(self.profile.serial.inter_attempt_delay)
                    continue

                response = self.submit_credential(ser, credential)
                outcome = classify_output(response, self.profile)
                result = AttemptResult(
                    credential=credential,
                    pre_output=pre_output,
                    response=response,
                    outcome=outcome,
                )
                self._log("attempt", f"{credential} => {outcome}\n{response}")

                if outcome in {"success", "interesting"}:
                    return result

                time.sleep(self.profile.serial.inter_attempt_delay)

            return None
        finally:
            ser.close()
            self._transcript.close()

    def execute_steps(self, ser: serial.Serial, steps: list[Step]) -> str:
        output = ""
        for step in steps:
            if step.action == "flush":
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            elif step.action == "send":
                if step.text is None:
                    raise ValueError("send step requires text")
                ser.write(step.text.encode())
            elif step.action == "sleep":
                time.sleep(step.seconds or 0)
            elif step.action == "read":
                output += self.read_available(
                    ser,
                    quiet_time=step.quiet_time or 0.4,
                    max_total=step.max_total or 2.0,
                )
            elif step.action == "wait_for":
                output += self.wait_for(
                    ser,
                    step.match,
                    quiet_time=step.quiet_time or 0.25,
                    max_total=step.max_total or 3.0,
                    optional=step.optional,
                )
            else:
                raise ValueError(f"unsupported step action: {step.action}")
        if output:
            self._log("steps", output)
        return output

    def submit_credential(self, ser: serial.Serial, credential: Credential) -> str:
        login_cfg = self.profile.login
        if login_cfg is None:
            raise ValueError("profile is missing login configuration")

        if login_cfg.mode in {"username_only", "username_password"} and credential.username is not None:
            self._wait_for_prompt(ser, login_cfg.username_prompt, "username")
            ser.write((credential.username + login_cfg.submit_suffix).encode())

        if login_cfg.mode in {"password_only", "username_password"} and credential.password is not None:
            self._wait_for_prompt(ser, login_cfg.password_prompt, "password")
            ser.write((credential.password + login_cfg.submit_suffix).encode())

        response = self.read_available(ser, quiet_time=0.5, max_total=2.5)
        return response

    def _wait_for_prompt(self, ser: serial.Serial, rule: MatchRule | None, label: str) -> None:
        if rule is None:
            return
        matched = self.wait_for(ser, rule, quiet_time=0.25, max_total=5.0, optional=False)
        self._log("prompt", f"{label}: {matched}")

    def read_available(self, ser: serial.Serial, quiet_time: float = 0.4, max_total: float = 2.0) -> str:
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

        text = data.decode(errors="ignore")
        if text:
            self._log("serial", text)
        return text

    def wait_for(
        self,
        ser: serial.Serial,
        rule: MatchRule | None,
        quiet_time: float,
        max_total: float,
        optional: bool,
    ) -> str:
        text = ""
        start = time.time()
        while time.time() - start < max_total:
            text += self.read_available(ser, quiet_time=quiet_time, max_total=quiet_time + 0.1)
            if rule is None or matches_rule(text, rule):
                return text
        if optional:
            return text
        raise TimeoutError(f"timed out waiting for match {rule}")

    def _log(self, kind: str, text: str) -> None:
        if not text:
            return
        self._transcript.write(f"\n[{kind}] {time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}\n")
        self._transcript.flush()


def matches_rule(text: str, rule: MatchRule) -> bool:
    flags = re.IGNORECASE if rule.case_insensitive else 0
    if rule.text is not None:
        haystack = text.lower() if rule.case_insensitive else text
        needle = rule.text.lower() if rule.case_insensitive else rule.text
        return needle in haystack
    if rule.regex is not None:
        return re.search(rule.regex, text, flags=flags) is not None
    return False


def classify_output(text: str, profile: Profile) -> str:
    for rule in profile.success:
        if matches_rule(text, rule):
            return "success"
    for rule in profile.failure:
        if matches_rule(text, rule):
            return "failure"
    for rule in profile.interesting:
        if matches_rule(text, rule):
            return "interesting"
    return "unknown"


def build_credentials(
    mode: str,
    usernames: list[str] | None = None,
    passwords: list[str] | None = None,
) -> list[Credential]:
    usernames = usernames or []
    passwords = passwords or []

    if mode == "password_only":
        return [Credential(password=value) for value in passwords]
    if mode == "username_only":
        return [Credential(username=value) for value in usernames]
    if mode == "username_password":
        if usernames and passwords:
            return [Credential(username=user, password=password) for user in usernames for password in passwords]
        if passwords:
            return [Credential(password=password) for password in passwords]
        return [Credential(username=user) for user in usernames]
    raise ValueError(f"unsupported login mode: {mode}")
