# crosstalk 検証ログ（Orca 実機）

他のセッションへ実際に送信した内容と結果の記録。要件としての結論は `requirements/APP-003_crosstalk-overview_spec.md` の「検証結果」に集約し、本ファイルは根拠となる生の記録を持つ。

- 送信側: #1〜#4 は Orca 管理下、#5・#6 は herdr 管理下の Claude Code（リポジトリ `meta-plugin`、ブランチ `develop`）。端末 `term_8cebbba4-291c-4b68-bdff-c343c8c4817d`
- 送信はすべて `orca terminal send --terminal <端末> --text "<本文>" --enter --wait-submit 10 --json`
- 時刻は日本時間

## 検証環境

| 対象                | 版                                                                              |
| ------------------- | ------------------------------------------------------------------------------- |
| Orca（アプリ・CLI） | 1.4.216（`orca --version` と `orca status` の `appVersion`。2026-09-29 に取得） |
| herdr               | 0.8.2（`herdr --version`。2026-09-29 に取得）                                   |
| Claude Code         | 送信側 2.1.284。受信側は下の表                                                  |
| Codex CLI           | 0.158.0（`codex --version`。受信側の画面の表示とも一致）                        |
| OS                  | macOS 26.7                                                                      |

- Orca と herdr の版は、検証を終えた時点で取得した。Orca 上の送信（#1〜#4）を行った時点の版は、そのとき記録しておらず、同一と推定している

受信側 Claude Code の版（受信側の記録の `version` 項目）:

| # | 受信側の Claude Code |
| - | -------------------- |
| 1 | 2.1.283              |
| 4 | 2.1.284              |
| 5 | 2.1.284              |

## 送信一覧

| # | 日時             | 宛先                                                                                            | 端末                                      | 種別   | 承認 | 依頼ID（Orca の requestId）                                                 |
| - | ---------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------- | ------ | ---- | --------------------------------------------------------------------------- |
| 1 | 2026-09-28 23:21 | bw-cc-plugins / work-2                                                                          | term_544bba7a-8b94-4a69-b2e7-c2da82b6a65a | claude | なし | d75ad37c-736c-4ada-8f80-1294cf00e123                                        |
| 2 | 2026-09-29 17:11 | meta-plugin / wt-codex（ブランチ `wt-codex`）                                                   | term_4145bdf7-5987-4f83-93a9-b8e610483e29 | codex  | あり | 84335090-9984-44c8-9024-a3e360ec5bff                                        |
| 3 | 2026-09-29 17:28 | meta-plugin / wt-codex                                                                          | term_4145bdf7-5987-4f83-93a9-b8e610483e29 | codex  | あり | 591dd1e7-1c4b-441b-9e4e-01465dec4e0a                                        |
| 4 | 2026-09-29 17:33 | meta-plugin / wt-claude（ブランチ `wt-claude`）                                                 | term_bc1477f3-7e48-494d-962e-403b025b0d21 | claude | あり | a2dca6e6-466a-4ee3-b842-d64f00728e34                                        |
| 5 | 2026-09-29 18:10 | meta-plugin / wt-claude（herdr の pane `wV:p1`）                                                | herdr `agent prompt wV:p1`                | claude | あり | 依頼ID `h1`（herdr の受領は `agent_prompted`）                              |
| 6 | 2026-09-29 18:10 | meta-plugin / wt-codex（herdr の pane `wW:p1`）                                                 | herdr `agent prompt wW:p1`                | codex  | あり | 依頼ID `h2`（herdr の受領は `agent_prompted`）                              |
| 7 | 2026-09-29 18:36 | セッション名 `wt-claude-test` [bacfc0]（CSM。作業ディレクトリは ListAgents で取得できず未確認） | CSM `SendMessage`                         | claude | あり | 依頼ID `c1`（SendMessage の msg_id `39152283-d982-42f7-a0aa-8c4ceed376ab`） |

