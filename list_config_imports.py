import pathlib
imports = set()
for path in pathlib.Path('src/chanlun').rglob('*.py'):
    text = path.read_text(encoding='utf-8', errors='ignore')
    for line in text.splitlines():
        if 'from chanlun.config import' in line:
            imports.add((str(path), line.strip()))
for file, line in sorted(imports):
    print(f"{file}: {line}")
