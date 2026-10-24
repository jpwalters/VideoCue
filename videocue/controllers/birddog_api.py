"""
BirdDog REST API client (camera web API on port 8080)
"""

import ipaddress
import json
import logging
import urllib.request
from enum import Enum

from videocue.constants import BirdDogConstants

logger = logging.getLogger(__name__)


class BirdDogModel(Enum):
    P400 = "P400"
    P200 = "P200"
    UNKNOWN = "UNKNOWN"


class BirdDogAPIError(Exception):
    """Raised when a BirdDog REST request fails"""


class BirdDogAPI:
    """Minimal client for the BirdDog P-series REST API."""

    def __init__(self, ip: str, port: int = BirdDogConstants.REST_PORT, timeout: float = None):
        # Reject anything that is not a literal IP so requests can't be redirected to other hosts
        self.ip = str(ipaddress.ip_address(ip.strip()))
        self.port = int(port)
        self.timeout = timeout if timeout is not None else BirdDogConstants.REST_TIMEOUT_S
        self._model: BirdDogModel | None = None

    def _url(self, endpoint: str) -> str:
        if endpoint not in BirdDogConstants.ALLOWED_ENDPOINTS:
            raise BirdDogAPIError(f"Endpoint not allowed: {endpoint}")
        return f"http://{self.ip}:{self.port}/{endpoint}"

    def get_endpoint(self, endpoint: str) -> dict:
        request = urllib.request.Request(self._url(endpoint), method="GET")
        return self._send(request)

    def post_endpoint(self, endpoint: str, values: dict) -> dict:
        body = json.dumps({k: str(v) for k, v in values.items()}).encode("utf-8")
        request = urllib.request.Request(
            self._url(endpoint),
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return self._send(request)

    def _send(self, request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace").strip()
        except OSError as e:  # includes URLError, HTTPError and timeouts
            raise BirdDogAPIError(f"{request.get_method()} {request.full_url} failed: {e}") from e
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Some firmware answers POSTs with plain text such as "OK"
            return {"_raw": raw}
        return data if isinstance(data, dict) else {"_raw": data}

    def get_about(self) -> dict:
        return self.get_endpoint("about")

    def detect_model(self) -> BirdDogModel:
        if self._model is not None:
            return self._model
        about = self.get_about()
        text = f"{about.get('FirmwareVersion', '')} {about.get('HardwareVersion', '')}".upper()
        if "P400" in text:
            self._model = BirdDogModel.P400
        elif "P200" in text:
            self._model = BirdDogModel.P200
        else:
            self._model = BirdDogModel.UNKNOWN
        return self._model
