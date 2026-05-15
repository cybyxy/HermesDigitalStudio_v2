import type { PlanArtifact, PlanStep } from '../types';
import { splitReasoning } from './reasoning';
import { stripStudioToolLines } from './studioInlineMarkers';

/** 围栏 JSON 后常见的 Markdown 分隔线（Studio 规划约定后接自然语言）。 */
function stripLeadingMarkdownDivider(s: string): string {
  let t = s.trimStart();
  const hr = /^(?:[ \t]*(?:-{3,}|_{3,}|\*{3,})[ \t]*)(?:\r?\n\s*|\r?\n*$)/u;
  while (t.length > 0 && hr.test(t)) {
    t = t.replace(hr, '').trimStart();
  }
  return t;
}

/** 去掉正文开头用于展示的 JSON 围栏 / 裸对象（与解析规划用同一套边界）。 */
function extractLeadingJsonRange(raw: string): { start: number; end: number } | null {
  const fence = /^(\s*)```(?:json)?\s*\n?([\s\S]*?)```\s*/.exec(raw);
  if (fence && fence.index === 0) {
    return { start: 0, end: fence[0].length };
  }
  let s = 0;
  while (s < raw.length && /\s/.test(raw[s])) s++;
  if (raw[s] !== '{') return null;
  let depth = 0;
  for (let i = s; i < raw.length; i++) {
    const c = raw[i];
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) {
        let end = i + 1;
        while (end < raw.length && (raw[end] === '\n' || raw[end] === '\r')) end++;
        return { start: 0, end };
      }
    }
  }
  return null;
}

function extractJsonObjectStringFromSlice(slice: string): string | null {
  const t = slice.trimStart();
  const fence = /^```(?:json)?\s*\n?([\s\S]*?)\n?```/;
  const m = t.match(fence);
  if (m?.[1]) {
    const inner = m[1].trim();
    if (inner.startsWith('{')) return inner;
  }
  if (!t.startsWith('{')) return null;
  let depth = 0;
  let start = -1;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (c === '{') {
      if (depth === 0) start = i;
      depth++;
    } else if (c === '}') {
      depth--;
      if (depth === 0 && start >= 0) return t.slice(start, i + 1);
    }
  }
  return null;
}

function normConfidence(v: unknown): PlanStep['confidence'] {
  const s = typeof v === 'string' ? v.toLowerCase() : '';
  if (s === 'high' || s === 'medium' || s === 'low') return s;
  return 'medium';
}

function normalizeArtifact(data: unknown): PlanArtifact | null {
  if (!data || typeof data !== 'object') return null;
  const o = data as Record<string, unknown>;
  const planSummary = typeof o.plan_summary === 'string' ? o.plan_summary.trim() : '';
  if (!Array.isArray(o.steps)) return null;

  // name: 优先取 JSON 中的 name 字段；若缺则降级用 plan_summary 前 50 字
  const rawName = typeof o.name === 'string' ? o.name.trim() : '';
  const name = rawName || (planSummary ? planSummary.slice(0, 50) : '');

  const steps: PlanStep[] = [];
  for (const item of o.steps) {
    if (!item || typeof item !== 'object') continue;
    const r = item as Record<string, unknown>;
    const idRaw = r.id;
    const id =
      typeof idRaw === 'number' && Number.isFinite(idRaw)
        ? idRaw
        : typeof idRaw === 'string'
          ? Number.parseInt(idRaw, 10)
          : NaN;
    const title = typeof r.title === 'string' ? r.title.trim() : '';
    const action = typeof r.action === 'string' ? r.action.trim() : '';
    const filePath =
      typeof r.file_path === 'string' && r.file_path.trim() ? r.file_path.trim() : undefined;
    if (!title && !action) continue;
    steps.push({
      id: Number.isFinite(id) ? id : steps.length + 1,
      title: title || `步骤 ${steps.length + 1}`,
      action: action || '—',
      filePath,
      confidence: normConfidence(r.confidence),
    });
  }
  return { name, planSummary, steps };
}

