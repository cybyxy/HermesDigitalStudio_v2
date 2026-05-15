/**
 * A* grid pathfinding.
 * Works on a 2D boolean grid (true = walkable).
 * Returns array of {x,y} tile coordinates from start to end, inclusive.
 * If no path exists, returns [].
 */

export interface AStarNode {
  x: number;
  y: number;
  g: number; // cost from start
  h: number; // heuristic to goal
  f: number; // g + h
  parent: AStarNode | null;
}

function heuristic(ax: number, ay: number, bx: number, by: number): number {
  return Math.abs(ax - bx) + Math.abs(ay - by);
}

export function astar(
  grid: boolean[][],
  startX: number,
  startY: number,
  goalX: number,
  goalY: number,
): { x: number; y: number }[] {
  const rows = grid.length;
  if (rows === 0) return [];
  const cols = grid[0]!.length;

  if (
    startX < 0 || startX >= cols || startY < 0 || startY >= rows ||
    goalX < 0 || goalX >= cols || goalY < 0 || goalY >= rows
  ) {
    return [];
  }

  if (!grid[startY]![startX]! || !grid[goalY]![goalX]!) {
    return [];
  }

  if (startX === goalX && startY === goalY) {
    return [{ x: startX, y: startY }];
  }

  const key = (x: number, y: number): string => `${x},${y}`;

  const open: AStarNode[] = [];
  const openSet = new Set<string>();
  const closed = new Set<string>();

  const startNode: AStarNode = {
    x: startX,
    y: startY,
    g: 0,
    h: heuristic(startX, startY, goalX, goalY),
    f: heuristic(startX, startY, goalX, goalY),
    parent: null,
  };
  open.push(startNode);
  openSet.add(key(startX, startY));

  // 4-directional movement
  const DIRS = [
    { dx: 0, dy: -1 },
    { dx: 1, dy: 0 },
    { dx: 0, dy: 1 },
    { dx: -1, dy: 0 },
  ];

  while (open.length > 0) {
    // pop node with lowest f
    open.sort((a, b) => a.f - b.f);
    const current = open.shift()!;
    const ck = key(current.x, current.y);
    openSet.delete(ck);
    closed.add(ck);

    if (current.x === goalX && current.y === goalY) {
      const path: { x: number; y: number }[] = [];
      let node: AStarNode | null = current;
      while (node) {
        path.unshift({ x: node.x, y: node.y });
        node = node.parent;
      }
      return path;
    }

    for (const { dx, dy } of DIRS) {
      const nx = current.x + dx;
      const ny = current.y + dy;
      const nk = key(nx, ny);

      if (
        nx < 0 || nx >= cols || ny < 0 || ny >= rows ||
        !grid[ny]![nx] ||
        closed.has(nk)
      ) {
        continue;
      }

      const g = current.g + 1;
      const h = heuristic(nx, ny, goalX, goalY);
      const f = g + h;

      const existingIdx = open.findIndex((n) => n.x === nx && n.y === ny);
      if (existingIdx !== -1) {
        if (g < open[existingIdx]!.g) {
          open[existingIdx]!.g = g;
          open[existingIdx]!.f = f;
          open[existingIdx]!.parent = current;
        }
      } else {
        open.push({ x: nx, y: ny, g, h, f, parent: current });
        openSet.add(nk);
      }
    }
  }

  return [];
}

/**
 * When a point falls on a blocked or out-of-bounds tile (e.g. map spawn on furniture),
 * find the closest walkable tile by BFS. Returns null if the grid has no walkable cells.
 */
export function nearestWalkableTile(
  grid: boolean[][],
  x: number,
  y: number,
): { x: number; y: number } | null {
  const rows = grid.length;
  if (rows === 0) return null;
  const cols = grid[0]!.length;

  const inBounds = (ix: number, iy: number) => ix >= 0 && ix < cols && iy >= 0 && iy < rows;
  const key = (ix: number, iy: number) => `${ix},${iy}`;

  if (inBounds(x, y) && grid[y]![x]!) {
    return { x, y };
  }

  const q: { x: number; y: number }[] = [{ x, y }];
  const seen = new Set<string>([key(x, y)]);
  const dirs = [
    { dx: 0, dy: -1 },
    { dx: 1, dy: 0 },
    { dx: 0, dy: 1 },
    { dx: -1, dy: 0 },
  ];

  for (let i = 0; i < q.length; i++) {
    const { x: cx, y: cy } = q[i]!;
    for (const { dx, dy } of dirs) {
      const nx = cx + dx;
      const ny = cy + dy;
      const k = key(nx, ny);
      if (seen.has(k)) continue;
      seen.add(k);
      if (!inBounds(nx, ny)) continue;
      if (grid[ny]![nx]!) {
        return { x: nx, y: ny };
      }
      q.push({ x: nx, y: ny });
    }
  }

  return null;
}