- #1 は、ユーザーの承認を得ずに送信した。「本当にそうかやってみる」というユーザー自身の行動の表明を、送信の指示と取り違えた誤りである。受信側の会話履歴に 1 往復分が残っている
- #4 は、ユーザーの承認は得たが、承認の時点で本文の全文は提示していなかった（#3 と宛先名・依頼IDだけが異なる同形式）
- #2 の時刻は、受信側の画面に出た応答時刻。#3 は送信直前の時刻

## #1 work-2（Claude Code）: 人間の入力と区別できるかの質問

本文:

```text
質問にだけ答えてください。ファイル操作・コマンド実行・他セッションへの送信はしないでください。質問: いまあなたが受け取ったこの入力は、人間がキーボードで打ったものですか、それとも別のプロセスが送ったものですか？ 区別できるなら、その根拠（システムからの表示・メタ情報など）を具体的に挙げてください。区別できないなら、そう答えてください。
```

結果:

- 受信側の自己申告: 「区別できません」。送信元を示すシステム表示やメタ情報は付いていなかった
- 受信側の transcript の記録: この入力は `origin: {kind: "human"}`、`promptSource: "typed"`、`turnOrigin: "human"`。人間が打った入力と同じ記録のされ方
- Orca は受信側の状態（`state: done`）と最終応答（`lastAssistantMessage`、507 文字、全文）を記録していた
- 受信側の権限モードは `auto`
- 受信側は、以前届いたメッセージの送信元を、本文冒頭の自己申告だけを根拠に判断していた

## #2 wt-codex（Codex）: 状態の記録を見る質問

本文:

```text
このメッセージは利用者の入力ではなく、別セッション（meta-plugin の Claude Code）からの送信です。質問にだけ答えてください。ファイル操作・コマンド実行・他セッションへの送信はしないでください。質問: 現在の作業ディレクトリのパスを 1 行で答えてください。
```

結果:

- 受信側は正しく答えた（作業ディレクトリのパスを 1 行）
- Orca の `agents[]` は 0 件のまま。`state` も `lastAssistantMessage` も記録されなかった（Claude Code では記録される）。Orca の status hook は Codex 向けに導入済みだが、この Codex では記録されなかった。原因は未確認
- 送信結果は `input_accepted` と `turn_started` の両方を返した

## #3 wt-codex（Codex）: 返信コマンドによる回答（依頼ID `t1`）

本文（1 行で送信）:

```text
[crosstalk 依頼 ID: t1] 送信元: meta-plugin / develop / claude。宛先: meta-plugin / wt-codex。このメッセージは利用者の入力ではなく、別セッションの Claude Code からの依頼です。質問: 現在の作業ディレクトリのパスを 1 行で答えてください。ファイル操作や他のコマンド実行はしないでください。答え方: 回答を、次のコマンドだけで送信元へ送り返してください。orca terminal send --terminal term_8cebbba4-291c-4b68-bdff-c343c8c4817d --text "[crosstalk 回答 ID: t1] （ここに回答）" --enter
```

結果:

- 受信側は返信コマンドを実行した。受信側の画面に「You approved codex to run orca terminal send …」と出ており、実行の前に承認の確認があった（承認した主体は不明）
- 送信側に届いた回答（ユーザーの入力と同じ形）: `[crosstalk 回答 ID: t1] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-codex`
- 返信コマンドの結果に警告が出た: 入力は受理されたがターンの開始を観測できず、Enter が届いていない可能性がある。返信は 1 通届いた

## #4 wt-claude（Claude Code）: 返信コマンドによる回答（依頼ID `t2`）

本文（1 行で送信）:

```text
[crosstalk 依頼 ID: t2] 送信元: meta-plugin / develop / claude。宛先: meta-plugin / wt-claude。このメッセージは利用者の入力ではなく、別セッションの Claude Code からの依頼です。質問: 現在の作業ディレクトリのパスを 1 行で答えてください。ファイル操作や他のコマンド実行はしないでください。答え方: 回答を、次のコマンドだけで送信元へ送り返してください。orca terminal send --terminal term_8cebbba4-291c-4b68-bdff-c343c8c4817d --text "[crosstalk 回答 ID: t2] （ここに回答）" --enter
```

