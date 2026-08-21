#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Generischer YAML-gesteuerter Workflow-Runner.

Neue Analysemodule werden ausschließlich in config_v2.yaml unter
`pipeline.modules` deklariert. workflow.py muss dafür nicht angepasst werden.
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

LOGGER = logging.getLogger("workflow")
TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def resolve_path(base: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def render_arg(value, runtime: dict) -> str:
    text = str(value)

    def repl(match):
        key = match.group(1)
        if key not in runtime:
            raise KeyError(f"Unbekannter Workflow-Platzhalter: {{{key}}}")
        return str(runtime[key])

    return TOKEN_RE.sub(repl, text)


def normalize_modules(config: dict) -> list[dict]:
    pipeline = config.get("pipeline", {})
    modules = pipeline.get("modules", [])
    if not isinstance(modules, list) or not modules:
        raise ValueError(
            "Keine Module gefunden. Erwartet wird config['pipeline']['modules']."
        )

    normalized = []
    ids = set()
    for raw in modules:
        if not isinstance(raw, dict):
            raise ValueError("Jeder Pipeline-Eintrag muss ein YAML-Objekt sein.")
        module_id = str(raw.get("id", "")).strip()
        script = str(raw.get("script", "")).strip()
        if not module_id or not script:
            raise ValueError("Jedes Modul benötigt mindestens 'id' und 'script'.")
        if module_id in ids:
            raise ValueError(f"Doppelte Modul-ID: {module_id}")
        ids.add(module_id)
        item = dict(raw)
        item["id"] = module_id
        item["script"] = script
        item["name"] = str(raw.get("name", module_id)).strip()
        item["enabled"] = bool(raw.get("enabled", True))
        deps = raw.get("depends_on", []) or []
        if isinstance(deps, str):
            deps = [deps]
        item["depends_on"] = [str(x).strip() for x in deps if str(x).strip()]
        normalized.append(item)

    return normalized


def topological_order(modules: list[dict]) -> list[dict]:
    by_id = {m["id"]: m for m in modules}
    enabled = {m["id"] for m in modules if m["enabled"]}

    for module in modules:
        if not module["enabled"]:
            continue
        for dep in module["depends_on"]:
            if dep not in by_id:
                raise ValueError(f"Modul {module['id']} referenziert unbekannte Abhängigkeit {dep}.")
            if dep not in enabled:
                raise ValueError(
                    f"Modul {module['id']} ist aktiv, aber Abhängigkeit {dep} ist deaktiviert."
                )

    ordered = []
    completed = set()
    remaining = [m for m in modules if m["enabled"]]

    while remaining:
        progress = False
        for module in list(remaining):
            if all(dep in completed for dep in module["depends_on"]):
                ordered.append(module)
                completed.add(module["id"])
                remaining.remove(module)
                progress = True
        if not progress:
            unresolved = {m["id"]: m["depends_on"] for m in remaining}
            raise ValueError(f"Zyklische oder unauflösbare Pipeline-Abhängigkeiten: {unresolved}")

    return ordered


def run_step(module: dict, command: list[str], cwd: Path):
    LOGGER.info("=" * 72)
    LOGGER.info("Starte Modul: %s (%s)", module["name"], module["id"])
    LOGGER.info("Befehl: %s", " ".join(str(x) for x in command))
    LOGGER.info("=" * 72)

    result = subprocess.run(command, cwd=str(cwd), text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Workflow abgebrochen: Modul '{module['id']}' endete mit Exit-Code {result.returncode}."
        )

    missing = []
    for output in module.get("outputs", []) or []:
        path = cwd / str(output)
        if not path.exists():
            missing.append(str(output))
    if missing:
        raise RuntimeError(
            f"Modul '{module['id']}' meldete Erfolg, aber deklarierte Outputs fehlen: {missing}"
        )

    LOGGER.info("Abgeschlossen: %s", module["name"])


def strip_first_heading(markdown: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def demote_headings(markdown: str, levels: int = 2) -> str:
    output = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            count = len(line) - len(line.lstrip("#"))
            if count > 0 and len(line) > count and line[count] == " ":
                line = "#" * min(6, count + levels) + line[count:]
        output.append(line)
    return "\n".join(output)


def build_full_report(output_dir: Path, modules: list[dict], created_at: str) -> Path:
    report_modules = []
    for module in modules:
        report_cfg = module.get("report")
        if not isinstance(report_cfg, dict):
            continue
        markdown = str(report_cfg.get("markdown", "")).strip()
        if not markdown:
            continue
        report_modules.append((module, markdown, str(report_cfg.get("title", module["name"]))))

    report = [
        "# Gesamtbericht qualitative Analyse\n",
        f"Erstellt am: {created_at}\n\n",
        "Dieser Bericht wurde automatisch aus den in der YAML aktivierten Analysestufen zusammengestellt.\n\n",
        "## Analyseschritte\n\n",
    ]

    for idx, (_, filename, title) in enumerate(report_modules, start=1):
        report.append(f"- {idx}. {title} (`{filename}`)\n")
    report.append("\n---\n\n")

    for idx, (_, filename, title) in enumerate(report_modules, start=1):
        report.append(f"## {idx}. {title}\n\n")
        path = output_dir / filename
        if not path.exists():
            report.append(f"_Datei `{filename}` wurde nicht gefunden._\n\n---\n\n")
            continue
        text = demote_headings(strip_first_heading(path.read_text(encoding="utf-8")), levels=2)
        report.append(text + "\n\n---\n\n")

    report_path = output_dir / "gesamtbericht.md"
    report_path.write_text("".join(report), encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generischer YAML-gesteuerter qualitativer Analyse-Workflow"
    )
    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--csv", "-i", default=None)
    parser.add_argument("--output-dir", "-o", default="workflow_output")
    parser.add_argument("--log-raw", action="store_true")
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    config_path = resolve_path(script_dir, args.config)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config nicht gefunden: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    configured_csv = config.get("paths", {}).get("input_csv")
    if args.csv:
        csv_path = resolve_path(Path.cwd(), args.csv)
    elif configured_csv:
        csv_path = resolve_path(config_path.parent, configured_csv)
    else:
        raise ValueError("Kein input_csv in der Config und kein --csv angegeben.")
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV nicht gefunden: {csv_path}")

    output_dir = resolve_path(script_dir, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(output_dir / "workflow.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    modules = topological_order(normalize_modules(config))
    runtime = {
        "config": str(config_path),
        "input_csv": str(csv_path),
        "output_dir": str(output_dir),
        "python": sys.executable,
        "log_raw_flag": "--log-raw" if args.log_raw else "",
    }

    started_at = datetime.now().isoformat()
    completed_steps = []

    try:
        for module in modules:
            script_path = resolve_path(script_dir, module["script"])
            if not script_path.is_file():
                raise FileNotFoundError(
                    f"Script für Modul '{module['id']}' nicht gefunden: {script_path}"
                )

            rendered_args = []
            for value in module.get("args", []) or []:
                rendered = render_arg(value, runtime).strip()
                if rendered:
                    rendered_args.append(rendered)

            command = [sys.executable, str(script_path), *rendered_args]
            run_step(module, command, output_dir)
            completed_steps.append(module["id"])

    except Exception as exc:
        manifest = {
            "started_at": started_at,
            "failed_at": datetime.now().isoformat(),
            "status": "failed",
            "completed_steps": completed_steps,
            "error": str(exc),
            "input_csv": str(csv_path),
            "config": str(config_path),
        }
        (output_dir / "workflow_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise

    finished_at = datetime.now().isoformat()
    report_path = build_full_report(output_dir, modules, finished_at)

    declared_outputs = []
    for module in modules:
        for output in module.get("outputs", []) or []:
            if output not in declared_outputs:
                declared_outputs.append(output)
    declared_outputs.extend(["gesamtbericht.md", "workflow_manifest.json"])

    manifest = {
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "success",
        "completed_steps": completed_steps,
        "input_csv": str(csv_path),
        "config": str(config_path),
        "output_dir": str(output_dir),
        "gesamtbericht": str(report_path),
        "outputs": declared_outputs,
    }
    (output_dir / "workflow_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    LOGGER.info("=" * 72)
    LOGGER.info("Workflow vollständig abgeschlossen: %s Module", len(modules))
    LOGGER.info("Gesamtbericht: %s", report_path)
    LOGGER.info("=" * 72)


if __name__ == "__main__":
    main()
