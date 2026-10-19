// SPIKE: lets a docs page feed this (unchanged) viewer bundle its data by postMessage instead of from data/ on a
// server. Runs before the viewer module: answers the viewer's fetch('data/...') and fetch('build.json') from the
// files the parent page sends, and follows the parent's light/dark scheme.
(function () {
  var resolveFiles;
  var files = new Promise(function (r) { resolveFiles = r; });
  addEventListener('message', function (e) {
    if (e.source !== parent) return;
    var m = e.data || {};
    if (m.type === 'runcode-data') resolveFiles(m.files);
    if (m.type === 'runcode-data' || m.type === 'runcode-theme') {
      document.documentElement.dataset.theme = m.dark ? 'dark' : 'light';
    }
  });
  var realFetch = window.fetch.bind(window);
  var base = new URL('./', location.href).href;
  window.fetch = function (input, init) {
    var url = new URL(typeof input === 'string' ? input : input.url, location.href).href.split(/[?#]/)[0];
    if (url.indexOf(base) === 0) {
      var rel = url.slice(base.length);
      if (rel === 'build.json') return Promise.resolve(new Response('', { status: 404 }));
      if (rel.indexOf('data/') === 0) {
        return files.then(function (f) {
          var text = f[rel.slice(5)];
          return text === undefined ? new Response('', { status: 404 })
            : new Response(text, { headers: { 'content-type': 'application/json' } });
        });
      }
    }
    return realFetch(input, init);
  };
  // Hash changes inside the frame must not add entries to the docs page's history (Back would step the frame).
  var push = history.pushState.bind(history);
  history.pushState = function (s, t, u) { history.replaceState(s, t, u); };
  void push;
  parent.postMessage({ type: 'runcode-ready' }, '*');
})();
