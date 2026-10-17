# ai-crosstalk

実行中の別のセッションで動く AI（Claude Code / Codex）に、質問や伝達を送り、回答を受け取る Claude Code プラグイン `crosstalk` を配布するリポジトリ。

---

## 何ができるのか

| やりたいこと                                                 | 使うスキル             |
| ------------------------------------------------------------ | ---------------------- |
| 別のセッションで動く AI に、質問・伝達して回答を受け取りたい | `/crosstalk:crosstalk` |

通信路は環境で決まる（herdr、Orca、それ以外は Claude Code の Cross-session messaging）。宛先は「別の worktree の Codex」のような言葉から探す。

**送信は 1 通ごとに、宛先と本文の全文を見せて、利用者が承認してから行う。** 再送・催促・代理の返信はしない。

**こんなときに使う:**

- 別の worktree で動いている AI に、設計の意図を聞きたい
- 別のセッションの AI に、作業を済ませたことを伝えたい

詳しくは [`crosstalk/skills/crosstalk/README.ja.md`](crosstalk/skills/crosstalk/README.ja.md)（英語版: [`README.md`](crosstalk/skills/crosstalk/README.md)）。

---

## インストール

```bash
/plugin marketplace add BlueEventHorizon/ai-crosstalk
/plugin install crosstalk@ai-crosstalk
/reload-plugins
# 使い方: /crosstalk:crosstalk
```

Claude Code v2.1.275 以降では、1 コマンドでもできる: `/plugin install crosstalk --marketplace BlueEventHorizon/ai-crosstalk`（新しい marketplace の追加は確認を求められる）。

### インストールのスコープ

| スコープ     | 適用範囲                   | 保存先                        | git で共有 |
| ------------ | -------------------------- | ----------------------------- | ---------- |
| user（既定） | 自分。すべてのプロジェクト | `~/.claude/settings.json`     | しない     |
| project      | このリポジトリの協働者全員 | `.claude/settings.json`       | 有効化のみ |
| local        | 自分。このリポジトリだけ   | `.claude/settings.local.json` | しない     |

- `/plugin install` は既定で user スコープに入る。すべてのプロジェクトで使える
- スコープを指定する場合: `claude plugin install crosstalk@ai-crosstalk --scope project`（`user` / `project` / `local`）
- project スコープで共有されるのは `.claude/settings.json` の有効化の記録だけ。協働者はそれぞれ、自分の環境で上記の install コマンドを 1 回実行する必要がある

---

## リポジトリ構造

```
.claude-plugin/marketplace.json          # マーケットプレイスカタログ (crosstalk を登録。source: ./crosstalk)
crosstalk/                               # プラグインルート
  .claude-plugin/plugin.json             # プラグインマニフェスト (namespace: "crosstalk")
  skills/
    crosstalk/
      SKILL.md                           # 別セッションの AI へ質問・伝達し、回答を提示
      references/                        # 通信路ごとの仕様・ヘッダ書式
      scripts/                           # crosstalk.py（通信路の判定・宛先解決・送信など）とテスト
docs/
  specs/crosstalk/                       # 要件定義書・設計書・ADR・検証記録
```

---

## 開発

テストの実行:

```bash
cd crosstalk/skills/crosstalk/scripts
python3 -m unittest discover -s tests -t .
```

manifest の検証:

```bash
claude plugin validate . --strict             # marketplace
claude plugin validate ./crosstalk --strict   # plugin
```

ローカルでの読み込み確認（marketplace を経由しない）:

```bash
claude --plugin-dir ./crosstalk
```

marketplace を経由した受け入れ確認:

```bash
/plugin marketplace add ./
/plugin install crosstalk@ai-crosstalk
/reload-plugins
```

## ライセンス

MIT
