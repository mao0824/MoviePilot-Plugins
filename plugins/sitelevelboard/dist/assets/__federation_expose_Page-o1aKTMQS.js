import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { f as fmtNum, S as SOURCE_LABEL, a as fmtEta, b as fmtGb, d as describeError, C as CONFIDENCE_LABEL, u as unwrapResponse } from './utils-CImzM-zu.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment,withModifiers:_withModifiers,normalizeClass:_normalizeClass,mergeProps:_mergeProps,unref:_unref} = await importShared('vue');


const _hoisted_1 = { class: "text-caption text-medium-emphasis" };
const _hoisted_2 = {
  key: 0,
  class: "text-caption text-medium-emphasis font-weight-regular",
  title: "按住条目可拖动调整顺序"
};
const _hoisted_3 = { class: "slb-name" };
const _hoisted_4 = { class: "slb-domain" };
const _hoisted_5 = {
  key: 0,
  class: "slb-account"
};
const _hoisted_6 = {
  key: 1,
  class: "pa-3 text-caption text-medium-emphasis"
};
const _hoisted_7 = { class: "pa-2" };
const _hoisted_8 = { class: "d-flex align-center flex-wrap ga-2 pa-4 pb-2" };
const _hoisted_9 = { class: "text-h6" };
const _hoisted_10 = { class: "slb-meta" };
const _hoisted_11 = { key: 0 };
const _hoisted_12 = { key: 1 };
const _hoisted_13 = { class: "d-flex align-center ga-3" };
const _hoisted_14 = { class: "text-caption font-weight-medium flex-shrink-0" };
const _hoisted_15 = {
  key: 0,
  class: "text-caption text-medium-emphasis flex-shrink-0"
};
const _hoisted_16 = { class: "mb-1 font-weight-medium" };
const _hoisted_17 = { class: "text-caption text-medium-emphasis" };
const _hoisted_18 = { key: 0 };
const _hoisted_19 = { key: 0 };
const _hoisted_20 = { key: 1 };
const _hoisted_21 = { key: 2 };
const _hoisted_22 = { key: 0 };
const _hoisted_23 = { class: "d-flex align-center flex-wrap" };
const _hoisted_24 = { class: "ml-1 text-medium-emphasis" };
const _hoisted_25 = { class: "text-caption" };
const _hoisted_26 = {
  key: 0,
  class: "text-caption text-warning ml-5"
};
const _hoisted_27 = {
  key: 0,
  class: "text-medium-emphasis mb-2"
};
const _hoisted_28 = {
  key: 1,
  class: "text-medium-emphasis"
};
const _hoisted_29 = {
  key: 0,
  class: "text-medium-emphasis"
};
const _hoisted_30 = { class: "mr-1" };
const _hoisted_31 = { key: 0 };
const _hoisted_32 = { key: 1 };
const _hoisted_33 = { class: "text-caption" };
const _hoisted_34 = {
  key: 0,
  class: "text-medium-emphasis"
};
const _hoisted_35 = { key: 1 };
const _hoisted_36 = {
  key: 2,
  class: "text-error"
};
const _hoisted_37 = { class: "text-caption" };
const _hoisted_38 = { class: "d-flex align-center flex-wrap ga-2 mb-2" };
const _hoisted_39 = ["viewBox"];
const _hoisted_40 = ["points"];
const _hoisted_41 = { class: "text-caption mt-1 mb-2" };
const _hoisted_42 = {
  key: 1,
  class: "text-medium-emphasis"
};
const _hoisted_43 = { class: "text-caption mb-2" };
const _hoisted_44 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_45 = { class: "text-caption text-medium-emphasis ml-2" };

const {computed,onMounted,ref} = await importShared('vue');

