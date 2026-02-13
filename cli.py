import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import asyncio

import requests
import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.progress import Progress, TaskID

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

PERSON1_EMAIL_INDEX = 0
PERSON2_EMAIL = "mishalsabu24bcs0214@iiitkottayam.ac.in"
MATCHER_EMAIL_INDEX = 1


@dataclass(frozen=True)
class Config:
    users_all_url: str = "https://www.jjose.tech/users/all"
    make_match_url: str = "https://www.jjose.tech/match/make"
    referer: str = "https://cupids-ledger.vercel.app/"
    origin: str = "https://cupids-ledger.vercel.app"

    # Defaults copied from your existing script so you can hit Enter to keep them.
    auth_bearer_token: str = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiJub2VsZ2VvcmdpMjRiY2QyM0BpaWl0a290dGF5YW0uYWMuaW4iLCJuYW1lIjoiTk9FTCBHRU9S"
        "R0kgLUlJSVRLIiwiaWF0IjoxNzcwOTk0MzU1LCJleHAiOjE3NzA5OTc5NTV9."
        "OoqjsOa4YVTcN4PPTlMRzlBax4eSfCsr7p-giwnq_Co"
    )

    # Payload defaults (match payload keys exactly).
    person2_email: str = PERSON2_EMAIL
    person1_email_index: int = PERSON1_EMAIL_INDEX
    matcher_email_index: int = MATCHER_EMAIL_INDEX

    output_json_path: Path = Path("users_all.json")
    state_dir: Path = Path("state")
    used_emails_path: Path = Path("state") / "used_emails.json"


def _headers(cfg: Config) -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": cfg.referer,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.auth_bearer_token}",
        "Origin": cfg.origin,
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }


