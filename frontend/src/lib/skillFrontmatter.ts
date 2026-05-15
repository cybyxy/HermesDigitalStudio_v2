/**
 * Parse YAML frontmatter from SKILL.md content
 * Frontmatter format:
 * ---
 * name: Skill Name
 * description: Skill description
 * version: 1.0.0
 * author: Hermes Agent
 * license: MIT
 * platforms: [macos]
 * metadata:
 *   hermes:
 *     tags: [Notes, Apple]
 * ---
 * # Markdown content
 */

export interface SkillFrontmatter {
  name: string;
  description: string;
  version?: string;
  author?: string;
  license?: string;
  platforms?: string[];
  prerequisites?: {
    commands?: string[];
    packages?: string[];
  };
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ParsedSkillContent {
  frontmatter: SkillFrontmatter;
  markdownContent: string;
  rawContent: string;
}

const FRONTMATTER_REGEX = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

export function parseSkillContent(rawContent: string): ParsedSkillContent {
  const match = rawContent.match(FRONTMATTER_REGEX);

  if (!match) {
    return {
      frontmatter: { name: '', description: '' },
      markdownContent: rawContent,
      rawContent,
    };
  }

  const [, frontmatterYaml, markdownContent] = match;
  const frontmatter = parseYamlFrontmatter(frontmatterYaml);

  return {
    frontmatter,
    markdownContent: markdownContent.trim(),
    rawContent,
  };
}

interface ParseContext {
  lines: string[];
  i: number;
}

function parseYamlFrontmatter(yaml: string): SkillFrontmatter {
  const result: SkillFrontmatter = { name: '', description: '' };
  const ctx: ParseContext = { lines: yaml.split('\n'), i: 0 };

  while (ctx.i < ctx.lines.length) {
    const line = ctx.lines[ctx.i];
    const indent = line.match(/^(\s*)/)?.[1].length ?? 0;

    // Empty line or comment
    if (line.trim() === '' || line.trim().startsWith('#')) {
      ctx.i++;
      continue;
    }

    // Check if this is a list item
    if (line.trim().startsWith('- ')) {
      const arrayValue = parseArrayItem(line.trim());
      if (arrayValue !== null) {
        // Get the key from previous line
        const key = getLastKey(result);
        if (key && Array.isArray(result[key])) {
          (result[key] as unknown[]).push(arrayValue);
        }
        ctx.i++;
        continue;
      }
    }

    const colonIndex = line.indexOf(':');
    if (colonIndex === -1) {
      ctx.i++;
      continue;
    }

    const key = line.slice(0, colonIndex).trim();
    const value = line.slice(colonIndex + 1).trim();

    // Empty value - might be nested object or array, check next lines
    if (value === '' || value === '|' || value === '>') {
      ctx.i++;
      const nested = parseNestedValue(ctx, indent, key);
      if (nested !== undefined) {
        result[key] = nested;
      }
      continue;
    }

    // Simple key: value
    result[key] = parseValue(value);
    ctx.i++;
  }

  return result;
}

function parseValue(value: string): unknown {
  // Quoted string
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }

  // Array
  if (value.startsWith('[') && value.endsWith(']')) {
    const arrayContent = value.slice(1, -1).trim();
    if (!arrayContent) return [];
    return arrayContent.split(',').map((item) => {
      const trimmed = item.trim();
      // Check for quoted items
      if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
        return trimmed.slice(1, -1);
      }
      return trimmed;
    });
  }

  // Boolean
  if (value === 'true') return true;
  if (value === 'false') return false;

  // Number
  const num = Number(value);
  if (!isNaN(num) && value !== '') return num;

  // String
  return value;
}

function parseArrayItem(line: string): string | null {
  const match = line.match(/^-\s*(.+)$/);
  if (match) {
    let value = match[1].trim();
    // Remove quotes if present
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    return value;
  }
  return null;
}

