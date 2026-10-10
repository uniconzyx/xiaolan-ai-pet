# 小蓝 AI 桌宠 · Windows 桌面 Q 版 3D 宠物

一只会「活」在桌面的 Q 版 3D 桌宠「小蓝」：金发蓝眸、白色铆钉外套、蓝白爪印鞋，透明置顶、可拖动，具备 **11 种状态动画、语音对话、DeepSeek 大模型对话、以及一整套实用工具**。它像一只真宠物的桌面伙伴，也是你的效率助手。

![小蓝 AI 桌宠](avatar.png)

## 功能特性

### 3D 形象 + 状态动画
- 3D 游戏低模风形象，9 张透明姿态图（`emotions/`）
- **11 种状态**：趴着待机 / 站立 / 挥手 / 跳跃 / 沮丧 / 期待 / 思考 / 左右走动 / 休眠 / 告警
- 空闲时自动在桌面左右漫步，屏幕边缘回弹；久置进入趴睡，点击唤醒

### AI 对话
- 接入 **DeepSeek**（OpenAI 兼容接口），也支持任意兼容 Base URL
- 保留最近 10 轮对话上下文，有连续记忆
- 支持**语音交互**：麦克风说话 → 离线识别（faster-whisper）→ 回复 → TTS 朗读

### 实用工具（让它不只是卖萌）
- **番茄钟**：倒计时提醒，到点切告警动画 + 气泡 + 语音
- **久坐提醒**：全局无操作超时提醒起身
- **待办清单**：气泡展示/管理任务
- **系统监控**：CPU、内存、当前时间
- **快捷启动**：点开文件夹 / 启动程序（如 jupyter）
- **专注陪伴**：检测到你在打字时自动安静、降低动画幅度
- **空闲休眠 + 自动吐泡**：长时间无操作进入低功耗趴睡；休息时随机冒出可爱气泡

### 交互
- 按住左键自由拖动；悬停唤醒；单击对话（语音或文字）
- 半透明蓝色圆角气泡（白字、自适应宽度），点击不退出
- 右键菜单：设置 API / 语音开关 / 清除对话 / 隐藏 / 退出
- 全局快捷键 `Ctrl+Alt+V` 录音

## 环境要求

- Windows 10 / 11
- Python 3.8+
- 语音对话需要麦克风；离线语音识别首次运行会下载 whisper 模型（约 145MB）

## 安装与运行

```bash
pip install -r requirements.txt
python main.py
```

首次运行会在同目录自动生成 `config.json`，填入 DeepSeek API Key 后即可聊天：

```json
{
  "api_key": "sk-你的APIKey",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat"
}
```

> **安全提示**：`config.json` 已加入 `.gitignore`，请勿把真实 API Key 提交到公共仓库。仓库提供 `config.example.json` 作为配置模板。

## 打包为 exe

```bash
pip install pyinstaller
pyinstaller -F -w -n AIPet --exclude-module onnxruntime main.py
```

> `--exclude-module onnxruntime` 用于规避 faster-whisper 的打包崩溃。打包后将 `avatar.png`、`emotions/` 与 exe 放同目录。

开机自启（可选）：将 exe 放入启动文件夹（`Win+R` → `shell:startup`），或用任务计划程序。

## 项目结构

```
ai-pet/
├── main.py                 # 主程序（全部功能）
├── config.example.json     # 配置模板（真实 config.json 由运行生成）
├── avatar.png              # 回退形象（无精灵图时）
├── emotions/               # 3D 姿态透明图（emo_*.png）
├── README.md
├── LICENSE                 # MIT
└── requirements.txt
```

## 主要参数（`main.py` 顶部可配置区）

| 参数 | 默认 | 说明 |
|---|---|---|
| `PET_SIZE` | 340 | 桌宠窗口尺寸 px |
| `MAX_HISTORY` | 10 | 对话记忆轮数 |
| `BUBBLE_BG / FG` | 蓝 / 白 | 气泡颜色 |
| `HOTKEY` | Ctrl+Alt+V | 全局录音快捷键 |
| `DEFAULT_MODEL` | deepseek-chat | 默认模型 |
| `DEFAULT_BASE` | https://api.deepseek.com | 默认 API 地址 |
| `WALK_MIN/MAX_DELAY` | 9~18s | 空闲随机走动间隔 |

## 数据与隐私

- 对话仅发送给配置的 API；语音识别默认**离线**（faster-whisper），不上传音频
- 所有配置与待办保存在本地 `config.json` / `todos.json`

## License

[MIT](LICENSE)
