// اصلاحیهٔ ۶ / amendment 6: bundle Monaco locally (no CDN) so the web editor works
// offline behind nginx. Importing this module once configures @monaco-editor/react's
// loader to use the bundled `monaco-editor` package and wires the language workers.
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker';
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker';
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker';

type WorkerFactory = () => Worker;

const workers: Record<string, WorkerFactory> = {
  json: () => new jsonWorker(),
  css: () => new cssWorker(),
  scss: () => new cssWorker(),
  less: () => new cssWorker(),
  html: () => new htmlWorker(),
  handlebars: () => new htmlWorker(),
  razor: () => new htmlWorker(),
  typescript: () => new tsWorker(),
  javascript: () => new tsWorker(),
};

(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    return (workers[label] ?? (() => new editorWorker()))();
  },
};

loader.config({ monaco });

const EXT_LANG: Record<string, string> = {
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript', mjs: 'javascript',
  py: 'python', json: 'json', md: 'markdown', markdown: 'markdown', html: 'html', htm: 'html',
  css: 'css', scss: 'scss', less: 'less', yaml: 'yaml', yml: 'yaml', sh: 'shell', bash: 'shell',
  sql: 'sql', go: 'go', rs: 'rust', java: 'java', c: 'c', h: 'c', cpp: 'cpp', hpp: 'cpp',
  toml: 'ini', ini: 'ini', xml: 'xml', txt: 'plaintext', env: 'ini', dockerfile: 'dockerfile',
};

export function languageForPath(path: string): string {
  const name = path.split('/').pop() ?? '';
  if (name.toLowerCase() === 'dockerfile') return 'dockerfile';
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : '';
  return EXT_LANG[ext] ?? 'plaintext';
}
