# Channels

What each channel does and what was observed on real installations. Output shapes below are the ones seen on the versions in "Checked versions"; other versions are not guaranteed. A statement marked "documented, not observed" comes from a tool's documentation or help text, not from a check on a real installation. When an output differs from what is written here, `crosstalk.py` stops with `status: error` instead of guessing.

## Overview

|                             | herdr                                                          | Orca                                                                              | CSM (Claude Code Cross-session messaging)         |
| --------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------- |
| Who can be reached          | any agent managed by herdr                                     | any agent managed by Orca                                                         | Claude Code sessions only                         |
| Managed-by check            | env `HERDR_ENV=1` and `herdr agent list` succeeds              | env `ORCA_TERMINAL_HANDLE` and `orca status --json` reports the runtime reachable | the `ListAgents` / `SendMessage` tools exist      |
| What identifies a recipient | working directory, pane, agent kind (no repository, no branch) | repository, worktree, branch, agent kind, terminal                                | session name only                                 |
| Receiver's state            | `agent_status` for every kind                                  | Claude Code: recorded state; Codex: judged from the screen                        | not available                                     |
| How a reply returns         | the receiver runs a herdr command                              | the receiver runs an Orca command                                                 | the receiver replies over CSM                     |
| Request ID                  | yes                                                            | yes                                                                               | no (matched by the sender's session name)         |
| What the receiver sees      | text indistinguishable from user input                         | text indistinguishable from user input                                            | a message labelled as coming from another session |

herdr and Orca are not expected to be active at the same time; `detect` tries herdr first and then Orca, so herdr wins if both are active. CSM is used only when neither is active, or when the recipient could not be settled and the user agrees.

## herdr

- **Candidates:** `herdr agent list`. Output: `{"id": ..., "result": {"agents": [...], "type": "agent_list"}}`. Each agent has `agent` (kind), `agent_status`, `cwd`, `pane_id`, and other fields; `agent_session` is missing for some agents. On failure the command exits with 1 and prints a JSON error on standard error (for example a protocol mismatch between the CLI and a server that has not been restarted).
- **State:** `agent_status` `idle` / `done` → idle, `working` → working, `blocked` → blocked (waiting for an approval). Any other value stops the command with an error.
- **Send:** `herdr agent prompt <pane> <text>`. Accepted output: `{"id": ..., "result": {"agent": {...}, "type": "agent_prompted"}}`. `agent_prompted` is the receipt. (Documented in herdr's help, not observed:) a blocked agent rejects the prompt before any input is sent; crosstalk itself does not send to a blocked agent.
- **Reply command written into the header:** `herdr agent prompt <your pane> "[crosstalk 回答 ID: <id>] <answer>"`. Your pane is read from `HERDR_PANE_ID`. herdr has no way to re-check a receipt, so the header does not mention one.
- **Not tied to a repository:** a working directory for which `git rev-parse --is-inside-work-tree` does not report `true`.

## Orca

- **Candidates:** `orca worktree ps --json` (repository, worktree path, branch, agents with their state) joined with `orca terminal list --json` (terminals and their agent kind) by worktree and by pane key.
- **State (Claude Code):** the recorded state of the agent in `worktree ps`: `done` → idle, `working` → working. A missing or other value gives `unknown`, and so does any agent kind other than Claude Code and Codex.
- **State (Codex):** Orca records no state for Codex. The screen is read with `orca terminal read --screen --json`; if the last three non-empty lines are the empty input box, the model/path line, and the shortcuts hint, the state is idle. Anything else is `unknown`. **A screen of a Codex that is working has not been observed, so an "idle" here means "looks idle", not "is not working".**
- **Send:** `orca terminal send --terminal <handle> --text <text> --enter --wait-submit 10 --json`. The result has `result.send.accepted` and `result.send.prompt.stages`, an array that contains `input_accepted` and, when the receiver started the turn, `turn_started`. The receipt is confirmed only when `accepted` is true and `stages` contains `turn_started`; with `input_accepted` alone the receipt is reported as not confirmed.
- **Reply command written into the header:** `orca terminal send --terminal <your terminal> --text "[crosstalk 回答 ID: <id>] <answer>" --enter`. Your terminal is read from `ORCA_TERMINAL_HANDLE`. If the command prints a warning that the input was accepted but the turn start could not be observed, the receiver does not resend; to re-check it runs the same command again with the `--retry-request <id>` the warning shows (a transport ID, not the request ID).
- **Not tied to a repository:** a worktree whose repository name or repository ID is empty, whose project ID is present but empty, whose kind is not a git repository, or whose path is under a temporary directory. A missing project ID alone does not count.

## CSM

- **Candidates:** `ListAgents` (session names). The names can change; they are the only thing a recipient is known by.
- **Send:** `SendMessage`. Returning means the message was queued. (Documented, not observed:) when the receiver is in a stricter permission mode it may hold the message or refuse it, and a `[Cross-session delivery notice]` tells the sender. In the one check made, both sessions were in the same permission mode, the message was delivered without a hold, and no notice arrived.
- **Reply:** arrives as a `cross-session-message` whose `from-name` is the recipient's session name. There is no request ID.

## Checked versions

| Tool               | Version |
| ------------------ | ------- |
| Orca (app and CLI) | 1.4.221 |
| herdr              | 0.9.3   |
| Claude Code        | 2.1.291 |
| Codex CLI          | 0.160.1 |

The end-to-end check of the skill (natural-language requests through herdr, Orca, and CSM, with Claude Code receivers) ended with these versions installed: Orca 1.4.222, herdr 0.9.3, Claude Code 2.1.294. The versions were read after the check, not before each send. Codex CLI was not a receiver in that check.

## Known limits

- The receiver's state is best-effort, and it can change between the check and the send; that is accepted. Whether a Codex that is working looks idle on the screen has not been checked.
- Over herdr and Orca the receiver cannot tell the text from user input, so the sender named in the header and the request ID in the reply are self-reported, not guaranteed.
- A receiver's own settings may require an approval before it runs the reply command; without it the reply does not arrive and the sender reports "no reply".
- Orca's output shape for a send is checked on the version above only; if it differs, the receipt is reported as not confirmed and nothing is resent.
