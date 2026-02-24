"""
Background thread for checking GitHub releases
"""

import json
import logging
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal  # type: ignore

logger = logging.getLogger(__name__)


class UpdateCheckThread(QThread):
    """Background thread for checking GitHub releases without blocking UI"""

    update_result = pyqtSignal(bool, object)  # success: bool, data: dict or error_msg: str

    def __init__(self, current_version: str):
        super().__init__()
        self.setObjectName("UpdateCheckThread")
        self.current_version = current_version

    def run(self) -> None:
        """Check GitHub API in background"""
        try:
            url = "https://api.github.com/repos/jpwalters/VideoCue/releases/latest"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("X-GitHub-Api-Version", "2022-11-28")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                logger.debug(f"GitHub API returned: {data.get('tag_name', 'Unknown')}")
                self.update_result.emit(True, data)
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            import traceback

            traceback.print_exc()
            self.update_result.emit(False, str(e))
