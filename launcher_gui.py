"""Entry point for source runs and the packaged Reloaded launcher."""

# The copied helper must run before normal imports resolve game/config paths.
import sys

if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--apply-update':
    from randomizer.core.update_helper import main as apply_update_main
    raise SystemExit(apply_update_main(sys.argv[2]))

import json
import traceback

from randomizer.audit import installation_report
from randomizer.config.game_profile import PRODUCT_NAME
from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import APP_DIR, LAUNCHER_LOG


def run_launcher():
    """Load config-dependent application modules with visible startup errors."""
    try:
        from randomizer.application.app import main
        main()
        return 0
    except Exception:
        detail = traceback.format_exc()
        log_event('launcher_startup_failed', traceback=detail)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                f'{PRODUCT_NAME} Startup Failed',
                'The launcher could not load its configuration or runtime.\n\n'
                f'{detail.splitlines()[-1]}\n\nSee {LAUNCHER_LOG} for details.',
            )
            root.destroy()
        except Exception:
            pass
        return 1


def run_self_check():
    """Write a read-only Reloaded foundation and installation report."""
    report_path = APP_DIR / 'self_check.json'
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        report = installation_report()
    except Exception:
        report = {'passed': False, 'traceback': traceback.format_exc()}
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    log_event('self_check_finished', **report)
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    if '--self-check' in sys.argv:
        raise SystemExit(run_self_check())
    raise SystemExit(run_launcher())
