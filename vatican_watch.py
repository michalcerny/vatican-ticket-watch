#!/usr/bin/env python3
"""Vatican Ticket Watch: get pinged the moment sold-out Vatican Museums tickets free up.

Unofficial tool. Polls the JSON API behind tickets.museivaticani.va (and, optionally, the
official same-day availability page) and alerts you through ntfy push notifications,
iMessage, macOS notifications, a spoken alarm or any shell command.

Standard library only, Python 3.9+. See README.md for setup.
"""
from __future__ import annotations

import argparse
import html
import http.cookiejar
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

__version__ = "1.0.0"

BOOKING = "https://tickets.museivaticani.va"
SAME_DAY_PAGE = "https://disponibilita.museivaticani.va/?_method=post&hl=en&pax={pax}"
USER_AGENT = f"vatican-ticket-watch/{__version__} (+https://github.com/michalcerny/vatican-ticket-watch)"
ROME = ZoneInfo("Europe/Rome")

# Ticket-level states in which the site enables its "Book" button. The site's own JS blocks
# SOLD_OUT and NOT_ALLOWED tickets even when single time slots still say AVAILABLE.
BOOKABLE = {"AVAILABLE", "LOW_AVAILABILITY"}

# Tickets that get you into the Vatican Museums and so the Sistine Chapel. The search also
# returns other sites (Castel Gandolfo, St Mary Major, hidden sections...), see --list.
DEFAULT_TICKETS = [
    "Vatican Museums - Admission Ticket",
    "Vatican Museums - Guided Tours for Individuals Museums",
    "Vatican Museums - Guided Tours for Individuals Gardens and Museums",
    "Guided Tours for Individuals - Art and Faith",
    "Vatican Museums - Vatican City Tours - Open Bus Gardens",
]

# Tags used by links on museivaticani.va; in a /home/fromtag/ URL they move that ticket to the
# top of the list.
TAGS = {
    "Vatican Museums - Admission Ticket": "MV-Biglietti",
    "Vatican Museums - Guided Tours for Individuals Museums": "VG-Musei",
    "Vatican Museums - Vatican City Tours - Open Bus Gardens": "VaticanCityTour",
}

MIN_INTERVAL = 10   # seconds; be nice to the site
PAGE_SIZE = 10      # search results per page (the site's nrResultsPerPage)
MAX_PAGES = 10


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


# --- dates ------------------------------------------------------------------------------

def parse_date(text: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"invalid date {text!r}, use YYYY-MM-DD")


def api_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def rome_today() -> date:
    return datetime.now(ROME).date()


def rome_midnight_ms(day: date) -> int:
    """The booking site encodes dates in URLs as midnight in Rome, in epoch milliseconds."""
    return int(datetime(day.year, day.month, day.day, tzinfo=ROME).timestamp() * 1000)


def booking_link(day: date, visitors: int, name: str, area: int = 1, who: int = 1) -> str:
    """Link straight to the ticket list for this date and party size. No URL preselects a time."""
    ms = rome_midnight_ms(day)
    tag = TAGS.get(name)
    if tag:
        return f"{BOOKING}/home/fromtag/{visitors}/{ms}/{tag}/{area}?lang=en"
    return f"{BOOKING}/home/visit/{visitors}/{ms}/{area}/{who}?lang=en"


# --- booking site API -------------------------------------------------------------------

class Api:
    """One browsing session.

    The API hands out ticket ids (visitTypeId) per session, so an id copied from your
    browser's DevTools fails with HTTP 500 anywhere else. Every check starts a fresh session
    and finds tickets by name.
    """

    def __init__(self, timeout: int = 30):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.opener.addheaders = [("User-Agent", USER_AGENT), ("Accept", "application/json, text/plain, */*")]
        self.timeout = timeout

    def get(self, path: str, **params) -> dict:
        url = f"{BOOKING}/api{path}?{urllib.parse.urlencode(params, safe='/')}"
        with self.opener.open(url, timeout=self.timeout) as r:
            return json.load(r)

    def search(self, day: date, visitors: int, area: int, who: int) -> list[dict]:
        visits: dict[str, dict] = {}
        for page in range(MAX_PAGES):
            batch = self.get("/search/result", lang="en", visitorNum=visitors, visitDate=api_date(day),
                             area=area, who=who, page=page).get("visits") or []
            for v in batch:
                visits.setdefault(v.get("name", ""), v)
            if len(batch) < PAGE_SIZE:
                break
        return list(visits.values())

    def free_times(self, visit_id, day: date, visitors: int) -> list[str]:
        slots = self.get("/visit/timeavail", lang="en", visitLang="", visitTypeId=visit_id,
                         visitorNum=visitors, visitDate=api_date(day))["timetable"]
        return [s["time"] for s in slots if s.get("availability") in BOOKABLE]


