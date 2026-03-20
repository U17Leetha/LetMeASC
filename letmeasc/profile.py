from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MatchRule:
    text: str | None = None
    regex: str | None = None
    case_insensitive: bool = True


@dataclass
class Step:
    action: str
    text: str | None = None
    seconds: float | None = None
    quiet_time: float | None = None
    max_total: float | None = None
    match: MatchRule | None = None
    optional: bool = False


@dataclass
class LoginConfig:
    mode: str
    username_prompt: MatchRule | None = None
    password_prompt: MatchRule | None = None
    submit_suffix: str = "\n"


@dataclass
class SerialConfig:
    baud: int = 115200
    timeout: float = 0.2
    startup_delay: float = 2.0
    initial_read_quiet_time: float = 0.5
    initial_read_max_total: float = 2.0
    inter_attempt_delay: float = 0.5


@dataclass
class Profile:
    name: str
    serial: SerialConfig = field(default_factory=SerialConfig)
    connect_steps: list[Step] = field(default_factory=list)
    pre_attempt_steps: list[Step] = field(default_factory=list)
    login: LoginConfig | None = None
    success: list[MatchRule] = field(default_factory=list)
    failure: list[MatchRule] = field(default_factory=list)
    interesting: list[MatchRule] = field(default_factory=list)
    transcript_path: str = "transcript.log"


def _load_match_rule(raw: dict[str, Any] | None) -> MatchRule | None:
    if not raw:
        return None
    return MatchRule(
        text=raw.get("text"),
        regex=raw.get("regex"),
        case_insensitive=raw.get("case_insensitive", True),
    )


def _load_step(raw: dict[str, Any]) -> Step:
    return Step(
        action=raw["action"],
        text=raw.get("text"),
        seconds=raw.get("seconds"),
        quiet_time=raw.get("quiet_time"),
        max_total=raw.get("max_total"),
        match=_load_match_rule(raw.get("match")),
        optional=raw.get("optional", False),
    )


def _load_match_rules(raw: list[dict[str, Any]] | None) -> list[MatchRule]:
    return [
        _load_match_rule(item)
        for item in (raw or [])
        if _load_match_rule(item) is not None
    ]


def load_profile(path: str | Path) -> Profile:
    data = yaml.safe_load(Path(path).read_text()) or {}

    serial_raw = data.get("serial", {})
    serial_cfg = SerialConfig(
        baud=serial_raw.get("baud", 115200),
        timeout=serial_raw.get("timeout", 0.2),
        startup_delay=serial_raw.get("startup_delay", 2.0),
        initial_read_quiet_time=serial_raw.get("initial_read_quiet_time", 0.5),
        initial_read_max_total=serial_raw.get("initial_read_max_total", 2.0),
        inter_attempt_delay=serial_raw.get("inter_attempt_delay", 0.5),
    )

    login_raw = data.get("login", {})
    login_cfg = None
    if login_raw:
        login_cfg = LoginConfig(
            mode=login_raw["mode"],
            username_prompt=_load_match_rule(login_raw.get("username_prompt")),
            password_prompt=_load_match_rule(login_raw.get("password_prompt")),
            submit_suffix=login_raw.get("submit_suffix", "\n"),
        )

    return Profile(
        name=data.get("name", Path(path).stem),
        serial=serial_cfg,
        connect_steps=[_load_step(item) for item in data.get("connect_steps", [])],
        pre_attempt_steps=[
            _load_step(item) for item in data.get("pre_attempt_steps", [])
        ],
        login=login_cfg,
        success=_load_match_rules(data.get("success")),
        failure=_load_match_rules(data.get("failure")),
        interesting=_load_match_rules(data.get("interesting")),
        transcript_path=data.get("transcript_path", "transcript.log"),
    )


def save_profile(profile: Profile, path: str | Path) -> None:
    payload = {
        "name": profile.name,
        "transcript_path": profile.transcript_path,
        "serial": {
            "baud": profile.serial.baud,
            "timeout": profile.serial.timeout,
            "startup_delay": profile.serial.startup_delay,
            "initial_read_quiet_time": profile.serial.initial_read_quiet_time,
            "initial_read_max_total": profile.serial.initial_read_max_total,
            "inter_attempt_delay": profile.serial.inter_attempt_delay,
        },
        "connect_steps": [_dump_step(step) for step in profile.connect_steps],
        "pre_attempt_steps": [_dump_step(step) for step in profile.pre_attempt_steps],
        "login": _dump_login(profile.login),
        "success": _dump_match_rules(profile.success),
        "failure": _dump_match_rules(profile.failure),
        "interesting": _dump_match_rules(profile.interesting),
    }
    Path(path).write_text(yaml.safe_dump(payload, sort_keys=False))


def _dump_step(step: Step) -> dict[str, Any]:
    data: dict[str, Any] = {"action": step.action}
    if step.text is not None:
        data["text"] = step.text
    if step.seconds is not None:
        data["seconds"] = step.seconds
    if step.quiet_time is not None:
        data["quiet_time"] = step.quiet_time
    if step.max_total is not None:
        data["max_total"] = step.max_total
    if step.match is not None:
        data["match"] = _dump_match_rule(step.match)
    if step.optional:
        data["optional"] = True
    return data


def _dump_login(login: LoginConfig | None) -> dict[str, Any] | None:
    if login is None:
        return None
    data: dict[str, Any] = {
        "mode": login.mode,
        "submit_suffix": login.submit_suffix,
    }
    if login.username_prompt is not None:
        data["username_prompt"] = _dump_match_rule(login.username_prompt)
    if login.password_prompt is not None:
        data["password_prompt"] = _dump_match_rule(login.password_prompt)
    return data


def _dump_match_rules(rules: list[MatchRule]) -> list[dict[str, Any]]:
    return [_dump_match_rule(rule) for rule in rules]


def _dump_match_rule(rule: MatchRule) -> dict[str, Any]:
    data: dict[str, Any] = {
        "case_insensitive": rule.case_insensitive,
    }
    if rule.text is not None:
        data["text"] = rule.text
    if rule.regex is not None:
        data["regex"] = rule.regex
    return data
