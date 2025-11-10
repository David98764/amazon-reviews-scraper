import io
import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional, TextIO

logger = logging.getLogger(__name__)

class StorageManager:
    """
    Simple abstraction around filesystem operations so they can be swapped or
    extended in future (e.g., to use S3, GCS, etc.).
    """

    def ensure_directory(self, path: str) -> None:
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create directory %s: %s", path, exc)
            raise

    @contextmanager
    def open_for_write(
        self,
        path: str,
        binary: bool = False,
        newline: Optional[str] = None,
    ) -> Generator[TextIO, None, None]:
        mode = "wb" if binary else "w"
        kwargs: dict = {"encoding": "utf-8"} if not binary else {}
        if newline is not None:
            kwargs["newline"] = newline

        try:
            self.ensure_directory(os.path.dirname(path))
            with open(path, mode, **kwargs) as f:
                yield f
        except OSError as exc:
            logger.error("Failed to open %s for writing: %s", path, exc)
            raise

    @contextmanager
    def open_for_read(
        self,
        path: str,
        binary: bool = False,
    ) -> Generator[io.IOBase, None, None]:
        mode = "rb" if binary else "r"
        kwargs: dict = {"encoding": "utf-8"} if not binary else {}
        try:
            with open(path, mode, **kwargs) as f:
                yield f
        except OSError as exc:
            logger.error("Failed to open %s for reading: %s", path, exc)
            raise