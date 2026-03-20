from __future__ import annotations

import argparse
from pathlib import Path

from letmeasc.firmware import extract_strings, score_candidates, write_wordlists
from letmeasc.ports import format_serial_ports
from letmeasc.profile import load_profile
from letmeasc.serial_engine import SerialRunner, build_credentials
from letmeasc.wizard import run_live_wizard, run_wizard


def main() -> None:
    parser = argparse.ArgumentParser(prog="letmeasc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract", help="Extract candidate lists from a firmware image"
    )
    extract_parser.add_argument("firmware", help="Path to firmware image")
    extract_parser.add_argument(
        "--out-dir", default="wordlists", help="Directory for generated wordlists"
    )

    wizard_parser = subparsers.add_parser(
        "wizard", help="Interactively create a device profile"
    )
    wizard_parser.add_argument(
        "--output",
        default="profiles/new_device.yaml",
        help="Path for the generated YAML profile",
    )

    subparsers.add_parser("ports", help="List detected serial ports")

    learn_parser = subparsers.add_parser(
        "learn",
        help="Connect to a serial device and build a profile from observed steps",
    )
    learn_parser.add_argument(
        "--port", required=True, help="Serial device path, for example /dev/ttyACM0"
    )
    learn_parser.add_argument(
        "--baud", type=int, default=115200, help="Serial baud rate"
    )
    learn_parser.add_argument(
        "--output",
        default="profiles/live_device.yaml",
        help="Path for the generated YAML profile",
    )

    run_parser = subparsers.add_parser("run", help="Run a serial login workflow")
    run_parser.add_argument(
        "--profile", required=True, help="Path to YAML device profile"
    )
    run_parser.add_argument(
        "--port", required=True, help="Serial device path, for example /dev/ttyACM0"
    )
    run_parser.add_argument("--username", help="Single username value")
    run_parser.add_argument("--username-file", help="File with one username per line")
    run_parser.add_argument("--password", help="Single password value")
    run_parser.add_argument("--password-file", help="File with one password per line")
    run_parser.add_argument("--transcript", help="Override transcript log path")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk the profile without sending credentials",
    )

    args = parser.parse_args()

    if args.command == "extract":
        raw_strings = extract_strings(args.firmware)
        usernames, passwords = score_candidates(raw_strings)
        write_wordlists(args.out_dir, usernames, passwords, raw_strings)
        print(f"Extracted {len(raw_strings)} strings")
        print(
            f"Wrote {len(usernames)} usernames and {len(passwords)} passwords to {args.out_dir}"
        )
        return

    if args.command == "wizard":
        run_wizard(args.output)
        return

    if args.command == "ports":
        print(format_serial_ports())
        return

    if args.command == "learn":
        run_live_wizard(args.output, args.port, baud=args.baud)
        return

    if args.command == "run":
        profile = load_profile(args.profile)
        if profile.login is None:
            raise SystemExit("Profile is missing a login section.")

        usernames = load_values(args.username, args.username_file)
        passwords = load_values(args.password, args.password_file)
        credentials = build_credentials(
            profile.login.mode, usernames=usernames, passwords=passwords
        )
        if not credentials:
            raise SystemExit(
                "No credentials loaded. Supply --username/--username-file and/or --password/--password-file."
            )

        runner = SerialRunner(profile, port=args.port, transcript_path=args.transcript)
        result = runner.run(credentials, dry_run=args.dry_run)
        if result is None:
            print(
                "No success or interesting response found in the supplied credential set."
            )
            return

        print(f"Outcome: {result.outcome}")
        print(
            f"Credential: username={result.credential.username!r} password={result.credential.password!r}"
        )
        if result.response.strip():
            print("Response:")
            print(result.response)


def load_lines(path: str) -> list[str]:
    return [
        line.strip()
        for line in Path(path).read_text(errors="ignore").splitlines()
        if line.strip()
    ]


def load_values(single_value: str | None, file_path: str | None) -> list[str]:
    values: list[str] = []
    if single_value:
        values.append(single_value)
    if file_path:
        values.extend(load_lines(file_path))
    return values


if __name__ == "__main__":
    main()
