/**
 * 模型或历史合并产生的内联工具行，仅应在「推理 · 工具」区展示，不应出现在主会话气泡。
 * 形态：``_工具 write_file_: /path/to/file``
 */
export function stripStudioToolLines(text: string): string {
  const next = text
    .split(/\r?\n/)
    .filter(line => !/^\s*_工具\s+.+?_:\s*/.test(line))
    .join('\n');
  return next.replace(/\n{3,}/g, '\n\n').trim();
}
