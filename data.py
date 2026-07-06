# -*- coding: utf-8 -*-
"""“寻迹校园”教学数据。所有状态均为进程内存数据。"""

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

