"""确定性的本地词面特征，用于单 DeepSeek Key 模式；不属于语义 embedding。"""

import hashlib
import math
import re
from collections import Counter

DIMENSIONS = 512


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        features = []
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()):
            if re.fullmatch(r"[a-z0-9]+", token):
                features.append(token)
            else:
                features.extend(
                    token[i : i + size] for size in (1, 2, 3) for i in range(len(token) - size + 1)
                )
        vector = [0.0] * DIMENSIONS
        for feature, count in Counter(features).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "little") % DIMENSIONS
            vector[index] += 1.0 + math.log(count)
        norm = math.sqrt(sum(value * value for value in vector))
        vectors.append([value / norm for value in vector] if norm else vector)
    return vectors
