# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 厳守事項

**Claude Code / Codex CLI の仕様・規約・配置・discovery・フラグ等について発言する前に、必ず公式資料を確認すること。** 記憶や推測で答えてはならない。

確認方法:

- **Claude Code 関連** (hooks / slash commands / MCP / settings / IDE integration / sub-agents / plugins / cross-session messaging 等): `claude-code-guide` agent を Agent ツールで起動する (WebFetch / WebSearch / Read を持つ専用 agent)。agent の引用は WebFetch 経由の要約なので、結論に使う箇所は下記「原文で確認する」で裏を取る
- **Codex CLI 関連** (`.agents/skills/` discovery / AGENTS.md / CLI フラグ等): 公式 docs (<https://learn.chatgpt.com/docs/>、索引は <https://learn.chatgpt.com/docs/llms.txt>) を確認する。旧 `developers.openai.com/codex/*` は移転済み
- **原文で確認する**: WebFetch はページを要約モデルに通した結果を返すため、原文引用の根拠にしない。各ページの Markdown 版 (Claude Code: `https://code.claude.com/docs/en/<page>.md`、Codex: `https://learn.chatgpt.com/docs/<slug>.md`、索引は各 `llms.txt`) を `curl` で `.claude/.temp/` に取得し、Read / grep で読んで引用する。取得時に 404・リダイレクトが出た参照 URL は、その場でリポジトリ内の記述も更新する

公式資料を未読の状態で「Codex は〜を読まない」「Claude Code の規約は〜」のような断定をしてはならない。読んだうえで該当箇所を引用すること。

## 構成の不変条件

- marketplace (`.claude-plugin/marketplace.json`、name `ai-crosstalk`) は `crosstalk` プラグイン 1 つだけを `source: "./crosstalk"` で配布する。リポジトリ直下には docs や CI など、プラグイン以外のファイルもあるため、`source: "./"` にしない（ルート全体がプラグインのキャッシュにコピーされてしまう）
- プラグインのルートは `crosstalk/`（`crosstalk/.claude-plugin/plugin.json`）。スキルは `crosstalk/skills/crosstalk/SKILL.md`。`plugin.json` にスキルを列挙しない（`skills/` はデフォルトで探索される）
- 配布物（`crosstalk/` 配下）から、開発リポジトリの文書（要件 ID、設計 ID、ADR、Issue 番号）を参照しない
- `crosstalk/skills/crosstalk/scripts/` は Python 3 の標準ライブラリだけを使う
- 英語のファイル（`*.md`）が正本。日本語のファイル（`*.ja.md`）は訳であり、英語版を変えたら同じ変更の中で日本語版も直す

## バージョン

- `crosstalk/.claude-plugin/plugin.json` の `version` と、marketplace の `plugins[].version` を一致させる。marketplace 自体の版は `metadata.version`。対象と同期の規則は `.version-config.yaml` にある
- `version` を上げない限り、既存の利用者には変更が届かない。リリースのたびに上げ、`CHANGELOG.md` に記録する

## よく使うコマンド

```bash
# crosstalk の単体テスト
cd crosstalk/skills/crosstalk/scripts && python3 -m unittest discover -s tests -t .

# manifest の検証
claude plugin validate . --strict
claude plugin validate ./crosstalk --strict
```

## 設計ドキュメント

- `docs/specs/crosstalk/requirements/` — 要件定義書 (APP-003, FNC-014〜017, SEC-001)
- `docs/specs/crosstalk/design/` — 設計書 (DES-011) と ADR (ADR-012〜014)
- `docs/specs/crosstalk/verification_log.md` — 実機での検証記録（当時の記録であり、リポジトリ名 `meta-plugin` 等は書き換えない）
