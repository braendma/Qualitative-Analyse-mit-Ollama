#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Gemeinsame, defensive Infrastruktur für Coding-Validierungsmodule."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

LOGGER = logging.getLogger("coding_validation")
PATH_SEPARATOR = " > "
UNKNOWN_CODES = {"unklar", "keine_zuordnung"}


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _clean(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def resolve_column(columns, configured: str | None, aliases: tuple[str, ...], label: str) -> str:
    by_key = {_key(column): str(column) for column in columns}
    candidates = ([configured] if configured else []) + list(aliases)
    for candidate in candidates:
        if candidate and _key(candidate) in by_key:
            return by_key[_key(candidate)]
    raise ValueError(
        f"Erforderliche Spalte '{label}' fehlt. Erkannte Spalten: {list(columns)}; "
        f"akzeptierte Namen: {[x for x in candidates if x]}"
    )


@dataclass(frozen=True)
class CodebookEntry:
    code: str
    kategorie: str
    unterkategorie: str
    auspraegung: str
    facette: str
    definition: str
    ankerbeispiel: str

    def as_prompt_dict(self) -> dict:
        return {
            "code": self.code,
            "definition": self.definition,
            "ankerbeispiel": self.ankerbeispiel,
        }

    def levels(self) -> dict[str, str | None]:
        parts = [self.kategorie, self.unterkategorie, self.auspraegung, self.facette]
        names = ["hauptkategorie", "unterkategorie", "auspraegung", "facette"]
        result: dict[str, str | None] = {}
        prefix: list[str] = []
        for name, part in zip(names, parts):
            if part:
                prefix.append(part)
                result[name] = PATH_SEPARATOR.join(prefix)
            else:
                result[name] = None
        return result


@dataclass(frozen=True)
class Segment:
    segment_id: str
    text: str
    human_code: str
    person: str


CODEBOOK_ALIASES = {
    "kategorie": ("Kategorie", "Hauptkategorie", "Main category"),
    "unterkategorie": ("Unterkategorie", "Subkategorie", "Subcategory"),
    "auspraegung": ("Ausprägung", "Auspraegung", "Dimension", "Expression"),
    "facette": ("Facette", "Fazette", "Facet"),
    "definition": ("Definition", "Code Definition", "Beschreibung"),
    "ankerbeispiel": ("Ankerbeispiel", "Ankerbeispiele", "Anchor example", "Beispiel"),
}


def load_codebook(path: str | Path) -> tuple[list[CodebookEntry], dict[str, CodebookEntry]]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Kategoriesystem nicht gefunden: {path}")
    try:
        frame = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError(f"Kategoriesystem konnte nicht als UTF-8/semikolon CSV gelesen werden: {path}: {exc}") from exc

    resolved = {
        name: resolve_column(frame.columns, None, aliases, name)
        for name, aliases in CODEBOOK_ALIASES.items()
    }
    if frame.empty:
        raise ValueError("Kategoriesystem enthält keine Datenzeilen.")

    grouped: dict[str, dict[str, Any]] = {}
    for row_index, row in frame.iterrows():
        values = {name: _clean(row[column]) for name, column in resolved.items()}
        parts = [values[x] for x in ("kategorie", "unterkategorie", "auspraegung", "facette") if values[x]]
        if not parts:
            raise ValueError(f"Kategoriesystem Zeile {row_index + 2}: leerer Codepfad.")
        code = PATH_SEPARATOR.join(parts)
        bucket = grouped.setdefault(code, {**values, "definitions": [], "anchors": []})
        if values["definition"] and values["definition"] not in bucket["definitions"]:
            bucket["definitions"].append(values["definition"])
        if values["ankerbeispiel"] and values["ankerbeispiel"] not in bucket["anchors"]:
            bucket["anchors"].append(values["ankerbeispiel"])

    entries = []
    for code, values in grouped.items():
        entries.append(CodebookEntry(
            code=code,
            kategorie=values["kategorie"],
            unterkategorie=values["unterkategorie"],
            auspraegung=values["auspraegung"],
            facette=values["facette"],
            definition=" | ".join(values["definitions"]),
            ankerbeispiel=" | ".join(values["anchors"]),
        ))
    if not entries:
        raise ValueError("Kategoriesystem enthält keinen verwendbaren Codepfad.")
    entries.sort(key=lambda item: item.code.casefold())
    return entries, {entry.code: entry for entry in entries}


def load_segments(
    path: str | Path,
    columns_config: dict | None = None,
    id_to_text_path: str | Path | None = None,
) -> list[Segment]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Interview-/MAXQDA-CSV nicht gefunden: {path}")
    frame = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if frame.empty:
        raise ValueError("Interview-/MAXQDA-CSV enthält keine Segmente.")
    cfg = columns_config or {}
    code_col = resolve_column(frame.columns, cfg.get("code"), ("Code", "Codes", "human_code"), "human_code")
    text_col = resolve_column(frame.columns, cfg.get("segment"), ("Segment", "Segmenttext", "Text"), "segment")
    person_col = resolve_column(frame.columns, cfg.get("person"), ("Dokumentname", "Dokument", "Person", "Interview"), "person")

    id_col = None
    for alias in (cfg.get("segment_id"), "segment_id", "Segment-ID", "SegmentID", "ID"):
        if alias and _key(alias) in {_key(c) for c in frame.columns}:
            id_col = next(c for c in frame.columns if _key(c) == _key(alias))
            break

    segments = []
    seen = set()
    for index, row in frame.reset_index(drop=True).iterrows():
        person = _clean(row[person_col])
        text = _clean(row[text_col])
        human_code = _clean(row[code_col])
        segment_id = _clean(row[id_col]) if id_col else f"{person}#SEG{index:05d}"
        if not segment_id or segment_id in seen:
            raise ValueError(f"Ungültige oder doppelte Segment-ID in Eingabezeile {index + 2}: {segment_id!r}")
        if not text:
            raise ValueError(f"Leerer Segmenttext in Eingabezeile {index + 2} ({segment_id}).")
        seen.add(segment_id)
        segments.append(Segment(segment_id, text, human_code, person))

    if id_to_text_path:
        id_path = Path(id_to_text_path)
        if id_path.is_file():
            id_map = json.loads(id_path.read_text(encoding="utf-8"))
            if not isinstance(id_map, dict):
                raise ValueError("id_to_text muss ein JSON-Objekt sein.")
            for segment in segments:
                mapped = id_map.get(segment.segment_id)
                if mapped is not None and _clean(mapped) != segment.text:
                    raise ValueError(f"Textabweichung zwischen CSV und id_to_text für {segment.segment_id}.")
    return segments


def parse_json_object(text: str) -> dict | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def default_llm(messages: list[dict], params: dict) -> str:
    from clusterer_core import ollama_chat
    return ollama_chat(
        messages,
        model=params["model"],
        temperature=params.get("temperature", 0.0),
        max_tokens=params.get("max_tokens", 4000),
    )


class MockLLM:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    @classmethod
    def from_path(cls, path: str | Path) -> "MockLLM":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("Mock-Responses müssen eine JSON-Liste sein.")
        return cls(value)

    def __call__(self, messages: list[dict], params: dict) -> str:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("Keine Mock-LLM-Antwort mehr verfügbar.")
        value = self.responses.pop(0)
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def call_json_with_repair(
    messages: list[dict],
    params: dict,
    validate: Callable[[dict], dict],
    llm: Callable[[list[dict], dict], str] = default_llm,
    raw_callback: Callable[[dict], None] | None = None,
) -> dict:
    raw = llm(messages, params)
    parsed = parse_json_object(raw)
    if parsed is not None:
        try:
            result = validate(parsed)
            if raw_callback:
                raw_callback({
                    "phase": "initial",
                    "raw_output": raw,
                    "validation_status": "accepted",
                    "validation_error": None,
                })
            return result
        except ValueError as exc:
            problem = str(exc)
            if raw_callback:
                raw_callback({
                    "phase": "initial",
                    "raw_output": raw,
                    "validation_status": "rejected",
                    "validation_error": problem,
                })
    else:
        problem = "Antwort enthält kein gültiges JSON-Objekt."
        if raw_callback:
            raw_callback({
                "phase": "initial",
                "raw_output": raw,
                "validation_status": "unparseable",
                "validation_error": problem,
            })

    repair_messages = [
        {
            "role": "system",
            "content": (
                "Du reparierst ausschließlich die folgende JSON-Antwort. "
                "Bewahre die inhaltliche Bedeutung, erfinde keine Codes oder Segment-IDs "
                "und gib nur ein gültiges JSON-Objekt ohne Markdown zurück."
            ),
        },
        {
            "role": "user",
            "content": f"Validierungsfehler: {problem}\n\nFehlerhafte Antwort:\n{raw}",
        },
    ]
    repaired_raw = llm(repair_messages, {**params, "temperature": 0.0})
    repaired = parse_json_object(repaired_raw)
    if repaired is None:
        if raw_callback:
            raw_callback({
                "phase": "repair",
                "raw_output": repaired_raw,
                "validation_status": "unparseable",
                "validation_error": "Self-Repair enthält kein gültiges JSON-Objekt.",
            })
        raise ValueError("LLM-Antwort konnte auch durch Self-Repair nicht als JSON gelesen werden.")
    try:
        result = validate(repaired)
    except ValueError as exc:
        if raw_callback:
            raw_callback({
                "phase": "repair",
                "raw_output": repaired_raw,
                "validation_status": "rejected",
                "validation_error": str(exc),
            })
        raise
    if raw_callback:
        raw_callback({
            "phase": "repair",
            "raw_output": repaired_raw,
            "validation_status": "accepted",
            "validation_error": None,
        })
    return result


class RawJsonlWriter:
    """Append-only Audit-Writer für unveränderte LLM-Antworten."""

    def __init__(self, path: str | Path, module: str):
        self.path = Path(path)
        self.module = module

    def callback_for(self, segment_id: str) -> Callable[[dict], None]:
        def write_event(event: dict) -> None:
            payload = {
                "timestamp": datetime.now().isoformat(),
                "module": self.module,
                "segment_id": segment_id,
                **event,
            }
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return write_event


def resolve_config_path(config_path: str | Path, explicit: str | None, configured: str | None) -> Path:
    value = explicit or configured
    if not value:
        raise ValueError("Kein Pfad zum Kategoriesystem konfiguriert (paths.category_system_csv).")
    path = Path(value)
    if not path.is_absolute():
        path = Path(config_path).resolve().parent / path
    return path.resolve()


def markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")

