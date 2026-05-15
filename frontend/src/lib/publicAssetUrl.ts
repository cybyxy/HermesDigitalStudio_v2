/**
 * Vite `public/` 下的资源 URL。
 * 在浏览器里拼成 **相对当前站点根路径的绝对地址**（含 origin），避免 History 路由、子路径或相对解析导致请求打到错误路径。
 */
export function publicAssetUrl(rel: string): string {
  const trimmed = rel.replace(/^\/+/, '');
  const rawBase = import.meta.env.BASE_URL ?? '/';
  const base = rawBase.endsWith('/') ? rawBase : `${rawBase}/`;
  let pathFromRoot = `${base}${trimmed}`;
  if (!pathFromRoot.startsWith('/')) {
    pathFromRoot = `/${pathFromRoot}`;
  }
  pathFromRoot = pathFromRoot.replace(/\/{2,}/g, '/');

  if (
    typeof window !== 'undefined' &&
    window.location?.protocol &&
    window.location.protocol !== 'file:' &&
    window.location.origin
  ) {
    return new URL(pathFromRoot, window.location.origin).href;
  }
  return pathFromRoot;
}
