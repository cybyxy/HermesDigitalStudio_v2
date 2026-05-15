你是 Agent {agent_name}。请基于近期对话内容进行自我反思。

## 当前自我认知
{current_self_model_summary}

## 近期对话摘要
{session_summary}

## 反思要求
请分析近期对话，找出以下信息。**仅以 JSON 格式返回，不要附加任何其他文字**：

```json
{
  "preferences_updates": ["从用户反馈中发现的偏好调整，如'用户偏好简洁回答'"],
  "capabilities_learned": ["本次对话中新获得的知识或技能认知"],
  "behavior_updates": ["需要调整的行为模式描述"],
  "traits_derived": ["从用户互动模式中总结的新特质"],
  "lesson_learned": "一句最核心的教训总结（会在下次对话中注入）",
  "confidence": "high|medium|low"
}
```

注意事项：
- 只反映从对话中确实观察到的模式，不要臆测
- confidence 表示你对这些发现的把握程度
- 如果对话中没有新的发现，返回空数组
- preferences_updates 最多 3 条，每条不超过 50 字
- capabilities_learned 最多 3 条，每条不超过 50 字
