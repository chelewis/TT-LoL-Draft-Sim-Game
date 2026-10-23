# Office Bug Hunt

A social-deduction browser game set in an office. The dev team walks between desks fixing tiny coding bugs before the release, while hidden spies take coworkers offline, push bad commits that reopen fixed tickets, and try to keep production down.

Single player against bots. No build step, no dependencies: open `index.html` in a browser (or serve the folder with any static server, e.g. `python3 -m http.server`).

## Rules

- **Developers** fix the tickets on their list (yellow desks). Each ticket is a very easy JavaScript task: predict the output, click the buggy line, fill in the blank, or edit a function until its tests pass. Devs win when every ticket in the sprint is fixed or every spy has been let go.
- **Spies** fake work, take devs offline when nobody is watching, push bad commits at desks (reopening a fixed ticket), and trigger a **prod outage**: two racks (Server Room and Reception's Network Closet) must be repaired before the timer runs out. Spies win when they equal the devs in number, or when prod stays down.
- Find a logged-off coworker and **Report** it, or ring the **Standup Bell** in the Conference Room (once per game), to call a standup. Read the chat, accuse, then vote someone out or skip.
- Taken offline or let go? You become a ghost: you walk through walls and can still fix tickets.

## Controls

`WASD`/arrows or click to move · `E` use · `R` report · `Q` takedown (spy) · `X` outage (spy) · `M` minimap · `Esc` close a ticket. On a tablet, tap to move and use the on-screen buttons. Fix tickets accept `Ctrl+Enter` to run tests.

## Code layout

| File | What it does |
| --- | --- |
| `js/map.js` | Office tile map, rooms, furniture, stations, line of sight, BFS pathfinding |
| `js/tasks.js` | The bug ticket bank (add new tickets here) and outage repair tasks |
| `js/ui.js` | Ticket modal, syntax highlighting, sandboxed test runner (Web Worker with a 1.5s timeout) |
| `js/game.js` | Game state, bot AI, standups and voting, rendering, input |

Append `?speed=4` to the URL to fast-forward the simulation when testing.