@dataclass
class Status:
    key: str            # stable id used to de-duplicate alerts
    label: str
    availability: str
    times: list
    url: str
    hint: str = "Open the link, press Book on this ticket, pick a time."

    def summary(self) -> str:
        name = self.label.replace("Vatican Museums - ", "")
        return f"{name}={self.availability}" + (f" {','.join(self.times)}" if self.times else "")


def matches(name: str, patterns: list[str]) -> bool:
    low = name.lower()
    return any(p == "*" or p.lower() in low for p in patterns)


def check_booking(day: date, visitors: int, patterns: list[str], area: int, who: int) -> list[Status]:
    api = Api()
    out = []
    for visit in api.search(day, visitors, area, who):
        name = visit.get("name", "")
        if not matches(name, patterns):
            continue
        availability = visit.get("availability") or "?"
        # Time slots only matter when the ticket itself is bookable; saves requests, too.
        times = api.free_times(visit["id"], day, visitors) if availability in BOOKABLE else []
        out.append(Status(f"{day}|{name}", name, availability, times,
                          booking_link(day, visitors, name, area, who)))
    return out


# --- same-day page ----------------------------------------------------------------------

def parse_same_day(page: str) -> tuple[str, list[str], str | None]:
    """Return (state, times, buy_url); state is 'available', 'none' or 'unknown'."""
    card = re.search(r'class="card (text-bg-[\w-]+)', page)
    card = card.group(1) if card else None
    body = page.split('class="card-body">', 1)[-1].split("Last update", 1)[0]
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
    times = sorted(set(re.findall(r"\b\d{1,2}[:.]\d{2}\b", text)))
    buy = re.search(r'href="(https://tickets\.museivaticani\.va/[^"]+)"', page)
    if card == "text-bg-danger" and "No time is available" in text:
        state = "none"
    elif times:
        state = "available"
    else:
        state = "unknown"
    return state, times, buy.group(1) if buy else None


def check_same_day(day: date, visitors: int) -> Status:
    url = SAME_DAY_PAGE.format(pax=visitors)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode("utf-8", "replace")
    state, times, buy = parse_same_day(page)
    if state == "unknown":
        raise RuntimeError("same-day page layout changed, cannot read it")
    return Status(f"{day}|same-day", "Same-day tickets", "AVAILABLE" if times else "SOLD_OUT",
                  times, buy or url, hint="Open the link and pick a time.")


# --- alerts -----------------------------------------------------------------------------

def osascript(lines: list[str], *argv: str) -> None:
    """Run AppleScript, passing text as arguments so nothing needs escaping."""
    script = ["on run argv", *lines, "end run"]
    cmd = ["osascript", *[x for line in script for x in ("-e", line)], *argv]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())


