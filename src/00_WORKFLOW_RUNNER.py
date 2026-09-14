#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Generischer YAML-gesteuerter Workflow-Runner.

Neue Analysemodule werden ausschließlich in config_v2.yaml unter
`pipeline.modules` deklariert. Der Runner muss dafür nicht angepasst werden.
"""

from project_paths import DEFAULT_CONFIG, DEFAULT_OUTPUT
from cost_profiles import normalize_cost_profile
from provider_keys import reject_config_secrets
from contextvars import ContextVar
from llm_providers import provider_environment, transport_selection
import argparse
import os
import uuid
import importlib.metadata
from runtime_support import atomic_json, atomic_text, fingerprint, file_hash
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
STEP_TRANSPORT = ContextVar('workflow_step_transport', default=None)


class ModulePaused(RuntimeError):
    """A module owning child runs reached a safe, resumable pause boundary."""


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
        after = raw.get('after_if_enabled', [])
        if not isinstance(after, list) or any(not isinstance(x, str) for x in after):
            raise ValueError('after_if_enabled muss eine Liste von Modul-IDs sein.')
        item['after_if_enabled'] = after
        if type(raw.get('requires_model', True)) is not bool:
            raise ValueError('requires_model muss true oder false sein.')
        item['requires_model'] = raw.get('requires_model', True)
        if type(raw.get('starts_child_runs', False)) is not bool:
            raise ValueError('starts_child_runs muss true oder false sein.')
        item['starts_child_runs'] = raw.get('starts_child_runs', False)
        if item['starts_child_runs'] and not item['requires_model']:
            raise ValueError('Module mit Modell-Unterläufen müssen requires_model: true ausweisen.')
        item["cost_profile"] = normalize_cost_profile(item)
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
            wait_for = set(module['depends_on']) | (set(module.get('after_if_enabled', [])) & enabled)
            if wait_for <= completed:
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

    previous = {}
    for output in module.get("outputs", []):
        path = cwd / output
        if path.is_file():
            previous[output] = (path.stat().st_mtime_ns, file_hash(path))
    progress_path = cwd / 'progress.json'
    atomic_json(progress_path, {'module':module['id'],'completed':0,'total':None,'requests':0,'request_active':False})
    selected = STEP_TRANSPORT.get() or {'provider':'ollama_local','api_key_env':'OLLAMA_API_KEY'}
    child_env = {**provider_environment(selected, os.environ), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                 'WORKFLOW_MODULE':module['id'],'WORKFLOW_PROGRESS_FILE':str(progress_path)}
    execution_path = cwd / ('execution_' + module['id'] + '.log')
    with execution_path.open('ab') as execution_log:
        result = subprocess.run(command, cwd=str(cwd), env=child_env,
                                stdout=execution_log, stderr=subprocess.STDOUT)
    if result.returncode == 75 and module.get('starts_child_runs'):
        raise ModulePaused('Modul hat seine Wiederholungen sicher pausiert.')
    if result.returncode != 0:
        with execution_path.open('rb') as failed_log:
            failed_log.seek(0, 2); size=failed_log.tell(); failed_log.seek(max(0,size-16000))
            tail=failed_log.read().decode('utf-8',errors='replace')
            LOGGER.error('Letzte Modulausgabe:\n%s', tail)
        from failure_help import failure_help,ModuleFailure
        raise ModuleFailure(f"Modul '{module['id']}' endete mit Exit-Code {result.returncode}.", failure_help(tail))

    missing = []
    for output in module.get("outputs", []) or []:
        path = cwd / str(output)
        if path.is_file() and str(output) in previous and previous[str(output)] == (path.stat().st_mtime_ns, file_hash(path)):
            raise RuntimeError(f"Modul {module['id']} hat alten Output nicht erneuert: {output}")
        if path.is_file() and path.suffix == '.json':
            value = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError(f"Ergebnis muss ein JSON-Objekt sein: {output}")
            if value.get('processing_status', 'completed') != 'completed':
                raise RuntimeError(f"Modul {module['id']} lieferte unvollständige Ergebnisse: {output}")
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

    snapshot = output_dir / 'config_snapshot.yaml'
    if snapshot.exists():
        source = yaml.safe_load(snapshot.read_text(encoding='utf-8')).get('review_provenance')
        if source:
            report.insert(2, '**Auswertung nach manueller Prüfung:** '+source.get('note','Keine unabhängige Validierung.')+'\n\n')

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
    atomic_text(report_path, "".join(report))
    from html_report import build_html_report
    build_html_report(output_dir, modules, created_at)
    return report_path


def execution_provenance(config_path, csv_path, config, script_dir=None):
    """Shared execution identity for ordinary runs and controlled repetitions."""
    reject_config_secrets(config)
    script_dir = Path(script_dir or Path(__file__).resolve().parent)
    config_path = Path(config_path)
    provenance = {
        'review_provenance': config.get('review_provenance'),
        "input_sha256": file_hash(csv_path),
        "config_sha256": file_hash(config_path),
        "code": {p.name: file_hash(p) for p in sorted([*script_dir.glob("*.py"), *script_dir.glob("*.html"), *script_dir.glob("*.js"), *script_dir.glob("*.css")])},
        "dependencies": {name: importlib.metadata.version(name) for name in ("pandas", "PyYAML", "ollama", "matplotlib")},
        "llm": config.get("llm", {}),
    }
    codebook_path = config.get("paths", {}).get("category_system_csv")
    if codebook_path:
        provenance["codebook_sha256"] = file_hash(resolve_path(config_path.parent, codebook_path))
    try:
        provenance["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=script_dir, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        provenance["commit"] = None
    return provenance


def verify_completed_outputs(output_dir, manifest, modules):
    """A failed result is not a checkpoint; reuse only verified completed modules."""
    for module in modules:
        if module["id"] in manifest.get('completed_steps', []):
            for filename in module.get("outputs", []):
                path = Path(output_dir) / filename
                if not path.is_file() or (path.suffix != '.log' and file_hash(path) != manifest.get("output_hashes", {}).get(filename)):
                    raise ValueError(f"Wiederaufnahme abgelehnt: Output verändert oder fehlt: {filename}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generischer YAML-gesteuerter qualitativer Analyse-Workflow"
    )
    parser.add_argument("--config", "-c", default=str(DEFAULT_CONFIG))
    parser.add_argument("--csv", "-i", default=None)
    parser.add_argument("--output-dir", "-o", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--log-raw", action="store_true")
    parser.add_argument("--resume", default=None, help="Laufverzeichnis eines unterbrochenen Laufs")
    parser.add_argument("--pause-file", default=None, help="Nach dem aktuellen Modul pausieren, sobald diese Datei existiert")
    parser.add_argument("--validate-only", action="store_true", help="Nur CSV, Codebuch und Pipeline prüfen; kein Modellaufruf")
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    config_path = resolve_path(Path.cwd(), args.config)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config nicht gefunden: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    reject_config_secrets(config)

    configured_csv = config.get("paths", {}).get("input_csv")
    if args.csv:
        csv_path = resolve_path(Path.cwd(), args.csv)
    elif configured_csv:
        csv_path = resolve_path(config_path.parent, configured_csv)
    else:
        raise ValueError("Kein input_csv in der Config und kein --csv angegeben.")
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV nicht gefunden: {csv_path}")

    modules = topological_order(normalize_modules(config))
    needs_model = any(m.get('requires_model', True) for m in modules)
    llm = config.get('llm', {})
    selected_transport = (transport_selection(llm, llm.get('model', '')) if needs_model else
                          {'provider':'ollama_local','api_key_env':llm.get('api_key_env','OLLAMA_API_KEY')})
    if config.get('_diagnostic_child') and any(m['starts_child_runs'] for m in modules):
        raise ValueError('Ein Diagnose-Unterlauf darf keine weiteren Modell-Unterläufe starten.')
    from stability_analysis import configured_plan, planning_summary
    stability_plan = configured_plan(config_path)
    sensitivity_plan = configured_plan(config_path, kind='sensitivity')
    if stability_plan and csv_path != Path(stability_plan['config']['paths']['input_csv']):
        raise ValueError('Stabilität benötigt dieselbe CSV wie die gespeicherte Konfiguration; paths.input_csv zuerst anpassen.')
    if sensitivity_plan and csv_path != Path(sensitivity_plan['configurations'][0]['config']['paths']['input_csv']):
        raise ValueError('Sensitivität benötigt dieselbe CSV wie die gespeicherte Konfiguration; paths.input_csv zuerst anpassen.')
    from coding_validation_common import load_codebook, load_segments
    codebook_config = config.get("paths", {}).get("category_system_csv")
    if not codebook_config:
        raise ValueError("paths.category_system_csv fehlt.")
    _, code_index = load_codebook(resolve_path(config_path.parent, codebook_config))
    input_segments = load_segments(csv_path, config.get("columns", {}))
    if config.get('coding_agreement', {}).get('label_mode') == 'multi_label':
        from multi_label_core import group_units
        group_units(input_segments)
    unknown = sum(s.human_code not in code_index for s in input_segments)
    if unknown:
        raise ValueError(f"{unknown} Codierzeilen passen nicht zum Codebuch. Codepfade vor dem Lauf abgleichen.")
    from managed_ollama import workers, ManagedOllama
    if needs_model:
        workers(config.get("llm", {}))
    from context_preflight import check_context, require_context
    context_check=check_context(config,input_segments,code_index,modules)
    require_context(context_check)
    for warning in context_check['warnings']:
        logging.warning('Kontext-Vorprüfung: %s',warning)
    if args.validate_only:
        validation = {"status": "valid", "segments": len(input_segments), "code_paths": len(code_index),
                      "modules": len(modules), "model_calls": 0}
        if stability_plan:
            validation['stability_plan'] = planning_summary(stability_plan)
        if sensitivity_plan:
            validation['sensitivity_plan'] = planning_summary(sensitivity_plan)
        from workflow_effort import effort_summary
        validation["effort"] = effort_summary(modules, stability=planning_summary(stability_plan),
                                              sensitivity=planning_summary(sensitivity_plan))
        print(json.dumps(validation))
        return
    provenance = execution_provenance(config_path, csv_path, config, script_dir)
    # Commit is descriptive; code content is the authoritative resume identity.
    identity = fingerprint({k: v for k, v in provenance.items() if k != "commit"})
    if args.resume:
        output_dir = Path(args.resume).resolve()
        manifest = json.loads((output_dir / "workflow_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("fingerprint") != identity:
            raise ValueError("Wiederaufnahme abgelehnt: Eingaben, Konfiguration, Code oder Abhängigkeiten geändert.")
        run_id = manifest["run_id"]
        completed_steps = list(manifest["completed_steps"])
        verify_completed_outputs(output_dir, manifest, modules)
        from runtime_evidence import verify_inventory
        verify_inventory(output_dir, manifest)
    else:
        run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        output_dir = resolve_path(Path.cwd(), args.output_dir) / run_id
        output_dir.mkdir(parents=True, exist_ok=False)
        completed_steps = []
        manifest = {"run_id": run_id, "started_at": datetime.now().isoformat(),
                    "fingerprint": identity, "provenance": provenance,
                    "completed_steps": [], "output_hashes": {}}
        atomic_text(output_dir / "config_snapshot.yaml", config_path.read_text(encoding="utf-8"))
    os.environ["WORKFLOW_RUN_ID"] = run_id
    os.environ["WORKFLOW_FINGERPRINT"] = identity
    os.environ["WORKFLOW_CHECKPOINT_DIR"] = str(output_dir / "_checkpoints")
    os.environ.pop('WORKFLOW_PAUSE_FILE', None)
    if args.pause_file:
        os.environ['WORKFLOW_PAUSE_FILE'] = str(Path(args.pause_file).resolve())
    from runtime_evidence import ENV as evidence_env
    os.environ.pop(evidence_env, None)
    if config.get('_diagnostic_child') is True:
        os.environ[evidence_env] = str(output_dir / '_runtime_evidence')
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(output_dir / "workflow.log", encoding="utf-8"), logging.StreamHandler()], force=True)
    runtime = {"config": str(config_path), "input_csv": str(csv_path), "output_dir": str(output_dir),
               "python": sys.executable, "log_raw_flag": "--log-raw" if args.log_raw else ""}
    manifest.update(status="running", output_dir=str(output_dir))
    if "error" in manifest:
        manifest.setdefault("failure_history", []).append({"failed_at": manifest.pop("failed_at", None), "error": manifest.pop("error")})
    manifest.pop("finished_at", None)
    atomic_json(output_dir / "workflow_manifest.json", manifest)
    managed = ManagedOllama(config.get("llm", {}), output_dir)
    managed_started = False
    from managed_ollama import HOST_ENV
    os.environ.pop(HOST_ENV, None)
    try:
        manifest["ollama_runtime"] = {'managed': False, 'model_required': needs_model, 'started': False}
        atomic_json(output_dir / "workflow_manifest.json", manifest)
        failures=[]
        for module in modules:
            if module["id"] in completed_steps:
                continue
            missing_dependencies=[d for d in module.get('depends_on',[]) if d not in completed_steps]
            if missing_dependencies:
                manifest.setdefault('module_status',{})[module['id']]='blocked'
                manifest.setdefault('blocked_by',{})[module['id']]=missing_dependencies
                atomic_json(output_dir/'workflow_manifest.json',manifest)
                continue
            if args.pause_file and Path(args.pause_file).is_file():
                manifest.update(status="paused", current_module=None)
                if config.get('_diagnostic_child') is True:
                    from runtime_evidence import summarize
                    manifest['runtime_evidence'] = summarize(output_dir / '_runtime_evidence', run_id, identity)
                atomic_json(output_dir / "workflow_manifest.json", manifest)
                LOGGER.info("Workflow auf Wunsch zwischen Modulen pausiert.")
                return
            manifest["current_module"] = module["id"]
            manifest.setdefault('module_status', {})[module['id']] = 'running'
            atomic_json(output_dir / "workflow_manifest.json", manifest)
            try:
                if module['starts_child_runs']:
                    managed.close()
                    managed_started = False
                    manifest['ollama_runtime'] = {'managed': False, 'released_for_child_runs': module['id']}
                elif module['requires_model'] and not managed_started:
                    manifest['ollama_runtime'] = managed.start()
                    manifest.setdefault('ollama_runtime_sessions', []).append(manifest['ollama_runtime'])
                    managed_started = True
                atomic_json(output_dir / 'workflow_manifest.json', manifest)
                script_path = resolve_path(script_dir, module["script"])
                if not script_path.is_file():
                    raise FileNotFoundError(script_path)
                rendered = [render_arg(value, runtime).strip() for value in module.get("args", [])]
                command = [sys.executable, str(script_path), *[v for v in rendered if v]]
                # Preserve the established module-call interface and isolate per-run credentials.
                token = STEP_TRANSPORT.set(selected_transport if module['requires_model'] else
                    {'provider':'ollama_local','api_key_env':selected_transport['api_key_env']})
                try:
                    run_step(module, command, output_dir)
                finally:
                    STEP_TRANSPORT.reset(token)
            except ModulePaused:
                manifest['module_status'][module['id']] = 'paused'
                manifest.update(status='paused', current_module=module['id'])
                atomic_json(output_dir / 'workflow_manifest.json', manifest)
                return
            except Exception as exc:
                from failure_help import failure_help
                failures.append((module['id'],exc))
                manifest['module_status'][module['id']]='failed'
                manifest.setdefault('module_errors',{})[module['id']]={
                    **getattr(exc,'diagnostic',failure_help(exc)), 'module_name':module['name']}
                atomic_json(output_dir/'workflow_manifest.json',manifest)
                LOGGER.error('Modul %s fehlgeschlagen; unabhängige Module werden weiter bearbeitet.',module['id'])
                continue
            completed_steps.append(module["id"])
            manifest['module_status'][module['id']] = 'success'
            manifest.get('module_errors',{}).pop(module['id'],None)
            manifest.get('blocked_by',{}).pop(module['id'],None)
            manifest["completed_steps"] = list(completed_steps)
            for filename in module.get("outputs", []):
                path = output_dir / filename
                if path.is_file():
                    manifest["output_hashes"][filename] = file_hash(path)
            atomic_json(output_dir / "workflow_manifest.json", manifest)
        if config.get('_diagnostic_child') is True:
            from runtime_evidence import summarize
            manifest['runtime_evidence'] = summarize(output_dir / '_runtime_evidence', run_id, identity)
            atomic_json(output_dir / 'workflow_manifest.json', manifest)
        if failures:
            manifest['current_module']=failures[0][0]
            raise failures[0][1]
        if any(m['id'] not in completed_steps for m in modules):
            raise RuntimeError('Einige Module warten auf fehlende Vorstufen; kein vollständiger Bericht erstellt.')
        finished_at = datetime.now().isoformat()
        report_path = build_full_report(output_dir, modules, finished_at)
        manifest['output_hashes'].update({name:file_hash(output_dir/name) for name in ('gesamtbericht.md','gesamtbericht.html')})
        manifest.update(status="success", current_module=None, finished_at=finished_at, gesamtbericht=str(report_path),
                        gesamtbericht_html=str(output_dir/'gesamtbericht.html'))
        atomic_json(output_dir / "workflow_manifest.json", manifest)
        LOGGER.info("Workflow abgeschlossen. Lauf-ID: %s. Bericht: %s", run_id, report_path)
    except Exception as exc:
        if manifest.get('current_module'):
            manifest.setdefault('module_status', {})[manifest['current_module']] = 'failed'
        manifest.update(status="failed", failed_at=datetime.now().isoformat(), error=str(exc))
        atomic_json(output_dir / "workflow_manifest.json", manifest)
        raise
    finally:
        managed.close()


if __name__ == "__main__":
    main()
