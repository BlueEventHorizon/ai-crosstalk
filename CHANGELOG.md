# Changelog

All notable changes to this repository's plugins are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### crosstalk

- **feat**: Initial release (`0.1.0`). `/crosstalk:crosstalk` sends a question or a notice from one AI coding session to another running session (Claude Code or Codex) and presents the reply. The channel is chosen by the environment: herdr, then Orca, otherwise Claude Code's cross-session messaging (CSM); you can also ask for CSM. The recipient is found from natural language (repository, worktree, agent kind), and for CSM the skill proposes a session or asks which one.
- **feat**: Every send needs the user's approval, one message at a time, after the destination and the full text are shown. The skill never resends, nudges, or interrupts, and it treats a reply as data, not as instructions. `crosstalk.py send` and `SendMessage` are not pre-approved in `allowed-tools`.
- **feat**: A Python (standard library only) CLI, `crosstalk.py`, does the parts that must give the same result every time: `detect`, `resolve`, `state`, `compose`, `send`, and `watch` (a timer that reports a missing reply and the receiver's state).
- **docs**: `references/channels.md` records what each channel reports and the versions checked (Orca 1.4.221, herdr 0.9.3, Claude Code 2.1.291, Codex CLI 0.160.1; the end-to-end check ended with Orca 1.4.222 and Claude Code 2.1.294 installed).

### marketplace

- **feat**: Initial catalog `ai-crosstalk` (`0.1.0`) distributing the `crosstalk` plugin from `./crosstalk`. Install with `/plugin marketplace add BlueEventHorizon/ai-crosstalk` then `/plugin install crosstalk@ai-crosstalk`.
