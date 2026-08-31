#!/usr/bin/env python3
"""Private macOS Keychain writer for agent-psql.

The password arrives on stdin and is hex-encoded only inside this process.
SecurityTool receives one bounded interactive command on stdin; neither the raw
password nor its hex encoding is placed in a process argument or environment
variable.

``tools/agent-psql`` supplies the password from a Bash variable. Bash strings
cannot contain NUL bytes, so embedded NUL is outside that caller's contract even
though this helper operates on bytes read from stdin.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol
from urllib.parse import unquote_to_bytes, urlsplit, urlunsplit

SECURITY_INPUT_LIMIT = 4096
SECURITY_TIMEOUT_SECONDS = 15
PROFILE_INPUT_LIMIT = 16384
PROFILE_STORE_OK = 0
PROFILE_KEYCHAIN_FAILURE = 1
PROFILE_STATE_FAILURE = 2
PROFILE_EXISTS = 3
PROFILE_NO_CREDENTIAL = 4
PROFILE_NOT_FOUND = 5
PROFILE_BUSY = 6
_SECURITY_BIN = "/usr/bin/security"
_KEYCHAIN_SERVICE = "agent-psql"
_MISSING = object()
_SECRET_QUERY_KEYS = {"password", "sslpassword"}


class _CompletedProcess(Protocol):
    returncode: int
    stdout: bytes
    stderr: bytes


_Runner = Callable[..., _CompletedProcess]


def _security_child_env() -> dict[str, str]:
    """Return a child environment without supported password holders."""

    child_env = os.environ.copy()
    for name in (
        "PGPASSWORD",
        "_PG_PASSWORD",
        "password",
        "keychain_secret",
        "pgpassword_value",
        "conn_string",
        "stored_pw",
    ):
        child_env.pop(name, None)
    return child_env


def _quote_security_arg(value: str) -> str:
    """Quote one argument for SecurityTool's interactive split_line parser."""

    if not value or any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError("invalid SecurityTool argument")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _build_store_command(account: str, secret: bytes) -> bytes:
    """Build one bounded add-or-update command for SecurityTool stdin."""

    if not secret:
        raise ValueError("empty secret")

    command = (
        "add-generic-password -U "
        f"-a {_quote_security_arg(account)} "
        f"-s {_quote_security_arg(_KEYCHAIN_SERVICE)} "
        f"-X {secret.hex()}\n"
    ).encode("utf-8")
    if len(command) >= SECURITY_INPUT_LIMIT:
        raise ValueError("SecurityTool command exceeds interactive parser bound")
    return command


