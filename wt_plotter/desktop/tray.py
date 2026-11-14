from pathlib import Path
import webbrowser

from PIL import Image, ImageDraw
import requests

from wt_plotter.i18n import get_language, translate


_icon = None


def _build_icon_image(size: int = 16) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, size - 1, size - 1), outline=(30, 144, 255, 255), width=2)
    radius = size // 5
    center = size // 2
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        fill=(250, 200, 30, 255),
    )
    return image


def menu_labels(settings_path: Path) -> tuple[str, str]:
    lang = get_language(settings_path)
    return translate(lang, "tray.open"), translate(lang, "tray.quit")


def start_tray(host: str, port: int, settings_path: Path) -> None:
    global _icon
    if _icon is not None:
        return
    import pystray

    url = f"http://{host}:{port}"

    def open_live():
        webbrowser.open(f"{url}/live")

    def quit_app():
        requests.post(f"{url}/shutdown", timeout=2.0).raise_for_status()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: menu_labels(settings_path)[0], open_live),
        pystray.MenuItem(lambda _: menu_labels(settings_path)[1], quit_app),
    )
    _icon = pystray.Icon("WT Plotter Plus", _build_icon_image(), "WT Plotter Plus", menu)
    _icon.run_detached()


def stop_tray() -> None:
    global _icon
    if _icon is not None:
        _icon.stop()
        _icon = None
