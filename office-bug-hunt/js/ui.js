'use strict';
// DOM helpers: toasts, the coding-task modal and the sandboxed test runner.

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

const TOKEN_RE = /(\/\/.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|(___)|(\b\d+(?:\.\d+)?\b)|(\b(?:const|let|var|function|return|if|else|for|while|of|in|true|false|null|undefined|new)\b)/g;

function highlightLine(line) {
  let out = '';
  let last = 0;
  line.replace(TOKEN_RE, (m, com, str, blank, num, kw, idx) => {
    out += escapeHtml(line.slice(last, idx));
    const cls = com ? 'com' : str ? 'str' : blank ? 'blank' : num ? 'num' : 'kw';
    out += `<span class="${cls}">${escapeHtml(m)}</span>`;
    last = idx + m.length;
    return m;
  });
  return out + escapeHtml(line.slice(last));
}

function renderCode(el, code, clickable) {
  el.innerHTML = code
    .split('\n')
    .map((line, i) => `<div class="line" data-line="${i + 1}"><span class="ln">${i + 1}</span><span>${highlightLine(line) || ' '}</span></div>`)
    .join('');
  el.classList.toggle('clickable', !!clickable);
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ---------------------------------------------------------------- toasts

function toast(text, kind = '') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = text;
  $('toasts').prepend(el);
  while ($('toasts').children.length > 5) $('toasts').lastChild.remove();
  setTimeout(() => el.remove(), 5000);
}

// ---------------------------------------------------------------- test runner

const WORKER_SRC = `
self.onmessage = (e) => {
  const { code, fn, tests } = e.data;
  try {
    const f = new Function(code + "\\n;return typeof " + fn + " === 'function' ? " + fn + " : undefined;")();
    if (!f) { postMessage({ error: "Couldn't find a function called " + fn + "()" }); return; }
    const results = tests.map(([args, expected]) => {
      try {
        const got = f(...JSON.parse(JSON.stringify(args)));
        return { args, expected, got: got === undefined ? 'undefined' : got, ok: JSON.stringify(got) === JSON.stringify(expected) };
      } catch (ex) {
        return { args, expected, got: String(ex), ok: false };
      }
    });
    postMessage({ results });
  } catch (ex) {
    postMessage({ error: String(ex) });
  }
};`;

// Runs player code in a Worker so an infinite loop can be killed.
function runTests(code, fn, tests) {
  return new Promise((resolve) => {
    let worker;
    try {
      worker = new Worker(URL.createObjectURL(new Blob([WORKER_SRC], { type: 'text/javascript' })));
    } catch (e) {
      resolve({ error: 'Your browser blocked the test sandbox, so the code could not be run.' });
      return;
    }
    const timer = setTimeout(() => {
      worker.terminate();
      resolve({ error: 'Timed out after 1.5s. Is there an infinite loop?' });
    }, 1500);
    worker.onmessage = (e) => {
      clearTimeout(timer);
      worker.terminate();
      resolve(e.data);
    };
    worker.onerror = (e) => {
      clearTimeout(timer);
      worker.terminate();
      resolve({ error: e.message || 'Syntax error' });
    };
    worker.postMessage({ code, fn, tests });
  });
}

// ---------------------------------------------------------------- task modal

const DEFAULT_PROMPTS = {
  output: 'What does this print?',
  spot: 'Click the line with the bug.',
  blank: 'Pick what goes in the yellow blank.',
  fix: 'Edit the code so every test passes, then run the tests.',
};

let taskModal = null; // { task, onSolved, onFailed, onClose, finished }

function isTaskModalOpen() {
  return taskModal !== null;
}

function openTaskModal({ ticketId, title, task, onSolved, onFailed, onClose }) {
  taskModal = { task, onSolved, onFailed, onClose, finished: false };
  $('task-ticket').textContent = ticketId;
  $('task-title').textContent = task.title ? `${title}: ${task.title}` : title;
  $('task-prompt').textContent = DEFAULT_PROMPTS[task.type];
  $('task-feedback').textContent = '';
  $('task-feedback').className = '';
  $('task-tests').innerHTML = '';
  $('task-choices').innerHTML = '';

  const codeEl = $('task-code');
  const editor = $('task-editor');
  const run = $('task-run');
  codeEl.classList.toggle('hidden', task.type === 'fix');
  editor.classList.toggle('hidden', task.type !== 'fix');
  run.classList.toggle('hidden', task.type !== 'fix');
  run.disabled = false;

  if (task.type === 'fix') {
    editor.value = task.code;
    editor.disabled = false;
    $('task-tests').innerHTML = task.tests.map(([args, exp]) => `<div>${escapeHtml(callText(task.fn, args))} should be ${escapeHtml(JSON.stringify(exp))}</div>`).join('') +
      `<div style="color:var(--muted);margin-top:4px">Hint: ${escapeHtml(task.hint)}</div>`;
    setTimeout(() => editor.focus(), 50);
  } else {
    renderCode(codeEl, task.code, task.type === 'spot');
    if (task.type === 'spot') {
      codeEl.querySelectorAll('.line').forEach((ln) => {
        ln.onclick = () => {
          if (taskModal.finished) return;
          const n = Number(ln.dataset.line);
          const good = n === task.answer;
          ln.classList.add(good ? 'picked-good' : 'picked-bad');
          if (!good) codeEl.querySelector(`[data-line="${task.answer}"]`).classList.add('picked-good');
          finishTask(good, task.explain);
        };
      });
    } else {
      for (const choice of shuffle(task.choices)) {
        const b = document.createElement('button');
        b.textContent = choice;
        b.onclick = () => {
          if (taskModal.finished) return;
          const good = choice === task.answer;
          b.classList.add(good ? 'good' : 'bad');
          if (!good) [...$('task-choices').children].find((x) => x.textContent === task.answer).classList.add('good');
          finishTask(good, task.explain);
        };
        $('task-choices').appendChild(b);
      }
    }
  }
  $('task-modal').classList.remove('hidden');
}

function callText(fn, args) {
  return `${fn}(${args.map((a) => JSON.stringify(a)).join(', ')})`;
}

function finishTask(good, explain) {
  const m = taskModal;
  m.finished = true;
  $('task-run').disabled = true;
  $('task-editor').disabled = true;
  const fb = $('task-feedback');
  if (good) {
    fb.className = 'good';
    fb.textContent = `Fixed! ${explain || ''} Ticket closed.`;
    m.onSolved();
    setTimeout(() => {
      if (taskModal === m) closeTaskModal();
    }, 1400);
  } else {
    fb.className = 'bad';
    fb.textContent = `Not quite. ${explain || ''} The ticket was reshuffled: try again in a few seconds.`;
    m.onFailed();
  }
}

async function runFixTests() {
  const m = taskModal;
  if (!m || m.finished) return;
  $('task-run').disabled = true;
  $('task-feedback').className = '';
  $('task-feedback').textContent = 'Running tests...';
  const res = await runTests($('task-editor').value, m.task.fn, m.task.tests);
  if (taskModal !== m) return;
  $('task-run').disabled = false;
  if (res.error) {
    $('task-feedback').className = 'bad';
    $('task-feedback').textContent = res.error;
    return;
  }
  $('task-tests').innerHTML = res.results
    .map((r) => `<div class="${r.ok ? 'ok' : 'fail'}">${r.ok ? '✓' : '✗'} ${escapeHtml(callText(m.task.fn, r.args))} → ${escapeHtml(JSON.stringify(r.got))}${r.ok ? '' : ` (expected ${escapeHtml(JSON.stringify(r.expected))})`}</div>`)
    .join('');
  if (res.results.every((r) => r.ok)) {
    finishTask(true, 'All tests pass.');
  } else {
    // Unlike the multiple-choice tickets, a failing run is not a strike: keep editing.
    $('task-feedback').className = 'bad';
    $('task-feedback').textContent = 'Some tests still fail. Keep editing.';
  }
}

function closeTaskModal() {
  if (!taskModal) return;
  const m = taskModal;
  taskModal = null;
  $('task-modal').classList.add('hidden');
  if (m.onClose) m.onClose();
}

$('task-close').onclick = closeTaskModal;
$('task-run').onclick = runFixTests;
$('task-editor').addEventListener('keydown', (e) => {
  e.stopPropagation();
  if (e.key === 'Tab') {
    e.preventDefault();
    const ed = e.target;
    const s = ed.selectionStart;
    ed.value = ed.value.slice(0, s) + '  ' + ed.value.slice(ed.selectionEnd);
    ed.selectionStart = ed.selectionEnd = s + 2;
  } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    runFixTests();
  } else if (e.key === 'Escape') {
    closeTaskModal();
  }
});
