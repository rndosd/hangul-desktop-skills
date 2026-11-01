"""Apply tools/template-layout-rules to a prepared template and rebuild its references (build tool).

For each named template folder under full-plans/: rewrite template.hwpx and example.hwpx with
normalize_template_layout.apply, export both through installed Hangul (run_native_job.py, OpenOnly),
re-render page images (preview_pdf, scale 1.5), store the Hangul receipts with local paths removed,
then replace every old file hash in the repository's JSON/Markdown with the new one until stable.
Requires Windows, Hangul and a reviewed security module. Nothing is written if a Hangul export fails.

Usage: rebuild_template_references.py WORK_DIR plan-school [plan-education ...]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / 'plugins/hancom-desktop/skills'
PLANS = SKILLS / 'hwpx/assets/document-templates/full-plans'
FINALIZE = SKILLS / 'hwpx-windows-finalize/scripts'
sys.path.insert(0, str(FINALIZE))
sys.path.insert(0, str(Path(__file__).parent))
import normalize_template_layout as normalize  # noqa: E402
from hancom_completion_gate import preview_pdf  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scrub(value):
    """Receipts are published: replace machine paths the way the existing evidence does."""
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str) and (':\\' in value or ':/' in value[:3] or value.startswith('/')):
        return '<local-path>'
    return value


def export(document, work):
    pdf, run = work / (document.stem + '.pdf'), work / ('run-' + document.stem)
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(FINALIZE / 'run_native_job.py'), str(document),
                             '--mode', 'OpenOnly', '--pdf', str(pdf), '--run', str(run), '--context', 'ordinary-shell'],
                            capture_output=True, text=True, encoding='utf-8')
    receipt = json.loads((run / 'native/receipt.json').read_text(encoding='utf-8-sig'))
    # A slow Hangul exit after a finished export is reported as BLOCKED by cleanup; the export itself must pass.
    if not (receipt.get('firstOpen') and receipt.get('pdfExport') and pdf.is_file()):
        raise RuntimeError(f'Hangul export failed for {document.name}: {result.stdout[-400:]}')
    return pdf, receipt


def normalize_prefixes(manifest_path, rules):
    """Fill writes each binding's prefix (symbol and leading spaces included) over the template text,
    so prefixes must carry the same leading-space count as the rules."""
    import layout_rules
    leads = {}
    for role, values in rules.items():
        if role.startswith('item|'):
            leads.setdefault(role.split('|')[2], values['lead'])
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    bindings = list(manifest['slots'].values()) + [field for repeat in manifest['repeats'].values() for field in repeat['fields'].values()]
    changed = 0
    for binding in bindings:
        prefix = binding.get('prefix', '')
        stripped = prefix.lstrip(' 　')
        symbol = layout_rules.SHOWN.get(stripped[:1], stripped[:1])
        if symbol in leads and stripped[1:2].isspace() and len(prefix) - len(stripped) != leads[symbol]:
            binding['prefix'] = ' ' * leads[symbol] + stripped
            changed += 1
    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return changed


def rebuild(name, work):
    folder, rules = PLANS / name, json.loads((ROOT / f'tools/template-layout-rules/{name}.json').read_text(encoding='utf-8'))
    work = work / name
    work.mkdir(parents=True)
    old = {p: sha(p) for p in folder.rglob('*') if p.is_file()}
    normalize_prefixes(folder / 'manifest.json', rules)
    built = {}
    for stem in ('template', 'example'):
        target = work / f'{stem}.hwpx'
        normalize.apply(folder / f'{stem}.hwpx', target, rules)
        pdf, receipt = export(target, work)
        pages = work / f'{stem}-pages'
        preview_pdf(pdf, pages)
        built[stem] = (target, pdf, receipt, pages)
    # Replace only after both exports succeeded.
    for stem, (hwpx, pdf, receipt, pages) in built.items():
        shutil.copyfile(hwpx, folder / f'{stem}.hwpx')
        shutil.copyfile(pdf, folder / f'{stem}.pdf')
        native = 'baseline-native.json' if stem == 'template' else 'example-native.json'
        (folder / native).write_text(json.dumps(scrub(receipt), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        destination = folder / ('pages' if stem == 'template' else 'example-pages')
        keep_receipt = (destination / 'preview.json').is_file()
        for image in destination.glob('*.png'):
            image.unlink()
        for image in sorted(pages.glob('*.png')):
            shutil.copyfile(image, destination / image.name)
        if keep_receipt:
            (destination / 'preview.json').write_text(
                json.dumps(scrub(json.loads((pages / 'preview.json').read_text(encoding='utf-8'))), ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8')
    shutil.copyfile(folder / 'pages/0001.png', folder / 'preview.png')
    return {old_hash: sha(path) for path, old_hash in old.items() if path.is_file() and sha(path) != old_hash}, {
        stem: len(list((folder / ('pages' if stem == 'template' else 'example-pages')).glob('*.png'))) for stem in built}


def cascade(pending):
    texts = [p for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.json', '.md')
             and '.git' not in p.parts and p.name != 'PAYLOAD-SHA256.json']
    while pending:
        following = {}
        for path in texts:
            raw = path.read_text(encoding='utf-8')
            new = raw
            for old_hash, new_hash in pending.items():
                new = new.replace(old_hash, new_hash)
            if new != raw:
                before = sha(path)
                path.write_text(new, encoding='utf-8', newline='')
                following[before] = sha(path)
        pending = following


if __name__ == '__main__':
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=False)
    for name in sys.argv[2:]:
        changes, pages = rebuild(name, work)
        cascade(changes)
        print(json.dumps({'template': name, 'filesChanged': len(changes), 'pages': pages}, ensure_ascii=False))
