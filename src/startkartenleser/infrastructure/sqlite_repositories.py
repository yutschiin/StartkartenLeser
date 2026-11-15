"""SQLite repositories, schema migration, recovery, and retryable image cleanup."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterator, Mapping

from startkartenleser.application.ports import ConcurrentCardUpdate
from startkartenleser.domain.contracts import (
    Card,
    CardEvent,
    CardId,
    CardState,
    CheckboxState,
    CheckboxValue,
    FieldProvenance,
    FieldReviewStatus,
    FieldValue,
    Session,
    SessionId,
    SharedTextCandidate,
)
from startkartenleser.domain.rules import InvalidCardTransition, transition_card
from startkartenleser.infrastructure.image_store import ManagedImageStore


SCHEMA_VERSION = 3


class CleanupPendingError(RuntimeError):
    """A delete was committed, but one or more managed files need retry cleanup."""


class SqliteRepositories:
    """Implements session/card repositories and a durable image-deletion outbox."""

    def __init__(self, database_path: Path | str, images: ManagedImageStore | None = None):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.images = images
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        try:
            with self._lock:
                self._connection.execute("PRAGMA foreign_keys = ON")
                self._connection.execute("PRAGMA busy_timeout = 10000")
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._migrate()
                self._recover_interrupted_cards()
        except Exception:
            self._connection.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        """Keep related reads consistent with writes on this shared connection."""
        with self._lock:
            yield

    def create_session(self, session: Session) -> Session:
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO sessions(
                    id,title,created_at,revision,number,distance_m,stroke,gender
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (session.id, session.title, _datetime_text(session.created_at), session.revision,
                 session.number, session.distance_m, session.stroke, session.gender),
            )
        return session

    def get_session(self, session_id: SessionId) -> Session | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        return _session_from_row(row) if row else None

    def list_sessions(self) -> tuple[Session, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC, id"
            ).fetchall()
        return tuple(_session_from_row(row) for row in rows)

    def delete_session(self, session_id: SessionId) -> None:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT image_reference FROM cards WHERE session_id=? AND image_reference IS NOT NULL",
                (session_id,),
            ).fetchall()
            self._enqueue_images(connection, (row[0] for row in rows))
            connection.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.retry_pending_cleanup()

    def create_card(self, card: Card) -> Card:
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO cards(
                    id,session_id,sequence,state,image_reference,schema_version,
                    model_version,crop_version,revision,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    card.id,
                    card.session_id,
                    card.sequence,
                    card.state.value,
                    card.image_reference,
                    card.schema_version,
                    card.model_version,
                    card.crop_version,
                    card.revision,
                    _datetime_text(card.created_at),
                    _datetime_text(card.updated_at),
                ),
            )
        return card

    def get_card(self, card_id: CardId) -> Card | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(row) if row else None

    def list_cards(self, session_id: SessionId) -> tuple[Card, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM cards WHERE session_id=? ORDER BY sequence ASC", (session_id,)
            ).fetchall()
        return tuple(_card_from_row(row) for row in rows)

    def next_sequence(self, session_id: SessionId) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 AS next FROM cards WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return int(row["next"])

    def transition_card(
        self, card_id: CardId, expected_revision: int, event: CardEvent
    ) -> Card:
        with self._transaction() as connection:
            row = self._expect_revision(connection, card_id, expected_revision)
            current = _card_from_row(row)
            try:
                next_state = transition_card(current.state, event)
            except InvalidCardTransition:
                raise
            updated_at = datetime.now(timezone.utc)
            cursor = connection.execute(
                "UPDATE cards SET state=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                (next_state.value, _datetime_text(updated_at), card_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ConcurrentCardUpdate("stale card revision")
            updated = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(updated)

    def get_field_values(self, card_id: CardId) -> Mapping[str, FieldValue]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM field_values WHERE card_id=? ORDER BY field_key", (card_id,)
            ).fetchall()
        return {row["field_key"]: _field_from_row(row) for row in rows}

    def get_checkbox_values(self, card_id: CardId) -> Mapping[str, CheckboxValue]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM checkbox_values WHERE card_id=? ORDER BY field_key", (card_id,)
            ).fetchall()
        return {row["field_key"]: _checkbox_from_row(row) for row in rows}

    def get_shared_candidates(self, card_id: CardId) -> Mapping[str, SharedTextCandidate]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM shared_candidates WHERE card_id=? ORDER BY region_key", (card_id,)
            ).fetchall()
        return {row["region_key"]: _shared_from_row(row) for row in rows}

    def get_reference_check(self, card_id: CardId) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT reference_check_json FROM cards WHERE id=?", (card_id,)
            ).fetchone()
        if row is None or row["reference_check_json"] is None:
            return None
        return json.loads(row["reference_check_json"])["response"]

    def get_reference_evidence(self, card_id: CardId) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT reference_check_json FROM cards WHERE id=?", (card_id,)
            ).fetchone()
        if row is None or row["reference_check_json"] is None:
            return None
        return json.loads(row["reference_check_json"])["evidence"]

    def save_reference_result(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
        reference_check: dict,
        evidence: dict,
    ) -> Card:
        """Persist the authoritative event fields and this run's comparison atomically."""
        with self._transaction() as connection:
            self._expect_revision(connection, card_id, expected_revision)
            for value in fields.values():
                connection.execute(
                    """INSERT INTO field_values(
                        card_id,field_key,value_json,provenance,review_status,
                        raw_transcription,confidence,confirmed,source_region
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(card_id,field_key) DO UPDATE SET
                        value_json=excluded.value_json,
                        provenance=excluded.provenance,
                        review_status=excluded.review_status,
                        raw_transcription=excluded.raw_transcription,
                        confidence=excluded.confidence,
                        confirmed=excluded.confirmed,
                        source_region=excluded.source_region""",
                    (
                        card_id, value.field_key, json.dumps(value.value, ensure_ascii=False),
                        value.provenance.value, value.review_status.value,
                        value.raw_transcription, value.confidence, int(value.confirmed),
                        value.source_region,
                    ),
                )
            for value in checkboxes.values():
                connection.execute(
                    """INSERT INTO checkbox_values(card_id,field_key,state,provenance,confirmed)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(card_id,field_key) DO UPDATE SET
                        state=excluded.state,provenance=excluded.provenance,
                        confirmed=excluded.confirmed""",
                    (
                        card_id, value.field_key, value.state.value,
                        value.provenance.value if value.provenance else None,
                        int(value.confirmed),
                    ),
                )
            persisted_check = {
                "response": reference_check,
                "evidence": evidence,
            }
            connection.execute(
                """UPDATE cards SET reference_check_json=?,revision=revision+1,updated_at=?
                   WHERE id=? AND revision=?""",
                (
                    json.dumps(persisted_check, ensure_ascii=False),
                    _datetime_text(datetime.now(timezone.utc)),
                    card_id,
                    expected_revision,
                ),
            )
            row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(row)

    def save_recognition(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
        shared_candidates: Mapping[str, SharedTextCandidate],
        model_version: str,
    ) -> Card:
        with self._transaction() as connection:
            row = self._expect_revision(connection, card_id, expected_revision)
            if CardState(row["state"]) is not CardState.RECOGNIZING:
                raise ConcurrentCardUpdate("card is no longer recognizing")
            self._replace_values(connection, card_id, fields, checkboxes, shared_candidates)
            cursor = connection.execute(
                """UPDATE cards SET state=?,model_version=?,revision=revision+1,updated_at=?
                   WHERE id=? AND revision=?""",
                (
                    CardState.NEEDS_REVIEW.value,
                    model_version,
                    _datetime_text(datetime.now(timezone.utc)),
                    card_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrentCardUpdate("stale card revision")
            updated = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(updated)

    def save_review(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
    ) -> Card:
        with self._transaction() as connection:
            row = self._expect_revision(connection, card_id, expected_revision)
            current_state = CardState(row["state"])
            if current_state not in (CardState.NEEDS_REVIEW, CardState.REVIEWED):
                raise InvalidCardTransition("card is not in review")
            self._replace_values(
                connection,
                card_id,
                fields,
                checkboxes,
                self._get_shared_candidates(connection, card_id),
            )
            cursor = connection.execute(
                "UPDATE cards SET state=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                (
                    CardState.REVIEWED.value,
                    _datetime_text(datetime.now(timezone.utc)),
                    card_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrentCardUpdate("stale card revision")
            updated = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(updated)

    def delete_card(self, card_id: CardId) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT image_reference FROM cards WHERE id=?", (card_id,)
            ).fetchone()
            if row is None:
                return
            self._enqueue_images(connection, (row["image_reference"],))
            connection.execute("DELETE FROM cards WHERE id=?", (card_id,))
        self.retry_pending_cleanup()

    def save_draft(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
    ) -> Card:
        """Persist edits without approval, invalidating any in-flight recognition."""
        with self._transaction() as connection:
            self._expect_revision(connection, card_id, expected_revision)
            self._replace_values(
                connection, card_id, fields, checkboxes,
                self._get_shared_candidates(connection, card_id),
            )
            connection.execute(
                "UPDATE cards SET state=?,revision=revision+1,updated_at=? WHERE id=?",
                (CardState.NEEDS_REVIEW.value,
                 _datetime_text(datetime.now(timezone.utc)), card_id),
            )
            row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(row)

    def capture_request(self, request_id: str, fingerprint: str) -> Card | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None:
                return None
            if row["fingerprint"] != fingerprint:
                raise ConcurrentCardUpdate("capture request was reused with different input")
            return self.get_card(row["card_id"])

    def save_capture(
        self, card: Card, request_id: str, fingerprint: str,
        *, replace_card_id: str | None = None, expected_revision: int | None = None,
        fields: Mapping[str, FieldValue] | None = None,
        checkboxes: Mapping[str, CheckboxValue] | None = None,
    ) -> Card:
        """Allocate a sequence or replace one image, atomically with deduplication."""
        with self._transaction() as connection:
            duplicate = self.capture_request(request_id, fingerprint)
            if duplicate is not None:
                return duplicate
            if replace_card_id is None:
                card = replace(card, sequence=self.next_sequence(card.session_id))
                connection.execute(
                    """INSERT INTO cards(id,session_id,sequence,state,image_reference,
                       schema_version,crop_version,revision,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (card.id, card.session_id, card.sequence, card.state.value,
                     card.image_reference, card.schema_version, card.crop_version,
                     card.revision, _datetime_text(card.created_at), _datetime_text(card.updated_at)),
                )
                self._replace_values(connection, card.id, fields or {}, checkboxes or {}, {})
            else:
                if expected_revision is None:
                    raise ValueError("retake requires a revision")
                row = self._expect_revision(connection, replace_card_id, expected_revision)
                if row["session_id"] != card.session_id:
                    raise ValueError("retake must keep its Wettkampf")
                self._enqueue_images(connection, (row["image_reference"],))
                self._replace_values(
                    connection, replace_card_id, fields or {}, checkboxes or {}, {},
                )
                connection.execute(
                    """UPDATE cards SET state=?,image_reference=?,model_version=NULL,
                       reference_check_json=NULL,revision=revision+1,updated_at=? WHERE id=?""",
                    (CardState.NEEDS_REVIEW.value, card.image_reference,
                     _datetime_text(card.updated_at), replace_card_id),
                )
                card = _card_from_row(connection.execute(
                    "SELECT * FROM cards WHERE id=?", (replace_card_id,)
                ).fetchone())
            connection.execute(
                "INSERT INTO capture_requests(request_id,fingerprint,card_id) VALUES(?,?,?)",
                (request_id, fingerprint, card.id),
            )
        return card

    def move_card(self, card_id: str, expected_revision: int, session_id: str) -> Card:
        with self._transaction() as connection:
            row = self._expect_revision(connection, card_id, expected_revision)
            destination = self.get_session(session_id)
            if destination is None or destination.number is None:
                raise ValueError("destination must be a classified Wettkampf")
            if row["session_id"] == session_id:
                raise ValueError("card already belongs to this Wettkampf")
            connection.execute(
                """UPDATE cards SET session_id=?,sequence=?,state=?,
                   revision=revision+1,updated_at=? WHERE id=?""",
                (session_id, self.next_sequence(session_id), CardState.NEEDS_REVIEW.value,
                 _datetime_text(datetime.now(timezone.utc)), card_id),
            )
            connection.execute(
                "UPDATE field_values SET confirmed=0 WHERE card_id=?", (card_id,)
            )
            connection.execute(
                "UPDATE field_values SET review_status=? WHERE card_id=?",
                (FieldReviewStatus.CANDIDATE.value, card_id),
            )
            connection.execute(
                "UPDATE checkbox_values SET confirmed=0 WHERE card_id=?", (card_id,)
            )
            updated = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _card_from_row(updated)

    def retry_pending_cleanup(self) -> None:
        if self.images is None:
            with self._lock:
                pending = self._connection.execute(
                    "SELECT COUNT(*) FROM pending_image_deletions"
                ).fetchone()[0]
            if pending:
                raise CleanupPendingError("managed image cleanup is unavailable")
            return
        with self._lock:
            rows = self._connection.execute(
                "SELECT image_reference FROM pending_image_deletions ORDER BY image_reference"
            ).fetchall()
        for row in rows:
            reference = row["image_reference"]
            try:
                self.images.delete_image(reference)
            except Exception as error:
                raise CleanupPendingError("managed image cleanup is pending") from error
            with self._transaction() as connection:
                connection.execute(
                    "DELETE FROM pending_image_deletions WHERE image_reference=?", (reference,)
                )

    def cleanup_storage_orphans(self) -> None:
        """Retry durable deletions, then remove crash-left unreferenced images."""
        if self.images is None:
            return
        self.retry_pending_cleanup()
        with self._lock:
            rows = self._connection.execute(
                "SELECT image_reference FROM cards WHERE image_reference IS NOT NULL"
            ).fetchall()
        referenced = {row["image_reference"] for row in rows}
        for reference in self.images.list_image_references():
            if reference not in referenced:
                self.images.delete_image(reference)
        self.images.cleanup_temporary_files()

    def pending_cleanup_count(self) -> int:
        with self._lock:
            return int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM pending_image_deletions"
                ).fetchone()[0]
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _migrate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"database schema {version} is newer than supported")
        if version == 1:
            backup = self.database_path.with_suffix(".before-v2.sqlite3")
            if backup.exists():
                raise RuntimeError(
                    f"migration backup already exists: {backup}; preserve or move it before retrying"
                )
            with sqlite3.connect(backup) as snapshot:
                self._connection.backup(snapshot)
        if version == 0:
            try:
                self._connection.executescript(
                    """
                    BEGIN EXCLUSIVE;
                    CREATE TABLE sessions(
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        revision INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE cards(
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                        sequence INTEGER NOT NULL CHECK(sequence > 0),
                        state TEXT NOT NULL,
                        image_reference TEXT,
                        schema_version TEXT NOT NULL,
                        model_version TEXT,
                        crop_version TEXT NOT NULL DEFAULT 'startkarte-crops-v5',
                        revision INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT,
                        updated_at TEXT,
                        UNIQUE(session_id, sequence)
                    );
                    CREATE INDEX cards_session_order ON cards(session_id, sequence);
                    CREATE TABLE field_values(
                        card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                        field_key TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        provenance TEXT NOT NULL,
                        review_status TEXT NOT NULL,
                        raw_transcription TEXT,
                        confidence REAL,
                        confirmed INTEGER NOT NULL DEFAULT 0,
                        source_region TEXT,
                        PRIMARY KEY(card_id, field_key)
                    );
                    CREATE TABLE checkbox_values(
                        card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                        field_key TEXT NOT NULL,
                        state TEXT NOT NULL,
                        provenance TEXT,
                        confirmed INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(card_id, field_key)
                    );
                    CREATE TABLE shared_candidates(
                        card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                        region_key TEXT NOT NULL,
                        raw_text TEXT NOT NULL,
                        confidence REAL,
                        provenance TEXT NOT NULL,
                        confirmed INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(card_id, region_key)
                    );
                    CREATE TABLE pending_image_deletions(
                        image_reference TEXT PRIMARY KEY
                    );
                    PRAGMA user_version = 1;
                    COMMIT;
                    """
                )
            except Exception:
                self._connection.rollback()
                raise
        if version < 2:
            try:
                self._connection.executescript(
                    """
                    BEGIN EXCLUSIVE;
                    ALTER TABLE sessions ADD COLUMN number INTEGER CHECK(number > 0);
                    ALTER TABLE sessions ADD COLUMN distance_m INTEGER CHECK(distance_m > 0);
                    ALTER TABLE sessions ADD COLUMN stroke TEXT;
                    ALTER TABLE sessions ADD COLUMN gender TEXT;
                    CREATE TABLE capture_requests(
                        request_id TEXT PRIMARY KEY,
                        fingerprint TEXT NOT NULL,
                        card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE
                    );
                    PRAGMA user_version = 2;
                    COMMIT;
                    """
                )
            except Exception:
                self._connection.rollback()
                raise
        if version < 3:
            try:
                columns = {
                    row["name"] for row in self._connection.execute("PRAGMA table_info(cards)")
                }
                self._connection.executescript(
                    """
                    BEGIN EXCLUSIVE;
                    """
                    + (
                        "ALTER TABLE cards ADD COLUMN reference_check_json TEXT;\n"
                        if "reference_check_json" not in columns else ""
                    )
                    + """
                    PRAGMA user_version = 3;
                    COMMIT;
                    """
                )
            except Exception:
                self._connection.rollback()
                raise

    def _recover_interrupted_cards(self) -> None:
        now = _datetime_text(datetime.now(timezone.utc))
        with self._transaction() as connection:
            connection.execute(
                """UPDATE cards SET state=?,revision=revision+1,updated_at=?
                   WHERE state IN (?,?)""",
                (
                    CardState.NEEDS_REVIEW.value,
                    now,
                    CardState.ALIGNING.value,
                    CardState.RECOGNIZING.value,
                ),
            )

    def _expect_revision(
        self, connection: sqlite3.Connection, card_id: CardId, expected_revision: int
    ) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if row is None or int(row["revision"]) != expected_revision:
            raise ConcurrentCardUpdate("stale card revision")
        return row

    def _replace_values(
        self,
        connection: sqlite3.Connection,
        card_id: CardId,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
        shared_candidates: Mapping[str, SharedTextCandidate],
    ) -> None:
        connection.execute("DELETE FROM field_values WHERE card_id=?", (card_id,))
        connection.execute("DELETE FROM checkbox_values WHERE card_id=?", (card_id,))
        connection.execute("DELETE FROM shared_candidates WHERE card_id=?", (card_id,))
        connection.executemany(
            """INSERT INTO field_values(
                card_id,field_key,value_json,provenance,review_status,
                raw_transcription,confidence,confirmed,source_region
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                (
                    card_id,
                    key,
                    json.dumps(value.value, ensure_ascii=False),
                    value.provenance.value,
                    value.review_status.value,
                    value.raw_transcription,
                    value.confidence,
                    int(value.confirmed),
                    value.source_region,
                )
                for key, value in fields.items()
            ),
        )
        connection.executemany(
            """INSERT INTO checkbox_values(card_id,field_key,state,provenance,confirmed)
               VALUES(?,?,?,?,?)""",
            (
                (
                    card_id,
                    key,
                    value.state.value,
                    value.provenance.value if value.provenance else None,
                    int(value.confirmed),
                )
                for key, value in checkboxes.items()
            ),
        )
        connection.executemany(
            """INSERT INTO shared_candidates(
                card_id,region_key,raw_text,confidence,provenance,confirmed
            ) VALUES(?,?,?,?,?,?)""",
            (
                (
                    card_id,
                    key,
                    value.raw_text,
                    value.confidence,
                    value.provenance.value,
                    int(value.confirmed),
                )
                for key, value in shared_candidates.items()
            ),
        )

    def _get_shared_candidates(
        self, connection: sqlite3.Connection, card_id: CardId
    ) -> Mapping[str, SharedTextCandidate]:
        rows = connection.execute(
            "SELECT * FROM shared_candidates WHERE card_id=?", (card_id,)
        ).fetchall()
        return {row["region_key"]: _shared_from_row(row) for row in rows}

    @staticmethod
    def _enqueue_images(connection: sqlite3.Connection, references) -> None:
        connection.executemany(
            "INSERT OR IGNORE INTO pending_image_deletions(image_reference) VALUES(?)",
            ((reference,) for reference in references if reference),
        )


def _session_from_row(row: sqlite3.Row) -> Session:
    return Session(
        row["id"], row["title"], datetime.fromisoformat(row["created_at"]), row["revision"],
        row["number"], row["distance_m"], row["stroke"], row["gender"],
    )


def _card_from_row(row: sqlite3.Row) -> Card:
    return Card(
        id=row["id"],
        session_id=row["session_id"],
        sequence=row["sequence"],
        state=CardState(row["state"]),
        image_reference=row["image_reference"],
        schema_version=row["schema_version"],
        model_version=row["model_version"],
        crop_version=row["crop_version"],
        revision=row["revision"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
    )


def _field_from_row(row: sqlite3.Row) -> FieldValue:
    return FieldValue(
        field_key=row["field_key"],
        value=json.loads(row["value_json"]),
        provenance=FieldProvenance(row["provenance"]),
        review_status=FieldReviewStatus(row["review_status"]),
        raw_transcription=row["raw_transcription"],
        confidence=row["confidence"],
        confirmed=bool(row["confirmed"]),
        source_region=row["source_region"],
    )


def _checkbox_from_row(row: sqlite3.Row) -> CheckboxValue:
    return CheckboxValue(
        field_key=row["field_key"],
        state=CheckboxState(row["state"]),
        provenance=FieldProvenance(row["provenance"]) if row["provenance"] else None,
        confirmed=bool(row["confirmed"]),
    )


def _shared_from_row(row: sqlite3.Row) -> SharedTextCandidate:
    return SharedTextCandidate(
        region_key=row["region_key"],
        raw_text=row["raw_text"],
        confidence=row["confidence"],
        provenance=FieldProvenance(row["provenance"]),
        confirmed=bool(row["confirmed"]),
    )


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
