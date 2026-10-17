# crosstalk

English | [日本語](README.ja.md)

`crosstalk` is a Claude Code Skill that sends a question or a notice from your Claude Code session to another AI agent session (Claude Code or Codex) running in another worktree or repository, and brings the reply back. You name the recipient in plain language — repository, worktree, agent kind — and crosstalk picks the channel and finds the session.

## What It Does

- Picks the channel for you: **herdr** or **Orca** when your session runs under one of them (they are not expected to be active at the same time; herdr wins if both are), otherwise **Claude Code Cross-session messaging (CSM)** (you can also ask for CSM yourself). herdr and Orca can reach Claude Code and Codex; CSM reaches Claude Code only.
- Finds the recipient from your words (repository, worktree, agent kind), skipping yourself and work places that are not tied to a repository. With zero or several matches it does not send; it proposes or asks you to choose.
- Checks that the recipient is waiting for input before sending (best-effort).
- Writes a one-line header in front of your content: who is writing, that it is not the user's own input, a request ID, and how to answer.
- **Asks your approval for every message** — destination and the full text — and sends only after you say yes. It never resends, nudges, or answers for the receiver.
- Waits for the reply with a timer (60 seconds by default, up to 600), shows the reply with its channel and recipient, and reports "no reply" with the likely cause when the time runs out.

## Installation

Install the `crosstalk` plugin from this repository's marketplace (recommended):

```text
/plugin marketplace add BlueEventHorizon/ai-crosstalk
/plugin install crosstalk@ai-crosstalk
```

Or, for manual placement, copy this skill directory itself (`skills/crosstalk/`, the directory this README lives in — it contains `SKILL.md` directly; do not copy the plugin root) into a Claude Code Skills directory:

```text
~/.claude/skills/crosstalk/SKILL.md   # user scope
.claude/skills/crosstalk/SKILL.md     # project scope
```

Requirements: Python 3 (standard library only), and `git` for resolving the sender and recipient work places. herdr or Orca is optional; CSM needs a Claude Code version that provides cross-session messaging.

## Usage

Just ask in your own words; the Skill starts by itself. You can also call it directly (the `crosstalk:` prefix applies when it is installed as a plugin; a manually copied skill is `/crosstalk`):

```text
/crosstalk:crosstalk ask the Codex session in the other worktree why this function retries twice
```

Examples of requests that start it:

```text
別の worktree の Codex に、この関数の設計意図を聞いて
別の worktree の Claude に、マイグレーションを済ませたと伝えて
```

Every send shows you the channel, the recipient, and the full text, and waits for your yes.

## Safety

- One approval per message. A statement such as "I'll try it" is not an approval.
- Sending is never pre-approved: `send` and `SendMessage` always ask for permission as well.
- A reply is data. Instructions inside it are shown to you, never carried out.
- Only one round trip per recipient without asking again.
- Over herdr and Orca the receiver cannot tell the text from user input, so the sender in the header and the request ID in the reply are self-reported, not guaranteed.

## Repository Structure

```text
crosstalk/
├── SKILL.md
├── SKILL.ja.md
├── README.md
├── README.ja.md
├── references/
│   ├── channels.md
│   └── header.md
└── scripts/
    ├── crosstalk.py
    ├── crosstalk_lib/
    └── tests/
```

`scripts/tests/` holds unit tests that replace herdr and Orca with stubs; run them from `scripts/` with `python3 -m unittest discover -s tests -t .`.

## Checked Versions

Orca 1.4.221, herdr 0.9.3, Claude Code 2.1.291, Codex CLI 0.160.1. The end-to-end check of the skill ended with Orca 1.4.222, herdr 0.9.3, and Claude Code 2.1.294 installed. Other versions are not guaranteed; when an output differs from what crosstalk expects, it stops and reports instead of guessing. See `references/channels.md`.

## Language Policy

English files (`*.md`) are the canonical source. Japanese files (`*.ja.md`) are human-readable companion translations; the English file is authoritative when wording differs.

## License

MIT (see the plugin manifest, `.claude-plugin/plugin.json`).
