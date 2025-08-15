# macOS packaging support
import sys
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

import multiprocessing
multiprocessing.set_start_method("spawn", force=True)

from nicegui import ui, app
from app.app import StratumApp

project_path = None

@ui.page('/')
def main_page():
    sapp = StratumApp()

    if project_path:
        try:
            with open(project_path, 'r') as f:
                content = f.read()
                sapp.project_io.load_project(content)
                sapp.project_io.last_saved_path = project_path
        except Exception as e:
            print(f"Error loading project {project_path}: {str(e)}")
            ui.notify(f'Error loading project: {str(e)}', color='red')
    else:
        sapp.new_project()


# define project with -p or --project
if '-p' in sys.argv or '--project' in sys.argv:
    project_index = sys.argv.index('-p') if '-p' in sys.argv else sys.argv.index('--project')
    project_path = sys.argv[project_index + 1]

reload = True if '--reload' in sys.argv else False

# --browser
if '--browser' in sys.argv:
    ui.run(native=False, reload=reload)
else:
    app.native.window_args['confirm_close'] = True
    ui.run(native=True, title="Stratum", window_size=(1480, 900), reload=reload)
