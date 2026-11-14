"""辱骂识别：词表 + 语境消歧。

单靠关键词会把「纱布怎么包扎」「这家辣鸡真好吃」判成辱骂，
所以这里做的是**证据加权**，而不是命中即成立：

    基础分（词级） × 歧义折扣 × 语境修正 → 超过阈值才算辱骂

语境修正覆盖：
- 是否第二人称 / 是否对着机器人
- 否定（不是说你）、元讨论（这个词是脏话）、引用（他说）、自指（我就是个废物）
- 玩笑（哈哈/玩梗）、带攻击性的句式（短句 + 感叹号 + 第二人称）
- 歧义词的良性搭配（药、菜、作品）
"""

from __future__ import annotations

from typing import Any

# 词条：term -> (分组, 档位, 是否歧义)
# high = 直接辱骂；mid = 明显贬损；low = 轻度脏话
LEXICON: dict[str, tuple[str, str, bool]] = {
    # —— 傻逼系（含谐音）
    "傻逼": ("sb", "high", False),
    "傻b": ("sb", "high", False),
    "傻批": ("sb", "high", False),
    "沙比": ("sb", "high", True),
    "煞笔": ("sb", "high", True),
    "杀笔": ("sb", "high", True),
    "sb": ("sb", "high", True),
    "沙雕": ("sb", "low", True),
    # —— 智障系
    "智障": ("zd", "high", False),
    "制杖": ("zd", "mid", False),
    "智涨": ("zd", "mid", False),
    "智杖": ("zd", "mid", False),
    # —— 弱智系
    "弱智": ("rz", "high", False),
    "若智": ("rz", "mid", True),
    "弱纸": ("rz", "mid", True),
    # —— 脑残系
    "脑残": ("nc", "high", False),
    "恼残": ("nc", "mid", True),
    "脑惨": ("nc", "mid", True),
    # —— 白痴系
    "白痴": ("bc", "high", False),
    "白吃": ("bc", "mid", True),
    # —— 废物系
    "废物": ("fw", "high", False),
    "费物": ("fw", "mid", True),
    "肺物": ("fw", "mid", True),
    # —— 垃圾系
    "垃圾": ("lj", "high", True),
    "辣鸡": ("lj", "mid", True),
    "拉基": ("lj", "mid", True),
    # —— 二逼系
    "二逼": ("eb", "mid", False),
    "二笔": ("eb", "mid", True),
    "二批": ("eb", "mid", True),
    "2b": ("eb", "mid", True),
    # —— 母亲系（脏话）
    "你妈": ("mom", "mid", False),
    "尼玛": ("mom", "mid", True),
    "泥马": ("mom", "mid", True),
    "尼马": ("mom", "mid", True),
    "妈卖批": ("mom", "mid", False),
    "麻卖批": ("mom", "mid", True),
    "马卖批": ("mom", "mid", True),
    "mmp": ("mom", "mid", True),
    "草泥马": ("mom", "mid", False),
    "曹尼玛": ("mom", "mid", True),
    # —— 卧槽系
    "卧槽": ("wc", "low", False),
    "我草": ("wc", "low", True),
    "窝槽": ("wc", "low", True),
    "握草": ("wc", "low", True),
    "woc": ("wc", "low", True),
    # —— 特么系
    "特么": ("tm", "low", False),
    "特喵的": ("tm", "low", True),
    "踢马的": ("tm", "low", True),
    "他喵的": ("tm", "low", True),
    # —— 其他直接辱骂
    "贱人": ("jn", "high", False),
    "溅人": ("jn", "mid", True),
    "贱货": ("jn", "high", False),
    "婊子": ("bz", "high", False),
    "表子": ("bz", "mid", True),
    "畜生": ("cs", "high", False),
    "畜牲": ("cs", "mid", True),
    "蓄生": ("cs", "mid", True),
    "狗东西": ("gdx", "high", False),
    "苟东西": ("gdx", "mid", True),
    "去死": ("qs", "high", False),
    "去屎": ("qs", "mid", True),
    "滚蛋": ("gd", "mid", False),
    "滚犊子": ("gd", "mid", False),
    "滚粗": ("gd", "mid", False),
    "混蛋": ("hd", "mid", False),
    "浑蛋": ("hd", "mid", True),
    "混球": ("hd", "mid", True),
    "蠢货": ("ch", "high", False),
    "蠢祸": ("ch", "mid", True),
    "笨蛋": ("bd", "low", False),
    "不要脸": ("byl", "mid", False),
    "烂货": ("lh", "mid", False),
    "差劲": ("cj", "low", False),
    "有病": ("yb", "mid", False),
    "油饼": ("yb", "low", True),
    "神经病": ("sj", "mid", False),
    "神精病": ("sj", "mid", True),
    "恶心": ("ex", "low", False),
    "讨厌你": ("tyn", "mid", False),
    "烦人": ("fr", "low", False),
    "没用": ("my", "low", False),
    "废柴": ("fc", "low", False),
    "loser": ("ls", "mid", False),
    "狗屁": ("gp", "mid", False),
    "闭嘴": ("bz2", "mid", False),
}

