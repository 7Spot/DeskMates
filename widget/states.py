"""姿势条、动作分组、按键这几张小表。别处不要再写姿势 id、分组 id。

文案只写动作，不写情绪：不出现 happy / sad / anxious / playing 这类词（动作名，tests/test_i18n.py 看着）。
"""

POSTURES = (("standing", "Stand"), ("sitting", "Sit"), ("lying", "Lie"), ("sleeping", "Sleep"))   # 动作行和「···」旁边的姿势条：短词（英文长词一行放不下）
WAKE = ("wake", "Wake up")                                                                       # 睡着时两处都只显示「醒来」

GROUPS: dict[str, str] = {           # 动作表盘的分组 id → 标题（clips.Action.group）
    "rest": "Resting",
    "move": "Moving",
    "body": "Body",
    "nose": "Nose & mouth",
    "pose": "Poses",
}

BANNED_WORDS = ("happy", "sad", "anxious", "playing", "play")
BANNED_WORDS_ZH = ("开心", "高兴", "难过", "伤心", "焦虑", "玩耍", "玩")
