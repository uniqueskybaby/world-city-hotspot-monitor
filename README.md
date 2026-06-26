# 世界城招商热点监测

第一版是一个可部署的网站：每天提前采集公开资讯，AI/规则引擎清洗后，在早上 8 点展示完成版招商热点。

## 功能

- 今日热点情报流：按国内新兴品牌、新消费爆款、国际新兴品牌、线下扩张、社媒爆火、融资动态筛选。
- 每日日报：总结昨日招商重点新闻、刚爆火的新兴品牌、招商动作建议和审核记录；每个日报块都能点开查看热点详情和原文。
- 热点详情：展示 AI 摘要、招商洞察、可信度、相关度和原始资讯链接。
- 历史日报：按日期保存每日发布版本。
- 信源管理：支持公开网页、RSS、公开链接列表和互联网搜索。
- 任务日志：支持手动更新、定时更新和失败日志查看。
- 登录预留：第一版不启用登录，但后端已预留角色和权限接口。

## 本地运行

### 双击运行

接收方解压本地运行包后：

- macOS：双击 `start-mac.command`
- Windows：双击 `start-windows.bat`
- Linux：运行 `start-linux.sh`

启动脚本会自动检查依赖、安装后端运行环境、等待服务就绪、打开浏览器并启动本地服务。Windows 如果缺少 Python 3.9+，会优先尝试通过系统自带的 `winget` 自动安装 Python 3.12；如果电脑没有 `winget`，脚本会打开 Python 下载页。交付包内已包含 `dist` 页面文件，所以接收方正常情况下不需要安装 Node.js；如果 `dist` 被删除，才需要 Node.js 20.19+ 或 22.12+ 重新构建前端。包内保留 `data/hotspots.db` 作为演示和测试数据。

Windows 如果启动失败，请查看同目录生成的 `startup-log.txt`。常见原因是网络无法安装 Python 依赖、公司电脑禁用 `winget`、或安全软件拦截本地服务。若浏览器没有自动打开，可手动复制启动窗口里显示的 `http://127.0.0.1:端口号`。

### 手动运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run build
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。

## 本地交付包

```bash
npm run package:local
```

输出文件位于 `release/world-city-hotspot-monitor-local.zip`。打包会排除 `.venv`、`node_modules`、`.npm-cache`、`artifacts`、`.env` 等开发中间产物，并保留演示数据库和可直接运行的 `dist` 页面文件。

## 远端部署

当前线上演示适合用 GitHub Pages 发布静态快照：先导出 `public/demo-data.json`，再用 `VITE_STATIC_DEMO=true npm run build:pages` 构建，并把 `dist` 发布到 `gh-pages` 分支。网页演示读取测试数据快照；完整采集、更新和后端 API 请使用本地运行或 Docker 部署。

```bash
cp .env.example .env
docker compose up -d --build
```

服务器上访问 `http://服务器IP:8000`。正式域名建议用 Nginx 或云厂商网关做 HTTPS 反向代理。

## 每日更新时间

默认配置：

- `06:30` 开始采集和清洗
- 服务如果在 `06:30` 之后启动且当天还没有成功任务，会自动补跑一次
- 任务完成后立即发布日报，目标是在 `08:00` 前展示完成版

可在 `.env` 中调整：

```bash
APP_TIMEZONE=Asia/Shanghai
DAILY_UPDATE_START=06:30
ENABLE_SCHEDULER=true
RUNNING_JOB_STALE_MINUTES=180
```

## DeepSeek AI 配置

没有模型 key 时，系统使用内置规则引擎和样例数据跑通流程。配置 DeepSeek 后，系统会默认启用多智能体工作流：

- 信息抽取智能体：`deepseek-v4-flash`
- 可信度判断智能体：`deepseek-v4-flash`
- 招商策略智能体：普通任务用 `deepseek-v4-flash`，高价值/复杂判断自动升到 `deepseek-v4-pro`
- 日报事实整理智能体：`deepseek-v4-flash`
- 日报撰写智能体：`deepseek-v4-pro`
- 日报准确性审核智能体：`deepseek-v4-flash`

日报编排会先基于热点证据生成事实卡，再撰写高密度招商日报，最后由独立审核智能体逐条检查是否能回溯到热点证据和原文链接。审核分低于阈值的日报会标记为待人工复核。

```bash
AI_PROVIDER=deepseek
AI_MULTI_AGENT=true
USE_DEEPSEEK_AI=true
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL_FLASH=deepseek-v4-flash
DEEPSEEK_MODEL_PRO=deepseek-v4-pro
DEEPSEEK_PRO_SCORE_THRESHOLD=84
DEEPSEEK_FORCE_PRO=false
```

如果希望所有招商策略判断都强制走 Pro，把 `DEEPSEEK_FORCE_PRO=true`。

## 互联网搜索配置

系统内置了“互联网搜索：国内新兴品牌”信源，会围绕“新店”“新品牌”“首店”“国货”“新锐消费品牌”等关键词补充搜索结果。支持 Tavily、Serper、SerpApi、Brave Search 和 Bing Search；如果没有配置搜索 key，会自动退回 Google News RSS 关键词搜索。

```bash
SEARCH_PROVIDER=tavily
SEARCH_API_KEY=你的搜索key

# 也可以使用服务专属 key：
TAVILY_API_KEY=
SERPER_API_KEY=
SERPAPI_API_KEY=
BRAVE_SEARCH_API_KEY=
BING_SEARCH_API_KEY=

SEARCH_MAX_QUERIES_PER_RUN=8
SEARCH_RESULTS_PER_QUERY=6
SEARCH_RESULTS_PER_SOURCE=36
SEARCH_TIME_RANGE=month
SEARCH_FETCH_ARTICLE_CONTENT=true
SEARCH_CONTENT_FETCH_LIMIT=24
SEARCH_SOURCE_TIME_BUDGET_SECONDS=45
SEARCH_MAX_QUERY_FAILURES=3
SEARCH_MAX_CONTENT_FAILURES=8
```

想覆盖更多关键词时，可以用分号或换行配置：

```bash
SEARCH_QUERIES=国内 新兴品牌 新店 开业;中国 新品牌 首店 购物中心;国货品牌 首店 新店
```

单次任务处理量可以这样控制，避免早晨任务被过多候选拖慢：

```bash
CRAWL_LINKS_PER_SOURCE=6
MAX_ARTICLES_PER_RUN=48
MAX_AI_ARTICLES_PER_RUN=16
MIN_RELEVANCE_SCORE=50
MIN_OPPORTUNITY_SCORE=65
MIN_BREAKOUT_SCORE=65
ENFORCE_COVERAGE_DATE=true
HTTP_TIMEOUT_SECONDS=10
```

`ENFORCE_COVERAGE_DATE=true` 时，系统会把日报限定为“昨日”资讯：能解析日期且不属于昨日的候选会被排除；日期无法解析的资讯会保留但标记为“日期待核验”，并在日报风险提示中暴露。

## 测试

```bash
npm run test:smoke
npm run test:stability
```

`test:smoke` 验证健康检查、每日更新、热点数据、原始链接、信源新增、信源停用和任务日志。`test:stability` 使用临时数据库和模拟外部服务，覆盖日期闸门、URL 去重、搜索熔断、噪音过滤、日报可追溯、审核拒绝和旧库迁移。