const REL_BASE = 'plugin/SiteLevelBoard';

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
},
  emits: ['action', 'close'],
  setup(__props, { emit: __emit }) {

/**
 * 站点等级看板 · 主界面(左侧站点列表 + 右侧等级详情)
 *
 * 宿主(MP)在渲染本组件时注入 ``api``(HTTP 客户端:get/post/put/delete);
 * 独立开发时没有 ``api``,自动退化为 fetch(带 cookie)。
 * 数据全部来自插件后端 11 个端点,契约见插件 __init__.py 顶部说明。
 */
const props = __props;

/**
 * ⚠️ 宿主(MP)注入的 ``api`` 客户端**自带前缀**:其 axios 实例 ``baseURL: 'api/v1/'``
 *    (见 MP 前端 bundles,「站点刷流」等插件同样按此约定调用)。
 *    所以传给它的必须是**相对 path** ``plugin/SiteLevelBoard/...``;
 *    若自己再叠一层 ``/api/v1`` 前缀,axios 会拼成 ``/api/v1/api/v1/...``
 *    → 前端报「Not Found」(2026-10-11 实际踩坑就是这个)。
 *    ``ABS_BASE`` 只在没有 ``api``(独立开发,退化为 fetch)时使用。
 */
const ABS_BASE = `/api/v1/${REL_BASE}`;

const loading = ref(true);
const busy = ref(false);
const error = ref('');
const snack = ref({ show: false, text: '', color: 'success' });

const tracked = ref([]);
const candidates = ref([]);
const meta = ref({ last_refresh: null, snapshot_date: null });
const selectedId = ref(0);
const detail = ref(null);
const detailLoading = ref(false);

/**
 * 右侧详情分三个页签:等级概览 / 等级阶梯 / 流量趋势(与「站点刷流」同样的切法)。
 * 切换站点时**保留当前页签**(正在看阶梯,点下一个站点还停在阶梯);数据都由 /detail
 * 一次性返回,切页签不发请求。
 */
const activeTab = ref('overview');

const addOpen = ref(false);
const addSearch = ref('');
const addSelected = ref([]);
const confirmTarget = ref(null);

const reportOpen = ref(false);
const reportText = ref('');
const reportLoading = ref(false);

const filteredCandidates = computed(() => {
  const kw = addSearch.value.trim().toLowerCase();
  if (!kw) return candidates.value
  return candidates.value.filter(
    item => `${item.name} ${item.domain}`.toLowerCase().includes(kw),
  )
});

const current = computed(() => tracked.value.find(item => item.id === selectedId.value) || null);

function toast(text, color = 'success') {
  snack.value = { show: true, text, color };
}

/** 发请求,拿**原始响应体**(有些端点把文本放在 message 里,比如 /report)。 */
async function rawReq(method, path, body) {
  if (props.api && typeof props.api[method] === 'function') {
    // 走宿主 api:相对 path(宿主已带 api/v1 前缀),见上方 REL_BASE 注释
    return await props.api[method](REL_BASE + path, body)
  }
  const res = await fetch(ABS_BASE + path, {
    method: method.toUpperCase(),
    credentials: 'include',
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return await res.json()
}

async function req(method, path, body) {
  return unwrapResponse(await rawReq(method, path, body))
}

async function loadSites(keepSelection = true) {
  loading.value = true;
  error.value = '';
  try {
    const data = await req('get', '/sites');
    tracked.value = data.tracked || [];
    candidates.value = data.candidates || [];
    meta.value = { last_refresh: data.last_refresh, snapshot_date: data.snapshot_date };
    const exists = tracked.value.some(item => item.id === selectedId.value);
    if (!keepSelection || !exists) {
      selectedId.value = tracked.value.length ? tracked.value[0].id : 0;
    }
    if (selectedId.value) await loadDetail(selectedId.value);
    else detail.value = null;
  } catch (e) {
    error.value = describeError(e);
  } finally {
    loading.value = false;
  }
}

async function loadDetail(siteId) {
  if (!siteId) return
  detailLoading.value = true;
  try {
    detail.value = await req('get', `/detail?site_id=${siteId}`);
  } catch (e) {
    detail.value = null;
    error.value = describeError(e);
  } finally {
    detailLoading.value = false;
  }
}

function selectSite(id) {
  if (selectedId.value === id) return
  selectedId.value = id;
  loadDetail(id);
}

async function refreshAll() {
  busy.value = true;
  try {
    await req('post', '/refresh', {});
    toast('已开始全量刷新,稍后自动更新列表', 'info');
    // 后台刷新约 10~60 秒;这里做一次延迟重取 + 允许手动再点
    setTimeout(() => loadSites(true), 12000);
    setTimeout(() => loadSites(true), 40000);
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

async function refreshOne() {
  const site = current.value;
  if (!site) return
  busy.value = true;
  try {
    const data = await req('post', '/refresh', { site_id: site.id });
    detail.value = data;
    await loadSites(true);
    toast('已刷新该站点', 'success');
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

function openAdd() {
  addSearch.value = '';
  addSelected.value = [];
  addOpen.value = true;
}

async function submitAdd() {
  if (!addSelected.value.length) {
    toast('请先勾选要加入的站点', 'warning');
    return
  }
  busy.value = true;
  try {
    await req('post', '/track', { site_ids: addSelected.value });
    addOpen.value = false;
    await loadSites(true);
    toast(`已加入 ${addSelected.value.length} 个站点`, 'success');
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

async function doRemove(site) {
  busy.value = true;
  try {
    await req('post', '/untrack', { site_id: site.id });
    confirmTarget.value = null;
    if (selectedId.value === site.id) {
      detail.value = null;
      selectedId.value = 0;
    }
    await loadSites(false);
    toast(`已把「${site.name}」移出看板(不影响 mp 站点管理)`, 'info');
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

/**
 * 复制汇总:取 /report 的文字版(全站等级/条件/风险),弹窗里可全选、一键复制。
 * 注意 /report 把文本放在 message 里(不是 data),所以这里用 rawReq 取原始响应。
 */
async function loadReport() {
  reportLoading.value = true;
  try {
    const raw = await rawReq('get', '/report');
    const text = String((raw && (raw.message || raw.data)) || '').trim();
    reportText.value = text || '(暂无内容:先在插件里刷新一次数据)';
    reportOpen.value = true;
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    reportLoading.value = false;
  }
}

async function copyReport() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(reportText.value);
    } else {
      // http 页面不是安全上下文,没有 clipboard API → 退回隐藏 textarea + execCommand
      const area = document.createElement('textarea');
      area.value = reportText.value;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      document.body.removeChild(area);
    }
    toast('已复制到剪贴板', 'success');
    reportOpen.value = false;
  } catch (e) {
    toast('复制失败,可在弹窗里手动全选复制', 'warning');
  }
}

/**
 * 左侧列表拖拽排序:用原生 HTML5 DnD,不引第三方库(vuedraggable 没在宿主 shared 里,
 * 自己打包一份不划算)。落点用 dragIndex/overIndex 标出插入线,松手后先本地生效、
 * 再 POST /reorder 落库;失败就把顺序回滚,避免界面与后端不一致。
 */
const dragIndex = ref(-1);
const overIndex = ref(-1);

function onDragStart(index, event) {
  dragIndex.value = index;
  overIndex.value = index;
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(tracked.value[index]?.id ?? ''));
  }
}

function onDragOver(index) {
  if (dragIndex.value >= 0) overIndex.value = index;
}

async function onDrop(index) {
  const from = dragIndex.value;
  dragIndex.value = -1;
  overIndex.value = -1;
  if (from < 0 || from === index) return
  const before = tracked.value.slice();
  const list = tracked.value.slice();
  const [moved] = list.splice(from, 1);
  list.splice(index, 0, moved);
  tracked.value = list;
  try {
    await req('post', '/reorder', { site_ids: list.map(x => x.id) });
  } catch (e) {
    tracked.value = before;
    toast(describeError(e), 'error');
  }
}

function onDragEnd() {
  dragIndex.value = -1;
  overIndex.value = -1;
}

/** 趋势可选指标(键名 = /detail 里 history 的字段)。 */
const TRAFFIC_METRICS = [
  { key: 'upload_gb', label: '上传', fmt: v => fmtGb(v) },
  { key: 'download_gb', label: '下载', fmt: v => fmtGb(v) },
  { key: 'ratio', label: '分享率', fmt: v => fmtNum(v, 3) },
  { key: 'bonus', label: '魔力/积分', fmt: v => fmtNum(v, 1) },
  { key: 'seeding_size_gb', label: '做种体积', fmt: v => fmtGb(v) },
  { key: 'seeding', label: '做种数', fmt: v => fmtNum(v, 0) },
];
const trafficMetric = ref('upload_gb');
const trafficRange = ref(14);
const trafficHover = ref(-1);

const trafficRows = computed(() => (detail.value?.history || []).slice(-trafficRange.value));
const trafficMetricDef = computed(
  () => TRAFFIC_METRICS.find(m => m.key === trafficMetric.value) || TRAFFIC_METRICS[0],
);

/** 内联 SVG 折线(不引第三方图表库;纵轴按当前指标自适应)。 */
const trafficChart = computed(() => {
  const rows = trafficRows.value;
  if (rows.length < 2) return null
  const vals = rows.map(h => Number(h[trafficMetric.value]) || 0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = Math.max(max - min, 1);
  const w = 100;
  const h = 28;
  const points = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / span) * h;
    return `${x.toFixed(2)},${y.toFixed(2)}`
  });
  return { min, max, w, h, points: points.join(' ') }
});

/** 鼠标在图上移动 → 定位到最近的采样日,读出当天数值。 */
function onChartMove(event) {
  const rows = trafficRows.value;
  if (!rows.length || !trafficChart.value) return
  const rect = event.currentTarget.getBoundingClientRect();
  const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
  trafficHover.value = Math.round(ratio * (rows.length - 1));
}

/** 区间变化一行:按当前指标与范围算首末差 + 日均。 */
const trafficTrend = computed(() => {
  const rows = trafficRows.value;
  if (rows.length < 2) return ''
  const key = trafficMetric.value;
  const def = trafficMetricDef.value;
  const first = Number(rows[0][key]) || 0;
  const last = Number(rows[rows.length - 1][key]) || 0;
  const delta = last - first;
  const perDay = delta / Math.max(rows.length - 1, 1);
  const sign = v => (v >= 0 ? '+' : '');
  return `${rows[0].day} → ${rows[rows.length - 1].day}:${def.label} ${sign(delta)}${def.fmt(delta)}`
    + ` · 日均 ${sign(perDay)}${def.fmt(perDay)}`
});

/**
 * 「最紧条件」——与后端 __progress 同一口径:取未达成条件里 当前/目标 最小的那个,
 * 让「到底卡在哪一项」直接写在脸上(进度条只给了个百分比)。
 */
const tightest = computed(() => {
  const unmet = (detail.value?.reqs || []).filter(r => !r.met);
  if (!unmet.length) return null
  const ratio = r => (r.target && typeof r.current === 'number' && r.target > 0
    ? Math.min(1, r.current / r.target) : null);
  const scored = unmet.map(r => ({ r, v: ratio(r) })).filter(x => x.v !== null);
  if (!scored.length) return unmet[0]
  return scored.reduce((a, b) => (b.v < a.v ? b : a)).r
});

/** 站点侧实时信息(目前来自馒头官方 API):最后登录 / 封存 / 警告。 */
const liveExtraText = computed(() => {
  const x = detail.value?.live_extras || {};
  const parts = [];
  if (x.joined) parts.push(`注册于 ${String(x.joined).slice(0, 10)}`);
  if (x.last_login) parts.push(`最后登录 ${String(x.last_login).slice(0, 16)}`);
  if ('parked' in x) parts.push(x.parked ? '已封存' : '未封存');
  if (x.warned) parts.push('⚠️ 有警告');
  if (x.leech_warn) parts.push('⚠️ 有下载警告');
  return parts.join(' · ')
});

/** 保号路线图(后端 roadmap:到「可封存 / 永久保留」档还差几级、照当前增速多久、卡在哪)。 */
const roadmapRows = computed(() => {
  const rm = detail.value?.roadmap || {};
  return [
    { key: 'parkable', label: '可封存保号', icon: 'mdi-shield-lock-outline', tone: 'success', data: rm.parkable },
    { key: 'permanent', label: '永久保留', icon: 'mdi-shield-star-outline', tone: 'primary', data: rm.permanent },
  ].filter(row => row.data)
});

function roadmapAway(m) {
  if (!m) return ''
  if (m.reached) return '已达成'
  return `还差 ${m.levels_away} 级${m.name ? ` → ${m.name}` : ''}`
}

function roadmapEta(m) {
  if (!m) return ''
  if (m.reached) return '✅'
  const hasEta = m.eta_days !== null && m.eta_days !== undefined;
  if (m.blockers?.length) {
    if (!hasEta) return '暂不可估'
    if (m.eta_days <= 0) return '其余条件已就位,只差卡点'
    return `最快 ${fmtEta(m.eta_days)}(仅按可推算条件)`
  }
  return hasEta ? `${fmtEta(m.eta_days)}(${CONFIDENCE_LABEL[m.confidence] || '?'})` : '暂不可估'
}

function roadmapBlocker(m) {
  return (m?.blockers || []).map(b => {
    const kind = b.kind === 'manual' ? '需人为推动' : '数据不足';
    const cur = (b.current === null || b.current === undefined) ? null : fmtNum(b.current);
    const target = `${fmtNum(b.target)}${b.unit || ''}`;
    return cur === null ? `${b.label}(${kind})` : `${b.label}:当前 ${cur} / 目标 ${target}(${kind})`
  }).join(' · ')
}

function riskColor(risk) {
  return risk === 'danger' ? 'error' : risk === 'warn' ? 'warning' : 'success'
}

/** 当前站点有没有风险 —— 显示成「等级概览」页签上的小圆点,人在别的页签也能看见。 */
const riskLevel = computed(() => {
  const risks = detail.value?.risks || [];
  if (risks.some(r => r.level === 'danger')) return 'danger'
  return risks.length ? 'warn' : ''
});

function etaText(site) {
  if (site.manual_blocked) return '受人为条件限制'
  if (site.eta_days === null || site.eta_days === undefined) {
    return site.next_level ? '无法估算' : '已最高/无规则'
  }
  return `${fmtEta(site.eta_days)}(${CONFIDENCE_LABEL[site.confidence] || '?'})`
}

/**
 * 进度条右侧那句「卡点」:百分比只说明差多少,说清「最紧的是哪一项、当前/目标」才知道该往哪使劲。
 * 口径与后端 __progress 一致(复用已有的 tightest 计算属性)。
 */
const tightestText = computed(() => {
  const r = tightest.value;
  if (!r) return ''
  const label = r.label || '-';
  const target = fmtNum(r.target) + (r.unit || '');
  const current = (r.current === null || r.current === undefined) ? null : fmtNum(r.current);
  return current === null ? label : label + ' ' + current + '/' + target
});

onMounted(() => loadSites(true));

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VListItemTitle = _resolveComponent("VListItemTitle");
  const _component_VListItemSubtitle = _resolveComponent("VListItemSubtitle");
  const _component_VListItem = _resolveComponent("VListItem");
  const _component_VList = _resolveComponent("VList");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VTable = _resolveComponent("VTable");
  const _component_VBtnToggle = _resolveComponent("VBtnToggle");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCheckboxBtn = _resolveComponent("VCheckboxBtn");
  const _component_VCardActions = _resolveComponent("VCardActions");
  const _component_VDialog = _resolveComponent("VDialog");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VSnackbar = _resolveComponent("VSnackbar");
  const _component_VContainer = _resolveComponent("VContainer");

  return (_openBlock(), _createBlock(_component_VContainer, {
    fluid: "",
    class: "pa-4"
  }, {
    default: _withCtx(() => [
      _createVNode(_component_VRow, {
        dense: "",
        align: "center",
        class: "mb-2"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCol, { cols: "auto" }, {
            default: _withCtx(() => [
              _createVNode(_component_VIcon, {
                icon: "mdi-account-star-outline",
                color: "primary",
                size: "28"
              })
            ]),
            _: 1
          }),
          _createVNode(_component_VCol, null, {
            default: _withCtx(() => [
              _cache[15] || (_cache[15] = _createElementVNode("div", { class: "text-h6" }, "站点等级看板", -1)),
              _createElementVNode("div", _hoisted_1, " 上次刷新:" + _toDisplayString(meta.value.last_refresh || '从未') + " · 内置等级规则快照:" + _toDisplayString(meta.value.snapshot_date || '-') + " · 看板站点 " + _toDisplayString(tracked.value.length) + " 个 ", 1)
            ]),
            _: 1
          }),
          _createVNode(_component_VCol, { cols: "auto" }, {
            default: _withCtx(() => [
              _createVNode(_component_VBtn, {
                size: "small",
                variant: "text",
                "prepend-icon": "mdi-file-document-outline",
                loading: reportLoading.value,
                onClick: loadReport
              }, {
                default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                  _createTextVNode(" 复制汇总 ", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode(_component_VBtn, {
                size: "small",
                variant: "tonal",
                "prepend-icon": "mdi-refresh",
                loading: busy.value,
                onClick: refreshAll
              }, {
                default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                  _createTextVNode(" 刷新全部 ", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      (error.value)
        ? (_openBlock(), _createBlock(_component_VAlert, {
            key: 0,
            type: "error",
            variant: "tonal",
            density: "compact",
            class: "mb-3",
            closable: "",
            "onClick:close": _cache[0] || (_cache[0] = $event => (error.value = ''))
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(error.value), 1)
            ]),
            _: 1
          }))
        : _createCommentVNode("", true),
      _createVNode(_component_VRow, null, {
        default: _withCtx(() => [
          _createVNode(_component_VCol, {
            cols: "12",
            md: "3"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_VCard, { variant: "outlined" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center ga-1 py-2" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-server-network",
                        size: "18",
                        color: "primary"
                      }),
                      _createTextVNode("站点(" + _toDisplayString(tracked.value.length) + ") ", 1),
                      _createVNode(_component_VSpacer),
                      (tracked.value.length > 1)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_2, [
                            _createVNode(_component_VIcon, {
                              icon: "mdi-drag-vertical",
                              size: "14"
                            }),
                            _cache[18] || (_cache[18] = _createTextVNode("拖动排序 ", -1))
                          ]))
                        : _createCommentVNode("", true)
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VDivider),
                  (tracked.value.length)
                    ? (_openBlock(), _createBlock(_component_VList, {
                        key: 0,
                        density: "compact",
                        nav: "",
                        class: "py-0"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tracked.value, (s, i) => {
                            return (_openBlock(), _createBlock(_component_VListItem, {
                              key: s.id,
                              active: s.id === selectedId.value,
                              color: "primary",
                              draggable: "true",
                              class: _normalizeClass([
                'slb-item',
                dragIndex.value === i ? 'slb-dragging' : '',
                overIndex.value === i && dragIndex.value >= 0 && dragIndex.value !== i
                  ? (dragIndex.value > i ? 'slb-drop-above' : 'slb-drop-below') : '',
              ]),
                              onClick: $event => (selectSite(s.id)),
                              onDragstart: $event => (onDragStart(i, $event)),
                              onDragover: _withModifiers($event => (onDragOver(i)), ["prevent"]),
                              onDrop: _withModifiers($event => (onDrop(i)), ["prevent","stop"]),
                              onDragend: onDragEnd
                            }, {
                              append: _withCtx(() => [
                                _createVNode(_component_VBtn, {
                                  icon: "mdi-delete-outline",
                                  size: "x-small",
                                  variant: "text",
                                  color: "error",
                                  title: "移出看板",
                                  class: "slb-del",
                                  onClick: _withModifiers($event => (confirmTarget.value = s), ["stop"])
                                }, null, 8, ["onClick"])
                              ]),
                              default: _withCtx(() => [
                                _createVNode(_component_VListItemTitle, { class: "text-body-2 d-flex align-center ga-1" }, {
                                  default: _withCtx(() => [
                                    _createElementVNode("span", _hoisted_3, _toDisplayString(s.name), 1),
                                    _createVNode(_component_VChip, {
                                      size: "x-small",
                                      variant: "tonal",
                                      class: "flex-shrink-0"
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(s.level || '?'), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode(_component_VListItemSubtitle, { class: "text-caption slb-sub" }, {
                                  default: _withCtx(() => [
                                    _createElementVNode("span", _hoisted_4, _toDisplayString(s.domain || '-'), 1),
                                    (s.username)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_5, [
                                          _createVNode(_component_VIcon, {
                                            icon: "mdi-account-outline",
                                            size: "11"
                                          }),
                                          _createTextVNode(_toDisplayString(s.username), 1)
                                        ]))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1032, ["active", "class", "onClick", "onDragstart", "onDragover", "onDrop"]))
                          }), 128))
                        ]),
                        _: 1
                      }))
                    : (_openBlock(), _createElementBlock("div", _hoisted_6, " 还没有站点。点下方「新增站点」从你的 mp 站点里挑。 ")),
                  _createVNode(_component_VDivider),
                  _createElementVNode("div", _hoisted_7, [
                    _createVNode(_component_VBtn, {
                      block: "",
                      variant: "tonal",
                      size: "small",
                      "prepend-icon": "mdi-plus",
                      onClick: openAdd
                    }, {
                      default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                        _createTextVNode("新增站点", -1)
                      ]))]),
                      _: 1
                    })
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_VCol, {
            cols: "12",
            md: "9"
          }, {
            default: _withCtx(() => [
              (!selectedId.value)
                ? (_openBlock(), _createBlock(_component_VCard, {
                    key: 0,
                    variant: "outlined"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VCardText, { class: "text-medium-emphasis" }, {
                        default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                          _createTextVNode("从左侧选择一个站点,这里会显示它的等级统计。", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createVNode(_component_VCard, {
                      variant: "outlined",
                      class: "mb-3"
                    }, {
                      default: _withCtx(() => [
                        _createElementVNode("div", _hoisted_8, [
                          _createElementVNode("span", _hoisted_9, _toDisplayString(detail.value?.site_name || current.value?.name), 1),
                          _createVNode(_component_VChip, {
                            color: "primary",
                            variant: "tonal",
                            size: "small"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(detail.value?.level || '?'), 1)
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_VIcon, {
                            icon: "mdi-arrow-right",
                            size: "16",
                            class: "text-medium-emphasis"
                          }),
                          _createVNode(_component_VChip, {
                            variant: "outlined",
                            size: "small"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(detail.value?.next_level || '已最高'), 1)
                            ]),
                            _: 1
                          }),
                          (detail.value)
                            ? (_openBlock(), _createBlock(_component_VChip, {
                                key: 0,
                                color: detail.value.manual_blocked ? 'warning' : 'success',
                                variant: "tonal",
                                size: "small"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(etaText(detail.value)), 1)
                                ]),
                                _: 1
                              }, 8, ["color"]))
                            : _createCommentVNode("", true),
                          _createVNode(_component_VSpacer),
                          _createVNode(_component_VBtn, {
                            icon: "mdi-refresh",
                            size: "x-small",
                            variant: "text",
                            title: "刷新本站",
                            loading: busy.value,
                            onClick: refreshOne
                          }, null, 8, ["loading"]),
                          (detail.value?.site_url)
                            ? (_openBlock(), _createBlock(_component_VBtn, {
                                key: 1,
                                icon: "mdi-open-in-new",
                                size: "x-small",
                                variant: "text",
                                title: "打开站点",
                                href: detail.value.site_url,
                                target: "_blank"
                              }, null, 8, ["href"]))
                            : _createCommentVNode("", true),
                          (detail.value)
                            ? (_openBlock(), _createBlock(_component_VTooltip, {
                                key: 2,
                                location: "bottom end",
                                "max-width": "420",
                                "open-delay": "150"
                              }, {
                                activator: _withCtx(({ props: tip }) => [
                                  _createVNode(_component_VBtn, _mergeProps(tip, {
                                    icon: "mdi-information-outline",
                                    size: "x-small",
                                    variant: "text",
                                    title: "数据来源与新鲜度"
                                  }), null, 16)
                                ]),
                                default: _withCtx(() => [
                                  _createElementVNode("div", _hoisted_10, [
                                    _createElementVNode("div", null, [
                                      _cache[21] || (_cache[21] = _createElementVNode("b", null, "数据来源", -1)),
                                      _createTextVNode(_toDisplayString(_unref(SOURCE_LABEL)[detail.value.source] || detail.value.source || '-'), 1)
                                    ]),
                                    (detail.value.source === 'ptd_snapshot')
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
                                          _cache[22] || (_cache[22] = _createElementVNode("b", null, "快照日期", -1)),
                                          _createTextVNode(_toDisplayString(detail.value.snapshot_date || '-'), 1)
                                        ]))
                                      : _createCommentVNode("", true),
                                    _createElementVNode("div", null, [
                                      _cache[23] || (_cache[23] = _createElementVNode("b", null, "数据更新", -1)),
                                      _createTextVNode(_toDisplayString(detail.value.l1_updated || '-'), 1)
                                    ]),
                                    (liveExtraText.value)
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_12, [
                                          _cache[24] || (_cache[24] = _createElementVNode("b", null, "站点侧", -1)),
                                          _createTextVNode(_toDisplayString(liveExtraText.value), 1)
                                        ]))
                                      : _createCommentVNode("", true)
                                  ])
                                ]),
                                _: 1
                              }))
                            : _createCommentVNode("", true)
                        ]),
                        (detail.value && detail.value.progress_pct !== null && detail.value.progress_pct !== undefined)
                          ? (_openBlock(), _createBlock(_component_VCardText, {
                              key: 0,
                              class: "pt-0 pb-3"
                            }, {
                              default: _withCtx(() => [
                                _createElementVNode("div", _hoisted_13, [
                                  _createVNode(_component_VProgressLinear, {
                                    "model-value": detail.value.progress_pct,
                                    height: "6",
                                    rounded: "",
                                    color: "primary",
                                    class: "flex-grow-1",
                                    style: {"min-width":"120px"}
                                  }, null, 8, ["model-value"]),
                                  _createElementVNode("span", _hoisted_14, "晋级 " + _toDisplayString(detail.value.progress_pct) + "%", 1),
                                  (tightestText.value)
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_15, _toDisplayString(tightestText.value), 1))
                                    : _createCommentVNode("", true)
                                ])
                              ]),
                              _: 1
                            }))
                          : _createCommentVNode("", true),
                        _createVNode(_component_VTabs, {
                          modelValue: activeTab.value,
                          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((activeTab).value = $event)),
                          color: "primary",
                          density: "comfortable",
                          class: "slb-tabs"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VTab, { value: "overview" }, {
                              default: _withCtx(() => [
                                _cache[25] || (_cache[25] = _createTextVNode(" 等级概览 ", -1)),
                                (riskLevel.value)
                                  ? (_openBlock(), _createBlock(_component_VIcon, {
                                      key: 0,
                                      icon: "mdi-circle",
                                      size: "10",
                                      color: riskColor(riskLevel.value),
                                      class: "ml-1"
                                    }, null, 8, ["color"]))
                                  : _createCommentVNode("", true)
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_VTab, { value: "ladder" }, {
                              default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                                _createTextVNode("等级阶梯", -1)
                              ]))]),
                              _: 1
                            }),
                            _createVNode(_component_VTab, { value: "traffic" }, {
                              default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                                _createTextVNode("流量趋势", -1)
                              ]))]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    (detailLoading.value)
                      ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                          key: 0,
                          indeterminate: "",
                          color: "primary",
                          class: "mb-3"
                        }))
                      : _createCommentVNode("", true),
                    (activeTab.value === 'overview')
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                          (tightest.value)
                            ? (_openBlock(), _createBlock(_component_VCard, {
                                key: 0,
                                variant: "outlined",
                                class: "mb-3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_VIcon, {
                                        icon: "mdi-target",
                                        start: "",
                                        size: "18",
                                        color: "primary"
                                      }),
                                      _cache[28] || (_cache[28] = _createTextVNode("卡住晋级的是 ", -1))
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VDivider),
                                  _createVNode(_component_VCardText, { class: "text-body-2" }, {
                                    default: _withCtx(() => [
                                      _createElementVNode("div", _hoisted_16, _toDisplayString(tightest.value.label), 1),
                                      _createElementVNode("div", _hoisted_17, [
                                        _createTextVNode(" 当前 " + _toDisplayString(tightest.value.current === null ? '取不到' : _unref(fmtNum)(tightest.value.current) + tightest.value.unit) + " → 目标 " + _toDisplayString(_unref(fmtNum)(tightest.value.target)) + _toDisplayString(tightest.value.unit) + " ", 1),
                                        (typeof tightest.value.current === 'number' && tightest.value.target)
                                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                              _createTextVNode(" · 还差 " + _toDisplayString(_unref(fmtNum)(Math.max(0, tightest.value.target - tightest.value.current))) + _toDisplayString(tightest.value.unit), 1)
                                            ], 64))
                                          : _createCommentVNode("", true),
                                        _createTextVNode(" · " + _toDisplayString(tightest.value.eta_days !== null && tightest.value.eta_days !== undefined
                  ? `${tightest.value.rate_label || ''} → ${_unref(fmtEta)(tightest.value.eta_days)}`
                  : (tightest.value.eta_kind === 'manual' ? '需人为推动,光等不会达成' : '趋势不足(攒够样本后可估)')), 1)
                                      ])
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }))
                            : (detail.value?.reqs?.length)
                              ? (_openBlock(), _createBlock(_component_VAlert, {
                                  key: 1,
                                  type: "success",
                                  variant: "tonal",
                                  density: "compact",
                                  class: "mb-3"
                                }, {
                                  default: _withCtx(() => [
                                    _cache[29] || (_cache[29] = _createTextVNode(" 当前等级的自动条件已全部达成 ✅", -1)),
                                    (detail.value.manual_blocked)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_18, ";仍有人为条件需要推进"))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode("", true),
                          (detail.value?.reqs?.length)
                            ? (_openBlock(), _createBlock(_component_VCard, {
                                key: 2,
                                variant: "outlined",
                                class: "mb-3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_VIcon, {
                                        icon: "mdi-checkbox-marked-circle-outline",
                                        start: "",
                                        size: "18",
                                        color: "primary"
                                      }),
                                      _createTextVNode(" 下一级条件(已达成 " + _toDisplayString(detail.value.reqs.filter(r => r.met).length) + " / " + _toDisplayString(detail.value.reqs.length) + ") ", 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VDivider),
                                  _createVNode(_component_VTable, { density: "compact" }, {
                                    default: _withCtx(() => [
                                      _cache[30] || (_cache[30] = _createElementVNode("thead", null, [
                                        _createElementVNode("tr", null, [
                                          _createElementVNode("th", { style: {"width":"46px"} }, "状态"),
                                          _createElementVNode("th", null, "条件"),
                                          _createElementVNode("th", { style: {"width":"120px"} }, "目标"),
                                          _createElementVNode("th", { style: {"width":"120px"} }, "当前"),
                                          _createElementVNode("th", { style: {"width":"190px"} }, "增速 / 预计")
                                        ])
                                      ], -1)),
                                      _createElementVNode("tbody", null, [
                                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.reqs, (r) => {
                                          return (_openBlock(), _createElementBlock("tr", {
                                            key: r.key,
                                            class: _normalizeClass({ 'text-medium-emphasis': r.met })
                                          }, [
                                            _createElementVNode("td", null, [
                                              _createVNode(_component_VIcon, {
                                                icon: r.met ? 'mdi-check-circle' : 'mdi-close-circle',
                                                color: r.met ? 'success' : 'error',
                                                size: "18"
                                              }, null, 8, ["icon", "color"])
                                            ]),
                                            _createElementVNode("td", null, _toDisplayString(r.label), 1),
                                            _createElementVNode("td", null, _toDisplayString(_unref(fmtNum)(r.target)) + _toDisplayString(r.unit), 1),
                                            _createElementVNode("td", null, _toDisplayString(r.current === null ? '取不到' : _unref(fmtNum)(r.current) + r.unit), 1),
                                            _createElementVNode("td", null, [
                                              (r.met)
                                                ? (_openBlock(), _createElementBlock("span", _hoisted_19, "已达成"))
                                                : (r.eta_days !== null && r.eta_days !== undefined)
                                                  ? (_openBlock(), _createElementBlock("span", _hoisted_20, _toDisplayString(r.rate_label || '') + " → " + _toDisplayString(_unref(fmtEta)(r.eta_days)), 1))
                                                  : (_openBlock(), _createElementBlock("span", _hoisted_21, _toDisplayString(r.rate_label || (r.eta_kind === 'manual' ? '需人为推动' : '趋势不足')), 1))
                                            ])
                                          ], 2))
                                        }), 128))
                                      ])
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }))
                            : (detail.value && !detail.value.reqs?.length)
                              ? (_openBlock(), _createBlock(_component_VAlert, {
                                  key: 3,
                                  type: "info",
                                  variant: "tonal",
                                  density: "compact",
                                  class: "mb-3"
                                }, {
                                  default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
                                    _createTextVNode(" 该站没有可解析的晋级条件(站点未公开门槛,可在插件配置里用「手动规则」补),以下仍显示当前等级与保号信息。 ", -1)
                                  ]))]),
                                  _: 1
                                }))
                              : _createCommentVNode("", true),
                          _createVNode(_component_VRow, { class: "mb-1" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_VCol, {
                                cols: "12",
                                md: "6"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VCard, {
                                    variant: "outlined",
                                    class: "h-100"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_VIcon, {
                                            icon: "mdi-shield-check-outline",
                                            start: "",
                                            size: "18",
                                            color: "success"
                                          }),
                                          _cache[32] || (_cache[32] = _createTextVNode("保号状态与路线 ", -1))
                                        ]),
                                        _: 1
                                      }),
                                      _createVNode(_component_VDivider),
                                      _createVNode(_component_VCardText, { class: "text-body-2" }, {
                                        default: _withCtx(() => [
                                          (detail.value)
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_22, [
                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(roadmapRows.value, (row) => {
                                                  return (_openBlock(), _createElementBlock("div", {
                                                    key: row.key,
                                                    class: "mb-2"
                                                  }, [
                                                    _createElementVNode("div", _hoisted_23, [
                                                      _createVNode(_component_VIcon, {
                                                        icon: row.icon,
                                                        size: "16",
                                                        color: row.tone,
                                                        class: "mr-1"
                                                      }, null, 8, ["icon", "color"]),
                                                      _createElementVNode("b", null, _toDisplayString(row.label), 1),
                                                      _createElementVNode("span", _hoisted_24, _toDisplayString(roadmapAway(row.data)), 1),
                                                      _createVNode(_component_VSpacer),
                                                      _createElementVNode("span", _hoisted_25, _toDisplayString(roadmapEta(row.data)), 1)
                                                    ]),
                                                    (roadmapBlocker(row.data))
                                                      ? (_openBlock(), _createElementBlock("div", _hoisted_26, " 卡点:" + _toDisplayString(roadmapBlocker(row.data)), 1))
                                                      : _createCommentVNode("", true)
                                                  ]))
                                                }), 128)),
                                                (!roadmapRows.value.length)
                                                  ? (_openBlock(), _createElementBlock("div", _hoisted_27, " 该站规则里没有保号档信息(仍可看下面的条款原文) "))
                                                  : _createCommentVNode("", true),
                                                _createVNode(_component_VDivider, { class: "my-2" }),
                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.keep_rules || [], (t, i) => {
                                                  return (_openBlock(), _createElementBlock("div", {
                                                    key: 'k' + i
                                                  }, "✅ " + _toDisplayString(t), 1))
                                                }), 128)),
                                                (!(detail.value.keep_rules || []).length)
                                                  ? (_openBlock(), _createElementBlock("div", _hoisted_28, "站点未提供保号条款"))
                                                  : _createCommentVNode("", true)
                                              ]))
                                            : _createCommentVNode("", true)
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VCol, {
                                cols: "12",
                                md: "6"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VCard, {
                                    variant: "outlined",
                                    class: "h-100"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_VIcon, {
                                            icon: "mdi-alert-octagon-outline",
                                            start: "",
                                            size: "18",
                                            color: "error"
                                          }),
                                          _cache[33] || (_cache[33] = _createTextVNode("封号 / 降级条款 ", -1))
                                        ]),
                                        _: 1
                                      }),
                                      _createVNode(_component_VDivider),
                                      _createVNode(_component_VCardText, { class: "text-body-2" }, {
                                        default: _withCtx(() => [
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value?.ban_rules || [], (t, i) => {
                                            return (_openBlock(), _createElementBlock("div", {
                                              key: 'b' + i,
                                              class: "mb-1"
                                            }, "⛔ " + _toDisplayString(t), 1))
                                          }), 128)),
                                          (!detail.value?.ban_rules?.length)
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_29, " 站点未提供(或不在公开页面)——请以站点公告为准 "))
                                            : _createCommentVNode("", true),
                                          (detail.value?.risks?.length)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                _createVNode(_component_VDivider, { class: "my-2" }),
                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.risks, (r, i) => {
                                                  return (_openBlock(), _createElementBlock("div", {
                                                    key: 'r' + i,
                                                    class: _normalizeClass(r.level === 'danger' ? 'text-error' : 'text-warning')
                                                  }, _toDisplayString(r.level === 'danger' ? '🔴' : '⚠️') + " " + _toDisplayString(r.text), 3))
                                                }), 128))
                                              ], 64))
                                            : _createCommentVNode("", true)
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ], 64))
                      : (activeTab.value === 'ladder')
                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                            (detail.value?.ladder?.length)
                              ? (_openBlock(), _createBlock(_component_VCard, {
                                  key: 0,
                                  variant: "outlined",
                                  class: "mb-3"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                      default: _withCtx(() => [
                                        _createVNode(_component_VIcon, {
                                          icon: "mdi-stairs",
                                          start: "",
                                          size: "18",
                                          color: "primary"
                                        }),
                                        _cache[34] || (_cache[34] = _createTextVNode("全部等级阶梯 ", -1)),
                                        _createVNode(_component_VSpacer),
                                        _cache[35] || (_cache[35] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "🏅 永久保号 · 🔒 可封存保号", -1))
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode(_component_VDivider),
                                    _createVNode(_component_VTable, { density: "compact" }, {
                                      default: _withCtx(() => [
                                        _cache[38] || (_cache[38] = _createElementVNode("thead", null, [
                                          _createElementVNode("tr", null, [
                                            _createElementVNode("th", { style: {"width":"150px"} }, "等级"),
                                            _createElementVNode("th", null, "晋级条件"),
                                            _createElementVNode("th", { style: {"width":"150px"} }, "特权 / 备注")
                                          ])
                                        ], -1)),
                                        _createElementVNode("tbody", null, [
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.ladder, (lv) => {
                                            return (_openBlock(), _createElementBlock("tr", {
                                              key: lv.order,
                                              class: _normalizeClass({ 'bg-primary': lv.order === detail.value.level_order, 'font-weight-bold': lv.order === detail.value.next_order })
                                            }, [
                                              _createElementVNode("td", null, [
                                                _createElementVNode("span", _hoisted_30, _toDisplayString(lv.order), 1),
                                                _createTextVNode(_toDisplayString(lv.name) + " ", 1),
                                                (lv.is_permanent)
                                                  ? (_openBlock(), _createElementBlock("span", _hoisted_31, "🏅"))
                                                  : _createCommentVNode("", true),
                                                (lv.is_parkable)
                                                  ? (_openBlock(), _createElementBlock("span", _hoisted_32, "🔒"))
                                                  : _createCommentVNode("", true),
                                                (lv.order === detail.value.level_order)
                                                  ? (_openBlock(), _createBlock(_component_VChip, {
                                                      key: 2,
                                                      size: "x-small",
                                                      color: "primary",
                                                      class: "ml-1"
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
                                                        _createTextVNode("当前", -1)
                                                      ]))]),
                                                      _: 1
                                                    }))
                                                  : (lv.order === detail.value.next_order)
                                                    ? (_openBlock(), _createBlock(_component_VChip, {
                                                        key: 3,
                                                        size: "x-small",
                                                        variant: "outlined",
                                                        class: "ml-1"
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                                                          _createTextVNode("下一级", -1)
                                                        ]))]),
                                                        _: 1
                                                      }))
                                                    : _createCommentVNode("", true)
                                              ]),
                                              _createElementVNode("td", _hoisted_33, [
                                                (!lv.requirements.length)
                                                  ? (_openBlock(), _createElementBlock("span", _hoisted_34, "默认/无自动条件"))
                                                  : (_openBlock(), _createElementBlock("span", _hoisted_35, _toDisplayString(lv.requirements.map(r => r.label).join(' · ')), 1)),
                                                (lv.demote_ratio)
                                                  ? (_openBlock(), _createElementBlock("span", _hoisted_36, " (分享率 < " + _toDisplayString(lv.demote_ratio) + " 降级)", 1))
                                                  : _createCommentVNode("", true)
                                              ]),
                                              _createElementVNode("td", _hoisted_37, _toDisplayString(lv.privilege || '-'), 1)
                                            ], 2))
                                          }), 128))
                                        ])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }))
                              : (_openBlock(), _createBlock(_component_VAlert, {
                                  key: 1,
                                  type: "info",
                                  variant: "tonal",
                                  density: "compact"
                                }, {
                                  default: _withCtx(() => [...(_cache[39] || (_cache[39] = [
                                    _createTextVNode(" 该站没有可解析的等级阶梯 —— 站点未公开等级规则,可在插件配置里用「手动规则」补。 ", -1)
                                  ]))]),
                                  _: 1
                                }))
                          ], 64))
                        : (_openBlock(), _createElementBlock(_Fragment, { key: 3 }, [
                            (detail.value?.history?.length)
                              ? (_openBlock(), _createBlock(_component_VCard, {
                                  key: 0,
                                  variant: "outlined",
                                  class: "mb-3"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                      default: _withCtx(() => [
                                        _createVNode(_component_VIcon, {
                                          icon: "mdi-chart-line",
                                          start: "",
                                          size: "18",
                                          color: "primary"
                                        }),
                                        _cache[40] || (_cache[40] = _createTextVNode(" 流量趋势 ", -1)),
                                        _createVNode(_component_VSpacer),
                                        _cache[41] || (_cache[41] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "来自 mp 的 siteuserdata 日快照", -1))
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode(_component_VDivider),
                                    _createVNode(_component_VCardText, null, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", _hoisted_38, [
                                          _createVNode(_component_VBtnToggle, {
                                            modelValue: trafficMetric.value,
                                            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((trafficMetric).value = $event)),
                                            density: "compact",
                                            variant: "outlined",
                                            divided: "",
                                            mandatory: ""
                                          }, {
                                            default: _withCtx(() => [
                                              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(TRAFFIC_METRICS, (m) => {
                                                return _createVNode(_component_VBtn, {
                                                  key: m.key,
                                                  value: m.key,
                                                  size: "small"
                                                }, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(_toDisplayString(m.label), 1)
                                                  ]),
                                                  _: 2
                                                }, 1032, ["value"])
                                              }), 64))
                                            ]),
                                            _: 1
                                          }, 8, ["modelValue"]),
                                          _createVNode(_component_VSpacer),
                                          _createVNode(_component_VBtnToggle, {
                                            modelValue: trafficRange.value,
                                            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((trafficRange).value = $event)),
                                            density: "compact",
                                            variant: "outlined",
                                            divided: "",
                                            mandatory: ""
                                          }, {
                                            default: _withCtx(() => [
                                              _createVNode(_component_VBtn, {
                                                value: 7,
                                                size: "small"
                                              }, {
                                                default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                                                  _createTextVNode("7 天", -1)
                                                ]))]),
                                                _: 1
                                              }),
                                              _createVNode(_component_VBtn, {
                                                value: 14,
                                                size: "small"
                                              }, {
                                                default: _withCtx(() => [...(_cache[43] || (_cache[43] = [
                                                  _createTextVNode("14 天", -1)
                                                ]))]),
                                                _: 1
                                              }),
                                              _createVNode(_component_VBtn, {
                                                value: 30,
                                                size: "small"
                                              }, {
                                                default: _withCtx(() => [...(_cache[44] || (_cache[44] = [
                                                  _createTextVNode("30 天", -1)
                                                ]))]),
                                                _: 1
                                              })
                                            ]),
                                            _: 1
                                          }, 8, ["modelValue"])
                                        ]),
                                        (trafficChart.value)
                                          ? (_openBlock(), _createElementBlock("div", {
                                              key: 0,
                                              class: "slb-chart",
                                              onMousemove: onChartMove,
                                              onMouseleave: _cache[4] || (_cache[4] = $event => (trafficHover.value = -1))
                                            }, [
                                              (_openBlock(), _createElementBlock("svg", {
                                                viewBox: `0 0 ${trafficChart.value.w} ${trafficChart.value.h}`,
                                                preserveAspectRatio: "none"
                                              }, [
                                                _createElementVNode("polyline", {
                                                  points: trafficChart.value.points,
                                                  fill: "none",
                                                  stroke: "rgb(var(--v-theme-primary))",
                                                  "stroke-width": "0.8",
                                                  "vector-effect": "non-scaling-stroke"
                                                }, null, 8, _hoisted_40)
                                              ], 8, _hoisted_39))
                                            ], 32))
                                          : _createCommentVNode("", true),
                                        _createElementVNode("div", _hoisted_41, [
                                          (trafficHover.value >= 0 && trafficRows.value[trafficHover.value])
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createTextVNode(_toDisplayString(trafficRows.value[trafficHover.value].day) + " · " + _toDisplayString(trafficMetricDef.value.label) + " ", 1),
                                                _createElementVNode("b", null, _toDisplayString(trafficMetricDef.value.fmt(Number(trafficRows.value[trafficHover.value][trafficMetric.value]) || 0)), 1)
                                              ], 64))
                                            : (trafficChart.value)
                                              ? (_openBlock(), _createElementBlock("span", _hoisted_42, " 纵轴 " + _toDisplayString(trafficMetricDef.value.fmt(trafficChart.value.min)) + " ~ " + _toDisplayString(trafficMetricDef.value.fmt(trafficChart.value.max)) + " · 鼠标移到曲线上可读某天数值 ", 1))
                                              : _createCommentVNode("", true)
                                        ]),
                                        _createElementVNode("div", _hoisted_43, _toDisplayString(trafficTrend.value), 1),
                                        _createVNode(_component_VTable, { density: "compact" }, {
                                          default: _withCtx(() => [
                                            _cache[45] || (_cache[45] = _createElementVNode("thead", null, [
                                              _createElementVNode("tr", null, [
                                                _createElementVNode("th", null, "日期"),
                                                _createElementVNode("th", null, "上传"),
                                                _createElementVNode("th", null, "下载"),
                                                _createElementVNode("th", null, "分享率"),
                                                _createElementVNode("th", null, "魔力/积分"),
                                                _createElementVNode("th", null, "做种"),
                                                _createElementVNode("th", null, "做种体积")
                                              ])
                                            ], -1)),
                                            _createElementVNode("tbody", null, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(trafficRows.value, (h) => {
                                                return (_openBlock(), _createElementBlock("tr", {
                                                  key: h.day
                                                }, [
                                                  _createElementVNode("td", null, _toDisplayString(h.day), 1),
                                                  _createElementVNode("td", null, _toDisplayString(_unref(fmtGb)(h.upload_gb)), 1),
                                                  _createElementVNode("td", null, _toDisplayString(_unref(fmtGb)(h.download_gb)), 1),
                                                  _createElementVNode("td", null, _toDisplayString(_unref(fmtNum)(h.ratio, 3)), 1),
                                                  _createElementVNode("td", null, _toDisplayString(_unref(fmtNum)(h.bonus, 1)), 1),
                                                  _createElementVNode("td", null, _toDisplayString(h.seeding ?? '-'), 1),
                                                  _createElementVNode("td", null, _toDisplayString(_unref(fmtGb)(h.seeding_size_gb)), 1)
                                                ]))
                                              }), 128))
                                            ])
                                          ]),
                                          _: 1
                                        })
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }))
                              : (_openBlock(), _createBlock(_component_VAlert, {
                                  key: 1,
                                  type: "info",
                                  variant: "tonal",
                                  density: "compact"
                                }, {
                                  default: _withCtx(() => [...(_cache[46] || (_cache[46] = [
                                    _createTextVNode(" 还没有历史快照 —— mp 的 siteuserdata 每天更新一行,攒几天后这里会出现曲线。 ", -1)
                                  ]))]),
                                  _: 1
                                }))
                          ], 64))
                  ], 64))
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VDialog, {
        modelValue: addOpen.value,
        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((addOpen).value = $event)),
        "max-width": "640",
        scrollable: ""
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCard, null, {
            default: _withCtx(() => [
              _createVNode(_component_VCardTitle, { class: "text-subtitle-1 d-flex align-center" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-plus-circle-outline",
                    start: "",
                    color: "primary"
                  }),
                  _cache[47] || (_cache[47] = _createTextVNode("新增站点到看板 ", -1))
                ]),
                _: 1
              }),
              _createVNode(_component_VDivider),
              _createVNode(_component_VCardText, null, {
                default: _withCtx(() => [
                  _createVNode(_component_VTextField, {
                    modelValue: addSearch.value,
                    "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((addSearch).value = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    "prepend-inner-icon": "mdi-magnify",
                    label: "筛选站点(名称或域名)",
                    class: "mb-3"
                  }, null, 8, ["modelValue"]),
                  (!filteredCandidates.value.length)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_44, " 没有可添加的站点(要么都已在看板里,要么 mp 里还没绑定站点) "))
                    : (_openBlock(), _createBlock(_component_VList, {
                        key: 1,
                        density: "compact",
                        class: "py-0"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(filteredCandidates.value, (c) => {
                            return (_openBlock(), _createBlock(_component_VListItem, {
                              key: c.id,
                              onClick: $event => (addSelected.value.includes(c.id)
              ? (addSelected.value = addSelected.value.filter(x => x !== c.id))
              : addSelected.value.push(c.id))
                            }, {
                              prepend: _withCtx(() => [
                                _createVNode(_component_VCheckboxBtn, {
                                  "model-value": addSelected.value.includes(c.id),
                                  color: "primary"
                                }, null, 8, ["model-value"])
                              ]),
                              default: _withCtx(() => [
                                _createVNode(_component_VListItemTitle, { class: "text-body-2" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(c.name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode(_component_VListItemSubtitle, { class: "text-caption" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(c.domain), 1)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1032, ["onClick"]))
                          }), 128))
                        ]),
                        _: 1
                      }))
                ]),
                _: 1
              }),
              _createVNode(_component_VDivider),
              _createVNode(_component_VCardActions, null, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_45, "已选 " + _toDisplayString(addSelected.value.length) + " 个", 1),
                  _createVNode(_component_VSpacer),
                  _createVNode(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[6] || (_cache[6] = $event => (addOpen.value = false))
                  }, {
                    default: _withCtx(() => [...(_cache[48] || (_cache[48] = [
                      _createTextVNode("取消", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_VBtn, {
                    color: "primary",
                    variant: "flat",
                    loading: busy.value,
                    onClick: submitAdd
                  }, {
                    default: _withCtx(() => [...(_cache[49] || (_cache[49] = [
                      _createTextVNode("加入看板", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"]),
      _createVNode(_component_VDialog, {
        "model-value": !!confirmTarget.value,
        "max-width": "420",
        "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => (confirmTarget.value = null))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCard, null, {
            default: _withCtx(() => [
              _createVNode(_component_VCardTitle, { class: "text-subtitle-1" }, {
                default: _withCtx(() => [...(_cache[50] || (_cache[50] = [
                  _createTextVNode("移出看板?", -1)
                ]))]),
                _: 1
              }),
              _createVNode(_component_VCardText, { class: "text-body-2" }, {
                default: _withCtx(() => [
                  _createTextVNode(" 将把「" + _toDisplayString(confirmTarget.value?.name) + "」从本站点看板里移除 —— ", 1),
                  _cache[51] || (_cache[51] = _createElementVNode("b", null, "不会", -1)),
                  _cache[52] || (_cache[52] = _createTextVNode("删除 mp 里的站点配置,之后还能再添加回来。 ", -1))
                ]),
                _: 1
              }),
              _createVNode(_component_VCardActions, null, {
                default: _withCtx(() => [
                  _createVNode(_component_VSpacer),
                  _createVNode(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[8] || (_cache[8] = $event => (confirmTarget.value = null))
                  }, {
                    default: _withCtx(() => [...(_cache[53] || (_cache[53] = [
                      _createTextVNode("取消", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_VBtn, {
                    color: "error",
                    variant: "flat",
                    loading: busy.value,
                    onClick: _cache[9] || (_cache[9] = $event => (doRemove(confirmTarget.value)))
                  }, {
                    default: _withCtx(() => [...(_cache[54] || (_cache[54] = [
                      _createTextVNode("移出", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["model-value"]),
      _createVNode(_component_VDialog, {
        modelValue: reportOpen.value,
        "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((reportOpen).value = $event)),
        "max-width": "760",
        scrollable: ""
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCard, null, {
            default: _withCtx(() => [
              _createVNode(_component_VCardTitle, { class: "text-subtitle-1 d-flex align-center" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-file-document-outline",
                    start: "",
                    color: "primary"
                  }),
                  _cache[55] || (_cache[55] = _createTextVNode("等级汇总(可复制) ", -1))
                ]),
                _: 1
              }),
              _createVNode(_component_VDivider),
              _createVNode(_component_VCardText, null, {
                default: _withCtx(() => [
                  _createVNode(_component_VTextarea, {
                    modelValue: reportText.value,
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((reportText).value = $event)),
                    readonly: "",
                    variant: "outlined",
                    rows: "18",
                    "hide-details": "",
                    class: "slb-report"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              _createVNode(_component_VCardActions, null, {
                default: _withCtx(() => [
                  _createVNode(_component_VSpacer),
                  _createVNode(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[12] || (_cache[12] = $event => (reportOpen.value = false))
                  }, {
                    default: _withCtx(() => [...(_cache[56] || (_cache[56] = [
                      _createTextVNode("关闭", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_VBtn, {
                    color: "primary",
                    variant: "flat",
                    "prepend-icon": "mdi-content-copy",
                    onClick: copyReport
                  }, {
                    default: _withCtx(() => [...(_cache[57] || (_cache[57] = [
                      _createTextVNode("复制", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"]),
      _createVNode(_component_VSnackbar, {
        modelValue: snack.value.show,
        "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((snack.value.show) = $event)),
        color: snack.value.color,
        timeout: 3000,
        location: "bottom"
      }, {
        default: _withCtx(() => [
          _createTextVNode(_toDisplayString(snack.value.text), 1)
        ]),
        _: 1
      }, 8, ["modelValue", "color"])
    ]),
    _: 1
  }))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-72f85682"]]);

export { Page as default };