function getLastKey(obj: Record<string, unknown>): string | null {
  const keys = Object.keys(obj);
  return keys.length > 0 ? keys[keys.length - 1] : null;
}

function parseNestedValue(ctx: ParseContext, baseIndent: number, key: string): unknown {
  const { lines, i } = ctx;
  const nextLine = lines[i];

  // Check if next line is indented
  const nextIndent = nextLine.match(/^(\s*)/)?.[1].length ?? 0;

  // Not indented means empty value
  if (nextIndent <= baseIndent) {
    return undefined;
  }

  // Array
  if (nextLine.trim().startsWith('-')) {
    const arr: unknown[] = [];
    while (ctx.i < ctx.lines.length) {
      const line = lines[ctx.i].trim();
      if (line.startsWith('- ')) {
        const item = parseArrayItem(line);
        if (item !== null) arr.push(item);
      } else {
        break;
      }
      ctx.i++;
    }
    return arr;
  }

  // Object
  const obj: Record<string, unknown> = {};
  while (ctx.i < ctx.lines.length) {
    const line = lines[ctx.i];
    const indent = line.match(/^(\s*)/)?.[1].length ?? 0;

    // Less indented - end of object
    if (indent <= baseIndent && line.trim() !== '') {
      break;
    }

    // Empty/comment line
    if (line.trim() === '' || line.trim().startsWith('#')) {
      ctx.i++;
      continue;
    }

    const colonIndex = line.trim().indexOf(':');
    if (colonIndex === -1) {
      ctx.i++;
      continue;
    }

    const k = line.trim().slice(0, colonIndex);
    const v = line.trim().slice(colonIndex + 1).trim();

    if (v === '' || v === '|' || v === '>') {
      ctx.i++;
      const nested = parseNestedValue(ctx, indent, k);
      if (nested !== undefined) {
        obj[k] = nested;
      }
    } else {
      obj[k] = parseValue(v);
      ctx.i++;
    }
  }

  return Object.keys(obj).length > 0 ? obj : undefined;
}

export function serializeSkillContent(
  frontmatter: SkillFrontmatter,
  markdownContent: string
): string {
  const yamlLines: string[] = ['---'];

  for (const [key, value] of Object.entries(frontmatter)) {
    if (value === undefined || value === null) continue;
    yamlLines.push(...serializeValue(key, value, 0));
  }

  yamlLines.push('---');

  return yamlLines.join('\n') + '\n\n' + markdownContent;
}

function serializeValue(key: string, value: unknown, indent: number): string[] {
  const prefix = '  '.repeat(indent);
  const lines: string[] = [];

  if (typeof value === 'string') {
    // Quote if contains special characters
    if (value.includes(':') || value.includes('#') || value.includes('[') || value.includes(']') || value.includes('{') || value.includes('}')) {
      lines.push(`${prefix}${key}: "${value.replace(/"/g, '\\"')}"`);
    } else {
      lines.push(`${prefix}${key}: ${value}`);
    }
  } else if (typeof value === 'number' || typeof value === 'boolean') {
    lines.push(`${prefix}${key}: ${String(value)}`);
  } else if (Array.isArray(value)) {
    if (value.length === 0) {
      lines.push(`${prefix}${key}: []`);
    } else {
      lines.push(`${prefix}${key}:`);
      for (const item of value) {
        if (typeof item === 'string') {
          if (item.includes(':') || item.includes(',') || item.includes('[') || item.includes(']')) {
            lines.push(`${prefix}  - "${item.replace(/"/g, '\\"')}"`);
          } else {
            lines.push(`${prefix}  - ${item}`);
          }
        } else {
          lines.push(`${prefix}  - ${String(item)}`);
        }
      }
    }
  } else if (typeof value === 'object' && value !== null) {
    lines.push(`${prefix}${key}:`);
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      lines.push(...serializeValue(k, v, indent + 1));
    }
  }

  return lines;
}
