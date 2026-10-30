from pathlib import Path

p = Path('dev/build-foundation.py')
s = p.read_text()
s = s.replace("    if before not in text:\n", "    if after in text:\n        return\n    if before not in text:\n", 1)
s = s.replace('            expandedInContext: state.expanded.includes(fold.id),', '              expandedInContext: (state.expanded ?? []).includes(String(row.id)),')
p.write_text(s)

p = Path('extensions/lib/retention.ts')
s = p.read_text()
s = s.replace('void Promise.resolve().then(() => this.service!.assess(request, controller.signal)).then((rows) => {', '''void Promise.resolve().then(() => {
      if (controller.signal.aborted || epoch !== this.epoch || !this.enabled()) return [];
      return this.service!.assess(request, controller.signal);
    }).then((rows) => {''')
p.write_text(s)
