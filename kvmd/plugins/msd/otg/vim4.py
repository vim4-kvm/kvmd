"""Read-only shared catalog entries for the board-owned media helper."""

import asyncio
import dataclasses
import json
import os

from .. import MsdOperationError
from .storage import FileImage


async def catalog() -> list[dict]:
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/sudo", "-n", "/usr/libexec/vim4-pikvm-media", "catalog",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise MsdOperationError(stderr.decode().strip() or "VIM4 catalog unavailable")
    return json.loads(stdout)


@dataclasses.dataclass(frozen=True, init=False)
class _CatalogImageDc(FileImage):
    source: str


class CatalogImage(_CatalogImageDc):
    def __init__(self, entry: dict) -> None:
        roots = {
            "shared": "/var/lib/vim4-kvm/images",
            "jetkvm": "/var/lib/jetkvm/images",
            "onekvm": "/var/lib/one-kvm/msd",
            "data": "/var/lib/vim4-kvm/usb",
        }
        super().__init__(os.path.join(roots[entry["source"]], entry["name"]),
                         "VIM4/" + entry["id"], True, True)
        object.__setattr__(self, "source", entry["source"])
        object.__setattr__(self, "size", entry["size"])
        object.__setattr__(self, "complete", True)
        object.__setattr__(self, "cdromable", entry["cdrom"])

    async def _reload(self) -> None:
        pass  # Metadata comes from the privileged catalog, including root-only disks.

    async def exists(self) -> bool:
        return any("VIM4/" + entry["id"] == self.name for entry in await catalog())


async def images() -> dict[str, FileImage]:
    result = {}
    for entry in await catalog():
        if entry["source"] != "pikvm":
            image = CatalogImage(entry)
            result[image.name] = image
    return result