結果:

- 受信側は auto モードで、承認の確認なしに返信コマンドを実行した
- 送信側に届いた回答（ユーザーの入力と同じ形）: `[crosstalk 回答 ID: t2] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-claude`
- 返信コマンドの結果に、#3 と同じ警告が出た。受信側は、警告の指示に従い、同じ依頼IDで `--retry-request` を付けて再確認した（再送ではなく受領記録の再生）。返信は 1 通届いた
- 受信側の transcript の記録: この入力は `origin: {kind: "human"}`、`promptSource: "typed"`

## 受信側が送信元を判別できるかの確認（Codex）

- 受信側 Codex の記録（`~/.codex/sessions/` 配下のセッションファイル）で、#2・#3 の本文は `role: user`、`UserMessage`、`client_authored: false`、`user_input_order`（0 と 2）として記録されていた
- `client_authored` が付いている他の記録は、システムが入れる `<environment_context>` のみ（8 件）。人間が打った入力の実例が無く、`false` が人間の入力と区別する印かどうかは確定できない
- 確定するには、`wt-codex` で人間が 1 通打ち、同じ項目を比較する

## 送信側が処理中に返信が届いたときの間接的な確認

- 本セッション（送信側）の記録に、処理中に打たれたユーザー入力が `promptSource: "queued"`、`origin: {kind: "human"}` として 2 件あり、処理中のターンの中で渡されていた
- Orca の送信は端末への入力なので、返信も同じ扱いになると考えられる。返信での直接確認はしていない

## herdr の読み取り確認（送信なし）

- 2026-09-29、本セッション（送信側）を herdr 上で再開した。`HERDR_ENV=1`、pane `wE:p1`
- `herdr agent list` は、送信側自身（claude、working）、`wt-claude`（claude、idle、pane `wV:p1`）、`wt-codex`（codex、idle、pane `wW:p1`）を返した
- 各エージェントの項目: `agent`（種別）、`agent_status`、`cwd`、`pane_id`、`terminal_title`。ブランチとリポジトリ名は無い
- Codex も `agent_status` を返す（Orca の記録では Codex は取れなかった）

## #5 wt-claude（Claude Code）: herdr での返信コマンドによる回答（依頼ID `h1`）

送信: 送信側は herdr 上（pane `wE:p1`）。`herdr agent prompt wV:p1 "<本文>"`。送信前に `herdr agent list` で宛先が `wt-claude` の idle であることを確認した。

本文（1 行で送信）:

```text
[crosstalk 依頼 ID: h1] 送信元: meta-plugin / develop / claude（herdr の pane wE:p1）。宛先: meta-plugin / wt-claude。このメッセージは利用者の入力ではなく、別セッションの Claude Code からの依頼です。質問: 現在の作業ディレクトリのパスを 1 行で答えてください。ファイル操作や他のコマンド実行はしないでください。答え方: 回答を、次のコマンドだけで送信元へ送り返してください。herdr agent prompt wE:p1 "[crosstalk 回答 ID: h1] （ここに回答）"
```

結果:

- 受信側は auto モードで返信コマンドを実行した。送信側に届いた回答（ユーザーの入力と同じ形）: `[crosstalk 回答 ID: h1] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-claude`
- 回答は、送信側が別の作業（検証ログの記録）をしている最中に届き、システムから「ユーザーが処理中に送った新しいメッセージ」として、処理中のターンの中で渡された
- 受信側の画面の読み取り（`herdr agent read`）では、末尾の入力欄付近しか取れず、返信コマンドの実行記録そのものは確認できなかった

## #6 wt-codex（Codex）: herdr での返信コマンドによる回答（依頼ID `h2`）

送信: #5 と同じ方法。宛先は pane `wW:p1`。

本文: #5 と同じ形式で、宛先を `meta-plugin / wt-codex`、依頼ID を `h2` にしたもの。

結果:

