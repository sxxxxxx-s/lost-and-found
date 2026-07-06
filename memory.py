# -*- coding: utf-8 -*-
"""会话记忆：滑动窗口、摘要压缩和非敏感长期画像。"""

import re

from llm import chat


class Memory:
    def __init__(self, window=6):
        if window < 1:
            raise ValueError("window必须大于0")
        self.window = window
        self.history = []
        self.summary = ""
        self.profile = {}

    def add(self, role, content):
        self.history.append({"role": role, "content": str(content)})
        if len(self.history) > self.window:
            old_messages = self.history[: -self.window]
            self.history = self.history[-self.window :]
            self.summary = self._summarize(old_messages)

    def _summarize(self, messages):
        text = "\n".join(
            f"{message['role']}: {message['content']}" for message in messages
        )
        previous = f"已有摘要:{self.summary}\n" if self.summary else ""
        prompt = (
            "把以下对话压缩成要点,保留失物编号、认领单编号、地点和诉求,"
            "不要保留隐藏证据原文:\n" + previous + text
        )
        return chat([{"role": "user", "content": prompt}]).content

    def remember(self, key, value):
        lowered = str(key).lower()
        if any(token in lowered for token in ("hidden", "secret", "evidence", "证据")):
            raise ValueError("隐藏证据不得写入长期画像")
        self.profile[str(key)] = value

    def build(self, system):
        messages = [{"role": "system", "content": system}]
        if self.profile:
            messages.append({"role": "system", "content": "用户画像:" + str(self.profile)})
        if self.summary:
            messages.append({"role": "system", "content": "历史摘要:" + self.summary})
        return messages + list(self.history)

    def recall_item(self):
        for message in reversed(self.history):
            item_ids = re.findall(r"LF\d+", message.get("content", ""), re.I)
            if item_ids:
                return item_ids[-1].upper()
        item_ids = re.findall(r"LF\d+", self.summary, re.I)
        return item_ids[-1].upper() if item_ids else None
