/**
 * Stores 统一导出
 *
 * 导出所有域 Store，支持新旧代码的 import 路径：
 * - 旧代码: `import { useChatStore } from '@/stores/chatStore'` (保持兼容)
 * - 新代码: `import { useSessionStore } from '@/stores'` (通过 index.ts)
 */
export { useAppStore } from './appStore';
export { useSessionStore } from './sessionStore';
export { useAgentStore } from './agentStore';
export { useUiStore } from './uiStore';
export { useChannelStore } from './channelStore';
export { useModelStore } from './modelStore';
export { useSkillStore } from './skillStore';
export { useFeishuStore } from './feishuStore';
export { usePlanStore } from './planStore';
export { useOfficeAgentPoseStore } from './officeAgentPoseStore';

// 向后兼容 - 保留旧 chatStore 引用
export { useChatStore } from './chatStore';