class Notifier:
    def __init__(self, args: argparse.Namespace):
        self.args = args

    @property
    def configured(self) -> bool:
        a = self.args
        return bool(a.ntfy or a.imessage or a.notify or a.say is not None or a.open or a.exec)

    def send(self, title: str, message: str, url: str, urgent: bool = True) -> None:
        a = self.args
        log(f"ALERT {title} | {message.replace(chr(10), ' | ')} | {url}")
        # Phone channels first: openings often last about a minute.
        channels = []
        if a.ntfy:
            channels.append(("ntfy", lambda: self.ntfy(title, message, url, urgent)))
        for to in a.imessage or []:
            channels.append((f"iMessage {to}", lambda to=to: self.imessage(to, f"{title}\n{message}\n{url}")))
        if a.notify:
            channels.append(("notification", lambda: osascript(
                ['display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"'],
                title, message)))
        if a.exec:
            channels.append(("exec", lambda: self.run_command(title, message, url)))
        if urgent and a.open:
            channels.append(("open", lambda: webbrowser.open(url)))
        if urgent and a.say is not None:
            voice = ["-v", a.say] if a.say else []
            channels.append(("say", lambda: subprocess.run(["say", *voice, title], check=True, timeout=60)))
        for name, send in channels:
            try:
                send()
            except Exception as e:  # one broken channel must not stop the others
                log(f"{name} failed: {e}")

    def ntfy(self, title: str, message: str, url: str, urgent: bool) -> None:
        body = json.dumps({"topic": self.args.ntfy, "title": title, "message": message,
                           "priority": 5 if urgent else 3, "tags": ["ticket"], "click": url}).encode()
        req = urllib.request.Request(self.args.ntfy_server.rstrip("/") + "/", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        urllib.request.urlopen(req, timeout=15).close()

    @staticmethod
    def imessage(to: str, text: str) -> None:
        osascript(['tell application "Messages"',
                   'send (item 1 of argv) to participant (item 2 of argv) of (1st account whose service type = iMessage)',
                   'end tell'], text, to)

    def run_command(self, title: str, message: str, url: str) -> None:
        env = {**os.environ, "VTW_TITLE": title, "VTW_MESSAGE": message, "VTW_URL": url}
        subprocess.run(self.args.exec, shell=True, env=env, check=True, timeout=60)


# --- state ------------------------------------------------------------------------------

def default_state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "vatican-ticket-watch" / "state.json"


class State:
    def __init__(self, path: Path):
        self.path = path
        data = json.loads(path.read_text()) if path.exists() else {}
        self.alerted: dict[str, list[str]] = data.get("alerted", {})
        self.failures: int = data.get("failures", 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"alerted": self.alerted, "failures": self.failures}, indent=2))
        tmp.replace(self.path)


def needs_alert(alerted: dict[str, list[str]], key: str, times: list[str]) -> bool:
    """Alert when a time shows up that we have not alerted about while it stayed free.

    Times that disappear are forgotten, so the same time freeing up again later alerts again.
    """
    previous = set(alerted.get(key, []))
    if times:
        alerted[key] = sorted(times)
    else:
        alerted.pop(key, None)
    return bool(set(times) - previous)


# --- main loop --------------------------------------------------------------------------

def run_once(args: argparse.Namespace, state: State, notifier: Notifier) -> bool:
    """One check of every upcoming date. Returns False once all dates have passed."""
    today = rome_today()
    days = [d for d in args.dates if d >= today]
    if not days:
        return False

    errors = []
    for day in days:
        statuses = []
        try:
            statuses += check_booking(day, args.visitors, args.tickets, args.area, args.who)
            if not statuses:
                log(f"{api_date(day)}: no ticket matches {args.tickets} on this date (try --list)")
        except Exception as e:
            errors.append(f"{api_date(day)}: {e}")
        if args.same_day and day == today:
            try:
                statuses.append(check_same_day(day, args.visitors))
            except Exception as e:
                errors.append(f"same-day page: {e}")
        if statuses:
            log(f"{api_date(day)}: " + " | ".join(s.summary() for s in statuses))
        for s in statuses:
            if needs_alert(state.alerted, s.key, s.times):
                notifier.send(f"Vatican tickets free on {api_date(day)}!",
                              f"{s.label}\n{args.visitors} people, times: {', '.join(s.times)}\n{s.hint}",
                              s.url)

    if errors:
        state.failures += 1
        log("error: " + "; ".join(errors))
        if state.failures == args.fail_alert:
            notifier.send("Vatican ticket watch is failing",
                          f"{state.failures} failed checks in a row: {errors[0]}", BOOKING, urgent=False)
    else:
        state.failures = 0
    state.save()
    return True


