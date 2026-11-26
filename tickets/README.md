# Tickets

A ticket states a requirement **before** the change. It is not a plan, a status list, or a claim
that the work is done. The archive and the receipts record what ran; a ticket with no row did not
happen, and a row with no ticket had no stated requirement.

## Format

Each ticket is `TICKET-NNNN-short-name.md` and carries:

- **Requirement** — the capability, with the owner's words where the requirement is theirs.
- **Acceptance** — the decidable observations that close it (`A1`, `A2`, …).
- **Evidence** — the receipts, commands, archive rows and witness captures that prove it.
- **State** — `open`, `blocked` or `closed`; only evidence may close it.
- **Supersession** — a dated line naming any earlier ticket it replaces.

A ticket is not closed by a compile, a receipt or a log line that does not meet its own acceptance.
A window claim needs a CUA capture: a JSON row that says the surface is fine is not a witness.

## The current set

| Ticket | Requirement |
|---|---|
| `TICKET-0001` | The call desk is a real-time line: a hang-up is detected, recorded as a hang-up, and the lane dials back once; the dial tone plays the number the call carried |
| `TICKET-0002` | The call desk's copy passes the family prose program itself, not a side invocation of its checker |
| `TICKET-0003` | Every tool added here ships a Popit surface and a probe that reads that surface over loopback |
| `TICKET-0004` | Any claim about what the desk shows is witnessed by a CUA driver capture of the window |
| `TICKET-0005` | The Debian lane stands on its own civilian record: C9 condition, care choice and a seven-field contract, spoken from the box |
