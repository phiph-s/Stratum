# macOS packaging support
import sys
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

import multiprocessing
multiprocessing.set_start_method("spawn", force=True)

from nicegui import ui, app
from app.app import StratumApp


@ui.page('/')
def main_page():
    sapp = StratumApp()
    sapp.build()

# --browser
if '--browser' in sys.argv:
    ui.run(native=False, reload=True)
ui.run(native=True, window_size=(1480, 900), reload=False)
