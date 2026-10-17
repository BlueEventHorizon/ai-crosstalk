"""resolve サブコマンド。宛先の候補を列挙し、除外・絞り込み・並べ替えを行う。

通信路ごとの分岐は持たない。違いは adapter の共通の口（candidates / is_self / is_unlinked）で扱う。
"""

from .adapters import get_adapter
from .output import CrosstalkError

REASON_SELF = "自分自身"
REASON_UNLINKED = "リポジトリに紐づかない作業場所"


def _describe(candidate):
    """宛先を特定する情報だけを返す。受信側の状態は state サブコマンドの担当なので含めない。"""
    data = candidate.to_dict()
    del data["state"]
    # 通信路が取得できず空だった項目。承認の提示で「取得不可」と明示するための情報
    data["unavailable"] = [
        name for name in ("repo", "branch") if not getattr(candidate, name)
    ]
    return data


def _contains(value, needle):
    return needle.lower() in value.lower()


def _matches(candidate, repo, worktree, agent_kind):
    """指定された項目すべてに部分一致（大文字小文字を区別しない）するか。"""
    if repo:
        # 通信路が repo を返さないとき（herdr）は、作業ディレクトリのパスで判定する
        if not _contains(candidate.repo or candidate.worktree, repo):
            return False
    if worktree and not _contains(candidate.worktree, worktree):
        return False
    if agent_kind and not _contains(candidate.agent_kind, agent_kind):
        return False
    return True


def _sort_key(candidate):
    return (candidate.repo, candidate.worktree, candidate.agent_kind, candidate.target)


def run(args):
    channel = getattr(args, "channel", None)
    if not channel:
        raise CrosstalkError("--channel が必要（herdr / orca のどちらかを指定する）")
    adapter = get_adapter(channel)

    kept = []
    excluded = []
    for candidate in adapter.candidates():
        if adapter.is_self(candidate):
            excluded.append((candidate, REASON_SELF))
        elif adapter.is_unlinked(candidate):
            excluded.append((candidate, REASON_UNLINKED))
        else:
            kept.append(candidate)

    repo = getattr(args, "repo", None)
    worktree = getattr(args, "worktree", None)
    agent_kind = getattr(args, "agent_kind", None)
    matched = [c for c in kept if _matches(c, repo, worktree, agent_kind)]
    matched.sort(key=_sort_key)
    excluded.sort(key=lambda item: _sort_key(item[0]))

    return {
        "channel": channel,
        "count": len(matched),
        "candidates": [_describe(c) for c in matched],
        "excluded": [
            {"candidate": _describe(c), "reason": reason} for c, reason in excluded
        ],
    }
