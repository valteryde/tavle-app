import re
from typing import Any

import httpx

SETUP_TOKEN_RE = re.compile(r'id="apiToken"\s+value="([^"]+)"')


class TavleClient:
    def __init__(self, base_url: str, admin_token: str | None):
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token

    def _headers(self) -> dict[str, str]:
        if not self.admin_token:
            return {}
        return {"Authorization": f"Bearer {self.admin_token}"}

    async def health(self) -> bool:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                r = await client.get(f"{self.base_url}/health")
                return r.status_code == 200
            except httpx.HTTPError:
                return False

    async def list_boards(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/api/boards", headers=self._headers()
            )
            r.raise_for_status()
            data = r.json()
            return data.get("boards", [])

    async def create_board(self, name: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/api/boards",
                headers=self._headers(),
                json={"name": name},
            )
            r.raise_for_status()
            return r.json()["board"]

    async def delete_board(self, board_id: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.delete(
                f"{self.base_url}/api/boards/{board_id}",
                headers=self._headers(),
            )
            r.raise_for_status()

    async def fetch_setup_token(self) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(f"{self.base_url}/setup")
            r.raise_for_status()
            match = SETUP_TOKEN_RE.search(r.text)
            if not match:
                raise RuntimeError("Could not parse admin token from Tavle setup page")
            return match.group(1)

    async def complete_setup(self) -> None:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.post(f"{self.base_url}/setup/complete")
            if r.status_code >= 400:
                raise RuntimeError(f"Setup complete failed: {r.status_code}")