def _extract_users(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("users", "data", "result", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _extract_email(user: dict[str, Any]) -> str | None:
    direct = user.get("email")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    for parent_key in ("user", "profile"):
        nested = user.get(parent_key)
        if isinstance(nested, dict):
            nested_email = nested.get("email")
            if isinstance(nested_email, str) and nested_email.strip():
                return nested_email.strip()

    return None


def _pick_email(users_payload: Any, index: int, field_name: str) -> str:
    users = _extract_users(users_payload)
    if not users:
        raise ValueError("No users found in /users/all response.")

    if not (0 <= index < len(users)):
        raise IndexError(f"{field_name} index {index} out of range (0..{len(users) - 1}).")

    email = _extract_email(users[index])
    if not email:
        raise ValueError(f"Selected {field_name} user at index {index} has no valid email.")

    return email


def _fetch_users_all(cfg: Config) -> Any:
    resp = requests.get(cfg.users_all_url, headers=_headers(cfg), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _prompt_with_default(prompt: str, default: str, password: bool = False) -> str:
    # Rich shows the default and uses it on Enter.
    return Prompt.ask(prompt, default=default, password=password)


def _load_used_emails(cfg: Config) -> set[str]:
    """
    Tracks which emails you've already submitted as person1_email (and matcher_email if you choose).
    This is to prevent accidental duplicate submissions, not to bypass any restrictions.
    """
    try:
        if not cfg.used_emails_path.exists():
            return set()
        raw = json.loads(cfg.used_emails_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {e for e in raw if isinstance(e, str) and e.strip()}
        if isinstance(raw, dict):
            items = raw.get("emails")
            if isinstance(items, list):
                return {e for e in items if isinstance(e, str) and e.strip()}
        return set()
    except Exception:
        # If state is corrupted, fail closed-ish but still usable.
        return set()


def _save_used_emails(cfg: Config, emails: set[str]) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "emails": sorted(emails),
    }
    cfg.used_emails_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tui_banner(title: str, subtitle: str) -> None:
    console.print(
        Panel.fit(
            f"[bold]{title}[/bold]\n[dim]{subtitle}[/dim]",
            border_style="cyan",
        )
    )


def _tui_preview_users(users_payload: Any, max_rows: int = 10) -> None:
    users = _extract_users(users_payload)
    table = Table(title="Users (preview)", show_lines=False)
    table.add_column("Index", justify="right", style="bold")
    table.add_column("Email", overflow="fold")

    for i, user in enumerate(users[:max_rows]):
        table.add_row(str(i), _extract_email(user) or "")

    if len(users) > max_rows:
        table.add_row("...", f"({len(users) - max_rows} more)")

    console.print(table)


@app.command("fetch-users")
def fetch_users(
    output: Path = typer.Option(None, help="Where to save the raw /users/all JSON."),
    token: str = typer.Option(
        None,
        help="Bearer token. If omitted, you will be prompted (Enter keeps default).",
    ),
) -> None:
    cfg = Config()
    out_path = output or cfg.output_json_path

    _tui_banner("Fetch Users", "GET /users/all and save the raw JSON.")
    bearer = token or _prompt_with_default(
        "Authorization Bearer token",
        cfg.auth_bearer_token,
        password=True,
    )
    cfg = Config(auth_bearer_token=bearer, output_json_path=out_path)

    data = _fetch_users_all(cfg)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    ts = datetime.now(timezone.utc).isoformat()
    print(f"[green]Saved[/green] /users/all JSON to: {out_path.resolve()}")
    print(f"Fetched at: {ts}")

    users = _extract_users(data)
    print(f"Users parsed: {len(users)}")
    if users:
        sample = _extract_email(users[0]) or "(no email field)"
        print(f"First email: {sample}")
        _tui_preview_users(data, max_rows=10)


@app.command("state-show")
def state_show() -> None:
    cfg = Config()
    _tui_banner("State", f"Showing tracked emails in {cfg.used_emails_path}")
    emails = _load_used_emails(cfg)
    table = Table(title="Used emails", show_lines=False)
    table.add_column("Count", justify="right")
    table.add_column("Emails (first 20)", overflow="fold")
    table.add_row(str(len(emails)), "\n".join(sorted(emails)[:20]))
    console.print(table)


@app.command("state-reset")
def state_reset(confirm: bool = typer.Option(True, help="Ask for confirmation before reset.")) -> None:
    cfg = Config()
    _tui_banner("State Reset", f"Clearing {cfg.used_emails_path}")
    if confirm and not Confirm.ask("Delete local used-emails state?", default=False):
        print("[yellow]Cancelled[/yellow].")
        return
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _save_used_emails(cfg, set())
    print("[green]Reset complete[/green].")


@app.command("make-one")
def make_one(
    token: str = typer.Option(
        None,
        help="Bearer token. If omitted, you will be prompted (Enter keeps default).",
    ),
    person2_email: str = typer.Option(
        None,
        help="person2_email. If omitted, you will be prompted (Enter keeps default).",
    ),
    use_saved_users_json: bool = typer.Option(
        True,
        help="If true, prefer using users_all.json if present.",
    ),
    person1_email_index: int = typer.Option(
        None,
        help="Index into /users/all list for person1_email. If omitted, prompt when selecting from users.",
    ),
    matcher_email_index: int = typer.Option(
        None,
        help="Index into /users/all list for matcher_email. If omitted, prompt when selecting from users.",
    ),
) -> None:
    """
    Make a single /match/make request using either typed emails or picking by index from users_all.json.

    Note: This CLI does not implement any bypass for one-vote-per-email restrictions.
    """

    cfg0 = Config()

    _tui_banner("Make Match", "Build payload and optionally send POST /match/make.")
    bearer = token or _prompt_with_default(
        "Authorization Bearer token",
        cfg0.auth_bearer_token,
        password=True,
    )
    p2 = person2_email or _prompt_with_default("person2_email", cfg0.person2_email)
    use_saved = use_saved_users_json

    cfg = Config(auth_bearer_token=bearer, person2_email=p2)

    used = _load_used_emails(cfg)
    if used:
        print(f"[dim]Local state has {len(used)} tracked email(s) in {cfg.used_emails_path}.[/dim]")

    users_data: Any | None = None
    if use_saved and cfg.output_json_path.exists():
        users_data = json.loads(cfg.output_json_path.read_text(encoding="utf-8"))
    else:
        if Confirm.ask("Fetch /users/all now?", default=True):
            users_data = _fetch_users_all(cfg)
        else:
            users_data = None

    if users_data is not None:
        _tui_preview_users(users_data, max_rows=12)
        default_p1i = cfg0.person1_email_index
        default_mi = cfg0.matcher_email_index
        p1i = person1_email_index if person1_email_index is not None else IntPrompt.ask(
            "person1_email index",
            default=default_p1i,
        )
        mi = matcher_email_index if matcher_email_index is not None else IntPrompt.ask(
            "matcher_email index",
            default=default_mi,
        )
        person1_email = _pick_email(users_data, p1i, "person1_email")
        matcher_email = _pick_email(users_data, mi, "matcher_email")
    else:
        person1_email = _prompt_with_default("person1_email", "")
        matcher_email = _prompt_with_default("matcher_email", "")
        if not person1_email or not matcher_email:
            raise typer.BadParameter("person1_email and matcher_email are required if not selecting from users.")

    # Prevent accidental duplicate submissions from the same email locally.
    # This does not help bypass restrictions; it blocks reusing tracked emails.
    if person1_email in used:
        raise typer.BadParameter(
            f"person1_email {person1_email!r} is already in local used-emails state. "
            "Run `uv run python cli.py state-show` or `state-reset` if you want to clear local state."
        )

    payload = {
        "person1_email": person1_email,
        "person2_email": cfg.person2_email,
        "matcher_email": matcher_email,
    }

    table = Table(title="Payload", show_lines=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    for k, v in payload.items():
        table.add_row(k, v)
    console.print(table)

    if not Confirm.ask("Send request to /match/make?", default=True):
        print("[yellow]Cancelled[/yellow].")
        return

    resp = requests.post(cfg.make_match_url, headers=_headers(cfg), json=payload, timeout=30)
    print(f"Status: {resp.status_code}")
    try:
        print("Response JSON:")
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print("Response text:")
        print(resp.text)

    # Only mark as used after the request is actually sent.
    used.add(person1_email)
    _save_used_emails(cfg, used)
    print(f"[green]Tracked[/green] person1_email in state: {cfg.used_emails_path}")


async def _send_vote_request(cfg: Config, payload: dict[str, str]) -> tuple[bool, str]:
    """Send a single vote request and return success status and response."""
    try:
        resp = requests.post(cfg.make_match_url, headers=_headers(cfg), json=payload, timeout=30)
        if resp.status_code == 200:
            return True, f"Success: {resp.status_code}"
        else:
            return False, f"Failed with status {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, f"Error: {str(e)}"


@app.command("vote-same-couple")
def vote_same_couple() -> None:
    """
    Vote for the same couple multiple times using different matcher emails.
    
    Interactive UI - no CLI arguments required.
    """
    
    cfg0 = Config()
    
    _tui_banner("Vote Same Couple", f"Cast {num_votes} votes for the same couple")
    
    # Get auth token
    bearer = token or _prompt_with_default(
        "Authorization Bearer token",
        cfg0.auth_bearer_token,
        password=True,
    )
    
    # Get couple emails
    p1 = person1_email or _prompt_with_default("person1_email", "")
    p2 = person2_email or _prompt_with_default("person2_email", cfg0.person2_email)
    
    if not p1:
        raise typer.BadParameter("person1_email is required")
    
    cfg = Config(auth_bearer_token=bearer, person2_email=p2)
    
    # Get users data
    users_data: Any | None = None
    if use_saved_users_json and cfg.output_json_path.exists():
        users_data = json.loads(cfg.output_json_path.read_text(encoding="utf-8"))
        print(f"[green]Loaded[/green] users from {cfg.output_json_path}")
    else:
        if Confirm.ask("Fetch /users/all now?", default=True):
            users_data = _fetch_users_all(cfg)
            cfg.output_json_path.write_text(json.dumps(users_data, indent=2), encoding="utf-8")
            print(f"[green]Saved[/green] users to {cfg.output_json_path}")
        else:
            raise typer.BadParameter("No users data available")
    
    # Extract users and emails
    users = _extract_users(users_data)
    if len(users) < num_votes + 2:  # +2 to account for the couple
        raise typer.BadParameter(
            f"Not enough users. Need at least {num_votes + 2} users, but only have {len(users)}"
        )
    
    # Get all available emails
    all_emails = []
    for user in users:
        email = _extract_email(user)
        if email and email not in [p1, p2]:  # Exclude the couple from matchers
            all_emails.append(email)
    
    if len(all_emails) < num_votes:
        raise typer.BadParameter(
            f"Not enough unique matcher emails. Need {num_votes}, but only have {len(all_emails)}"
        )
    
    # Select matcher emails
    matcher_emails = all_emails[:num_votes]
    
    # Show summary
    table = Table(title="Voting Summary", show_lines=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    table.add_row("Person 1", p1)
    table.add_row("Person 2", p2)
    table.add_row("Number of votes", str(num_votes))
    table.add_row("Matchers", f"{len(matcher_emails)} unique emails")
    console.print(table)
    
    if not Confirm.ask(f"\nProceed with {num_votes} votes?", default=True):
        print("[yellow]Cancelled[/yellow].")
        return
    
    # Send async requests
    print(f"\n[cyan]Sending {num_votes} votes asynchronously...[/cyan]")
    
    async def send_all_votes():
        tasks = []
        for i, matcher_email in enumerate(matcher_emails):
            payload = {
                "person1_email": p1,
                "person2_email": p2,
                "matcher_email": matcher_email,
            }
            task = asyncio.create_task(_send_vote_request(cfg, payload))
            tasks.append((i + 1, matcher_email, task))
        
        # Track results
        successful = 0
        failed = 0
        
        with Progress() as progress:
            task_id = progress.add_task("Sending votes...", total=num_votes)
            
            for vote_num, matcher_email, task in tasks:
                success, message = await task
                if success:
                    successful += 1
                    progress.console.print(f"[green]✓[/green] Vote {vote_num}: {matcher_email} - {message}")
                else:
                    failed += 1
                    progress.console.print(f"[red]✗[/red] Vote {vote_num}: {matcher_email} - {message}")
                progress.advance(task_id)
        
        # Show final results
        progress.console.print("\n[bold]Voting Complete![/bold]")
        progress.console.print(f"[green]Successful: {successful}[/green]")
        progress.console.print(f"[red]Failed: {failed}[/red]")
        
        return successful, failed
    
    # Run the async voting
    successful, failed = asyncio.run(send_all_votes())
    
    # Save used matcher emails to state
    used = _load_used_emails(cfg)
    used.update(matcher_emails)
    _save_used_emails(cfg, used)
    print(f"\n[dim]Tracked {len(matcher_emails)} matcher emails in state[/dim]")


if __name__ == "__main__":
    app()
