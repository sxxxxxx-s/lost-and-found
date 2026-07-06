# -*- coding: utf-8 -*-
"""字符 n-gram 向量检索；NumPy 可用时加速，否则使用标准库。"""

import math
import os
import re

from data import POLICIES

try:
    import numpy as np
except ImportError:  # 教学环境未安装 NumPy 时仍可离线运行
    np = None


def _ngrams(text, sizes=(1, 2)):
    normalized = re.sub(r"\s+", "", str(text)).lower()
    grams = []
    for size in sizes:
        grams.extend(
            normalized[index : index + size]
            for index in range(max(0, len(normalized) - size + 1))
        )
    return grams


class VectorStore:
    def __init__(self, documents):
        self.ids = list(documents.keys())
        self.texts = list(documents.values())
        indexed_texts = [
            f"{document_id}:{text}"
            for document_id, text in zip(self.ids, self.texts)
        ]
        vocabulary = {}
        for text in indexed_texts:
            for gram in _ngrams(text):
                vocabulary.setdefault(gram, len(vocabulary))
        self.vocab = vocabulary

        rows = []
        for text in indexed_texts:
            vector = [0.0] * len(vocabulary)
            for gram in _ngrams(text):
                vector[vocabulary[gram]] += 1.0
            rows.append(vector)

        if np is not None:
            self.matrix = np.asarray(rows, dtype=np.float32)
            self.norms = np.linalg.norm(self.matrix, axis=1) + 1e-8
        else:
            self.matrix = rows
            self.norms = [math.sqrt(sum(value * value for value in row)) for row in rows]

    def _vectorize(self, query):
        vector = [0.0] * len(self.vocab)
        for gram in _ngrams(query):
            index = self.vocab.get(gram)
            if index is not None:
                vector[index] += 1.0
        if np is not None:
            return np.asarray(vector, dtype=np.float32)
        return vector

    def search(self, query, k=2):
        vector = self._vectorize(query)
        if np is not None:
            vector_norm = float(np.linalg.norm(vector))
            if vector_norm == 0:
                return []
            similarities = (self.matrix @ vector) / (self.norms * (vector_norm + 1e-8))
            order = np.argsort(-similarities)[: max(0, k)]
            return [
                (self.ids[index], self.texts[index], float(similarities[index]))
                for index in order
                if similarities[index] > 0
            ]

        vector_norm = math.sqrt(sum(value * value for value in vector))
        if vector_norm == 0:
            return []
        scored = []
        for index, row in enumerate(self.matrix):
            denominator = self.norms[index] * vector_norm
            similarity = (
                sum(left * right for left, right in zip(row, vector)) / denominator
                if denominator
                else 0.0
            )
            if similarity > 0:
                scored.append((self.ids[index], self.texts[index], float(similarity)))
        scored.sort(key=lambda result: (-result[2], result[0]))
        return scored[: max(0, k)]


KB = VectorStore(POLICIES)


def policy_k():
    """读取并约束评测使用的默认政策检索条数。"""
    try:
        return max(1, min(int(os.getenv("POLICY_K", "2")), len(POLICIES)))
    except ValueError:
        return 2


def retrieve(query, k=None):
    selected_k = policy_k() if k is None else k
    return [
        text for _document_id, text, _score in KB.search(query, selected_k)
    ]


def retrieve_scored(query, k=3):
    return KB.search(query, k)


if __name__ == "__main__":
    for question in ["高价值电脑怎么认领", "隐藏特征能公开吗", "多久完成交接"]:
        print(f"\n问:{question}")
        for document_id, text, score in retrieve_scored(question, 2):
            print(f"  [{score:.3f}] {document_id}: {text}")
