import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default
from pathlib import Path
from typing import Any


@dataclass
class StoredMessage:
    id: str
    received_at: str
    mail_from: str
    rcpt_tos: list[str]
    subject: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MailStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()
        self.inbox_dir = self.data_dir / "inbox"
        self.index_path = self.data_dir / "index.json"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index([])

    def _read_index(self) -> list[dict[str, Any]]:
        with self.index_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_index(self, rows: list[dict[str, Any]]) -> None:
        with self.index_path.open("w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)

    def save(
        self,
        raw: bytes,
        mail_from: str,
        rcpt_tos: list[str],
    ) -> StoredMessage:
        msg_id = uuid.uuid4().hex
        received_at = datetime.now(timezone.utc).isoformat()
        file_path = self.inbox_dir / f"{msg_id}.eml"

        with file_path.open("wb") as f:
            f.write(raw)

        parsed = message_from_bytes(raw, policy=default)
        subject = parsed.get("Subject", "") or ""

        relative_path = f"inbox/{msg_id}.eml"
        record = StoredMessage(
            id=msg_id,
            received_at=received_at,
            mail_from=mail_from,
            rcpt_tos=list(rcpt_tos),
            subject=subject,
            path=relative_path,
        )

        index = self._read_index()
        index.insert(0, record.to_dict())
        self._write_index(index)
        return record

    def list_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        index = self._read_index()
        return index[:limit]

    def _resolve_path(self, stored_path: str) -> Path:
        path = Path(stored_path)
        if path.is_absolute():
            return path
        return self.data_dir / path

    def get_message(self, msg_id: str) -> tuple[StoredMessage, bytes] | None:
        for row in self._read_index():
            if row["id"] == msg_id:
                path = self._resolve_path(row["path"])
                if not path.exists():
                    return None
                record = StoredMessage(**row)
                return record, path.read_bytes()
        return None
