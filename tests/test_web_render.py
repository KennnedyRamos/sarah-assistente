"""Testa o renderizador de Markdown da interface (segurança contra XSS) usando o Node, se instalado."""
import json
import re
import shutil
import subprocess

import pytest

from jarvis import config

CASES = [
    ("Seu nome é **Kennedy**.", "Seu nome é <strong>Kennedy</strong>."),
    ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)&gt;"),
    ("**<script>x</script>**", "<strong>&lt;script&gt;x&lt;/script&gt;</strong>"),
    ("use `npm i` agora", "use <code>npm i</code> agora"),
    ("```py\nprint(1)\n```", "<pre><code>print(1)\n</code></pre>"),
    ("```py\nprint(1)", "<pre><code>print(1)</code></pre>"),
    ("## Título", "<strong>Título</strong>"),
    ("[abrir](https://mail.google.com/mail/?authuser=a@b.com#all/abc)",
     '<a href="https://mail.google.com/mail/?authuser=a@b.com#all/abc" target="_blank" rel="noopener noreferrer">abrir</a>'),
    ("[x](javascript:alert(1))", "[x](javascript:alert(1))"),  # só https vira link
    ('[x](https://a.com/"onmouseover="alert(1))', '[x](https://a.com/"onmouseover="alert(1))'),  # aspas não passam
]


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js não instalado")
def test_render_markdown_escapes_html():
    src = (config.ROOT / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    fn = re.search(r"function renderMarkdown[\s\S]*?\n}\n", src).group(0)
    script = fn + f"process.stdout.write(JSON.stringify({json.dumps([c[0] for c in CASES])}.map(renderMarkdown)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert json.loads(out.stdout) == [c[1] for c in CASES]