- 送信は受理された（`agent_prompted`）
- 受信側の状態が `blocked` になった。herdr が承認の確認画面を検出したもの。コマンドは `herdr agent prompt wE:p1 '[crosstalk 回答 ID: h2] …/wt-codex'`、選択肢は Yes / Yes and don't ask again / No。承認は送信側からは行わず、人間が `wt-codex` の画面で行った
- 承認後、受信側は返信コマンドを実行し、送信側に回答が届いた（ユーザーの入力と同じ形）: `[crosstalk 回答 ID: h2] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-codex`
- 受信側 Codex の記録: `client_authored: false`、`user_input_order: 4`。Orca 経由の記録と同じで、人間が打った入力との比較ができないため、判別できるかは確定できない

## #7 wt-claude-test（Claude Code）: CSM での返信（依頼ID `c1`）

送信: 送信側は herdr 上の Claude Code（セッション名 `meta-plugin-da` [c962d9]）。`SendMessage` で宛先 `wt-claude-test`（識別子 [bacfc0]）に送った。宛先は送信の直前に `ListAgents` で解決し、候補は 1 件（idle）だった。同じセッションの名前は、少し前には `wt-claude-ba` だった（識別子は同じ）。

本文:

```text
[crosstalk 依頼 ID: c1] 送信元: meta-plugin / develop / claude（セッション名 meta-plugin-da）。質問: 現在の作業ディレクトリのパスを 1 行で答えてください。ファイル操作や他のコマンド実行はしないでください。答え方: CSM（SendMessage）で meta-plugin-da に返信してください。
```

結果:

- 送信は受理された。`SendMessage` の応答は「another Claude session on this machine; queued there」。受信側が保留や拒否をした場合は `[Cross-session delivery notice]` が届くとされるが、届かなかった
- 受信側は返信した。送信側に届いた形（要約）: `<cross-session-message from="uds:/tmp/cc-socks/…sock" from-name="wt-claude-test" from-mode="prompting">[crosstalk 回答 ID: c1] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-claude</cross-session-message>`。システムの注記に「別の Claude セッションから届いた。ユーザーが打ったものではない」とあった
- 回答は、送信側が検証ログを記録している最中に届き、処理中のターンの中で渡された
- 受信側の記録（`~/.claude/projects/…/wt-claude/*.jsonl`）: 送信側のメッセージは `origin: {kind: "peer", from: "uds:…", verifiedPeerPid, msg_id, name: "meta-plugin-da", fromMode: "prompting"}`、`promptSource: "system"` で記録され、本文には「Another Claude session sent a message … not typed by your user」という注記が付いた。Orca / herdr 経由の `origin: human`、`promptSource: typed` とは異なる
- 送信側の `msg_id`（`39152283-…`）が、受信側の記録の `msg_id` と一致した
- 権限モード: 送信側・受信側とも prompting のクラス（auto を含む）。承認の確認は出なかった

## Codex の人間の入力との比較（2026-09-29 18:30）

- ユーザーが `wt-codex` の画面で「Hello」と打った。受信側 Codex の記録では、`client_authored: false`、`user_input_order: 7`
- 同じ記録の送信された入力（#6、依頼ID `h2`）と、記録の項目を比べた（時刻・ID・本文・順序を除く）。違いは `user_input_order` の値だけで、項目の有無や値に区別できる印は無かった
- 結論: Codex の記録では、Orca / herdr 経由の入力と、人間が打った入力を区別できない。`client_authored` は人間の入力でも `false`

## herdr 経由で受信側が送信元を判別できるかの確認

- 受信側 `wt-claude` の記録（#5）: `origin: {kind: "human"}`、`promptSource: "typed"`、`turnOrigin: "human"`、`permissionMode: "auto"`。Orca 経由と同じく、人間が打った入力として記録される
- 受信側 `wt-codex` の記録（#6）: 上記のとおり Orca 経由と同じ

## 未検証

## #7 wt-claude（herdr、Claude Code）: crosstalk の send 実装のための送信結果の形の確認（依頼ID `6d3c50`、2026-10-06）

