# -*- coding: utf-8 -*-
"""“寻迹校园”教学数据。所有状态均为进程内存数据。"""

import re
from datetime import date, timedelta

ITEMS = {
    "LF2026001": {
        "item_id": "LF2026001",
        "category": "蓝牙耳机",
        "color": "黑色",
        "found_location": "图书馆",
        "found_date": "2026-06-28",
        "public_description": "黑色入耳式蓝牙耳机和充电盒",
        "secret_features": ["盒内刻有ZL", "左耳有划痕"],
        "secret_keywords": [["zl"], ["左耳", "划痕"]],
        "high_value": False,
        "status": "待认领",
    },
    "LF2026002": {
        "item_id": "LF2026002",
        "category": "笔记本电脑",
        "color": "银色",
        "found_location": "教学楼",
        "found_date": "2026-06-27",
        "public_description": "银色轻薄笔记本电脑",
        "secret_features": ["底部有星空贴纸", "序列号后四位A7C9"],
        "secret_keywords": [["星空", "贴纸"], ["a7c9"]],
        "high_value": True,
        "status": "待认领",
    },
    "LF2026003": {
        "item_id": "LF2026003",
        "category": "校园卡",
        "color": "蓝色",
        "found_location": "食堂",
        "found_date": "2026-06-29",
        "public_description": "带蓝色卡套的校园卡",
        "secret_features": ["姓名为张同学", "学号后四位0629"],
        "secret_keywords": [["张同学"], ["0629"]],
        "high_value": False,
        "status": "待认领",
    },
}

CLAIMS = {}
APPOINTMENTS = {}

HANDOVER_SLOTS = {
    "LF2026001": ["2026-06-30 16:00 图书馆服务台", "2026-07-01 10:00 图书馆服务台"],
    "LF2026002": ["2026-06-30 15:00 保卫处", "2026-07-01 15:00 保卫处"],
    "LF2026003": ["2026-06-30 12:30 食堂服务台"],
}

POLICIES = {
    "自动认领": "普通物品证据匹配度达到80分可自动通过认领。",
    "高价值物品": "手机、电脑和贵重首饰必须转人工复核。",
    "隐私保护": "系统不得向申请人公开失物的隐藏特征。",
    "交接时限": "认领通过后应在3日内完成线下交接。",
    "实名证件": "校园卡等实名证件只能交给实名一致的申请人。",
}

_PRIVATE_ITEM_FIELDS = {"secret_features", "secret_keywords"}
_REQUIRED_FOUND_ITEM_FIELDS = (
    "category",
    "color",
    "found_location",
    "found_date",
    "public_description",
    "secret_features",
)


def public_item(item):
    return {
        key: value
        for key, value in item.items()
        if key not in _PRIVATE_ITEM_FIELDS
    }


def _next_item_id():
    numbers = []
    for item_id in ITEMS:
        match = re.fullmatch(r"LF(\d+)", str(item_id), re.I)
        if match:
            numbers.append(int(match.group(1)))
    return f"LF{max(numbers, default=2026000) + 1:07d}"


def _split_secret_features(value):
    if isinstance(value, list):
        features = [str(feature).strip() for feature in value]
    else:
        features = [
            feature.strip()
            for feature in re.split(r"[\n,，;；]+", str(value or ""))
        ]
    return [feature for feature in features if feature]


def _secret_keywords(secret_features):
    keywords = []
    for feature in secret_features:
        tokens = re.findall(r"[A-Za-z0-9]+", feature)
        if tokens:
            keywords.append([token.lower() for token in tokens])
        else:
            keywords.append([feature.lower()])
    return keywords


def _is_high_value(category):
    return any(
        keyword in str(category)
        for keyword in ("手机", "电脑", "笔记本", "首饰", "贵重")
    )


def _default_handover_slots(item_id, found_location, found_date):
    try:
        base_date = date.fromisoformat(str(found_date))
    except ValueError:
        base_date = date.today()
    location = str(found_location).strip()
    desk = location if location.endswith("服务台") else location + "服务台"
    HANDOVER_SLOTS[item_id] = [
        f"{base_date + timedelta(days=1)} 16:00 {desk}",
        f"{base_date + timedelta(days=2)} 10:00 {desk}",
    ]


def add_found_item(payload):
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是JSON对象")
    normalized = {}
    missing = []
    for field in _REQUIRED_FOUND_ITEM_FIELDS:
        value = payload.get(field)
        if field == "secret_features":
            value = _split_secret_features(value)
            if not value:
                missing.append(field)
        else:
            value = str(value or "").strip()
            if not value:
                missing.append(field)
        normalized[field] = value
    if missing:
        raise ValueError("缺少字段:" + ",".join(missing))
    try:
        date.fromisoformat(normalized["found_date"])
    except ValueError as error:
        raise ValueError("found_date必须是YYYY-MM-DD") from error

    item_id = _next_item_id()
    item = {
        "item_id": item_id,
        "category": normalized["category"],
        "color": normalized["color"],
        "found_location": normalized["found_location"],
        "found_date": normalized["found_date"],
        "public_description": normalized["public_description"],
        "secret_features": normalized["secret_features"],
        "secret_keywords": _secret_keywords(normalized["secret_features"]),
        "high_value": _is_high_value(normalized["category"]),
        "status": "待认领",
    }
    ITEMS[item_id] = item
    _default_handover_slots(
        item_id, normalized["found_location"], normalized["found_date"]
    )
    return item
