'use strict';
// Bug tickets. Every one is meant to take a beginner under a minute.
//   output: predict what the code prints          (answer = correct choice)
//   spot:   click the line that has the bug       (answer = 1-based line number)
//   blank:  pick what fills the ___               (answer = correct choice)
//   fix:    edit the code until the tests pass    (fn + tests run in a sandboxed worker)

const TASK_BANK = [
  // ---- predict the output ----
  {
    type: 'output',
    code: 'let x = 5;\nx = x + 2;\nconsole.log(x);',
    choices: ['5', '7', '52', 'x + 2'],
    answer: '7',
    explain: 'x starts at 5, then x + 2 makes it 7.',
  },
  {
    type: 'output',
    code: 'console.log("2" + 2);',
    choices: ['4', '22', 'NaN', 'Error'],
    answer: '22',
    explain: 'Adding a number to a string joins them as text: "2" + 2 is "22".',
  },
  {
    type: 'output',
    code: 'const arr = [10, 20, 30];\nconsole.log(arr[1]);',
    choices: ['10', '20', '30', 'undefined'],
    answer: '20',
    explain: 'Arrays start counting at 0, so arr[1] is the second item: 20.',
  },
  {
    type: 'output',
    code: 'const bugs = ["a", "b", "c", "d"];\nconsole.log(bugs.length);',
    choices: ['3', '4', '5', '"d"'],
    answer: '4',
    explain: 'length counts the items: there are 4.',
  },
  {
    type: 'output',
    code: 'let sum = 0;\nfor (let i = 1; i <= 3; i++) {\n  sum += i;\n}\nconsole.log(sum);',
    choices: ['3', '5', '6', '123'],
    answer: '6',
    explain: 'The loop adds 1 + 2 + 3 = 6.',
  },
  {
    type: 'output',
    code: 'console.log(10 % 3);',
    choices: ['0', '1', '3', '3.33'],
    answer: '1',
    explain: '% gives the remainder: 10 divided by 3 is 3 remainder 1.',
  },
  {
    type: 'output',
    code: 'console.log("bug".toUpperCase());',
    choices: ['bug', 'BUG', 'Bug', 'Error'],
    answer: 'BUG',
    explain: 'toUpperCase() turns every letter into a capital.',
  },
  {
    type: 'output',
    code: 'console.log(3 > 2 && 2 > 5);',
    choices: ['true', 'false', '5', 'undefined'],
    answer: 'false',
    explain: '&& needs both sides true. 2 > 5 is false, so the result is false.',
  },
  {
    type: 'output',
    code: 'const name = "Ada";\nconsole.log(`Hi ${name}!`);',
    choices: ['Hi name!', 'Hi ${name}!', 'Hi Ada!', 'Hi !'],
    answer: 'Hi Ada!',
    explain: 'Inside backticks, ${name} is replaced with the value of name.',
  },
  {
    type: 'output',
    code: 'const nums = [1, 2, 3];\nconsole.log(nums.map(n => n * 2));',
    choices: ['[1, 2, 3]', '[2, 4, 6]', '12', '[1, 4, 9]'],
    answer: '[2, 4, 6]',
    explain: 'map() runs n * 2 on every item and returns a new array.',
  },
  {
    type: 'output',
    code: 'let count = 0;\ncount++;\ncount++;\nconsole.log(count);',
    choices: ['0', '1', '2', '"count++"'],
    answer: '2',
    explain: 'Each count++ adds one, so 0 becomes 2.',
  },
  {
    type: 'output',
    code: 'console.log(Math.max(4, 9, 2));',
    choices: ['2', '4', '9', '15'],
    answer: '9',
    explain: 'Math.max returns the biggest number.',
  },
  {
    type: 'output',
    code: 'const ok = !true;\nconsole.log(ok);',
    choices: ['true', 'false', '!true', 'null'],
    answer: 'false',
    explain: '! flips a boolean, so !true is false.',
  },

  // ---- spot the buggy line ----
  {
    type: 'spot',
    title: 'add() returns the wrong total',
    code: 'function add(a, b) {\n  return a - b;\n}',
    answer: 2,
    explain: 'It subtracts instead of adding: should be a + b.',
  },
  {
    type: 'spot',
    title: 'isEven(4) says false',
    code: 'function isEven(n) {\n  return n % 2 === 1;\n}',
    answer: 2,
    explain: 'Even numbers have remainder 0: n % 2 === 0.',
  },
  {
    type: 'spot',
    title: 'last() returns undefined',
    code: 'function last(arr) {\n  return arr[arr.length];\n}',
    answer: 2,
    explain: 'The last index is arr.length - 1.',
  },
  {
    type: 'spot',
    title: 'Should print 1 to 5, but stops at 4',
    code: 'for (let i = 1; i < 5; i++) {\n  console.log(i);\n}',
    answer: 1,
    explain: 'i < 5 stops before 5. Use i <= 5.',
  },
  {
    type: 'spot',
    title: 'Everyone is treated as 18',
    code: 'function checkAge(age) {\n  if (age = 18) {\n    return "just turned adult";\n  }\n  return "nope";\n}',
    answer: 2,
    explain: '= assigns a value. Comparing needs ===.',
  },
  {
    type: 'spot',
    title: 'greet() crashes',
    code: 'function greet(name) {\n  const hello = "Hello, ";\n  return hello + nme;\n}',
    answer: 3,
    explain: 'Typo: nme should be name.',
  },
  {
    type: 'spot',
    title: 'average([2, 4, 6]) is wrong',
    code: 'function average(nums) {\n  let total = 0;\n  for (const n of nums) total += n;\n  return total / 2;\n}',
    answer: 4,
    explain: 'Divide by how many numbers there are: nums.length, not 2.',
  },
  {
    type: 'spot',
    title: 'max() returns the smaller number',
    code: 'function max(a, b) {\n  return a < b ? a : b;\n}',
    answer: 2,
    explain: 'When a < b, b is the bigger one. Flip it: a > b ? a : b.',
  },
  {
    type: 'spot',
    title: 'isEmpty("") returns false',
    code: 'function isEmpty(str) {\n  return str.length > 0;\n}',
    answer: 2,
    explain: 'An empty string has length 0, so check str.length === 0.',
  },

  // ---- fill in the blank ----
  {
    type: 'blank',
    title: 'Win only when score is exactly 100',
    code: 'if (score ___ 100) {\n  win();\n}',
    choices: ['=', '===', '!==', '=>'],
    answer: '===',
    explain: '=== compares; = would overwrite score.',
  },
  {
    type: 'blank',
    title: 'Add "c" to the end of the list',
    code: 'const items = ["a", "b"];\nitems.___("c");',
    choices: ['push', 'pop', 'shift', 'length'],
    answer: 'push',
    explain: 'push() adds to the end. pop() removes from the end.',
  },
  {
    type: 'blank',
    title: 'Loop over every item without going past the end',
    code: 'for (let i = 0; i ___ arr.length; i++) {\n  check(arr[i]);\n}',
    choices: ['<', '<=', '>', '==='],
    answer: '<',
    explain: 'Indexes go from 0 to length - 1, so keep going while i < length.',
  },
  {
    type: 'blank',
    title: 'double() gives back undefined',
    code: 'function double(n) {\n  ___ n * 2;\n}',
    choices: ['return', 'print', 'const', 'break'],
    answer: 'return',
    explain: 'A function needs return to give a value back.',
  },
  {
    type: 'blank',
    title: 'Deploy only if tests pass AND review is approved',
    code: 'if (testsPass ___ approved) {\n  deploy();\n}',
    choices: ['&&', '||', '!', '??'],
    answer: '&&',
    explain: '&& means both must be true. || would deploy if only one is.',
  },
  {
    type: 'blank',
    title: 'Glue two strings together',
    code: 'const msg = "Build " ___ "passed";',
    choices: ['+', '-', '*', '&'],
    answer: '+',
    explain: '+ joins strings.',
  },
  {
    type: 'blank',
    title: 'How many letters in the word?',
    code: 'const size = "office".___;',
    choices: ['length', 'size', 'count', 'len'],
    answer: 'length',
    explain: 'Strings and arrays use .length in JavaScript.',
  },
  {
    type: 'blank',
    title: 'This value should never change',
    code: '___ MAX_USERS = 50;',
    choices: ['const', 'let', 'var', 'function'],
    answer: 'const',
    explain: 'const makes a variable that cannot be reassigned.',
  },

  // ---- fix it yourself ----
  {
    type: 'fix',
    title: 'add() subtracts',
    code: 'function add(a, b) {\n  return a - b;\n}',
    fn: 'add',
    tests: [[[2, 3], 5], [[10, 4], 14], [[-1, 1], 0]],
    hint: 'Check the operator.',
  },
  {
    type: 'fix',
    title: 'isEven() is backwards',
    code: 'function isEven(n) {\n  return n % 2 === 1;\n}',
    fn: 'isEven',
    tests: [[[4], true], [[7], false], [[0], true]],
    hint: 'Even numbers have no remainder when divided by 2.',
  },
  {
    type: 'fix',
    title: 'last() returns undefined',
    code: 'function last(arr) {\n  return arr[arr.length];\n}',
    fn: 'last',
    tests: [[[[1, 2, 3]], 3], [[['x']], 'x']],
    hint: 'Indexes start at 0.',
  },
  {
    type: 'fix',
    title: 'greet() crashes',
    code: 'function greet(name) {\n  return "Hello " + nme;\n}',
    fn: 'greet',
    tests: [[['Ada'], 'Hello Ada'], [['Linus'], 'Hello Linus']],
    hint: 'Look closely at the variable name.',
  },
  {
    type: 'fix',
    title: 'square() doubles instead',
    code: 'function square(n) {\n  return n * 2;\n}',
    fn: 'square',
    tests: [[[3], 9], [[5], 25], [[2], 4]],
    hint: 'Square means a number times itself.',
  },
  {
    type: 'fix',
    title: 'isAdult(18) should be true',
    code: 'function isAdult(age) {\n  return age > 18;\n}',
    fn: 'isAdult',
    tests: [[[18], true], [[30], true], [[12], false]],
    hint: '18 itself should count.',
  },
  {
    type: 'fix',
    title: 'countdown() never ends',
    code: 'function countdown(n) {\n  const out = [];\n  for (let i = n; i > 0; i++) {\n    out.push(i);\n  }\n  return out;\n}',
    fn: 'countdown',
    tests: [[[3], [3, 2, 1]], [[1], [1]]],
    hint: 'Counting down means i should get smaller each step.',
  },
  {
    type: 'fix',
    title: 'max() picks the smaller number',
    code: 'function max(a, b) {\n  return a < b ? a : b;\n}',
    fn: 'max',
    tests: [[[3, 8], 8], [[9, 2], 9]],
    hint: 'Swap the comparison or the results.',
  },
];

