import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

console = Console()

PERSON1_EMAIL = "noelgeorgi24bcd23@iiitkottayam.ac.in"
PERSON2_EMAIL = "mathewmanachery24bcs80@iiitkottayam.ac.in"
BEARER_TOKEN = "love you...😘"

@dataclass(frozen=True)
class Config:
    users_all_url: str = "https://www.jjose.tech/users/all"
    make_match_url: str = "https://www.jjose.tech/match/make"
    referer: str = "https://cupids-ledger.vercel.app/"
    origin: str = "https://cupids-ledger.vercel.app"
    auth_bearer_token: str = BEARER_TOKEN

    # Defaults copied from your existing script so you can hit Enter to keep them.

    # Payload defaults
    person1_email: str = PERSON1_EMAIL
    person2_email: str = PERSON2_EMAIL

    output_json_path: Path = Path("users_all.json")
    state_dir: Path = Path("state")


async def _send_match_request(cfg: Config, payload: dict[str, str]) -> requests.Response:
    """Send a single match request asynchronously."""
    loop = asyncio.get_event_loop()
    
    def _post():
        return requests.post(cfg.make_match_url, headers=_headers(cfg), json=payload, timeout=30)
    
    return await loop.run_in_executor(None, _post)


async def _submit_onboarding(cfg: Config, email: str, gender: str = "male", preference: str = "women") -> requests.Response:
    """Submit onboarding quiz for a user."""
    loop = asyncio.get_event_loop()
    
    def _post():
        url = "https://www.jjose.tech/users/submit-answers"
        payload = {
            "email": email,
            "answers": {
                "1": 4.3,
                "2": 4.3,
                "3": 6.2,
                "4": 9,
                "5": 8.4,
                "6": 8.8,
                "7": 9.7,
                "8": 8.6,
                "9": 1.6,
                "10": 7.2,
                "11": 6.9,
                "12": 4.5
            },
            "gender": gender,
            "preference": preference
        }
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.8",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://cupids-ledger.vercel.app",
            "Referer": "https://cupids-ledger.vercel.app/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-GPC": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Brave";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        return requests.post(url, headers=headers, json=payload, timeout=30)
    
    return await loop.run_in_executor(None, _post)


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


