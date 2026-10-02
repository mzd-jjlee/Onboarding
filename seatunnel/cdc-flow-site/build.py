"""Dependency-free static build; npm is not installed in this environment."""
from pathlib import Path
from html.parser import HTMLParser
import shutil
root = Path(__file__).resolve().parent
source = root / 'index.html'
parser = HTMLParser()
parser.feed(source.read_text())
(root / 'dist').mkdir(exist_ok=True)
shutil.copy2(source, root / 'dist/index.html')
print('Static build complete: dist/index.html')
