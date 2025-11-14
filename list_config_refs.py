import pathlib
refs = set()
for path in pathlib.Path('src/chanlun').rglob('*.py'):
    text = path.read_text(encoding='utf-8', errors='ignore')
    if 'chanlun.config' in text:
        refs.add(str(path))
for file in sorted(refs):
    print(file)
