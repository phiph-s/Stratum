# macOS packaging support
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

import multiprocessing
multiprocessing.set_start_method("spawn", force=True)

from nicegui import ui
from app.app import StratumApp


@ui.page('/')
def main_page():
    app = StratumApp()
    app.build()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(native=False)
