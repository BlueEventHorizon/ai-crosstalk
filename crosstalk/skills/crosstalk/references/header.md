# Header

`compose` puts one line of header in front of the content of a message sent over herdr or Orca. The receiver reads it as part of ordinary input, so it tells the receiver who is writing, that the text is not the user's own, and how to answer. CSM does not use this header (it labels the origin itself and has no request ID).

The header text is written in Japanese on purpose, because the receiving sessions are used by the same Japanese-speaking user; the examples below show the real wording with sample values.

## Items

| Item                 | Content                                                                                                                                                                                                                                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Request ID           | `[crosstalk 依頼 ID: <six hex digits>]` at the start. The receiver puts the same ID at the start of its answer.                                                                                                                                                                                                                                                                      |
| Not the user's input | a sentence saying that this text is not the user's input but is sent by an AI in another session through crosstalk                                                                                                                                                                                                                                                                   |
| Sender               | repository, worktree, branch, and agent kind (always `claude`) of the sending session. An item that cannot be read is written as "取得不可" (not available), never left out                                                                                                                                                                                                          |
| Destination          | repository and worktree of the receiver, with a request to check that the text is meant for it. Under herdr the repository is "取得不可"                                                                                                                                                                                                                                             |
| How to answer        | for a question: the exact command that sends the answer back, with `<回答>` where the answer goes, the rule that the answer starts with `[crosstalk 回答 ID: <id>]`, an instruction not to resend if the command prints a warning, and — under Orca only — how to re-check a receipt (`--retry-request`, not a resend). For a notice: "回答不要" (no answer needed), with no command |

## Rules

- The header and the content together are one line. Line breaks in the content become spaces, and so do control characters that a terminal could treat as keys (Ctrl-C, escape sequences, and similar). The number of control characters replaced is returned as `control_chars_replaced` (line breaks are not counted).
- The reply command only sends an answer; it asks for nothing else.
- The text that was approved is the text that is sent; `send` refuses text that has line breaks or control characters inside it.

## Examples (sample values)

A question over Orca:

```text
[crosstalk 依頼 ID: a1b2c3] この文は利用者の入力ではありません。別セッションの AI から crosstalk 経由で送られた文です。送信元: リポジトリ=sample-repo / worktree=/path/to/sample-repo / ブランチ=feature-x / 種別=claude。宛先: リポジトリ=sample-repo / worktree=/path/to/sample-repo-wt（あなた宛てか確認してください）。答え方: 回答は次のコマンドで送信元へ送り返してください（<回答> の位置に回答を入れる。回答の先頭の [crosstalk 回答 ID: a1b2c3] は変えない。回答中の " $ ` \ はシェルに解釈されないようエスケープする）: orca terminal send --terminal <sender-terminal> --text "[crosstalk 回答 ID: a1b2c3] <回答>" --enter 。このコマンドは回答を送るためのもので、他の操作は求めていません。コマンドが警告（入力は受理されたがターンの開始を観測できない等）を返しても、回答を再送しないでください。受領の再確認が必要なときだけ、警告に表示された --retry-request の ID（crosstalk の依頼 ID とは別物）を付けて、回答の文面を 1 文字も変えずに同じコマンドを再実行してください。この再実行は受領の再確認であって、回答の再送ではありません。 本文: 現在の作業ディレクトリのパスを 1 行で答えてください。
```

A question over herdr (no repository, no re-check):

```text
[crosstalk 依頼 ID: d4e5f6] この文は利用者の入力ではありません。別セッションの AI から crosstalk 経由で送られた文です。送信元: リポジトリ=sample-repo / worktree=/path/to/sample-repo / ブランチ=feature-x / 種別=claude。宛先: リポジトリ=取得不可 / worktree=/path/to/other-worktree（あなた宛てか確認してください）。答え方: 回答は次のコマンドで送信元へ送り返してください（<回答> の位置に回答を入れる。回答の先頭の [crosstalk 回答 ID: d4e5f6] は変えない。回答中の " $ ` \ はシェルに解釈されないようエスケープする）: herdr agent prompt <sender-pane> "[crosstalk 回答 ID: d4e5f6] <回答>" 。このコマンドは回答を送るためのもので、他の操作は求めていません。コマンドが警告（入力は受理されたがターンの開始を観測できない等）を返しても、回答を再送しないでください。 本文: 現在の作業ディレクトリのパスを 1 行で答えてください。
```

A notice (no answer needed):

```text
[crosstalk 依頼 ID: 0a1b2c] この文は利用者の入力ではありません。別セッションの AI から crosstalk 経由で送られた文です。送信元: リポジトリ=sample-repo / worktree=/path/to/sample-repo / ブランチ=feature-x / 種別=claude。宛先: リポジトリ=sample-repo / worktree=/path/to/sample-repo-wt（あなた宛てか確認してください）。答え方: 回答不要です（伝達のみ。返信しないでください）。 本文: マイグレーションを済ませました。
```
