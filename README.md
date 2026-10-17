# Vatican Ticket Watch

**Forgot to book the Vatican Museums and now it's sold out? Run this watcher. It keeps checking the official site and pings your phone the moment tickets free up.**

[Italiano](#italiano) · [Deutsch](#deutsch) · [Français](#français) · [Español](#español) · [Português](#português) · [Nederlands](#nederlands) · [Polski](#polski) · [Čeština](#čeština)

Tickets for the Vatican Museums and the Sistine Chapel sell out weeks ahead. Cancellations and released slots do show up, often at odd hours, and most are gone within a minute or two. Refreshing the site by hand doesn't work. This script refreshes it for you and gets the alert to your phone with a direct link.

- Watches the official booking site [tickets.museivaticani.va](https://tickets.museivaticani.va) for your dates and party size.
- By default it watches every ticket that gets you into the Museums and the Sistine Chapel: plain admission, guided tours and the open bus tour. You can pick others.
- On the day of your visit it can also watch the official [same-day availability page](https://disponibilita.museivaticani.va).
- It alerts only when the site really lets you book, with no false alarms from leftover time slots on sold-out tickets.
- Each alert links straight to your date and party size, so you skip the calendar.
- Alerts can go to a push notification on your phone (ntfy), iMessage, a macOS notification, a spoken alarm, your browser or any shell command.
- One file, Python standard library only. No accounts, no API keys, no `pip install`.

It does **not** buy tickets for you. Checkout on the official site has a captcha, as it should: you book, the watcher just makes sure you hear about it first.

## Quick start

You need Python 3.9 or newer. On macOS, `python3` comes with the Xcode command line tools or Homebrew.

```bash
git clone https://github.com/michalcerny/vatican-ticket-watch.git
cd vatican-ticket-watch

# 1. Install the ntfy app (iOS / Android) and subscribe to a long, random topic name.
# 2. Check that alerts reach your phone:
python3 vatican_watch.py --test-alert --ntfy vatican-k7f2q9xw

# 3. Start watching:
python3 vatican_watch.py --date 2026-10-17 --visitors 4 --same-day --ntfy vatican-k7f2q9xw
```

```
2026-10-17 07:18:02 watching 17/10/2026 for 4 people, Vatican Museums tickets + same-day page, every 60 s
2026-10-17 07:18:03 17/10/2026: Admission Ticket=SOLD_OUT | Guided Tours for Individuals Museums=SOLD_OUT | ... | Same-day tickets=SOLD_OUT
2026-10-17 07:19:04 17/10/2026: Admission Ticket=AVAILABLE 13:30 | Guided Tours for Individuals Museums=SOLD_OUT | ...
2026-10-17 07:19:04 ALERT Vatican tickets free on 17/10/2026! | Vatican Museums - Admission Ticket | 4 people, times: 13:30 | ...
```

The watcher keeps running until you stop it with Ctrl+C or until all your dates have passed. On a Mac, prefix the command with `caffeinate -i` so the computer doesn't fall asleep.

## Options

| Option | What it does |
|---|---|
| `--date 2026-10-17` | Visit date. Repeat it to watch several dates. `17/10/2026` also works. |
| `--visitors 4` | Party size (default 2). |
| `--ticket TEXT` | A ticket name or part of one, case-insensitive. Repeat it to watch several. `'*'` watches every ticket on the site. |
| `--same-day` | On the visit day, also watch the same-day availability page. |
| `--interval 60` | Seconds between checks (default 60, minimum 10). |
| `--once` | Check once and exit, for cron. |
| `--list` | Show every ticket offered on the first `--date` and exit. |
| `--state PATH` | Where sent alerts are remembered (default `~/.local/state/vatican-ticket-watch/state.json`). |
| `--fail-alert 5` | Send a warning after this many failed checks in a row. |

### Which tickets get you into the Sistine Chapel?

When you leave out `--ticket`, the watcher watches these five. Each includes entry to the Vatican Museums:

- **Vatican Museums - Admission Ticket**: the classic ticket, covering the whole museum route that ends in the Sistine Chapel.
- **Guided Tours for Individuals Museums** and **... Gardens and Museums**: guided tours. Check the route on the site.
- **Guided Tours for Individuals - Art and Faith**: a guided tour through the Pio Christian Museum, Pinacoteca, Upper Galleries and the Sistine Chapel.
- **Vatican City Tours - Open Bus Gardens**: a bus ride through the Vatican Gardens plus museum admission.

The search also returns tickets for other papal sites, such as the Castel Gandolfo palace, basilica areas, hidden sections and panoramic terraces. None of these include the Sistine Chapel. Run `--list` to see everything on offer for your date:

```bash
python3 vatican_watch.py --list --date 2026-10-20 --visitors 4
```

## Alerts

Combine as many channels as you like. Phone channels always go first.

| Option | Channel | Works on |
|---|---|---|
| `--ntfy TOPIC` | Push notification through the free [ntfy](https://ntfy.sh) app. Sent at max priority; tapping it opens the booking link. | any OS → iOS / Android / desktop |
| `--ntfy-server URL` | Your own ntfy server instead of ntfy.sh | |
| `--imessage +15551234567` | iMessage with the link. Repeat it for everyone in your party. | macOS with Messages signed in |
| `--notify` | Notification with a sound | macOS |
| `--say [VOICE]` | Reads the alert out loud, e.g. `--say Samantha` | macOS |
| `--open` | Opens the booking link in your browser | any OS |
| `--exec CMD` | Runs a command with `$VTW_TITLE`, `$VTW_MESSAGE` and `$VTW_URL` set | any OS |

`--exec` lets you plug in anything else:

```bash
--exec 'notify-send "$VTW_TITLE" "$VTW_MESSAGE"'                       # Linux desktop
--exec 'curl -s "https://api.telegram.org/bot$TOKEN/sendMessage" -d chat_id=$CHAT -d text="$VTW_TITLE $VTW_URL"'
```

Notes:

- **ntfy topics are public.** Anyone who guesses the name can read your alerts, so pick something long and random.
- **iMessage** goes through the Messages app on your Mac. The first time, macOS asks whether Terminal (or Python) may control Messages. If it runs from launchd and nothing arrives, check System Settings → Privacy & Security → Automation.
- You get one alert per opening. If new times appear while the ticket is still free, you get another. A time that disappears and later frees up again also triggers a new alert.

## Run it in the background

- **Terminal or tmux**: just leave it running. On a Mac, `caffeinate -i python3 vatican_watch.py ...` keeps it awake.
- **macOS launchd**: [`contrib/launchd/local.vatican-ticket-watch.plist`](contrib/launchd/local.vatican-ticket-watch.plist) starts it at login and survives restarts.
- **Linux systemd**: [`contrib/systemd/vatican-ticket-watch.service`](contrib/systemd/vatican-ticket-watch.service) is a user service.
- **cron**: `* * * * * python3 /path/vatican_watch.py --once --date ... --ntfy ...`

In every setup, the watcher exits cleanly once your last date has passed.

## Tips from real use

These come from watching a sold-out Saturday in October for a family of four:

- **Openings happen, but they are short.** On the visit day alone the watcher caught five, all between 3:00 and 7:30 in the morning. Daytime ones were gone within about a minute; night-time ones lasted up to about 15 minutes.
- **The same-day page is worth watching on the day.** In our runs, a slot there showed up about an hour before its start time and stayed until then.
- **Speed is everything, and the slow part is the checkout form.** Have ready the names of all visitors (every name is required), the lead visitor's birth date, phone and email, and your card.
- **Send alerts to everyone in your party** (`--imessage` can be repeated, and several phones can subscribe to the same ntfy topic). Whoever is free books.
- **Smaller groups get in sooner.** Two cancelled tickets never show up for a party of four. Consider running a second watcher with `--visitors 2` and booking in two orders.
- **Watch several ticket types.** Guided tours freed up more often than plain admission did.

## How it works

The booking site is an Angular app on top of a JSON API. Each check:

1. **Searches tickets.** `GET /api/search/result?visitorNum=4&visitDate=17/10/2026&area=1&who=1&page=0` returns tickets with a ticket-level `availability` of `AVAILABLE`, `LOW_AVAILABILITY`, `SOLD_OUT` or `NOT_ALLOWED`.
2. **Fetches time slots** for bookable tickets only: `GET /api/visit/timeavail?visitTypeId=...&visitorNum=4&visitDate=...`. When nothing is free, a check costs one request.

Things that are easy to get wrong:

- **Ticket ids are tied to a session.** The `visitTypeId` you see in your browser's DevTools only works inside that browser session; anywhere else it returns HTTP 500. The watcher starts a fresh session on every check and finds tickets by name.
- **Ticket-level availability beats slot-level availability.** The site disables the Book button for `SOLD_OUT` and `NOT_ALLOWED` tickets even when single time slots still say `AVAILABLE`. Sold-out tickets also show phantom `LOW_AVAILABILITY` slots with `residual: 0`. Alerting on slots alone gives false alarms that you can't book.
- **Deep links.** `/home/visit/{visitors}/{midnight in Rome, epoch ms}/{area}/{who}` opens the ticket list for a date. `/home/fromtag/{visitors}/{ms}/{tag}/{area}` also moves one ticket to the top. No URL preselects a time.
- **The same-day page** is plain server-rendered HTML. It shows a red card with "No time is available" when nothing is free, and a green card with times and a Buy link when something is. It updates every couple of minutes.

## Be nice

- This is an unofficial tool and is not affiliated with the Vatican Museums. The API is undocumented and may change at any time; if it breaks, please open an issue.
- It is meant for booking your own visit. Don't use it to hoard or resell tickets.
- The default check interval is 60 s and the minimum is 10 s. Checks identify themselves with the `vatican-ticket-watch` user agent.

## Other languages

### Italiano

Hai dimenticato di prenotare i Musei Vaticani e ora è tutto esaurito? Avvia questo script: controlla di continuo il sito ufficiale e ti avvisa (notifica sul telefono, iMessage, allarme) appena si libera un biglietto, con il link diretto per prenotare. Le istruzioni complete sono in inglese qui sopra.

### Deutsch

Vergessen, die Vatikanischen Museen zu buchen, und jetzt ist alles ausverkauft? Starte diesen Watcher: Er prüft die offizielle Ticketseite rund um die Uhr und benachrichtigt dich (Push aufs Handy, iMessage, Alarm), sobald Tickets frei werden – mit direktem Buchungslink. Die vollständige Anleitung steht oben auf Englisch.

### Français

Vous avez oublié de réserver les Musées du Vatican et tout est complet ? Lancez ce script : il surveille le site officiel en continu et vous prévient (notification sur le téléphone, iMessage, alarme) dès qu'un billet se libère, avec un lien direct pour réserver. Le mode d'emploi complet est en anglais ci-dessus.

### Español

¿Olvidaste reservar los Museos Vaticanos y ya está todo agotado? Ejecuta este vigilante: revisa la web oficial sin parar y te avisa (notificación en el móvil, iMessage, alarma) en cuanto se libera una entrada, con el enlace directo para reservar. Las instrucciones completas están en inglés más arriba.

### Português

Esqueceu-se de reservar os Museus do Vaticano e agora está esgotado? Execute este vigia: verifica o site oficial sem parar e avisa-o (notificação no telemóvel, iMessage, alarme) assim que um bilhete fica livre, com o link direto para reservar. As instruções completas estão em inglês acima.

### Nederlands

Vergeten de Vaticaanse Musea te boeken en nu is alles uitverkocht? Start deze watcher: hij controleert de officiële ticketsite continu en waarschuwt je (pushmelding op je telefoon, iMessage, alarm) zodra er tickets vrijkomen, met een directe boekingslink. De volledige handleiding staat hierboven in het Engels.

### Polski

Zapomniałeś zarezerwować Muzea Watykańskie i wszystko jest wyprzedane? Uruchom ten skrypt: stale sprawdza oficjalną stronę i powiadamia cię (powiadomienie na telefon, iMessage, alarm), gdy tylko zwolni się bilet, z bezpośrednim linkiem do rezerwacji. Pełna instrukcja jest powyżej po angielsku.

### Čeština

Zapomněli jste si zarezervovat Vatikánská muzea a je vyprodáno? Pusťte si tenhle hlídač: nepřetržitě kontroluje oficiální web a jakmile se uvolní vstupenka, pošle vám upozornění (push na mobil, iMessage, alarm) s přímým odkazem na rezervaci. Kompletní návod je výše v angličtině.

## License

[MIT](LICENSE)