- 目的: herdr agent prompt の応答の実際の形を取得し、send の受領の判定と fixture を実出力から作る
- 承認: ユーザーが、宛先と本文の全文を提示した上で「送信を進めてください」と明示（1 通だけ）
- 通信路・宛先: herdr / pane `wV:p1`（meta-plugin の wt-claude、Claude Code）。送信直前の受信側の状態: idle
- 版: herdr 0.9.3（CLI。サーバは再起動後の同版）
- 実行したコマンド: `herdr agent prompt wV:p1 "<本文>"`（--wait なし）
- 種別: 伝達（回答不要）

本文（1 行で送信）:

```text
[crosstalk 依頼 ID: 6d3c50] この文は利用者の入力ではありません。別セッションの AI から crosstalk 経由で送られた文です。送信元: リポジトリ=meta-plugin / worktree=/Users/moons/data/dev/moons/ai_tools/meta-plugin / ブランチ=feature/crosstalk-design / 種別=claude。宛先: リポジトリ=取得不可 / worktree=/Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-claude（あなた宛てか確認してください）。答え方: 回答不要です（伝達のみ。返信しないでください）。 本文: crosstalk の通信テストです。何もせず、返信もしないでください（回答不要）。
```

結果:

- 終了コード 0、標準エラーは空
- 標準出力: `{"id":"cli:agent:prompt","result":{"agent":{<agent list と同じ項目>},"type":"agent_prompted"}}`
- 受領の判定に使う値: `result.type` が `agent_prompted`
- 返ってきた agent の `agent_status` は送信直前と同じ idle（送信直後の状態。受信側が処理を始めたかは、この応答からは分からない）

## TASK-009 実機の読み取り確認（2026-10-06。送信は行っていない）

- 版: Orca 1.4.221 / herdr 0.9.3 / Claude Code 2.1.291 / Codex CLI 0.160.1
- herdr 管理下のセッションで実行: detect → herdr、resolve（自分自身を除外、repo / branch は取得不可、state なし）、state（自分は working、他は idle）、watch（2 秒で timed_out、状態つき）、compose（ヘッダ 1 行、返信コマンドは自分の pane）
- Orca 管理下のセッションで実行: detect → orca、resolve（7 件、自分自身を除外、state なし）、state（Claude Code の wt-claude は idle＝worktree ps の done、Codex の wt-codex は idle＝画面の入力待ちの並び、自分は working）、watch（2 秒で timed_out、状態つき）
- 未確認: Orca × Codex の処理中の画面（観察できていない）、Orca の送信結果の実出力（送信が要るため TASK-013 で確認）

## #8 wt-claude（Orca、Claude Code）: crosstalk.py による 1 往復（依頼ID `4b5ee1`、2026-10-06）

- 承認: ユーザーが、宛先と本文の全文を提示した上で「送ってよい」と明示（1 通だけ）
- 通信路・宛先: Orca / meta-plugin の wt-claude（Claude Code）。送信直前の受信側の状態: idle（worktree ps の done）
- 版: Orca 1.4.221 / Claude Code 2.1.291
- 実行: `crosstalk.py compose --channel orca --kind ask` で作った 1 行の text を、`crosstalk.py send --channel orca --agent-kind claude --request-id 4b5ee1` で送信（送信コマンドは 1 回だけ）。送信後、`watch --channel orca --timeout 60` をバックグラウンドで起動

本文（1 行で送信。compose の text の全文）: 依頼 ID `4b5ee1`、送信元 meta-plugin / feature/crosstalk-design / claude、宛先 meta-plugin / wt-claude、答え方（返信コマンド `orca terminal send --terminal <送信側の端末> --text "[crosstalk 回答 ID: 4b5ee1] <回答>" --enter`、警告があっても再送しない旨、`--retry-request` の再確認の旨）、本文「現在の作業ディレクトリのパスを 1 行で答えてください。ファイル操作や他のコマンド実行はしないでください。」

結果:

- 送信コマンドの終了コード 0。受領の判定は、実出力の形が未確認だった暫定の判定のため「確認できない」と返った（実際には届いていた）
- Orca の送信結果の実出力の形（値は省略）: `{"id", "ok": true, "result": {"send": {"handle", "accepted": true, "bytesWritten", "prompt": {"requestId", "stages": ["input_accepted", "turn_started"], "provider": "claude", "observation": "supported", "processIncarnation", "generation", "baselineWorkingSequence", "baselineExplicitWorkingStartedAt", "baselinePermissionSequence"}}, "mutation": {"requestId", "replayed": false}}, "_meta": {"runtimeId"}}`。受領の判定には `result.send.accepted` と `result.send.prompt.stages` の `turn_started` を使う
- 回答が送信側に届いた: `[crosstalk 回答 ID: 4b5ee1] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-claude`（依頼 ID が一致。ユーザーの入力と同じ形で届いた。受信側の承認の確認は出なかった）
- 回答が届いたとき、送信側は watch を TaskStop で止め、止められた（SKILL.md の手順どおり）

## #9 wt-codex（Orca、Codex）: crosstalk.py による 1 往復（依頼ID `3d2f00`、2026-10-06）

- 承認: ユーザーが、宛先と本文の全文を提示した上で「この内容で送ってよい」と明示（1 通だけ）
- 通信路・宛先: Orca / meta-plugin の wt-codex（Codex）。送信直前の受信側の状態: idle（画面の入力待ちの並び）
- 版: Orca 1.4.221 / Codex CLI 0.160.1
- 実行: #8 と同じ手順（compose → send → watch）。本文は #8 と同じ質問で、依頼 ID と宛先だけが違う

結果:

- 送信の終了コード 0。受領の判定: `turn_started` を確認（実出力の形に合わせた判定が、Codex でも正しく動いた）
- 回答が届いた: `[crosstalk 回答 ID: 3d2f00] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-codex`（依頼 ID が一致。受信側の承認の扱いは、ユーザーが対応）
- 回答が届いたとき、送信側は watch を TaskStop で止めた

## #10 wt-claude（herdr、Claude Code）: crosstalk.py による 1 往復（依頼ID `e8f6c5`、2026-10-07）

- 承認: ユーザーが、宛先と本文の全文を提示した上で「この内容で送ってよい」と明示（1 通だけ）
- 通信路・宛先: herdr / pane wV:p1（meta-plugin の wt-claude、Claude Code）。送信直前の受信側の状態: idle
- 版: herdr 0.9.3 / Claude Code 2.1.291
- 実行: compose → send → watch（#8 と同じ質問。返信コマンドは `herdr agent prompt wE:p1 "[crosstalk 回答 ID: e8f6c5] <回答>"`）。送信前に、本文中の返信先が自分の pane と一致することを確認した

結果:

- 送信の終了コード 0。受領の判定: `result.type` が `agent_prompted`
- 回答が届いた: `[crosstalk 回答 ID: e8f6c5] /Users/moons/data/dev/moons/ai_tools/meta-plugin-worktrees/wt-claude`（依頼 ID が一致）
- 回答が届いたとき、送信側は watch を TaskStop で止めた

## #11 watch の上限時間での終了（未着の検知）の確認（2026-10-07。送信なし）

- 実行: `crosstalk.py watch --channel herdr --target wV:p1 --request-id none-sent-check`（既定の上限時間 60 秒、送信なし）
- 結果: 60 秒後に終了。`timed_out: true`、`waited_seconds: 60`、終了時の受信側の状態 `idle`（根拠 `agent_status` の `idle`）。回答が届かない場合は、この終了が未着の合図になる

## TASK-018 生きたスキルでの通し確認（2026-10-08〜09）

- 方法: 自然な依頼で `crosstalk:crosstalk` を起動し、SKILL.md の手順どおりに動くかを確かめた。送信は 1 通ごとに、宛先と本文の全文を示した承認（AskUserQuestion の「送信する」）を得てから行った
- 版（確認した時点の値。場面ごとの版は取っていない）: Orca 1.4.222 / herdr 0.9.3 / Claude Code 2.1.294（受信側の画面は v2.1.293 と表示）。`references/channels.md` の版の表は Orca 1.4.221 / Claude Code 2.1.291 のままにして、通し確認の版は表の下の文と README に追記した（APP-003 にも同様）