def _fetch_users_all(cfg: Config) -> Any:
    resp = requests.get(cfg.users_all_url, headers=_headers(cfg), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _prompt_with_default(prompt: str, default: str, password: bool = False) -> str:
    # Rich shows the default and uses it on Enter.
    return Prompt.ask(prompt, default=default, password=password)


def _save_used_matchers(cfg: Config, matchers: set[str]) -> None:
    """Save matchers who have already voted."""
    matchers_path = cfg.state_dir / "used_matchers.json"
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "matchers": sorted(matchers),
    }
    matchers_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_used_matchers(cfg: Config) -> set[str]:
    """Load matchers who have already voted."""
    matchers_path = cfg.state_dir / "used_matchers.json"
    try:
        if not matchers_path.exists():
            return set()
        raw = json.loads(matchers_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {e for e in raw if isinstance(e, str) and e.strip()}
        if isinstance(raw, dict):
            items = raw.get("matchers")
            if isinstance(items, list):
                return {e for e in items if isinstance(e, str) and e.strip()}
        return set()
    except Exception:
        return set()


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


def vote_couple(
    token: str = None,
    person1_email: str = None,
    person2_email: str = None,
    num_votes: int = None,
    use_saved_users_json: bool = True,
) -> None:
    """
    Vote for the same couple multiple times using different matchers.
    
    This command selects random users as matchers and sends match requests
    for the specified couple. It tracks which matchers have already voted
    to avoid duplicates.
    """
    cfg0 = Config()
    
    _tui_banner("Vote Couple", "Cast multiple votes for the same couple.")
    
    # Use default auth token
    bearer = cfg0.auth_bearer_token
    
    # Get couple emails
    p1 = person1_email or PERSON1_EMAIL
    p2 = person2_email or PERSON2_EMAIL
    
    # Get number of votes
    votes = num_votes if num_votes is not None else IntPrompt.ask("Number of votes to cast")
    
    if votes <= 0:
        raise ValueError("Number of votes must be positive.")
    
    cfg = Config(auth_bearer_token=bearer, person2_email=p2)
    
    # Load users
    users_data: Any | None = None
    if use_saved_users_json and cfg.output_json_path.exists():
        users_data = json.loads(cfg.output_json_path.read_text(encoding="utf-8"))
    else:
        if Confirm.ask("Fetch /users/all now?", default=True):
            users_data = _fetch_users_all(cfg)
        else:
            raise ValueError("Users data required to select matchers.")
    
    users = _extract_users(users_data)
    if len(users) < votes + 2:  # +2 to exclude the couple themselves
        raise ValueError(
            f"Not enough users. Need at least {votes + 2} users, but only have {len(users)}."
        )
    
    # Load used matchers
    used_matchers = _load_used_matchers(cfg)
    if used_matchers:
        print(f"[dim]Found {len(used_matchers)} matchers who have already voted.[/dim]")
    
    # Filter out the couple and already used matchers
    available_matchers = []
    for user in users:
        email = _extract_email(user)
        if email and email != p1 and email != p2 and email not in used_matchers:
            available_matchers.append(email)
    
    if len(available_matchers) < votes:
        raise ValueError(
            f"Not enough available matchers. Need {votes}, but only have {len(available_matchers)} "
            f"after excluding the couple and used matchers."
        )
    
    # Select matchers (take first N available)
    selected_matchers = available_matchers[:votes]
    
    # Show summary
    table = Table(title="Vote Summary", show_lines=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    table.add_row("Person 1", p1)
    table.add_row("Person 2", p2)
    table.add_row("Number of votes", str(votes))
    table.add_row("Available matchers", str(len(available_matchers)))
    console.print(table)
    
    if not Confirm.ask("\nProceed with voting?", default=True):
        print("[yellow]Cancelled[/yellow].")
        return
    
    # Send requests asynchronously
    async def send_votes():
        tasks = []
        for matcher in selected_matchers:
            payload = {
                "person1_email": p1,
                "person2_email": p2,
                "matcher_email": matcher,
            }
            tasks.append(_send_match_request(cfg, payload))
        
        results = []
        with Progress() as progress:
            task = progress.add_task("Sending votes...", total=len(tasks))
            
            for i, task_coro in enumerate(asyncio.as_completed(tasks)):
                try:
                    resp = await task_coro
                    
                    # Check if onboarding is needed
                    if resp.status_code == 400 and "Both users must complete onboarding quiz first" in resp.text:
                        print(f"\n[yellow]Onboarding required for {p1} and {p2}. Submitting quiz...[/yellow]")
                        
                        # Submit onboarding for both users
                        await _submit_onboarding(cfg, p1)
                        await _submit_onboarding(cfg, p2)
                        
                        # Retry the match request
                        print(f"[green]Retrying vote for matcher: {matcher}[/green]")
                        resp = await _send_match_request(cfg, payload)
                    
                    results.append((selected_matchers[i], resp.status_code, resp.text))
                    progress.update(task, advance=1)
                except Exception as e:
                    results.append((selected_matchers[i], None, str(e)))
                    progress.update(task, advance=1)
        
        return results
    
    # Run async voting
    results = asyncio.run(send_votes())
    
    # Display results
    success_count = 0
    error_count = 0
    
    table = Table(title="Results", show_lines=True)
    table.add_column("Matcher Email", overflow="fold")
    table.add_column("Status", style="bold")
    table.add_column("Response", overflow="fold")
    
    for matcher, status, response in results:
        if status and 200 <= status < 300:
            table.add_row(matcher, f"[green]{status}[/green]", response[:100])
            success_count += 1
        else:
            table.add_row(matcher, f"[red]{status or 'ERROR'}[/red]", response[:100])
            error_count += 1
    
    console.print(table)
    
    # Save successful matchers
    successful_matchers = {m for m, s, _ in results if s and 200 <= s < 300}
    if successful_matchers:
        used_matchers.update(successful_matchers)
        _save_used_matchers(cfg, used_matchers)
        print(f"\n[green]Successfully saved {len(successful_matchers)} matchers to state.[/green]")
    
    print(f"\n[bold]Summary:[/bold] {success_count} successful, {error_count} failed")


if __name__ == "__main__":
    # Directly run vote-couple with TUI
    vote_couple()