// Quick fixes for the production outage sabotage.
const RACK_TASKS = [
  {
    type: 'blank',
    title: 'Prod is down! Bring it back up',
    code: 'server.___();',
    choices: ['restart', 'delete', 'sleep', 'crash'],
    answer: 'restart',
    explain: 'restart() brings the service back.',
  },
  {
    type: 'blank',
    title: 'Reboot only when the status is down',
    code: 'if (status ___ "down") {\n  reboot();\n}',
    choices: ['===', '=', '!==', '+'],
    answer: '===',
    explain: '=== checks whether status equals "down".',
  },
  {
    type: 'blank',
    title: 'The server is healthy when there are zero errors',
    code: 'const healthy = errors.length ___ 0;',
    choices: ['===', '>', '+', '='],
    answer: '===',
    explain: 'Zero errors means errors.length === 0.',
  },
  {
    type: 'output',
    title: 'Which port is prod listening on?',
    code: 'const port = 8000 + 80;\nconsole.log(port);',
    choices: ['8080', '800080', '80', '8000'],
    answer: '8080',
    explain: '8000 + 80 = 8080.',
  },
];

function randomTask(exclude) {
  const pool = TASK_BANK.filter((t) => t !== exclude);
  return pool[Math.floor(Math.random() * pool.length)];
}

function randomRackTask() {
  return RACK_TASKS[Math.floor(Math.random() * RACK_TASKS.length)];
}
