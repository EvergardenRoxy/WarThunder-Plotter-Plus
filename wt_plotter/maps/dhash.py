from io import BytesIO

from PIL import Image


WIDTH = 16
HEIGHT = WIDTH - 1
# 缩略图里一整行都不超过这个亮度，说明这一行还没画出来。
BLANK_ROW_LEVEL = 8


def _thumbnail(image_data: bytes) -> bytes:
    with Image.open(BytesIO(image_data)) as image:
        return image.convert("L").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).tobytes()


def is_map_loaded(image_data: bytes) -> bool:
    """游戏刚进图时 map.img 会先返回上半部分全黑的半成品图。"""
    pixels = _thumbnail(image_data)
    return all(max(pixels[y * WIDTH:(y + 1) * WIDTH]) > BLANK_ROW_LEVEL for y in range(HEIGHT))


def compute_dhash(image_data: bytes) -> str:
    width, height = WIDTH, HEIGHT
    pixels = _thumbnail(image_data)

    bits = "".join(
        "1" if pixels[y * width + x] > pixels[y * width + x + 1] else "0"
        for y in range(height)
        for x in range(width - 1)
    )
    return "".join(
        format(int(bits[i:i + 4].ljust(4, "0"), 2), "x")
        for i in range(0, len(bits), 4)
    )