def list_tickets(day: date, visitors: int, area: int, who: int) -> None:
    visits = Api().search(day, visitors, area, who)
    if not visits:
        print(f"No tickets offered on {api_date(day)} (closed day?)")
    for v in visits:
        print(f"{v.get('availability', '?'):<17} {v.get('name')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="vatican_watch.py",
        description="Watch sold-out Vatican Museums tickets and get alerted the moment they free up.",
        epilog="Example: vatican_watch.py --date 2026-10-17 --visitors 4 --ntfy my-secret-topic")
    p.add_argument("--date", dest="dates", action="append", type=parse_date, default=[], metavar="DATE",
                   help="visit date, YYYY-MM-DD (repeat for several dates)")
    p.add_argument("--visitors", type=int, default=2, metavar="N", help="party size (default: 2)")
    p.add_argument("--ticket", dest="tickets", action="append", metavar="TEXT",
                   help="ticket name or part of it, case-insensitive; repeat for several; '*' = every ticket "
                        "on the site (default: the tickets that include the Vatican Museums)")
    p.add_argument("--same-day", action="store_true",
                   help="on the visit day, also watch the official same-day availability page")
    p.add_argument("--interval", type=float, default=60, metavar="SECONDS",
                   help=f"seconds between checks (default: 60, minimum: {MIN_INTERVAL})")
    p.add_argument("--once", action="store_true", help="check once and exit (for cron)")
    p.add_argument("--list", action="store_true", help="list tickets offered on the first --date and exit")
    p.add_argument("--area", type=int, default=1, help="site area (default: 1 = Vatican Museums)")
    p.add_argument("--who", type=int, default=1, help="visitor category (default: 1 = individuals)")
    p.add_argument("--state", type=Path, default=default_state_path(), metavar="PATH",
                   help="file that remembers sent alerts (default: %(default)s)")
    p.add_argument("--fail-alert", type=int, default=5, metavar="N",
                   help="send a warning after N failed checks in a row (default: 5)")

    a = p.add_argument_group("alerts (combine any)")
    a.add_argument("--ntfy", metavar="TOPIC", help="push to the ntfy app on your phone (https://ntfy.sh)")
    a.add_argument("--ntfy-server", default="https://ntfy.sh", metavar="URL", help="self-hosted ntfy server")
    a.add_argument("--imessage", action="append", metavar="RECIPIENT",
                   help="phone number or Apple ID to iMessage (macOS; repeat for several people)")
    a.add_argument("--notify", action="store_true", help="macOS notification with sound")
    a.add_argument("--say", nargs="?", const="", metavar="VOICE", help="speak the alert out loud (macOS)")
    a.add_argument("--open", action="store_true", help="open the booking link in your browser")
    a.add_argument("--exec", metavar="CMD",
                   help="run a shell command; gets $VTW_TITLE, $VTW_MESSAGE and $VTW_URL")
    a.add_argument("--test-alert", action="store_true", help="send a test alert and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = p.parse_args(argv)
    args.tickets = args.tickets or DEFAULT_TICKETS
    if not args.dates and not args.test_alert:
        p.error("--date is required")
    if args.interval < MIN_INTERVAL:
        print(f"--interval raised to the minimum of {MIN_INTERVAL} s", file=sys.stderr)
        args.interval = MIN_INTERVAL
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    notifier = Notifier(args)
    if not notifier.configured:
        print("No alert channel set (e.g. --ntfy TOPIC); alerts will only be printed.", file=sys.stderr)

    if args.test_alert:
        notifier.send("Vatican ticket watch: test", "If you can read this, alerts work.", BOOKING)
        return 0
    if args.list:
        list_tickets(args.dates[0], args.visitors, args.area, args.who)
        return 0

    state = State(args.state)
    tickets = "Vatican Museums tickets" if args.tickets == DEFAULT_TICKETS else ", ".join(args.tickets)
    log(f"watching {', '.join(api_date(d) for d in args.dates)} for {args.visitors} people, "
        f"{tickets}" + (" + same-day page" if args.same_day else "")
        + ("" if args.once else f", every {args.interval:g} s"))
    try:
        while run_once(args, state, notifier):
            if args.once:
                return 0
            time.sleep(args.interval * random.uniform(0.9, 1.1))
    except KeyboardInterrupt:
        return 130
    log("all dates have passed, stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
