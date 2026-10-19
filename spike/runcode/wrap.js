// SPIKE: the snippet wrapping of docs/javascripts/interactive-code.js, unchanged in behaviour (imports added when
// missing; a fragment without `with Workspace(...)` is indented into one). Without the save() call: the data is built
// from the Workspace object.
const IMPORTS = `from buildzr.dsl import *
`;
function wrapSnippet(code) {
  const hasWorkspace = /with\s+Workspace\s*\([^)]*\)\s+as\s+\w+\s*:/i.test(code);
  const hasImports = /from\s+buildzr\.dsl\s+import/i.test(code);
  if (!hasWorkspace) {
    return IMPORTS + "with Workspace('w') as w:\n" + code.split('\n').map((l) => '    ' + l).join('\n') + '\n';
  }
  return (hasImports ? '' : IMPORTS) + code;
}
if (typeof module !== 'undefined') module.exports = { wrapSnippet };