function artifactFromText(text: string): PlanArtifact | null {
  const range = extractLeadingJsonRange(text);
  const slice = range ? text.slice(range.start, range.end) : text;
  const jsonStr = extractJsonObjectStringFromSlice(slice);
  if (!jsonStr) return null;
  try {
    const data = JSON.parse(jsonStr) as unknown;
    const out = normalizeArtifact(data);
    if (!out) return null;
    if (!out.planSummary.trim() && out.steps.length === 0) return null;
    return out;
  } catch {
    return null;
  }
}

/** 解析规划 + 去掉开头 JSON 后的自然语言正文（用于右侧气泡）。 */
export function parseAssistantPlanPayload(text: string): { artifact: PlanArtifact | null; bodyText: string } {
  const logical = splitReasoning(text).text.trimStart();
  const range = extractLeadingJsonRange(logical);
  const artifact = artifactFromText(logical);
  let bodyText = range ? (logical.slice(0, range.start) + logical.slice(range.end)).trim() : logical;
  bodyText = stripStudioToolLines(stripLeadingMarkdownDivider(bodyText)).trim();
  return { artifact, bodyText };
}

/** 流式阶段：若开头 JSON 围栏已闭合则只显示其后正文，否则用省略号占位，避免半屏 raw JSON。 */
export function assistantVisibleBodyWhileStreaming(full: string): string {
  const t = splitReasoning(full).text;
  const open = /^\s*```(?:json)?\s*\n?/.exec(t);
  if (open) {
    const afterOpen = t.slice(open[0].length);
    const close = afterOpen.indexOf('```');
    if (close === -1) return '…';
    let afterFence = afterOpen.slice(close + 3).replace(/^\s*\n?/, '');
    afterFence = stripStudioToolLines(stripLeadingMarkdownDivider(afterFence)).trim();
    return afterFence ? afterFence : '…';
  }
  const r = extractLeadingJsonRange(t);
  if (r && r.end <= t.length) {
    const rest = stripStudioToolLines(
      stripLeadingMarkdownDivider((t.slice(0, r.start) + t.slice(r.end)).trim()),
    ).trim();
    return rest || '…';
  }
  return stripStudioToolLines(t);
}

/** @deprecated 使用 ``parseAssistantPlanPayload`` */
export function tryParsePlanArtifactFromAssistantText(text: string): PlanArtifact | null {
  return parseAssistantPlanPayload(text).artifact;
}

// ── 规划关键词检测 & 模板注入引导 ─────────────────────────────────────────────

/** 规划类关键词（用于检测 AI 回复是否涉及规划但未返回结构化 JSON）。 */
const PLAN_KEYWORDS = [
  '规划', '计划', '任务', '编排', '步骤', '执行步骤',
  'plan', 'planning', 'task', 'tasks', 'step', 'steps',
  'todo', 'todos', 'to-do', 'roadmap', 'workflow',
  '安排', '策畧', '策略', '分解', '拆分',
];

/** 检测文本是否包含规划类关键词。 */
export function containsPlanKeywords(text: string): boolean {
  if (!text) return false;
  const lower = text.toLowerCase();
  return PLAN_KEYWORDS.some(kw => lower.includes(kw.toLowerCase()));
}

/** 判断 AI 回复是否需要注入 JSON 模板重新推理：
 *  - 包含规划类关键词
 *  - 但没有成功解析出结构化 PlanArtifact
 *  - 且不是已经流式完成（有完整 JSON）的情况
 */
export function shouldInjectPlanTemplate(
  text: string,
  hasCompleteJson: boolean,
): boolean {
  if (!text || hasCompleteJson) return false;
  return containsPlanKeywords(text) && !artifactFromText(text);
}

/** JSON 模板注释（注入模型后引导生成结构化规划）。 */
export const PLAN_TEMPLATE_ANNOTATION = `
请将上述内容整理为以下 JSON 格式返回（只需返回 JSON，无需其他文字）：

\`\`\`json
{
  "name": "规划名称",
  "plan_summary": "一句话概括整体目标",
  "steps": [
    {
      "id": 1,
      "title": "步骤标题",
      "action": "具体执行动作描述",
      "filePath": "相关文件路径（可选）",
      "confidence": "high/medium/low"
    }
  ]
}
\`\`\`
`.trim();
