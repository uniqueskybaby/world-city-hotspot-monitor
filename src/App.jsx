import {
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  ExternalLink,
  FileText,
  Flame,
  Globe2,
  LayoutDashboard,
  ListFilter,
  Loader2,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Store,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const signalTabs = ["全部信号", "国内新兴品牌", "新消费爆款", "国际新兴品牌", "线下扩张", "社媒爆火", "融资动态"];
const navItems = [
  { id: "today", label: "今日热点", icon: Radio },
  { id: "briefing", label: "每日日报", icon: FileText },
  { id: "history", label: "历史日报", icon: FileText },
  { id: "sources", label: "信源管理", icon: DatabaseZap },
  { id: "jobs", label: "任务日志", icon: BarChart3 },
  { id: "settings", label: "系统设置", icon: Settings },
];

const staticDemoMode = import.meta.env.VITE_STATIC_DEMO === "true";
let demoDataPromise = null;

function loadDemoData() {
  if (!demoDataPromise) {
    demoDataPromise = fetch(`${import.meta.env.BASE_URL}demo-data.json`).then((res) => {
      if (!res.ok) throw new Error("Demo data is unavailable");
      return res.json();
    });
  }
  return demoDataPromise;
}

const api = {
  dashboard: () => (staticDemoMode ? loadDemoData().then((data) => data.dashboard) : fetch("/api/dashboard").then((res) => res.json())),
  reports: () => (staticDemoMode ? loadDemoData().then((data) => ({ reports: data.reports || [] })) : fetch("/api/reports").then((res) => res.json())),
  run: () =>
    staticDemoMode
      ? Promise.resolve({ status: "demo", message: "当前是 GitHub Pages 演示版，本地运行后可执行真实采集更新。" })
      : fetch("/api/jobs/run-sync", { method: "POST" }).then((res) => res.json()),
  createSource: (payload) =>
    staticDemoMode
      ? Promise.resolve({ source: { ...payload, id: Date.now(), enabled: true } })
      : fetch("/api/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((res) => res.json()),
  toggleSource: (id, enabled) =>
    staticDemoMode
      ? Promise.resolve({ source: { id, enabled } })
      : fetch(`/api/sources/${id}/enabled`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).then((res) => res.json()),
};

export function App() {
  const [activePage, setActivePage] = useState(readPageFromLocation);
  const [dashboard, setDashboard] = useState(null);
  const [reports, setReports] = useState([]);
  const [activeSignal, setActiveSignal] = useState("全部信号");
  const [regionFilter, setRegionFilter] = useState("全部地区");
  const [categoryFilter, setCategoryFilter] = useState("全部业态");
  const [trustFilter, setTrustFilter] = useState("全部可信度");
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState("");

  async function loadData() {
    const [dashboardData, reportsData] = await Promise.all([api.dashboard(), api.reports()]);
    setDashboard(dashboardData);
    setReports(reportsData.reports || []);
    if (!selectedId && dashboardData.hotspots?.length) {
      setSelectedId(dashboardData.hotspots[0].id);
    }
  }

  useEffect(() => {
    loadData()
      .catch(() => setNotice("数据读取失败，请确认后端服务已启动。"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const syncLocation = () => setActivePage(readPageFromLocation());
    window.addEventListener("popstate", syncLocation);
    window.addEventListener("hashchange", syncLocation);
    return () => {
      window.removeEventListener("popstate", syncLocation);
      window.removeEventListener("hashchange", syncLocation);
    };
  }, []);

  const hotspots = dashboard?.hotspots || [];
  const sources = dashboard?.sources || [];
  const jobs = dashboard?.jobs || [];
  const report = dashboard?.report;

  const categories = useMemo(
    () => ["全部业态", ...Array.from(new Set(hotspots.map((item) => item.category))).filter(Boolean)],
    [hotspots],
  );

  const filteredHotspots = useMemo(() => {
    return hotspots.filter((item) => {
      const signalOk = activeSignal === "全部信号" || item.signal_type === activeSignal;
      const categoryOk = categoryFilter === "全部业态" || item.category === categoryFilter;
      const trustOk =
        trustFilter === "全部可信度" ||
        (trustFilter === "高可信" && item.confidence >= 85) ||
        (trustFilter === "中可信" && item.confidence >= 70 && item.confidence < 85);
      const regionOk = regionFilter === "全部地区" || item.regions.includes(regionFilter);
      return signalOk && categoryOk && trustOk && regionOk;
    });
  }, [hotspots, activeSignal, categoryFilter, trustFilter, regionFilter]);

  const selectedHotspot =
    filteredHotspots.find((item) => item.id === selectedId) || filteredHotspots[0] || hotspots[0] || null;

  async function handleRun() {
    setRunning(true);
    setNotice("正在更新今日热点，请稍等。");
    try {
      const result = await api.run();
      await loadData();
      if (result.status === "demo") {
        setNotice(result.message);
      } else {
        setNotice(result.status === "success" ? "今日热点已更新完成。" : "更新任务完成，但有异常需要查看日志。");
      }
    } catch {
      setNotice("更新失败，请查看任务日志。");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} onChange={setActivePage} />
      <main className="workspace">
        <Topbar report={report} scheduler={dashboard?.scheduler} running={running} onRun={handleRun} />
        {notice ? <div className="notice">{notice}</div> : null}
        {loading ? (
          <LoadingState />
        ) : (
          <>
            {activePage === "today" && (
              <TodayPage
                report={report}
                hotspots={filteredHotspots}
                allHotspots={hotspots}
                selectedHotspot={selectedHotspot}
                onSelect={setSelectedId}
                activeSignal={activeSignal}
                setActiveSignal={setActiveSignal}
                categoryFilter={categoryFilter}
                setCategoryFilter={setCategoryFilter}
                categories={categories}
                trustFilter={trustFilter}
                setTrustFilter={setTrustFilter}
                regionFilter={regionFilter}
                setRegionFilter={setRegionFilter}
                sources={sources}
              />
            )}
            {activePage === "briefing" && <BriefingPage report={report} hotspots={hotspots} />}
            {activePage === "history" && <HistoryPage reports={reports} />}
            {activePage === "sources" && <SourcesPage sources={sources} reload={loadData} />}
            {activePage === "jobs" && <JobsPage jobs={jobs} reload={loadData} running={running} onRun={handleRun} />}
            {activePage === "settings" && <SettingsPage auth={dashboard?.auth} scheduler={dashboard?.scheduler} />}
          </>
        )}
      </main>
    </div>
  );
}

function Sidebar({ activePage, onChange }) {
  return (
    <aside className="sidebar">
      <div className="brand-row">
        <div className="brand-mark">
          <Sparkles size={20} />
        </div>
        <div>
          <div className="product-name">世界城招商热点监测</div>
          <div className="product-subtitle">每日 AI 招商情报速递</div>
        </div>
      </div>
      <nav className="side-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <a key={item.id} href={`/?page=${item.id}`} className={`nav-button ${activePage === item.id ? "active" : ""}`}>
              <Icon size={18} />
              <span>{item.label}</span>
            </a>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <ShieldCheck size={18} />
        <div>
          <strong>内部访问</strong>
          <span>权限接口已预留</span>
        </div>
      </div>
    </aside>
  );
}

function readPageFromLocation() {
  if (typeof window === "undefined") return "today";
  const params = new URLSearchParams(window.location.search);
  const page = params.get("page");
  if (navItems.some((item) => item.id === page)) return page;
  const hash = window.location.hash.replace("#", "");
  return navItems.some((item) => item.id === hash) ? hash : "today";
}

function Topbar({ report, scheduler, running, onRun }) {
  const today = report?.report_date || new Date().toISOString().slice(0, 10);
  const nextRun = scheduler?.next_run_at ? formatTime(scheduler.next_run_at) : "等待调度";
  return (
    <header className="topbar">
      <div className="date-chip">
        <CalendarDays size={18} />
        <span>今日日期：{today}</span>
      </div>
      <div className="publish-status">
        <CheckCircle2 size={24} />
        <div>
          <span>每日更新状态</span>
          <strong>{report?.status === "published" ? "已发布" : "待更新"}</strong>
          <small>{scheduler?.enabled ? `下次自动：${nextRun}` : "自动调度已关闭"}</small>
        </div>
      </div>
      <div className="top-actions">
        <button className="ghost-button" type="button" onClick={onRun} disabled={running}>
          {running ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
          立即更新
        </button>
        <button className="ghost-button" type="button">
          <CalendarDays size={17} />
          选择日期
        </button>
        <button className="primary-button" type="button">
          <FileText size={17} />
          导出日报
        </button>
      </div>
    </header>
  );
}

function TodayPage(props) {
  const {
    report,
    hotspots,
    allHotspots,
    selectedHotspot,
    onSelect,
    activeSignal,
    setActiveSignal,
    categoryFilter,
    setCategoryFilter,
    categories,
    trustFilter,
    setTrustFilter,
    regionFilter,
    setRegionFilter,
    sources,
  } = props;

  return (
    <section className="main-grid">
      <div className="feed-panel">
        <div className="filter-row">
          {signalTabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`signal-tab ${activeSignal === tab ? "active" : ""}`}
              onClick={() => setActiveSignal(tab)}
            >
              {tab}
              <span>{tab === "全部信号" ? allHotspots.length : allHotspots.filter((item) => item.signal_type === tab).length}</span>
            </button>
          ))}
        </div>
        <div className="toolbar">
          <div className="search-field">
            <Search size={17} />
            <span>搜索品牌、事件、来源</span>
          </div>
          <SelectPill value={regionFilter} onChange={setRegionFilter} options={["全部地区", "全国", "国际"]} />
          <SelectPill value={categoryFilter} onChange={setCategoryFilter} options={categories} />
          <SelectPill value={trustFilter} onChange={setTrustFilter} options={["全部可信度", "高可信", "中可信"]} />
          <button className="sort-button" type="button">
            <ListFilter size={17} />
            最新发布
          </button>
        </div>
        <div className="feed-header">
          <span>信号类型</span>
          <span>资讯内容</span>
          <span>来源类型</span>
          <span>发布时间</span>
          <span>可信度</span>
          <span>相关度</span>
        </div>
        <div className="feed-list">
          {hotspots.length ? (
            hotspots.map((item) => (
              <HotspotRow
                key={item.id}
                item={item}
                active={selectedHotspot?.id === item.id}
                onClick={() => onSelect(item.id)}
              />
            ))
          ) : (
            <EmptyState />
          )}
        </div>
      </div>
      <RightPanel report={report} hotspots={allHotspots} selectedHotspot={selectedHotspot} sources={sources} />
    </section>
  );
}

function BriefingPage({ report, hotspots }) {
  const briefing = report?.briefing || buildFallbackBriefing(report, hotspots);
  const initialId =
    briefing.breakout_brands?.[0]?.hotspot_id ||
    briefing.key_news?.[0]?.hotspot_id ||
    briefing.top_takeaways?.[0]?.hotspot_ids?.[0] ||
    hotspots[0]?.id;
  const [selectedId, setSelectedId] = useState(initialId);
  const selectedHotspot = hotspots.find((item) => item.id === selectedId) || hotspots[0] || null;

  function selectFirst(ids) {
    const id = (ids || []).find((value) => hotspots.some((item) => item.id === value));
    if (id) setSelectedId(id);
  }

  return (
    <section className="briefing-grid">
      <div className="briefing-main">
        <div className="briefing-cover">
          <div>
            <span>昨日招商日报</span>
            <h1>{briefing.report_title || "招商日报"}</h1>
            <p>
              覆盖 {briefing.coverage_date || report?.report_date || "昨日"} 公开资讯，筛出 {briefing.total_hotspots || hotspots.length} 条高价值招商线索。
            </p>
          </div>
          <div className="briefing-score">
            <ShieldCheck size={22} />
            <span>{briefing.verification_status || "待审核"}</span>
            <strong>{briefing.accuracy_score || 0}</strong>
          </div>
        </div>

        <section className="briefing-section">
          <div className="section-title">
            <Sparkles size={18} />
            <h2>今日重点判断</h2>
          </div>
          <div className="takeaway-grid">
            {(briefing.top_takeaways || []).map((item) => (
              <button className="takeaway-card" key={`${item.label}-${item.text}`} type="button" onClick={() => selectFirst(item.hotspot_ids)}>
                <span>{item.label}</span>
                <p>{item.text}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="briefing-section">
          <div className="section-title">
            <Flame size={18} />
            <h2>刚爆火的新兴品牌</h2>
          </div>
          <div className="brand-brief-list">
            {(briefing.breakout_brands || []).map((item) => (
              <button
                className={`brand-brief-card ${selectedId === item.hotspot_id ? "active" : ""}`}
                key={`${item.hotspot_id}-${item.brand_name}`}
                type="button"
                onClick={() => setSelectedId(item.hotspot_id)}
              >
                <div>
                  <span>{item.signal}</span>
                  <h3>{item.brand_name}</h3>
                  <p>{item.why_now}</p>
                </div>
                <div className="briefing-card-side">
                  <strong>{item.score}</strong>
                  <em>招商价值</em>
                </div>
                <small>{item.leasing_angle}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="briefing-section">
          <div className="section-title">
            <FileText size={18} />
            <h2>重点新闻与招商含义</h2>
          </div>
          <div className="brief-news-list">
            {(briefing.key_news || []).map((item) => (
              <button
                className={`brief-news-row ${selectedId === item.hotspot_id ? "active" : ""}`}
                key={`${item.hotspot_id}-${item.title}`}
                type="button"
                onClick={() => setSelectedId(item.hotspot_id)}
              >
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.summary}</p>
                  <strong>{item.implication}</strong>
                </div>
                <div className="tag-line">
                  {(item.tags || []).slice(0, 3).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="briefing-section">
          <div className="section-title">
            <ListFilter size={18} />
            <h2>招商动作建议</h2>
          </div>
          <div className="action-list">
            {(briefing.leasing_actions || []).map((item) => (
              <button className="action-row" key={`${item.priority}-${item.action}`} type="button" onClick={() => selectFirst(item.hotspot_ids)}>
                <strong>{item.priority}</strong>
                <div>
                  <span>{item.action}</span>
                  <p>{item.reason}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      </div>

      <aside className="briefing-side">
        <section className="panel-section">
          <div className="section-title">
            <Store size={18} />
            <h2>点击查看详情</h2>
          </div>
          {selectedHotspot ? <HotspotDetail item={selectedHotspot} /> : <p className="muted">暂无可查看详情。</p>}
        </section>
        <section className="panel-section">
          <div className="section-title">
            <ShieldCheck size={18} />
            <h2>审核记录</h2>
          </div>
          <div className="audit-list">
            {(briefing.agent_trace || []).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
          {(briefing.verification_notes || briefing.risk_notes || []).slice(0, 4).map((note) => (
            <p className="muted audit-note" key={note}>{note}</p>
          ))}
        </section>
      </aside>
    </section>
  );
}

function buildFallbackBriefing(report, hotspots) {
  return {
    report_title: `${report?.report_date || "今日"} 招商日报`,
    coverage_date: report?.report_date || "",
    total_hotspots: hotspots.length,
    verification_status: "规则审核通过",
    accuracy_score: hotspots.length ? 82 : 0,
    top_takeaways: hotspots.slice(0, 3).map((item) => ({
      label: item.signal_type,
      text: `${item.brand_name}出现可跟踪招商信号，建议结合原文核查门店模型。`,
      hotspot_ids: [item.id],
    })),
    breakout_brands: hotspots.slice(0, 5).map((item) => ({
      hotspot_id: item.id,
      brand_name: item.brand_name,
      signal: item.signal_type,
      why_now: item.ai_summary,
      leasing_angle: item.leasing_insight,
      score: item.opportunity_score,
    })),
    key_news: hotspots.slice(0, 8).map((item) => ({
      hotspot_id: item.id,
      title: item.title,
      summary: item.ai_summary,
      implication: item.leasing_insight,
      tags: item.tags || [],
    })),
    leasing_actions: [],
    risk_notes: ["日报暂未生成结构化 AI 简报，当前展示由热点数据自动汇总。"],
    agent_trace: ["fact_curator:rules", "report_writer:rules", "verifier:rules"],
  };
}

function SelectPill({ value, onChange, options }) {
  return (
    <select className="select-pill" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option}>{option}</option>
      ))}
    </select>
  );
}

function HotspotRow({ item, active, onClick }) {
  const signalMeta = signalStyle(item.signal_type);
  const SignalIcon = signalMeta.icon;
  return (
    <button className={`feed-row ${active ? "active" : ""}`} type="button" onClick={onClick}>
      <div className={`signal-cell ${signalMeta.className}`}>
        <SignalIcon size={28} />
        <strong>{item.signal_type}</strong>
      </div>
      <div className="story-cell">
        <h3>{item.title}</h3>
        <div className="meta-line">
          <span>{item.brand_name}</span>
          <span>{item.category}</span>
          <span>{item.regions}</span>
        </div>
        <p>{item.ai_summary}</p>
        <div className="tag-line">
          {(item.tags || []).slice(0, 4).map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      </div>
      <div className="source-cell">
        <span>{item.source_type}</span>
        <strong>{item.source_name}</strong>
      </div>
      <div className="time-cell">{formatTime(item.published_at)}</div>
      <ScoreBadge value={item.confidence} tone="green" />
      <ScoreBadge value={item.relevance} tone="blue" />
    </button>
  );
}

function RightPanel({ report, hotspots, selectedHotspot, sources }) {
  const topInsights = report?.insights || [];
  const coverage = report?.coverage || {};
  return (
    <aside className="right-panel">
      <section className="panel-section">
        <div className="section-title">
          <Sparkles size={18} />
          <h2>AI 今日判断</h2>
        </div>
        <div className="rank-list">
          {topInsights.map((item, index) => (
            <div className="rank-item" key={item.name}>
              <strong>{index + 1}</strong>
              <div>
                <span>{item.name}</span>
                <p>{item.summary}</p>
              </div>
              <em>{item.count} 条相关</em>
            </div>
          ))}
        </div>
      </section>
      <section className="panel-section">
        <div className="section-title">
          <Globe2 size={18} />
          <h2>信源覆盖情况</h2>
        </div>
        <div className="coverage-list">
          {Object.entries(coverage).map(([name, count]) => (
            <div className="coverage-row" key={name}>
              <span>{name}</span>
              <strong>{count}</strong>
            </div>
          ))}
          {!Object.keys(coverage).length ? <p className="muted">今日暂无覆盖统计。</p> : null}
        </div>
      </section>
      <section className="panel-section">
        <div className="section-title">
          <Store size={18} />
          <h2>选中情报</h2>
        </div>
        {selectedHotspot ? <HotspotDetail item={selectedHotspot} /> : <p className="muted">请选择一条情报查看详情。</p>}
      </section>
      <section className="panel-section data-overview">
        <div>
          <span>今日新增情报</span>
          <strong>{report?.total_articles || 0}</strong>
        </div>
        <div>
          <span>进入今日榜单</span>
          <strong>{hotspots.length}</strong>
        </div>
        <div>
          <span>启用信源</span>
          <strong>{sources.filter((item) => item.enabled).length}</strong>
        </div>
      </section>
    </aside>
  );
}

function HotspotDetail({ item }) {
  const sourceLinks =
    item.source_links?.length
      ? item.source_links
      : [{ source_name: item.source_name, source_type: item.source_type, source_url: item.source_url }];
  return (
    <div className="detail-block">
      <h3>{item.brand_name}</h3>
      <p>{item.leasing_insight}</p>
      <div className="detail-grid">
        <span>爆款潜力</span>
        <strong>{item.breakout_score}</strong>
        <span>招商价值</span>
        <strong>{item.opportunity_score}</strong>
        <span>可信度</span>
        <strong>{item.confidence}</strong>
      </div>
      <div className="evidence-list">
        {(item.evidence || []).slice(0, 3).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      {sourceLinks.slice(0, 5).map((link, index) => (
        <a className="source-link" href={link.source_url} target="_blank" rel="noreferrer" key={`${link.source_url}-${index}`}>
          {sourceLinks.length > 1 ? `${link.source_name || "来源"} · ${link.source_type || "公开资讯"}` : "查看原始链接"}
          <ExternalLink size={15} />
        </a>
      ))}
    </div>
  );
}

function HistoryPage({ reports }) {
  return (
    <section className="page-panel">
      <div className="page-title">
        <h1>历史日报</h1>
        <p>按日期查看每日生成的招商热点版本。</p>
      </div>
      <div className="simple-table">
        <div className="table-head">
          <span>日期</span>
          <span>状态</span>
          <span>候选资讯</span>
          <span>入选热点</span>
          <span>发布时间</span>
        </div>
        {reports.map((item) => (
          <div className="table-row" key={item.report_date}>
            <strong>{item.report_date}</strong>
            <span className="status-good">{item.status}</span>
            <span>{item.total_articles}</span>
            <span>{item.total_hotspots}</span>
            <span>{formatTime(item.published_at)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SourcesPage({ sources, reload }) {
  const [form, setForm] = useState({
    name: "",
    source_type: "公开资讯平台",
    url: "",
    adapter: "html",
    notes: "",
  });
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    await api.createSource({ ...form, enabled: true });
    setForm({ name: "", source_type: "公开资讯平台", url: "", adapter: "html", notes: "" });
    await reload();
    setSaving(false);
  }

  async function toggle(item) {
    await api.toggleSource(item.id, !item.enabled);
    await reload();
  }

  return (
    <section className="page-panel split-page">
      <div>
        <div className="page-title">
          <h1>信源管理</h1>
          <p>公开资讯平台、品牌官网、公众号公开文章和社媒公开页都可以在这里扩展。</p>
        </div>
        <div className="source-list">
          {sources.map((item) => (
            <div className="source-row" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <span>{item.source_type} · {item.adapter}</span>
                {isExternalUrl(item.url) ? (
                  <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a>
                ) : (
                  <span>{sourceLocationLabel(item)}</span>
                )}
              </div>
              <button className={item.enabled ? "enabled-toggle" : "disabled-toggle"} onClick={() => toggle(item)} type="button">
                {item.enabled ? "已启用" : "已停用"}
              </button>
            </div>
          ))}
        </div>
      </div>
      <form className="source-form" onSubmit={submit}>
        <h2>新增公开信源</h2>
        <label>
          信源名称
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
        </label>
        <label>
          信源类型
          <select value={form.source_type} onChange={(event) => setForm({ ...form, source_type: event.target.value })}>
            <option>公开资讯平台</option>
            <option>品牌官网</option>
            <option>公众号公开文章</option>
            <option>社媒公开页</option>
            <option>商业地产媒体</option>
            <option>国际媒体</option>
            <option>互联网搜索</option>
          </select>
        </label>
        <label>
          适配器
          <select value={form.adapter} onChange={(event) => setForm({ ...form, adapter: event.target.value })}>
            <option value="html">公开网页</option>
            <option value="rss">RSS</option>
            <option value="url_list">公开链接列表</option>
            <option value="web_search">互联网搜索</option>
          </select>
        </label>
        <label>
          URL / 搜索标识
          <input
            value={form.url}
            onChange={(event) => setForm({ ...form, url: event.target.value })}
            placeholder={form.adapter === "web_search" ? "search://domestic-emerging-brands" : ""}
            required
          />
        </label>
        <label>
          备注 / 搜索关键词
          <textarea
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
            placeholder={form.adapter === "web_search" ? "queries:\n国内 新兴品牌 新店 开业\n中国 新品牌 首店 购物中心" : ""}
          />
        </label>
        <button className="primary-button full" disabled={saving} type="submit">
          <Plus size={17} />
          {saving ? "保存中" : "添加信源"}
        </button>
      </form>
    </section>
  );
}

function JobsPage({ jobs, reload, running, onRun }) {
  return (
    <section className="page-panel">
      <div className="page-title inline-title">
        <div>
          <h1>任务日志</h1>
          <p>查看每日自动更新、手动更新和失败重试状态。</p>
        </div>
        <button className="primary-button" onClick={onRun} disabled={running} type="button">
          {running ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
          立即更新
        </button>
      </div>
      <div className="job-list">
        {jobs.map((job) => (
          <details className="job-row" key={job.id}>
            <summary>
              <span className="job-name">
                #{job.id} {job.job_type}
                <small>{triggerLabel(job.trigger)}</small>
              </span>
              <strong className={job.status === "success" ? "status-good" : job.status === "failed" ? "status-bad" : "status-running"}>
                {job.status}
              </strong>
              <em>{formatTime(job.started_at)}</em>
            </summary>
            <div className="job-detail">
              {(job.logs || []).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </details>
        ))}
      </div>
      <button className="ghost-button refresh-line" onClick={reload} type="button">
        <RefreshCw size={16} />
        刷新日志
      </button>
    </section>
  );
}

function SettingsPage({ auth, scheduler }) {
  const nextRun = scheduler?.next_run_at ? formatTime(scheduler.next_run_at) : "等待服务启动";
  const latestJob = scheduler?.latest_job;
  return (
    <section className="page-panel settings-grid">
      <div className="page-title">
        <h1>系统设置</h1>
        <p>查看远端部署、每日自动更新、AI 模型和后期登录接入状态。</p>
      </div>
      <div className="setting-card">
        <Clock3 size={22} />
        <div>
          <strong>自动调度</strong>
          <span>
            {scheduler?.enabled
              ? `已开启，下一次运行：${nextRun}。错过 06:30 会自动补跑。`
              : "已关闭，需要手动点击立即更新。"}
          </span>
        </div>
      </div>
      <div className="setting-card">
        <Sparkles size={22} />
        <div>
          <strong>AI 清洗模式</strong>
          <span>无模型 key 时使用规则引擎；配置 key 后自动切换到 AI 结构化判断。</span>
        </div>
      </div>
      <div className="setting-card">
        <ShieldCheck size={22} />
        <div>
          <strong>登录权限</strong>
          <span>{auth?.message || "接口已预留，第一版不强制登录。"}</span>
        </div>
      </div>
      <div className="setting-card">
        <DatabaseZap size={22} />
        <div>
          <strong>最近任务</strong>
          <span>
            {latestJob
              ? `${triggerLabel(latestJob.trigger)} · ${latestJob.status} · ${formatTime(latestJob.started_at)}`
              : "暂无任务记录。"}
          </span>
        </div>
      </div>
    </section>
  );
}

function ScoreBadge({ value, tone }) {
  return (
    <div className={`score-badge ${tone}`}>
      <strong>{value}</strong>
      <span>{tone === "green" ? "可信度" : "相关度"}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading-state">
      <Loader2 className="spin" size={28} />
      <span>正在读取招商热点...</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty-state">
      <Flame size={28} />
      <strong>暂无符合筛选条件的情报</strong>
      <span>可以切换筛选条件，或立即更新今日热点。</span>
    </div>
  );
}

function signalStyle(signal) {
  const map = {
    国内新兴品牌: { className: "domestic", icon: Sparkles },
    新消费爆款: { className: "hot", icon: Flame },
    国际新兴品牌: { className: "global", icon: Globe2 },
    线下扩张: { className: "store", icon: Store },
    社媒爆火: { className: "social", icon: Sparkles },
    融资动态: { className: "funding", icon: BarChart3 },
  };
  return map[signal] || { className: "neutral", icon: Radio };
}

function isExternalUrl(value) {
  return /^https?:\/\//i.test(value || "");
}

function sourceLocationLabel(item) {
  if (item.adapter === "web_search") return "搜索关键词组";
  return item.url;
}

function formatTime(value) {
  if (!value) return "今日";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function triggerLabel(value) {
  const map = {
    scheduled: "自动定时",
    scheduled_catchup: "自动补跑",
    manual: "手动更新",
    manual_sync: "手动更新",
    first_boot: "首次启动",
  };
  return map[value] || value || "未知触发";
}