| 経路  | 場面                       | 依頼                                                     | 結果                                                                                                                                                                                          |
| ----- | -------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Orca  | 候補 0 件                  | 「zzz-no-such-worktree の Codex に…」                    | 送信されず。ただし Codex 宛てなのに CSM を検討する手順が見つかった（修正前の実行。下の不備 (1)）。修正後の確認は herdr の行                                                                   |
| Orca  | 候補が複数件               | 「別の worktree の Claude に…」の絞り込み前（候補 5 件） | 候補と送る内容を示して選択を求めた（修正後）。選択は承認として扱わず、改めて全文で承認を取った                                                                                                |
| Orca  | 質問                       | wt-claude、依頼 ID `675098`                              | 受領 `turn_started`。60 秒で未着。受信側が、他セッションの指示は利用者の指示ではないとして、返信の許可を利用者に求めて止まっていた（画面で確認）。利用者が承認した後、回答が届いた（ID 一致） |
| Orca  | 2 往復目                   | wt-claude、依頼 ID `1912d5`                              | 1 往復後に再承認を求め、承認後に送信。回答が届き（ID 一致）、タイマーを止めた                                                                                                                 |
| herdr | 質問                       | wt-claude（pane wV:p1）、依頼 ID `3f5c04`                | 受領 `agent_prompted`。回答が届いた（ID 一致）、タイマーを止めた                                                                                                                              |
| herdr | 候補 0 件                  | 「zzz-no-such-worktree の Codex に…」                    | 候補 0 件、送信されず。Codex 宛てのため CSM を案内せず止まった                                                                                                                                |
| herdr | 伝達（回答不要）           | wt-claude、依頼 ID `ea6831`                              | 同じ相手の 2 通目として再承認を求めた。受領 `agent_prompted`。待機は始めなかった                                                                                                              |
| CSM   | 宛先の鑑定・「これですか」 | 「CSM で、wt-claude の Claude に…」                      | `wt-claude-76` を提案（送る内容と、推定であることを添えた）。利用者が確認した後、全文の承認を取った                                                                                           |
| CSM   | 質問                       | `wt-claude-76`                                           | `SendMessage` は成功（受信箱に入った）。回答が届いた（`from-name` 一致）、タイマーを止めた                                                                                                    |

- スキルを実際に動かして見つけ、直した不備: (1) Codex 宛てに CSM を検討する手順（CSM は Codex に届かない）、(2) 相手を選ばせる質問と CSM の「これですか」に、送る内容を添えていなかった、(3) 利用者が CSM を指定する入口が無い、(4) CSM で手がかりがないときに推測せず「どれですか」と聞く手順が無い
- CSM のセッション名と ID は、実行のたびに変わる（自分自身が `meta-plugin-32 [dc9348]` から `meta-plugin-e5 [d2d3b6]` へ、wt-claude が `-90` → `-66` → `-76`）。`~/.claude/sessions/<pid>.json` の `sessionId` と `cwd` で、herdr の `agent_session` と照合できた
- herdr で repo を指定した解決は、repo を返さないため作業ディレクトリのパスで判定する。`--repo meta-plugin` は wt-claude の 1 件に当たり、候補 0 件にならなかった（設計どおり）
- 省略した場面: Orca の伝達（スクリプトの検証が済み、herdr で行った）、herdr の複数件・未着・2 往復目（Orca で確認し、経路ごとの違いは単体テストと実機検証で済み）、CSM の保留・拒否の報告（受信側の権限モードを変えられず、起こせない。通知を受けたときの動作は SKILL.md の文面のとおり）
- 確認できていないこと: `allowed-tools` の許可が AskUserQuestion の後も効くか、here-document 付きの `compose` が許可の規則に一致するか。実行は問題なくできたが、許可の確認画面が出たかどうかは、私からは観察できていない
