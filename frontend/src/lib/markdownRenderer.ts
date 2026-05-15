/**
 * Simple Markdown to HTML renderer for skill preview
 * Supports: headings, bold, italic, code blocks, inline code, links, lists, blockquotes, horizontal rules
 */

export function renderMarkdown(markdown: string): string {
  if (!markdown) return '';

  let html = escapeHtml(markdown);

  // Code blocks (must be before inline code)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre class="md-code-block"><code class="md-code">${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');

  // Headings
  html = html.replace(/^### (.*$)/gm, '<h3 class="md-h3">$1</h3>');
  html = html.replace(/^## (.*$)/gm, '<h2 class="md-h2">$1</h2>');
  html = html.replace(/^# (.*$)/gm, '<h1 class="md-h1">$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/___(.+?)___/g, '<strong><em>$1</em></strong>');
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
  html = html.replace(/_(.+?)_/g, '<em>$1</em>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a class="md-link" href="$2" target="_blank" rel="noopener">$1</a>');

  // Blockquotes
  html = html.replace(/^&gt; (.*$)/gm, '<blockquote class="md-blockquote">$1</blockquote>');

  // Unordered lists
  html = html.replace(/^[-*+] (.*$)/gm, '<li class="md-li">$1</li>');
  html = html.replace(/(<li class="md-li">.*<\/li>\n?)+/g, '<ul class="md-ul">$&</ul>');

  // Ordered lists
  html = html.replace(/^\d+\. (.*$)/gm, '<li class="md-li">$1</li>');

  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr class="md-hr">');
  html = html.replace(/^\*\*\*$/gm, '<hr class="md-hr">');

  // Paragraphs (double newlines)
  html = html.replace(/\n\n+/g, '</p><p class="md-p">');
  html = '<p class="md-p">' + html + '</p>';

  // Clean up empty paragraphs
  html = html.replace(/<p class="md-p"><\/p>/g, '');
  html = html.replace(/<p class="md-p">(<h[1-3]|<ul|<blockquote|<pre|<hr)/g, '$1');
  html = html.replace(/(<\/h[1-3]>|<\/ul>|<\/blockquote>|<\/pre>)<\/p>/g, '$1');

  return html;
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}

export function renderMarkdownToElement(container: HTMLElement, markdown: string): void {
  container.innerHTML = renderMarkdown(markdown);
}
