from io import BytesIO

from PIL import Image


def compute_dhash(image_data: bytes) -> str:
    width = 16
    height = width - 1
    with Image.open(BytesIO(image_data)) as image:
        pixels = image.convert("L").resize((width, height), Image.Resampling.LANCZOS).tobytes()

    bits = "".join(
        "1" if pixels[y * width + x] > pixels[y * width + x + 1] else "0"
        for y in range(height)
        for x in range(width - 1)
    )
    return "".join(
        format(int(bits[i:i + 4].ljust(4, "0"), 2), "x")
        for i in range(0, len(bits), 4)
    )