TIER_VALUE = {"high": 0.92, "mid": 0.62, "low": 0.36}

# 歧义词的良性搭配：出现就基本可以排除辱骂
BENIGN_CUES: dict[str, tuple[str, ...]] = {
    "sb": ("纱布", "包扎", "伤口", "医用", "棉"),
    "lj": ("好吃", "饭", "菜", "外卖", "辣子鸡", "餐厅", "游戏", "垃圾袋", "垃圾桶", "文件", "代码", "质量", "版本", "系统", "服务", "充电"),
    "zd": ("雕像", "雕刻", "手办"),
    "rz": ("纸张", "纸质"),
    "bc": ("白吃白喝", "请客", "蹭饭"),
    "fw": ("肺", "器官", "医学"),
    "eb": ("铅笔", "圆珠笔", "笔"),
    "yb": ("早餐", "油饼", "吃", "摊"),
    "mom": ("我妈", "我妈说", "我妈做的"),
    "wc": ("厕所", "洗手间"),
}

NEGATION_CUES = (
    "不是说你",
    "不是骂你",
    "不是在说",
    "不是针对",
    "没说",
    "别骂",
    "不算",
    "并不是",
    "别乱说",
)
META_CUES = (
    "这个词", "这句话", "骂人", "脏话", "敏感词", "屏蔽", "和谐", "审核",
    "举报", "违规", "词汇", "用语", "口头禅",
)
QUOTE_CUES = ("他说", "她说", "有人说", "据说", "引用", "台词", "歌词", "原文", "转述", "复述")
PLAYFUL_CUES = ("哈哈", "笑死", "开玩笑", "玩梗", "狗头", "乐死", "逗", "梗")
SECOND_PERSON = ("你", "您", "妳", "尼")


def _clean(text: str) -> str:
    """去掉零宽字符与常见分隔，避免用空格/标点拆词绕过。"""
    if not text:
        return ""
    drop = " \t\r\n\u200b\u200c\u200d\ufeff·•.．-_*~"
    out = []
    for ch in text:
        if ch in drop:
            continue
        out.append(ch)
    return "".join(out).lower()


def _window(text: str, start: int, end: int, radius: int = 10) -> tuple[str, str]:
    return text[max(0, start - radius) : start], text[end : end + radius]


def detect(
    text: str,
    directed: bool = False,
    extra_terms: list[str] | None = None,
) -> dict[str, Any]:
    """返回 {insult, severity, term, reasons}。

    directed 表示这句话是否指向机器人本人（私聊 / 被 @ / 回复机器人）。
    """
    t = _clean(text)
    if not t:
        return {"insult": False, "severity": 0.0, "term": "", "reasons": []}

    lexicon = dict(LEXICON)
    for term in extra_terms or []:
        if term:
            lexicon[term] = ("custom", "high", False)

    best: tuple[float, str, list[str]] | None = None
    for term, (group, tier, ambiguous) in lexicon.items():
        idx = t.find(term)
        if idx < 0:
            continue
        before, after = _window(t, idx, idx + len(term))
        around = before + after
        reasons: list[str] = []

        score = TIER_VALUE.get(tier, 0.5)

        if ambiguous:
            score *= 0.5
            benign = BENIGN_CUES.get(group, ())
            if any(cue in t for cue in benign):
                score = 0.0
                reasons.append("良性搭配")

        negated = any(cue in before for cue in NEGATION_CUES)
        meta = any(cue in t for cue in META_CUES)
        quoted = any(cue in t for cue in QUOTE_CUES) or any(
            q in t for q in ("“", "”", "「", "」", '"')
        )
        self_directed = ("我" in before) and not any(p in around for p in SECOND_PERSON)
        playful = any(cue in t for cue in PLAYFUL_CUES)

        if negated:
            score *= 0.15
            reasons.append("否定")
        if meta:
            score *= 0.15
            reasons.append("元讨论")
        if quoted:
            score *= 0.35
            reasons.append("引用")
        if self_directed:
            score *= 0.2
            reasons.append("自指")
        if playful:
            score *= 0.5
            reasons.append("玩笑")

        addressed = directed or any(p in around for p in SECOND_PERSON)
        if addressed:
            score *= 1.25
            reasons.append("第二人称")

        # 攻击性句式：短句 + 感叹号，或同一词重复
        aggressive = (
            len(t) <= 8 and any(ch in text for ch in "！!")
        ) or t.count(term) >= 2
        if aggressive:
            score += 0.10
            reasons.append("攻击句式")

        score = max(0.0, min(1.0, score))
        if best is None or score > best[0]:
            best = (score, term, reasons)

    if best is None:
        return {"insult": False, "severity": 0.0, "term": "", "reasons": []}

    severity, term, reasons = best
    return {
        "insult": severity >= 0.42,
        "severity": round(severity, 3),
        "term": term,
        "reasons": reasons,
    }