def store_password(
    account: str,
    secret: bytes,
    *,
    runner: _Runner = subprocess.run,
    security_bin: str = _SECURITY_BIN,
) -> bool:
    """Store ``secret`` under the agent-psql service, returning only success."""

    try:
        command = _build_store_command(account, secret)
        result = runner(
            [security_bin, "-i", "-q"],
            input=command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=_security_child_env(),
            timeout=SECURITY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return False
    return result.returncode == 0


def read_password(
    account: str,
    *,
    runner: _Runner = subprocess.run,
    security_bin: str = _SECURITY_BIN,
) -> bytes | None:
    """Read a stored password, decoding SecurityTool's binary hex display."""

    if not account or any(character in account for character in ("\x00", "\r", "\n")):
        return None
    child_env = _security_child_env()
    common = [security_bin, "find-generic-password", "-a", account, "-s", _KEYCHAIN_SERVICE]
    try:
        detail = runner(
            [*common, "-g"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=child_env,
            timeout=SECURITY_TIMEOUT_SECONDS,
        )
        if detail.returncode != 0:
            return None
        password_line = next(
            (line for line in detail.stderr.splitlines() if line.startswith(b"password: ")),
            None,
        )
        if password_line is None:
            return None
        hex_prefix = b"password: 0x"
        if password_line.startswith(hex_prefix):
            token = password_line[len(hex_prefix) :].split(maxsplit=1)[0]
            if not token or len(token) % 2:
                return None
            return bytes.fromhex(token.decode("ascii"))
        if not password_line.startswith(b'password: "'):
            return None

        plain = runner(
            [*common, "-w"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            env=child_env,
            timeout=SECURITY_TIMEOUT_SECONDS,
        )
        if plain.returncode != 0:
            return None
        return plain.stdout[:-1] if plain.stdout.endswith(b"\n") else plain.stdout
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return None


def delete_password(
    account: str,
    *,
    runner: _Runner = subprocess.run,
    security_bin: str = _SECURITY_BIN,
) -> bool:
    """Best-effort removal for one agent-psql Keychain account."""

    if not account or any(character in account for character in ("\x00", "\r", "\n")):
        return False
    try:
        result = runner(
            [
                security_bin,
                "delete-generic-password",
                "-a",
                account,
                "-s",
                _KEYCHAIN_SERVICE,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=_security_child_env(),
            timeout=SECURITY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return False
    return result.returncode == 0


class _ProfileBusyError(Exception):
    """Raised when another profile mutation already owns the state lock."""


@contextmanager
def _profile_mutation_lock(profiles_path: Path) -> Iterator[None]:
    """Hold one bounded sibling lock across a complete profile mutation."""

    profiles_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = profiles_path.with_name(f".{profiles_path.name}.lock")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise _ProfileBusyError from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _load_profiles(profiles_path: Path) -> dict[str, object]:
    if not profiles_path.exists():
        return {}

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate profile-state key")
            result[key] = value
        return result

    with profiles_path.open(encoding="utf-8") as stream:
        profiles = json.load(stream, object_pairs_hook=unique_object)
    if not isinstance(profiles, dict):
        raise ValueError("profile state must be an object")
    return profiles


def _valid_profile_account(account: str) -> bool:
    """Keep user profiles outside the reserved session credential namespace."""

    return bool(account) and not account.startswith("session-") and not any(
        character in account for character in ("\x00", "\r", "\n")
    )


def _validated_profile_uri(connection_string: str):
    """Parse one supported URI and reject query-parameter secrets."""

    if not connection_string.casefold().startswith(("postgresql://", "postgres://")):
        raise ValueError("profile connection string must use PostgreSQL URI syntax")
    try:
        parsed = urlsplit(connection_string)
    except ValueError as error:
        raise ValueError("profile connection string is invalid") from error
    try:
        # urllib delays nonnumeric/out-of-range port validation until access.
        # Force it before a malformed user:password typo can be classified as
        # a passwordless host:port record and persisted verbatim. This also
        # rejects per-host port lists, which agent-psql's existing single-port
        # connection parser cannot consume. Empty endpoints remain supported;
        # that parser has historically mapped them to localhost.
        parsed.port
    except ValueError as error:
        raise ValueError("profile endpoint is invalid") from error

    # libpq accepts every connection keyword as a URI query parameter. Query
    # passwords would bypass userinfo masking and land in profiles.json.
    for field in parsed.query.split("&"):
        encoded_key = field.partition("=")[0]
        try:
            decoded_key = unquote_to_bytes(encoded_key).decode("ascii")
        except UnicodeError:
            continue
        if decoded_key.casefold() in _SECRET_QUERY_KEYS:
            raise ValueError("profile query passwords are not supported")
    return parsed


def _profile_record(record: object) -> tuple[str, bool]:
    """Return the bounded connection string and its credential expectation."""

    if not isinstance(record, dict):
        raise ValueError("profile record must be an object")
    connection_string = record.get("connection_string")
    if not isinstance(connection_string, str) or not connection_string:
        raise ValueError("profile connection string is invalid")
    try:
        encoded_connection = connection_string.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("profile connection string is invalid") from error
    if len(encoded_connection) > PROFILE_INPUT_LIMIT:
        raise ValueError("profile connection string is outside the supported bound")
    if any(character in connection_string for character in ("\x00", "\r", "\n")):
        raise ValueError("profile connection string contains a control character")
    parsed_password = _validated_profile_uri(connection_string).password

    explicit = record.get("credential_required", _MISSING)
    if explicit is _MISSING:
        # Legacy records predate the explicit bit. Only the historical masked
        # placeholder proves that those records expect a Keychain credential.
        if parsed_password == "****":
            return connection_string, True
        if parsed_password in (None, ""):
            return connection_string, False
        raise ValueError("legacy profile contains an unbounded password")
    if type(explicit) is not bool:
        raise ValueError("profile credential marker must be a boolean")
    if (explicit and parsed_password != "****") or (
        not explicit and parsed_password not in (None, "")
    ):
        raise ValueError("profile credential marker and connection string disagree")
    return connection_string, explicit


def read_profile(
    account: str,
    profiles_path: str | os.PathLike[str],
) -> tuple[str, bool] | None:
    """Read one atomically published profile without touching Keychain state."""

    if not _valid_profile_account(account):
        raise ValueError("invalid profile account")
    try:
        profiles = _load_profiles(Path(profiles_path))
        if account not in profiles:
            return None
        return _profile_record(profiles[account])
    except (OSError, TypeError, ValueError):
        raise ValueError("invalid profile state") from None


def _parse_profile_uri(raw_connection: bytes) -> tuple[str, bytes, bool]:
    """Split one bounded URI into a masked record and byte-exact credential."""

    if not raw_connection or len(raw_connection) > PROFILE_INPUT_LIMIT:
        raise ValueError("profile connection string is outside the supported bound")
    if any(character in raw_connection for character in (b"\x00", b"\r", b"\n")):
        raise ValueError("profile connection string contains a raw control character")
    try:
        connection_string = raw_connection.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("profile connection string is invalid") from error
    parsed = _validated_profile_uri(connection_string)

    netloc = parsed.netloc
    if "@" not in netloc:
        return connection_string, b"", False
    userinfo, endpoint = netloc.rsplit("@", 1)
    if ":" not in userinfo:
        return connection_string, b"", False
    username, encoded_password = userinfo.split(":", 1)
    if not encoded_password:
        passwordless = urlunsplit(
            (parsed.scheme, f"{username}@{endpoint}", parsed.path, parsed.query, parsed.fragment)
        )
        return passwordless, b"", False

    secret = unquote_to_bytes(encoded_password)
    if not secret or b"\x00" in secret:
        raise ValueError("profile password is outside the Bash boundary")
    masked = urlunsplit(
        (
            parsed.scheme,
            f"{username}:****@{endpoint}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )
    return masked, secret, True


def store_profile_uri(
    account: str,
    raw_connection: bytes,
    profiles_path: str | os.PathLike[str],
    *,
    runner: _Runner = subprocess.run,
    platform_name: str = sys.platform,
) -> tuple[int, bool]:
    """Parse and store a profile without copying its password into child argv."""

    try:
        connection_string, secret, credential_required = _parse_profile_uri(raw_connection)
    except ValueError:
        return PROFILE_STATE_FAILURE, False
    return (
        store_profile(
            account,
            secret,
            profiles_path,
            connection_string,
            runner=runner,
            store_credential=credential_required and platform_name == "darwin",
            credential_required=credential_required,
        ),
        credential_required,
    )


def _stage_profiles(profiles_path: Path, profiles: dict[str, object]) -> Path:
    """Write a same-directory candidate file without publishing it."""

    profiles_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{profiles_path.name}.",
        dir=profiles_path.parent,
        text=True,
    )
    staged_path = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(profiles, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            staged_path.unlink()
        except OSError:
            pass
        raise
    return staged_path


def store_profile(
    account: str,
    secret: bytes,
    profiles_path: str | os.PathLike[str],
    connection_string: str,
    *,
    runner: _Runner = subprocess.run,
    replacer: Callable[..., object] = os.replace,
    store_credential: bool = True,
    credential_required: bool | None = None,
) -> int:
    """Stage a new profile, store its credential, then atomically publish it.

    Existing names are removal-first: overwriting one could bind a new Keychain
    password to an old endpoint if the later profile-file publish failed.
    """

    path = Path(profiles_path)
    if not _valid_profile_account(account):
        return PROFILE_STATE_FAILURE
    if type(store_credential) is not bool:
        return PROFILE_STATE_FAILURE
    if credential_required is None:
        credential_required = store_credential
    if type(credential_required) is not bool:
        return PROFILE_STATE_FAILURE
    if credential_required and not secret:
        return PROFILE_KEYCHAIN_FAILURE
    if not credential_required and secret:
        return PROFILE_STATE_FAILURE
    if store_credential and not credential_required:
        return PROFILE_STATE_FAILURE
    staged_path: Path | None = None
    try:
        with _profile_mutation_lock(path):
            try:
                profiles = _load_profiles(path)
                if account in profiles:
                    return PROFILE_EXISTS
                # Validate the exact record before any credential mutation.
                record = {
                    "connection_string": connection_string,
                    "credential_required": credential_required,
                }
                _profile_record(record)
                profiles[account] = record
                staged_path = _stage_profiles(path, profiles)
            except (OSError, TypeError, ValueError):
                return PROFILE_STATE_FAILURE

            if store_credential and not store_password(account, secret, runner=runner):
                return PROFILE_KEYCHAIN_FAILURE
            try:
                replacer(staged_path, path)
            except OSError:
                return PROFILE_STATE_FAILURE
            staged_path = None
            return PROFILE_STORE_OK
    except _ProfileBusyError:
        return PROFILE_BUSY
    except OSError:
        return PROFILE_STATE_FAILURE
    finally:
        if staged_path is not None:
            try:
                staged_path.unlink()
            except OSError:
                pass


def remove_profile(
    account: str,
    profiles_path: str | os.PathLike[str],
    *,
    runner: _Runner = subprocess.run,
    replacer: Callable[..., object] = os.replace,
    delete_credential: bool = True,
) -> int:
    """Atomically remove one profile and its explicitly bound credential."""

    path = Path(profiles_path)
    if not _valid_profile_account(account):
        return PROFILE_STATE_FAILURE
    staged_path: Path | None = None
    try:
        with _profile_mutation_lock(path):
            try:
                profiles = _load_profiles(path)
                if account not in profiles:
                    return PROFILE_NOT_FOUND
                _, credential_required = _profile_record(profiles[account])
                del profiles[account]
                staged_path = _stage_profiles(path, profiles)
                replacer(staged_path, path)
                staged_path = None
            except (OSError, TypeError, ValueError):
                return PROFILE_STATE_FAILURE

            # The published profile map is already safe. Cleanup is best effort
            # and only follows an explicit (or compatible legacy) credential
            # binding. Passwordless records and missing names never authorize a
            # Keychain mutation; any orphan remains inert because reads consult
            # the binding bit before touching Keychain.
            if delete_credential and credential_required:
                delete_password(account, runner=runner)
            return PROFILE_STORE_OK
    except _ProfileBusyError:
        return PROFILE_BUSY
    except OSError:
        return PROFILE_STATE_FAILURE
    finally:
        if staged_path is not None:
            try:
                staged_path.unlink()
            except OSError:
                pass


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    runner: _Runner = subprocess.run,
    platform_name: str = sys.platform,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 3 and args[0] == "--profile-uri":
        stream = sys.stdin.buffer if stdin is None else stdin
        try:
            raw_connection = stream.read(PROFILE_INPUT_LIMIT + 1)
        except OSError:
            return PROFILE_STATE_FAILURE
        if len(raw_connection) > PROFILE_INPUT_LIMIT:
            return PROFILE_STATE_FAILURE
        status, credential_required = store_profile_uri(
            args[1],
            raw_connection,
            args[2],
            runner=runner,
            platform_name=platform_name,
        )
        if status != PROFILE_STORE_OK:
            return status
        return PROFILE_STORE_OK if credential_required else PROFILE_NO_CREDENTIAL
    if len(args) == 3 and args[0] == "--profile-read":
        try:
            profile = read_profile(args[1], args[2])
        except ValueError:
            return PROFILE_STATE_FAILURE
        if profile is None:
            return PROFILE_NOT_FOUND
        connection_string, credential_required = profile
        sys.stdout.write(connection_string)
        return PROFILE_STORE_OK if credential_required else PROFILE_NO_CREDENTIAL
    if len(args) == 3 and args[0] == "--profile-remove":
        return remove_profile(
            args[1],
            args[2],
            runner=runner,
            delete_credential=platform_name == "darwin",
        )
    if len(args) == 2 and args[0] == "--read":
        if platform_name != "darwin":
            return 1
        secret = read_password(args[1], runner=runner)
        if secret is None:
            return 1
        sys.stdout.buffer.write(secret)
        return 0
    if len(args) == 1:
        mode = "password"
        account = args[0]
    elif len(args) == 4 and args[0] in ("--profile", "--profile-no-secret"):
        mode = "profile"
        account = args[1]
    else:
        return 1

    stream = sys.stdin.buffer if stdin is None else stdin
    try:
        secret = stream.read(SECURITY_INPUT_LIMIT + 1)
    except OSError:
        return 1
    if mode == "profile":
        return store_profile(
            account,
            secret,
            args[2],
            args[3],
            runner=runner,
            store_credential=args[0] == "--profile" and platform_name == "darwin",
            credential_required=args[0] == "--profile",
        )
    if platform_name != "darwin":
        return 0
    return 0 if store_password(account, secret, runner=runner) else 1


if __name__ == "__main__":
    raise SystemExit(main())
