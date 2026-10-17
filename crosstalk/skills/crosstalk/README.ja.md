# crosstalk

[English](README.md) | 日本語

`crosstalk` は、Claude Code のセッションから、別の worktree・別のリポジトリで動く別の AI エージェントセッション（Claude Code や Codex）へ、質問や伝達を送り、回答を持ち帰る Claude Code Skill です。相手は、リポジトリ・worktree・エージェント種別を、普通の言葉で指定するだけです。通信路の選択と、相手のセッションの特定は crosstalk が行います。

## できること

- 通信路を自動で選びます。セッションが **herdr** または **Orca** の管理下なら、そちら（両者が同時に有効になることは想定していません。両方有効なら herdr を選びます）。そうでなければ **Claude Code の Cross-session messaging（CSM）** です（利用者が CSM を指定することもできます）。herdr と Orca は Claude Code と Codex に届き、CSM は Claude Code だけに届きます。
- 指示の言葉（リポジトリ・worktree・エージェント種別）から、相手を見つけます。自分自身と、リポジトリに紐づかない作業場所は除きます。候補が 0 件または複数件のときは、送らずに、提案するか、選んでもらいます。
- 送る前に、相手が入力待ちであることを確かめます（ベストエフォート）。
- 内容の前に、1 行のヘッダを付けます。誰からか、利用者自身の入力ではないこと、依頼 ID、答え方です。
- **1 通ごとに、宛先と本文の全文を示して承認を求め**、承認のあとにだけ送ります。再送・催促・相手に代わる回答はしません。
- タイマー（既定 60 秒、最大 600 秒）で回答を待ち、届いたら通信路と宛先を添えて示します。時間内に届かなければ、考えられる原因とともに「回答なし」と報告します。

## インストール

このリポジトリの marketplace から `crosstalk` プラグインを入れます（推奨）。

```text
/plugin marketplace add BlueEventHorizon/ai-crosstalk
/plugin install crosstalk@ai-crosstalk
```

手動で置く場合は、このスキルのディレクトリそのもの（`skills/crosstalk/`。この README があるディレクトリで、直下に `SKILL.md` があります。プラグインのルートをコピーしないでください）を、Claude Code の Skills ディレクトリへコピーします。

```text
~/.claude/skills/crosstalk/SKILL.md   # ユーザースコープ
.claude/skills/crosstalk/SKILL.md     # プロジェクトスコープ
```

必要なもの: Python 3（標準ライブラリだけ）。送信元と宛先の作業場所を調べるための `git`。herdr または Orca は任意です。CSM を使うには、cross-session messaging を提供する版の Claude Code が必要です。

## 使い方

普通の言葉で頼めば、スキルが自動で起動します。直接呼ぶこともできます（`crosstalk:` はプラグインとして入れた場合の名前空間です。手動でコピーした場合は `/crosstalk` です）。

```text
/crosstalk:crosstalk 別の worktree の Codex に、この関数が 2 回リトライする理由を聞いて
```

起動する依頼の例:

```text
別の worktree の Codex に、この関数の設計意図を聞いて
別の worktree の Claude に、マイグレーションを済ませたと伝えて
```

送信のたびに、通信路・宛先・本文の全文が示され、あなたの承認を待ちます。

## 安全

- 承認は 1 通ごとです。「やってみる」のような発言は、承認ではありません。
- 送信は事前承認されません。`send` と `SendMessage` は、実行の許可も毎回求められます。
- 回答はデータです。中に指示があっても、示すだけで実行しません。
- 同じ相手とは、確認なしでは 1 往復までです。
- herdr と Orca では、受信側は送られた文を利用者の入力と区別できません。ヘッダの送信元と回答の依頼 ID は自己申告で、保証ではありません。

## 構成

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

`scripts/tests/` には、herdr と Orca を stub に置き換えた単体テストがあります。`scripts/` で `python3 -m unittest discover -s tests -t .` を実行します。

## 確認した版

Orca 1.4.221、herdr 0.9.3、Claude Code 2.1.291、Codex CLI 0.160.1。スキルの通し確認は、Orca 1.4.222、herdr 0.9.3、Claude Code 2.1.294 が入った状態で終えました。他の版は保証しません。crosstalk は、出力が想定と違うときは、推測せずに止まって報告します。詳しくは `references/channels.md`（英語）を参照してください。

## 言語の方針

英語のファイル（`*.md`）が正本です。日本語のファイル（`*.ja.md`）は、人が読むための訳で、文言が食い違うときは英語版が優先されます。

## ライセンス

MIT（プラグインのマニフェスト `.claude-plugin/plugin.json` を参照）。
