"""Separate worker entry point for crash/recovery checks and headless production."""

import os
import time
from pathlib import Path

from studio.storage import Store
from studio.worker import Worker


def main():
    worker = Worker(Store(Path(os.environ.get("STUDIO_DATA", "data"))))
    worker.start()
    try:
        while worker.thread and worker.thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        worker.close()


if __name__ == "__main__":
    main()
