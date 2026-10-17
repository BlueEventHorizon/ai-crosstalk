"""adapter の共通の口と、候補・状態の値。"""

from dataclasses import dataclass

STATE_IDLE = "idle"
STATE_WORKING = "working"
STATE_BLOCKED = "blocked"
STATE_UNKNOWN = "unknown"
STATES = (STATE_IDLE, STATE_WORKING, STATE_BLOCKED, STATE_UNKNOWN)


@dataclass(frozen=True)
class Candidate:
    """宛先の候補。repo と branch は、通信路が返さないときは空文字にする。"""

    channel: str
    target: str
    repo: str
    worktree: str
    branch: str
    agent_kind: str
    state: str

    def to_dict(self):
        return {
            "channel": self.channel,
            "target": self.target,
            "repo": self.repo,
            "worktree": self.worktree,
            "branch": self.branch,
            "agent_kind": self.agent_kind,
            "state": self.state,
        }


SEND_FAILED_REASON = "送信に失敗した。届いたか確認できない場合がある。再送しない"

REDACTED_TEXT = "<本文>"


def redact_text(detail, text):
    """失敗の説明（外部 CLI の出力）に、送った本文がそのまま入っていたら伏せる。

    CLI がエラーに引数をエコーすると、本文が出力に載る。本文は承認済みで 1 行だが、出力へ
    不必要に載せない。
    """
    return detail.replace(text, REDACTED_TEXT) if text else detail


# 受領を確認できなかったときの根拠の observed
RECEIPT_NOT_OBSERVED = "確認できない"


@dataclass(frozen=True)
class SendResult:
    """送信コマンドが成功（終了コード 0）したときの結果。confirmed は受領を確認できたか。"""

    confirmed: bool
    source: str
    observed: str

    def to_dict(self):
        return {
            "confirmed": self.confirmed,
            "evidence": {"source": self.source, "observed": self.observed},
        }


class ChannelAdapter:
    """通信路ごとの adapter が満たす共通の口。期待と異なる出力は CrosstalkError で止まる。"""

    channel = ""

    def available(self):
        """この通信路を使えるか（bool）。"""
        raise NotImplementedError

    def candidates(self):
        """宛先の候補（Candidate のリスト）を返す。"""
        raise NotImplementedError

    def receiver_state(self, target):
        """target の受信側の状態（STATES のいずれか）を返す。"""
        raise NotImplementedError

    def receiver_state_with_evidence(self, target):
        """(状態, 根拠) を返す。根拠は {"source": 見た記録・画面, "observed": 判定に使った特徴}。"""
        raise NotImplementedError

    def is_self(self, candidate):
        """candidate が自分自身（送信側の端末・pane）か。"""
        raise NotImplementedError

    def is_unlinked(self, candidate):
        """candidate が、リポジトリに紐づかない作業場所（一時ディレクトリの worktree 等）か。"""
        raise NotImplementedError

    def receipt_recheck_guide(self):
        """返信コマンドの受領を再確認する手順の案内文（答え方に添える）。再確認の手段が無い通信路は空文字。"""
        return ""

    def send(self, target, text):
        """target へ text を 1 回だけ送り、SendResult を返す。再試行しない。

        送信コマンドの失敗（終了コードが 0 以外・タイムアウト・実行ファイルが無い）は
        SEND_FAILED_REASON を reason にした CrosstalkError にする。
        受領を確認できないこと（出力が JSON でない等）は失敗ではなく、confirmed=False の結果にする。
        """
        raise NotImplementedError

    def reply_command(self, request_id):
        """受信側が回答を送り返すコマンドの文字列を返す。

        回答を入れる位置は <回答> で示し、回答の先頭には依頼 ID の印を付ける。
        送信側の端末・pane は環境変数から取る。取れなければ CrosstalkError。
        """
        raise NotImplementedError
